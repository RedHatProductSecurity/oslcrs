# Script to import, analyze, and record package license results
# WARNING...PROTOTYPE CODE
#
# Bryan Sutula, Red Hat, revised 4/20/23
# Released under GPL version 2

import json
import os                               # Environment variable support
import fcntl                            # Lower-level file control
import subprocess                       # To execute command line *stuff*
import re                               # Regular expression support
import time                             # May not be needed
import requests                         # In order to upload analysis jsons
import psycopg2                         # Postgress connector library
from pyrpm.spec import Spec, replace_macros # For parsing rpm spec files


# Global constants
tmpdir = "/tmp/oslcrs/"                 # Directory used to store working files
RETRIES = 3                             # Number of analysis retries before
                                        # we consider this a failed run
ocwd = os.getcwd()                      # Where are we now?
extractcode = f"{ocwd}/../scancode/extractcode"
scancode = f"{ocwd}/../scancode/scancode"


# Functions needed by this program
# FIXME: This code is also in oslcrs...remove and put in a separate file
class ldb():                            # License database class
    # Open report database, returning a connection cursor
    def open(db, host, port, user, passwd):
        try:
            ldb.conn = psycopg2.connect(f"dbname='{db}' port='{port}' " + \
                                        f"host='{host}' user='{user}' " + \
                                        f"password='{passwd}'")
            ldb.cdb = ldb.conn.cursor()
            return(ldb.cdb)
        except Exception as e:
            print("Failed to connect to report database")
            print(e)
            return(None)

    # Commit changes to the report database
    def commit():
        ldb.conn.commit()

    # Rollback any changes to the report database
    def rollback():
        ldb.conn.rollback()

    # Close the report database
    def close():
        ldb.cdb.close()
        ldb.conn.close()


# Analysis process level resources.
# Lock is used to avoid having two copies of the analysis program running at
# the same time.  Note that this implementation is not very robust, because
# every time oslcrs runs, it removes and recreates the tmp subdirectory where
# the lockfiles live.  This is a future FIXME.
class analysis():                       # Analysis class resources
    global lockfile
    lockfile = tmpdir + "analysis.lock"

    # Obtain the analysis lock
    def lock():
        global f
        f = open(lockfile, 'w+')
        try:
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return True                 # Got the lock
        except:
            return False                # Failed to obtain lock

    # Unlock
    def unlock():
        fcntl.flock(f, fcntl.LOCK_UN)


# Compute SWH UUID of a file
# This code is stolen from the SWH utility that computes UUIDs.  For the
# record, this code is under GPL-3.0
def swhid_of_file(path):
    from swh.model.from_disk import Content

    object = Content.from_file(path=path)
    return str(object.swhid())


# Look to see what analysis work needs to be done.
# Returns a set of database query rows.
# WARNING: Ensure analysis_decode() matches the query order.
def analysis_work():
    # Fetch sources where analysis != 1000 and retries < RETRIES
    # FIXME: currently using "9" rather than 1000
    sql = f"SELECT \
                id, name, checksum, state, retries, type, fetch_info \
            FROM sources \
            WHERE state != 9 and retries < {RETRIES} \
            ORDER BY id;"
    try:
        cdb.execute(sql)
        rows = cdb.fetchall()
    except Exception as e:
        print("Failed to execute sources analysis list query")
        print("Error: " + e.args[0])
        ldb.close()
        exit(1)
    return rows

# Decode a row provided by analysis_work() above.  FIXME: Probably a more clever
# way to do this.
def analysis_decode(row):
    w = dict()
    w["id"] = row[0]
    w["name"] = row[1]
    w["checksum"] = row[2]
    w["state"] = row[3]
    w["retries"] = row[4]
    w["type"] = row[5]
    w["fetch_info"] = row[6]
    return w


# Update a source analysis.  This code will update all the items passed to
# it in the "params" dictionary parameter.
def source_update(id, params):
    # Issue
    if int(db_version[0]) > 9:
        need_row = "ROW"
    else:
        need_row = ""

    sql = "UPDATE sources SET ("
    sql += ", ".join(params.keys())
    sql += f") = {need_row}(%("
    sql += ")s, %(".join(params.keys())
    sql += f")s) WHERE id = {id}"
    # print (f"Generated sql: {sql}")
    try:
        cdb.execute(sql, params)
        ldb.commit()
    except Exception as e:
        print(f"Failed to update sources table with analysis status:")
        print(params)
        print("Error: " + e.args[0])
        ldb.close()
        exit(1)


# Have we already analyzed a specific file?
# FIXME: This function may change when we take into account scancode versions.
# Returns file id if we already have license data for this file, or else None.
def isfile_done(uuid):
    sql = f"SELECT id FROM files WHERE swh = '{uuid}';"
    try:
        cdb.execute(sql)
        rows = cdb.fetchall()
    except Exception as e:
        print("Failed to execute files uuid query")
        print("Error: " + e.args[0])
        ldb.close()
        exit(1)
    if len(rows) > 0:
        return rows[0][0]
    else:
        return None


# Add a file that we've analyzed
def addfile(uuid):
    sql = f"INSERT INTO files (swh) VALUES ('{uuid}') \
            RETURNING id;"
    try:
        cdb.execute(sql)
        ldb.commit()
        row = cdb.fetchone()
        return(row[0])
    except Exception as e:
        print("Failed to add to the files table")
        print("Error: " + e.args[0])
        ldb.close()
        exit(1)


# Add to a table, where we don't need an id back.  This is a general routine
# that works on several tables.  Please note that this routine currently
# ignores the insert if it violates a table constraint.  This may be a FIXME.
def addrow(table, params):
    sql = f"INSERT INTO {table} ("
    sql += ", ".join(params.keys())
    sql += ") VALUES (%("
    sql += ")s, %(".join(params.keys())
    sql += ")s) ON CONFLICT DO NOTHING;"
    try:
        cdb.execute(sql, params)
        ldb.commit()
    except Exception as e:
        print(f"Failed to add a row to the {table} table")
        print("Error: " + e.args[0])
        ldb.close()
        exit(1)


# Vacuum the database, something that needs to be done occassionally
# FIXME: This code doesn't work, errors on the "SET AUTOCOMMIT" statement.
# It's not currently in use, but left in the code in case it's necessary in
# the future.
def vacuum():
    try:
        cdb.execute("SET AUTOCOMMIT TO ON;")
        ldb.commit()
        print("Attempting vacuum of report database...")
        cdb.execute("VACUUM ANALYZE;")
        print("...completed vacuum of report database")
        cdb.execute("SET AUTOCOMMIT TO OFF;")
        ldb.commit()
    except Exception as e:
        print("Failed to vacuum database")
        print("Error: " + e.args[0])
        ldb.close()
        exit(1)


# Clean the temporary source analysis subdirectory.  This gets done a lot, so
# keep all the code here.
def clean_temp():
    os.chdir(tmpdir)
    output = subprocess.run(["/bin/rm", "-rf", pkgdir], capture_output=True)
    if output.returncode != 0:
        print("error: failed to remove package analysis subdirectory")
        print(str(output.stderr, 'UTF-8'))
        exit(1)


# Run a command, log errors to the database, and return a True (error) or
# False (successful command) to the caller.
def cmd(cmd, err):
    # We use the global "source_id" to know where to log any error messages
    # and the value of "retries" to keep count of failures.  The value of
    # "pkgdir" is used to clean tempfiles.
    output = subprocess.run(cmd, capture_output=True)
    if output.returncode == 0:
        return False
    else:
        error_str = "error: "
        if err != "":
            error_str += err
        error_str += '\n'
        error_str += str(output.stderr, 'UTF-8')
        print(error_str)
        p = {"error": error_str, "retries": str(retries + 1)}
        sql = f"UPDATE sources \
                SET (error, retries) = (%(error)s, %(retries)s) \
                WHERE id = {source_id}"
        try:
            cdb.execute(sql, p)
            ldb.commit()
        except Exception as e:
            ldb.rollback()
            print(f"error: failed to log error to DB for source id {source_id}")
            print("Error: " + e.args[0])
            exit(1)
        return True


# Locates a spec file in the top level of the unpacked subdirectory, then
# parses that spec file.  Returns a structure with the required metadata.
def parse_spec_file(pkg_name):      # Get metadata from spec file
    cwd = os.getcwd()               # Remember where we were
    # print(f"Starting subdirectory was {cwd}")
    os.chdir(pkg_name)
    # Locate spec file
    topdir = [f for f in os.listdir('.') if os.path.isfile(f)]
    specfiles = [ f for f in topdir if re.search(r'\.spec$', f)]
    if len(specfiles) == 0:         # Missing specfile
        os.chdir(cwd)
        return None
    elif len(specfiles) == 1:
        # print(f"Found specfile {specfiles[0]}")
        pass
    else:
        # FIXME: Can there be more than one specfile?  According to David
        # Cantrell, this would not be expected.
        print("error: found more than one specfile:")
        print(specfiles)
        os.chdir(cwd)
        return None

    spec = Spec.from_file(specfiles[0])

    # Get the package info from this specfile
    summary = dict()
    try:
        summary['name'] = replace_macros(spec.name, spec)
    except:
        summary['name'] = None
    try:
        summary['upstream'] = replace_macros(spec.url, spec)
    except:
        summary['upstream'] = None
    try:
        summary['license'] = replace_macros(spec.license, spec)
    except:
        summary['license'] = None

    # Specfile NVR is missing the "build" portion of the release.  Figure this
    # out from the package name.
    # FIXME Warning: This seems brittle, and there's probably a better way to
    # get the full NVR.
    summary['src_name'] = re.sub(f'^(.*)\\.src\\.rpm$', '\\1', pkg_name)
    summary['vr'] = re.sub(f'^{summary["name"]}(.*)$',
                           '\\1', summary['src_name'])
    # print(f"Got vr of {summary['vr']}")

    # FIXME: WARNING:  This code is no longer being used!
    # We found that it's nearly impossible to accurately predict the actual
    # binary packages being produced from any given source package.  The spec
    # files include (essentially) shell variables that are set from the build
    # environment, and these variables can become part of the binary rpm name.
    # Due to this, we found that we get erroneous binary names, leading to
    # report errors.
    #
    # This code has been left in the source file for historical reasons, but
    # it is no longer being used.
    """
    # Iterate over all binary packages produced
    summary['packages'] = []
    for package in spec.packages:
        name = replace_macros(package.name, spec) + summary['vr']
        if hasattr(package, "license"):
            license = replace_macros(package.license, spec)
            # print(f"Debug: name is {name}, license is {license} from binary")
        else:
            license = summary['license']
            # print(f"Debug: name is {name}, license is {license} from source")
        summary['packages'].append({"nvr": name, "license": license})
    """
    # END FIXME: WARNING: for dead code

    os.chdir(cwd)
    return summary


# Unpacks a source archive
#
# This code used to be essentially a one-liner.  However, in practice, we find
# that unpack failures are pretty common, and that we need to separate a
# complete failure of unpack (which means we can't do any license analysis)
# from cases where just a few files failed to unpack, perhaps because the
# source was corrupt, and it's reasonable to proceed with license analysis.
# On top of this, we want to capture diagnostic output, so that we know
# a) what we analyzed and b) can feed back failures to upstream projects.
# Return code is 0 for success (proceed with license analysis) or 1 to quit.
def unpack_archive(pkgdir, pkgname):
    archive = pkgdir + '/' + pkgname
    # FIXME: A few comments on the lines below:
    # 1) It's nice to use --quiet in scripts, but at least at one point
    #    in the development, --quiet threw away all errors.  We need to
    #    see the error messages to know what didn't get unpacked.
    # 2) I'd love to use --all-formats, so that we unpack as much as we
    #    can.  But almost immediately, unpack failed on .patch files.  I
    #    don't know what's up with that, and didn't have time to investigate.
    # 3) I *really* need to use --replace-originals so that we don't try to
    #    scan both the archive files and also the extracted files.  Also,
    #    I'd rather not inject extra "-extract" characters into the file paths.
    #    However, extractcode has been buggy.  First, it would crash due to
    #    https://github.com/nexB/scancode-toolkit/issues/2723  This was fixed
    #    upstream, but the new code still doesn't work right.  As of this
    #    writing, I have my own patch to extractcode, but this needs to be
    #    worked out with upstream.
    # 4) I've seen one case where a test archive was built that contains
    #    bunches, actually 1.2M, empty files.  The specific case is in
    #    apache-commons-compress, an archive called zip64support.tar.bz2
    #    in a test subdirectory.  We may wish to have a list of archives
    #    that should not be unpacked, and extractcode provides a
    #    --ignore option for this purpose.  However, be aware that other
    #    files that happen to match this name would then be ignored.
    # if cmd([extractcode, "--quiet", "--all-formats", "--replace-originals",
    if cmd([extractcode, "--replace-originals", archive],
           "source code extraction output:"):
        # Here, we need to determine whether the failure was complete, or
        # whether it's useful to continue with scancode analysis.  We could
        # look at the extractcode output that got logged to the DB, but then
        # we'd be sensitive to any upstream changes in that output.  Instead,
        # the bottom line is whether the main archive itself has been
        # converted into a subdirectory and now contains at least one file.
        # This is an easy test.
        try:
            topdir = os.listdir(pkgdir + '/' + pkgname)
            # print(topdir)
            if len(topdir) < 1:
                returncode = 1          # Failed to unpack (don't try to scan)
            else:
                returncode = 0          # Successful unpack
        except:
            returncode = 1              # Failed to unpack
    else:
        returncode = 0                  # Successful unpack

    # Yet another extractcode problem: It's leaving temporary subdirectories
    # under /tmp.  Normally, they're very small and don't cause trouble, but
    # sometimes the sizes can be substantial.  These can fill the disk and
    # bring the system down.  Try to remove them.
    tmpdirs = os.listdir("/tmp")
    for tmpdir in tmpdirs:
        if tmpdir[0:12] == "scancode-tk-":
            cmd(["rm", "-rf", "/tmp/" + tmpdir],
                "removing extractcode tmp files:")

    return returncode



#
# This is the analysis script, starting here
#


# Do we have a temporary directory?  Error out if we don't.
if not os.path.isdir(tmpdir):
    print(f"Missing temporary subdirectory {tmpdir} (needed for analysis work)")
    exit(1)


# Connect to the database.  We can't do anything without a connection.
DBhost = os.environ['DB_HOST']
DBuser = os.environ['DB_USER']
DBpassword = os.environ['DB_PASSWD']
DBdatabase = os.environ['DB_NAME']
DBport = os.environ['DB_PORT']
print("Starting analysis run")
# print("Connection information:")
# print("  Host:", DBhost)
# print("  Port:", DBport)
# print("  DB:  ", DBdatabase)
# print("  User:", DBuser)

cdb = ldb.open(DBdatabase, DBhost, DBport, DBuser, DBpassword)
if cdb == None:
    print("Bummer...the database isn't connected")
    exit(1)


# We have at least one SQL statement problem that depends on the version
# of the database.  Let's query the DB to get the version first.
sql = "SHOW server_version;"
try:
    cdb.execute(sql)
    row = cdb.fetchone()
except Exception as e:
    print("Failed to query the postgreSQL server version")
    print("Error: " + e.args[0])
    ldb.close()
    exit(1)
db_version = row[0].split('.')
#print("Database version", db_version)


# Is there anything that needs analysis?  Don't grab the lock unless there is.
# Fetch sources where analysis != 1000 and retries < RETRIES
rows = analysis_work()
if len(rows) == 0:
    # Nothing to do, so just quit
    print("No source packages need analysis")
    ldb.close()
    exit(0)
print(f"Got {len(rows)} package(s) that need(s) analysis")


# Check for and obtain the analysis lock.  No sense running two copies of this
# process right now.  Not that once grabbed, we need to ensure we don't exit
# this program without releasing the lock.
# FIXME: In the future, we may want parallel analysis tasks, and would need a
# more robust way to handle queueing of these analyses.
if not analysis.lock():
    print("It appears another analysis task is running.  This one is exiting.")
    exit(2)


###
# Main loop starts here.  Grab one package that needs analysis from the DB.
###

# FIXME: Python 3.8 brings in the := operator which would reduce the next few
# lines.
while True:
    rows = analysis_work()
    if len(rows) < 1:
        break                           # End of FIXME

    w = analysis_decode(rows[0])        # Assign names to the values
    source_id = w['id']                 # Keep these available for convenience
    source_name = w['name']
    source_type = w['type']
    retries = w['retries']
    print(f"Starting package analysis on {source_name}")


    # Create a temp subdirectory for this analysis run
    pkgdir = tmpdir + str(w['id'])
    if cmd(["/bin/mkdir", pkgdir],
           "failed to create package analysis subdirectory"):
        break                           # Don't retry on this sort of error
    os.chdir(pkgdir)


    # Source containers are special beasts.  The process for a source container
    # is to download the container contents, identify the packages that are
    # part of the container, then add them all to the analysis queue.  In
    # addition, add a container structure that manifests the contents of the
    # source container.
    #
    # The "tools/source-container" script can create the entire json structure
    # to perform all this.  So we need to execute the script, ensure there are
    # no errors, then remove the entry from the sources table.
    if source_type == "scnt":
        source_update(source_id, {"status": "Executing source-container script",
                                  "error": ""})

        # We will need the tools subdirectory environment variable
        try:
            TOOLSDIR = os.environ['OSLCRS_TOOLS']
        except:
            print("Failed to locate tools subdirectory")
            clean_temp()
            source_update(source_id, {"retries": RETRIES}) # No need to retry
            continue

        # If the Flask application has a requested port, use it
        try:
            FLASKport = os.environ['OSLCRS_PORT']
        except:
            FLASKport = 5000
        # print("Got FLASKport of", FLASKport)

        print(f"Starting import of source container {source_name}")
        # scnt = [TOOLSDIR + "/test-brew-API"]
        scnt = [TOOLSDIR + "/source-container", "-q", w['fetch_info']]
        with open("load.json", "w") as outfile:
            output = subprocess.run(scnt, stdout=outfile,
                                    stderr=subprocess.PIPE)
            if output.returncode != 0:
                error_str = "error: failed to import source container"
                error_str += '\n'
                error_str += str(output.stderr, 'UTF-8')
                print(error_str)
                p = {"error": error_str, "retries": str(retries + 1)}
                sql = f"UPDATE sources \
                        SET (error, retries) = (%(error)s, %(retries)s) \
                        WHERE id = {source_id}"
                try:
                    cdb.execute(sql, p)
                    ldb.commit()
                except Exception as e:
                    ldb.rollback()
                    print("error: failed DB error log for",
                          f"source id {source_id}")
                    print("Error: " + e.args[0])
                    exit(1)
                clean_temp()            # Clean download subdirectory
                continue

        # The file load.json now contains the json structure that
        # needs to be imported into oslcrs.  Perform this action.
        upf = {'file': ('file', open('load.json', 'rb'), 'multipart/form-data')}
        r = requests.post(f"http://127.0.0.1:{FLASKport}/upload", files=upf)
        if r.status_code != 200:
            error_str = "error: failed source container json structure import"
            print(error_str)
            print("html response:", r)
            p = {"error": error_str}
            sql = f"UPDATE sources \
                    SET (error, retries) = (%(error)s, %(retries)s) \
                    WHERE id = {source_id}"
            try:
                cdb.execute(sql, p)
                ldb.commit()
            except Exception as e:
                ldb.rollback()
                print("error: failed to log error to DB for",
                      f"source id {source_id}")
                print("Error: " + e.args[0])
                exit(1)
            clean_temp()
            source_update(source_id, {"retries": RETRIES}) # No need to retry
            continue
        print(f"Successfully scheduled analysis of container {source_name}")

        # Remove the source container entry from the analysis queue
        sql = f"DELETE FROM sources WHERE id = {source_id};"
        try:
            cdb.execute(sql)
            ldb.commit()
        except Exception as e:
            ldb.rollback()
            print("Failed to remove sources container analysis request")
            print("Error: " + e.args[0])
            ldb.close()
            exit(1)
        clean_temp()                    # Clean download subdirectory
        continue                        # Nothing else to be done here
    # End of source container section


    # Download the requested package
    # Note "error" is cleared here in case there's old *stuff* from a prior
    # failed analysis.
    source_update(source_id, {"status": "Downloading source package",
                              "error": ""})
    fetch_info = json.loads(w['fetch_info'])
    fetch_url = fetch_info['fetch_url'] # All types require a "fetch_url"
    src_loc = ""                        # Keep this around for later
    # print(f"Got fetch_url of {fetch_url}")
    if re.search('^file://', fetch_url):
        src_loc = re.sub('^file://', '', fetch_url)
        if cmd(["cp", src_loc, '.'], "failed source file copy"):
            clean_temp()
            source_update(source_id, {"retries": RETRIES}) # No need to retry
            continue
    else:
        if cmd(["/usr/bin/wget", "--no-check-certificate", fetch_url],
               "failed source URL fetch"):
            clean_temp()
            continue                    # This could benefit from a retry
    archive = [f for f in os.listdir('.') if os.path.isfile(f)][0]
    # print(f"Successful download of {archive}")


    # Checksum the package?  Is it already analyzed?
    # FIXME: If we have a newer scancode, we may wish to re-analyze.
    # Capture new/different URL, even if we already analyzed this package.
    pkg_name = os.listdir('.')[0]
    # print(f"Found package name of {pkg_name}")
    pkg_uuid = swhid_of_file(archive)   # Compute SWH UUID for entire archive
    # print(f"Computed package UUID of {pkg_uuid}")
    # FIXME: The "state = 9" will need to change when we do other pieces
    sql = f"SELECT id FROM sources \
            WHERE checksum = '{pkg_uuid}' AND \
                  state = 9"
    try:
        cdb.execute(sql)
        rows = cdb.fetchall()
    except Exception as e:
        print("Failed to execute sources checksum query")
        print("Error: " + e.args[0])
        ldb.close()
        exit(1)
    if len(rows) > 0:
        # We apparently already analyzed this package
        print(f"We have already analyzed package {pkg_name} " +
              f"(source ID {rows[0][0]})")
        print("FIXME: Maybe parts of the analysis aren't complete")
        print("FIXME: Code here to record new URL if necessary")
        print("FIXME: Not supported different names for same package SWHID")
        # Remove this analysis request
        sql = f"DELETE FROM sources WHERE id = {source_id};"
        try:
            cdb.execute(sql)
            ldb.commit()
        except Exception as e:
            ldb.rollback()
            print("Failed to remove sources entry that is already analyzed")
            print("Error: " + e.args[0])
            ldb.close()
            exit(1)
        # If we were analyzing a local file, remove it.  See comments at end of
        # loop.
        if src_loc != "":
            if cmd(["rm", src_loc],
                   f"failed to remove already-analyzed file {src_loc}"):
                clean_temp()
                continue
            # Try to remove the subdirectory this file was in, in case it's now
            # empty.
            cmdstr = f'rmdir --ignore-fail-on-non-empty "`dirname {src_loc}`"'
            if cmd(["/bin/bash", "-c", cmdstr],
                   "failed to remove subdir of already-analyzed file" +
                   f"{src_loc}"):
                clean_temp()
                continue
        clean_temp()                    # Clean download subdirectory
        continue                        # Nothing else to be done here


    # Unpack the archive
    source_update(source_id, {"status": "Unpacking source archive"})
    if unpack_archive(pkgdir, pkg_name):
        # print("Failed extract")
        # exit(0)
        clean_temp()                    # Clean download subdirectory
        source_update(source_id, {"retries": RETRIES}) # No need to try again
        continue
    # print("Successful extract")
    # exit(0)


    # Now that we have the source package and it's unpacked, we want to gather
    # available metadata.  This will depend on the type of source it is.  Over
    # time, we will want to support other source formats, and we'll be adding
    # those right here.
    #
    # Each block needs to produce the following, which will be used by code
    # that follows:
    #   src_pkg_name: string
    #   upstream_url: string
    #   pkg_sum_license: string
    #   binaries: array of dictionary, where dictionary is:
    #     nvr: string (nvr of binary package)
    #     license: string (summary license expression for binary package)
    # FIXME: Need some error checks here
    if source_type == "custom":         # This is where everything is specified
        src_pkg_name = source_name      # The uploader gave us this value
        upstream_url = fetch_info['upstream_url']
        pkg_sum_license = fetch_info['license']
        binaries = fetch_info['binaries']

    # FIXME: After much work on SRPM import, it has been demonstrated that
    # it is not possible to import a SRPM and correctly determine binary
    # package N-V-Rs produced from this SRPM.  Though the following code is
    # left in the prototype, it does not work correctly in all cases.
    elif source_type == "srpm":         # This is a source RPM
        summary = parse_spec_file(pkg_name) # Get metadata from spec file
        if summary == None:             # Failed to find or parse spec file
            printf(f"Failed to locate single spec file or parse it correctly")
            source_update(source_id, {"retries": RETRIES}) # Don't try again
            clean_temp()                    # Clean download subdirectory
            continue
        src_pkg_name = summary['src_name']
        upstream_url = summary['upstream']
        pkg_sum_license = summary['license']
        # FIXME: WARNING: See note in parse_spec_file()
        # binaries = summary['packages']
        binaries = []                   # Empty array for SRPM import type
        # print(f"Got upstream url of {upstream_url}")
        # print(f"Got binaries of {binaries}")
        cwd = os.getcwd()
        # print(f"Ending subdirectory was {cwd}")

    else:
        # This will be an "unimplemented" error
        print(f"error: unimplemented source type {source_type}")
        source_update(source_id, {"retries": RETRIES}) # No need to try again
        clean_temp()                    # Clean download subdirectory
        continue


    ###
    # Here is where we can do some steps in parallel.  Right now, just working
    # on local scancode analysis.  Other steps (TBD) are Fossology submit and
    # SWH deposit.
    #
    # In the case of SWH, the most expedient way to do a deposit is to tar the
    # source code and submit the tar to SWH.  For example:
    #   tar cvjf <package_name>.tar.bz <package_subdirectory>
    #   <code to do SWH deposit>
    #
    # In the case of Fossology, it's easier to submit the original source
    # package, allowing Fossology to do its own unpack.
    #
    # In both of these cases, we need to arrange to be notified when the step
    # is complete, and we need to capture the e.g. Fossology URL in our DB.
    # We also need to update the analysis status when one of these steps
    # finishes.
    ###


    source_update(source_id, {"status": "Pruning individual source files"})
    # Generate file list
    # FIXME: We ran into a problem where some test code included archives of
    # about 1.2M empty files.  As a temporary workaround, we're going to avoid
    # processing any file that is zero-length or one character long.  This is
    # relatively safe since we can't imagine how copyrightable content could
    # exist in files this short.
    if cmd(["/bin/bash", "-c",
            "cd *; /usr/bin/find -type f -size -2c -exec rm -f {} \;"],
           "failed small file removal"):
        clean_temp()                    # Clean download subdirectory
        continue
    # END FIXME for large number of empty or small files
    if cmd(["/bin/bash", "-c",
            "cd *; /usr/bin/find -type f | /bin/sed 's/^\.\///' >../filelist"],
           "failed file list"):
        clean_temp()                    # Clean download subdirectory
        continue
    # print("Successfully listed all files")


    # Iterate over files:
    # - compute per-file UUID
    # - prune if we already analyzed this file
    # Keep list of file paths, files, and UUIDs
    uuids = dict()                      # SWH UUIDs indexed by path
    file_adds = dict()                  # List of all SWH UUIDs we need to add
                                        # to the DB, indexed by UUID
    with open("paths", 'w') as ofp:
        # ofp.write('Hello\n')
        with open("filelist") as ifp:
            line = ifp.readline()[:-1]  # Eliminate only trailing newline
            while line:
                thisfile = pkg_name + '/' + line
                file_uuid = swhid_of_file(thisfile) # Compute file SWH UUID
                ofp.write(file_uuid + ' ' + line + '\n')
                uuids[line] = file_uuid # Keep all of these paths
                file_id = isfile_done(file_uuid)
                if file_id == None:
                    file_adds[file_uuid] = None # We'll get file ID later
                else:
                    # print(f"file {thisfile} was already done")
                    os.remove(thisfile) # Prune the file to save analysis time
                line = ifp.readline()[:-1]


    # Submit remaining tree to scancode for license and copyright analysis
    source_update(source_id, {"status": "Scancode license/copyright analysis"})
    os.chdir(pkg_name)
    if cmd([scancode, "-plc", "--quiet", "--json", "../scancode.json",
            "--only-findings", "--strip-root", "--processes", "16",
            "--timeout", "0", "--max-depth", "0", '.'],
           "failed scancode license/copyright analysis"):
        clean_temp()                    # Clean download subdirectory
        source_update(source_id, {"retries": RETRIES}) # No need to try again
        continue
    # print("Successful scancode license/copyright analysis")
    os.chdir('..')


    # Each new result will require a "files" table entry.  Add these first.
    source_update(source_id, {"status": "Adding new files to database"})
    for swh_uuid in file_adds.keys():
        file_adds[swh_uuid] = addfile(swh_uuid)


    # Record per-file license and copyright results in DB
    # FIXME: When results from an updated version of scancode are to replace
    # existing entries, the SQL will be a lot more complicated!  Right now,
    # duplicates are being ignored, which leads to out-of-date information.
    source_update(source_id, {"status": "Recording license/copyright info"})
    with open("scancode.json") as scfp:
        sc = json.load(scfp)            # Read scan results into memory
                                        # FIXME: Might this be too big a
                                        # structure to fit?
    scancode_version = sc["headers"][0]["tool_version"]
    d = scancode_version.split('.')     # Compute an integer version related
                                        # to the scancode version
    detector = 0
    for i in d:
        detector = detector * 1000 + int(i)
    # print(f"Detector: {detector}")
    for scf in sc["files"]:
        if scf["type"] == "file":
            # print(f"Results for file {scf['path']}")
            # print(f"SWH UUID: {uuids[scf['path']]}")
            fid = file_adds[uuids[scf['path']]]
            # print(f"DB id was {fid}")
            for lic in scf["licenses"]:
                # print(f"License {lic['key']}, score {lic['score']}, " +
                #       f"rule {lic['matched_rule']['identifier']}, " +
                #       f"start {lic['start_line']} end {lic['end_line']}")

                ###
                # FIXME WARNING
                #
                # Early in its use of scancode, the PELC team found that
                # certain license detections were seen, but these detections
                # are not useful.  Although scancode is detecting "something",
                # it's not an actionable result.  We decided that these would
                # be ignored.  Due to this, these detections were dropped
                # before they became part of the result database, as well
                # as not being present in the licenses table.  This is not a
                # good long-term strategy.  It would be better to record the
                # detection, but then filter it out upon presentation to the
                # user.  However, this will take more work on the reporting
                # side.
                #
                # For now, I am following the PELC example of skipping the
                # recording of these license detections.  However, we will
                # need to change how we handle these in the future, as well
                # as rescan *all* the packages/files that we have in the DB,
                # in order to update the detection results.
                ###
                if lic['key'] == 'unknown-license-reference':
                    continue            # Skip adding this license detection
                addrow("license_detects",
                       {
                         "file_id": fid,
                         "lic_name": lic['key'],
                         "score": lic['score'],
                         "rule": lic['matched_rule']['identifier'],
                         "start_line": lic['start_line'],
                         "end_line": lic['end_line'],
                         "detector": detector
                       })
            for copy in scf["copyrights"]:
                # print(f"Copyright: {copy['value']}")
                addrow("copyrights",
                       {
                         "file_id": fid,
                         "copyright": copy['value'],
                         "start_line": copy['start_line'],
                         "end_line": copy['end_line'],
                         "detector": detector
                       })
        else:
            # print(f"Would ignore {scf['path']}, type {scf['type']}")
            pass                        # Python NOOP


    # Record all file paths in the "paths" table
    source_update(source_id, {"status": "Recording file paths"})
    for key, value in uuids.items():
        # params = {
        #            "source_id": source_id,
        #            "file_id": isfile_done(value),
        #            "path": key
        #          }
        addrow("paths",
               {
                 "source_id": source_id,
                 "file_id": isfile_done(value),
                 "path": key
               })


    # We need to record the upstream URL in the sources table.  The value comes
    # from earlier, when we gathered metadata from the source archive or else
    # it was provided to us.
    source_update(source_id, {"url": upstream_url})


    # Now that source analysis is done, we need to add the binary packages
    # FIXME: Error checks?  Duplicates?  The current code will simply replace
    # existing nvr values with new ones.  This is *not* desired.  We *hope* to
    # not have duplicate nvr values, as these will make it difficult/impossible
    # to refer to packages by nvr, but if/when there is a duplicate, we need
    # to detect it and decide what to do about it.
    for binary in binaries:
        addrow("packages",
               {
                 "nvr": binary['nvr'],
                 "source_id": source_id,
                 "sum_license": binary['license']
               })
    # One last special case, and this is probably a future FIXME!
    # We have imported source packages, yet this system is designed to produce
    # reports indexed by binary packages.  (After all, that's what we ship,
    # right?)  Yet, depending on the way the manifest data is handed to us and
    # the customer desires, we may want to index these license reports based on
    # source packages.  We could have a lot of duplicate reporting code (and we
    # might want to do this in the future for full flexibility), but since this
    # is a prototype, I'm trying a short-cut, to see how well it works.
    #
    # We've already added the specified binary packages.  We will ALSO add
    # another binary package and set a flag so we know it's not a real binary
    # package, but one corresponding to the source package name.  Doing this
    # means that the reporting code can simply search on package names and not
    # have to handle special cases.  Yet, these extra entries are flagged in
    # case we want to eliminate them later.  Here's the code that adds these
    # fake binary packages.
    addrow("packages",
           {
             "nvr": src_pkg_name,
             "source_id": source_id,
             "sum_license": pkg_sum_license,
             "source": 1
           })
    # END fake binary package FIXME
    source_update(source_id, {"status": "scancode analysis complete"})


    # Record package checksum and mark scancode as being "done"
    # Do not clear "error", because unpack errors may need to be reviewed
    source_update(source_id, {"checksum": pkg_uuid, "state": "9"})


    # If we were analyzing a local file, now is the time to remove that file
    # so we don't run out of server space.  Recall that we saved src_loc
    # earlier for this purpose.
    if src_loc != "":
        if cmd(["rm", src_loc],
               f"failed to remove already-analyzed file {src_loc}"):
            clean_temp()
            continue
        # Try to remove the subdirectory this file was in, in case it's now
        # empty.
        cmdstr = f'rmdir --ignore-fail-on-non-empty "`dirname {src_loc}`"'
        if cmd(["/bin/bash", "-c", cmdstr],
               f"failed to remove subdir of already-analyzed file {src_loc}"):
            clean_temp()
            continue


    ###
    # End of parallel paths
    ###


    # Update "sources" table with results of this analysis.
    # FIXME: The missing parts are the SWH deposit and Fossology run


    ###
    # End of main loop.  Ensure clean-up of last analysis is done.
    ###
    clean_temp()                        # Clean download subdirectory


# Perform routine maintenance, since the system should now be idle
# vacuum()                              # Not currently in use (see function)


# Clean up and exit script
# - Release any lock file
ldb.close()
print("End of analysis script")
exit(0)
