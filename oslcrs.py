# Application to serve up data from the prototype license reporting database
# WARNING...PROTOTYPE CODE
#
# Bryan Sutula, Red Hat, revised 4/21/22
# Released under GPL version 2

import json                             # May not be needed
import os                               # Environment variable support
import subprocess                       # Used to analyze packages
import psycopg2                         # Postgress connector library
import requests                         # Used to obtain Corgi data
from urllib.parse import urlencode, quote_plus
from flask import Flask, render_template, request, jsonify, Response
app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = "/tmp"    # Flask application configuration
app.config['MAX_CONTENT_PATH'] = 256 * 1024 * 1024 # 256 MB maximum upload


# Global constants
# This is the "enumeration" of the "licenses" table, "approved" column
legend = ["Proposed", "Approved", "Rejected", "New", "Ignored", "Provisional"]
# Note that all paths are relative to the subdirectory from which oslcrs is run
upload_dir = "/tmp/oslcrs/"             # Directory used to store source files
analysis_program = "./analyze.py"       # This is the script that performs all
                                        # license analysis


# These are the set of files that we consider to be potential summary license
# candidate file names.  Wildcard is '%', based on SQL SELECT WHERE...LIKE...
summary_license_file_patterns = [
    "/C[Oo][Pp][Yy][Ii][Nn][Gg][^/]*$",
    "/C[Oo][Pp][Yy][Rr][Ii][Gg][Hh][Tt][^/]*$",
    "/L[Ii][Cc][Ee][Nn][CcSs][Ee][^/]*$"
]
summary_license_threshold = 30          # Percent matching threshold for valid
                                        # license matches
RETRIES = 3                             # Number of analysis retries before
                                        # we consider this a failed run
                                        # WARNING: Ensure the value in
                                        # analyze.py is consistent with this
                                        # value


# Functions needed by this program
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


# This function returns a list of licenses detected in a package, considering
# only those named files defined by the summary_license_file_patterns array.
def summary_licenses(pkg_id, cdb):
    # Collect the summary license detections for this package
    sql = f"SELECT DISTINCT license_detects.lic_name \
            FROM files \
            JOIN paths on files.id = paths.file_id \
            JOIN sources on paths.source_id = sources.id \
            JOIN packages on packages.source_id = sources.id \
            JOIN license_detects on files.id = license_detects.file_id \
            WHERE packages.id = {pkg_id} and ( "
    first = True
    for term in summary_license_file_patterns:
        if not first:
            sql += "or "
        sql += f"paths.path ~ '{term}' "
        first = False
    sql = sql + f") and license_detects.score > {summary_license_threshold} \
            ORDER BY license_detects.lic_name;"
    # print(sql)
    try:
        cdb.execute(sql)
        rows = cdb.fetchall()
    except Exception as e:
        s.append("<br>Failed to execute package file paths query")
        s.append("<br>Error: " + e.args[0])
        return render_template("base.html", content=s, em=EM)

    expression = ""
    for row in rows:
        if expression == "":
            expression = row[0]
        else:
            expression = expression + ' and ' + row[0]
    return expression



# This function examines an uploaded json structure for errors.  If no errors
# are found, False is returned.  True otherwise.  If the passed "cdb" is
# is non-None, then perform database updates based on the passed json.
def parse_json(js, cdb, s):
    # We allow four types of json input structures, which are:
    # - Manifest: product, container, release
    # - Source Code: source
    # We also allow one additional "linking" json input structure:
    # - Binary package to Source package mapping
    # We require that dependent manifest elements already exist in the DB.
    #
    # Source elements are independent of product manifest elements, and
    # product manifest elements are independent of sources.  Products are
    # required to exist before releases, and containers must exist before
    # releases that require them.

    # We also handle arrays of json imports, so that a single json file can
    # specify multiple things.  Detect the case of arrays first, then recurse
    # on each element of the array.
    if isinstance(js, list):
        s.append(f"Received a list of {len(js)} json import structures<br>")
        for json_item in js:
            if parse_json(json_item, cdb, s):
                s.append(f"error: failed json import on {json_item}<br>")
                return True             # Early exit on error
        return False                    # All json structures must have worked

    # Since we handle only one top-level, then length of top level must be 1
    if len(js) != 1:
        s.append("error: json upload can handle only one type at a time<br>")
        s.append(f"current json includes {len(js)} elements<br>")
        return True

    # PRODUCT JSON IMPORT
    if "product" in js:
        # print("json product import")
        sp = js["product"]
        for key, value in sp.items():
            if not key in ["name", "displayname", "description", "family"]:
                s.append(f"error: bad key for product import: {key}<br>")
                return True
            if not isinstance(value, str):
                s.append(f"error: value for key {key} is not a string<br>")
                return True
        # Minimally, need at least a product name
        if not "name" in sp:
            s.append("error: missing product name (required)<br>")
            return True
        # We have done all the data checks.  Do the DB insert, if necessary.
        if cdb != None:                 # This block can get skipped
            sql = "INSERT INTO products \
                          (name, displayname, description, family) \
                   VALUES (%(name)s, %(displayname)s, \
                           %(description)s, %(family)s) \
                   ON CONFLICT (name) DO UPDATE \
                       SET (displayname, description, family) = \
                           (%(displayname)s, %(description)s, %(family)s) \
                   RETURNING id"
            try:
                cdb.execute(sql, sp)
                result = cdb.fetchone()
                product_id = result[0]
                ldb.commit()
                s.append(f"Successfully inserted product {sp['name']}<br>")
                return False            # Successful product import
            except Exception as e:
                ldb.rollback()
                s.append(f"error: failed to add product {sp['name']}<br>")
                s.append(f"DB error: {e}<br>")
                return True
        else:
            return False                # Successful product import check

    # CONTAINER JSON IMPORT
    elif "container" in js:
        # print("json container import")
        sp = js["container"]
        for key, value in sp.items():
            if not key in ["reference", "bin_packages", "src_packages"]:
                s.append(f"error: bad key for container import: {key}<br>")
                return True
        # Minimally, need at least a container reference
        if not "reference" in sp:
            s.append("error: missing container reference (required)<br>")
            return True
        if not isinstance(sp["reference"], str):
            s.append(f"error: value for key reference is not a string<br>")
            return True
        # If packages are present, check them
        # FIXME: A better code structure here would eliminate duplicate code
        if "bin_packages" in sp:
            if not isinstance(sp["bin_packages"], list):
                s.append(f"error: value for key bin_packages is not an array<br>")
                return True
            for item in sp["bin_packages"]:
                if not isinstance(item, str):
                    s.append(f"error: bin_package nvr {item} is not a string<br>")
                    return True
            bin_packages = sp["bin_packages"]
        else:
            bin_packages = []           # Empty package list skips loop later
        if "src_packages" in sp:
            if not isinstance(sp["src_packages"], list):
                s.append(f"error: value for key src_packages is not an array<br>")
                return True
            for item in sp["src_packages"]:
                if not isinstance(item, str):
                    s.append(f"error: src_package nvr {item} is not a string<br>")
                    return True
            src_packages = sp["src_packages"]
        else:
            src_packages = []               # Empty package list skips loop later
        # We have done all the data checks.  Do the DB insert, if necessary.
        if cdb != None:                 # This block can get skipped
            # This is the container reference insert
            sql = f"INSERT INTO containers \
                           (reference) \
                    VALUES (%(reference)s) \
                    ON CONFLICT (reference) DO UPDATE \
                        SET (reference) = {need_row}(%(reference)s) \
                    RETURNING id"
            try:
                cdb.execute(sql, sp)
                result = cdb.fetchone()
                container_id = result[0]
                ldb.commit()
                s.append("Successfully inserted container " +
                         f"{sp['reference']}<br>")
            except Exception as e:
                ldb.rollback()
                s.append("error: failed to add container " +
                         f"{sp['reference']}<br>")
                s.append(f"DB error: {e}<br>")
                return True
            # This ensures prior packages listed in this container are gone
            sql = f"DELETE FROM container_packages \
                    WHERE container_id = {container_id}"
            try:
                cdb.execute(sql)
                ldb.commit()
            except Exception as e:
                ldb.rollback()
                s.append("error: failed to remove package NVRs " +
                         f"for container {sp['reference']}<br>")
                s.append(f"DB error: {e}<br>")
                return True
            # This adds the references to all the binary packages
            # FIXME: More duplicate code below
            for nvr in bin_packages:
                binpkg = {"cid": container_id, "nvr": nvr, "source": 0}
                sql = "INSERT INTO container_packages \
                              (container_id, package_nvr, source) \
                       VALUES (%(cid)s, %(nvr)s, %(source)s) \
                       ON CONFLICT DO NOTHING"
                try:
                    cdb.execute(sql, binpkg)
                    ldb.commit()
                except Exception as e:
                    ldb.rollback()
                    s.append("error: failed to add container " +
                             f"{sp['reference']} bin_package NVR {nvr}<br>")
                    s.append(f"DB error: {e}<br>")
                    return True
            # This adds the references to all the source packages
            for nvr in src_packages:
                srcpkg = {"cid": container_id, "nvr": nvr, "source": 1}
                sql = "INSERT INTO container_packages \
                              (container_id, package_nvr, source) \
                       VALUES (%(cid)s, %(nvr)s, %(source)s) \
                       ON CONFLICT DO NOTHING"
                try:
                    cdb.execute(sql, srcpkg)
                    ldb.commit()
                except Exception as e:
                    ldb.rollback()
                    s.append("error: failed to add container " +
                             f"{sp['reference']} src_package NVR {nvr}<br>")
                    s.append(f"DB error: {e}<br>")
                    return True
            return False                # Successful container import
        else:
            return False                # Successful container import check

    # RELEASE JSON IMPORT
    elif "release" in js:
        # print("json release import")
        sp = js["release"]
        for key, value in sp.items():
            if not key in ["productname", "version", "notes",
                           "containers", "bin_packages", "src_packages"]:
                s.append(f"error: bad key for release import: {key}<br>")
                return True
        # Minimally, need at least a product name and release version
        if not "productname" in sp:
            s.append("error: missing productname (required)<br>")
            return True
        if not "version" in sp:
            s.append("error: missing release version (required)<br>")
            return True
        if not isinstance(sp["productname"], str):
            s.append(f"error: value for key productname is not a string<br>")
            return True
        if not isinstance(sp["version"], str):
            s.append(f"error: value for key version is not a string<br>")
            return True
        # If notes are present, they must be a string
        if "notes" in sp:
            if not isinstance(sp["notes"], str):
                s.append(f"error: value for key notes is not a string<br>")
                return True
        else:
            sp["notes"] = ""            # DB insert will need some value
        # If containers are present, check them
        if "containers" in sp:
            if not isinstance(sp["containers"], list):
                s.append(f"error: value for key containers is not an array<br>")
                return True
            for item in sp["containers"]:
                # FIXME source: Add requirement for "source" parameter?
                if not isinstance(item, str):
                    s.append(f"error: container ref {item} is not a string<br>")
                    return True
            containers = sp["containers"]
        else:
            containers = []             # Empty container list skips loop later
        # If packages are present, check them as well
        # FIXME: A better code structure here would eliminate duplicate code
        if "bin_packages" in sp:
            if not isinstance(sp["bin_packages"], list):
                s.append(f"error: value for key bin_packages is not an array<br>")
                return True
            for item in sp["bin_packages"]:
                if not isinstance(item, str):
                    s.append(f"error: bin_package nvr {item} is not a string<br>")
                    return True
            bin_packages = sp["bin_packages"]
        else:
            bin_packages = []           # Empty package list skips loop later
        if "src_packages" in sp:
            if not isinstance(sp["src_packages"], list):
                s.append(f"error: value for key src_packages is not an array<br>")
                return True
            for item in sp["src_packages"]:
                if not isinstance(item, str):
                    s.append(f"error: src_package nvr {item} is not a string<br>")
                    return True
            src_packages = sp["src_packages"]
        else:
            src_packages = []           # Empty package list skips loop later
        # We have done all the data checks.  Do the DB insert, if necessary.
        if cdb != None:                 # This block can get skipped
            # Prior to inserting anything in the DB, try to gather IDs from
            # referenced items.  This work would need to be done eventually,
            # and doing it first allows for a potential error exit before
            # making a change to the DB.  We can't cover all error cases,
            # but hopefully have covered most.
            sql = "SELECT id from products \
                   WHERE name = %(productname)s"
            try:
                cdb.execute(sql, sp)
                result = cdb.fetchone()
                sp["product_id"] = result[0]
            except Exception as e:
                s.append("error: failed to find product name " +
                         f"{sp['productname']}<br>")
                s.append(f"DB error: {e}<br>")
                return True
            # print(f"Found product id {sp['product_id']}")
            # Form dictionary of referenced containers with their container IDs
            relations = dict()
            for ref in containers:
                spc = {"reference": ref}
                sql = "SELECT id from containers \
                       WHERE reference = %(reference)s"
                try:
                    cdb.execute(sql, spc)
                    result = cdb.fetchone()
                    relations[ref] = result[0]
                except Exception as e:
                    s.append("error: failed to find container reference " +
                             f"{ref}<br>")
                    s.append(f"DB error: {e}<br>")
                    return True
            # This is the release version insert
            sql = "INSERT INTO releases \
                          (product_id, version, notes) \
                   VALUES (%(product_id)s, %(version)s, %(notes)s) \
                   ON CONFLICT ON CONSTRAINT releases_product_id_version_key \
                       DO UPDATE \
                       SET (product_id, version, notes) = \
                           (%(product_id)s, %(version)s, %(notes)s) \
                   RETURNING id"
            try:
                cdb.execute(sql, sp)
                result = cdb.fetchone()
                release_id = result[0]
                ldb.commit()
                s.append("Successfully inserted release " +
                         f"{sp['version']}<br>")
            except Exception as e:
                ldb.rollback()
                s.append("error: failed to add release " +
                         f"{sp['version']}<br>")
                s.append(f"DB error: {e}<br>")
                return True
            # This ensures prior packages listed in this release are gone
            sql = f"DELETE FROM release_packages \
                    WHERE release_id = {release_id}"
            try:
                cdb.execute(sql)
                ldb.commit()
            except Exception as e:
                ldb.rollback()
                s.append("error: failed to remove package NVRs " +
                         f"for release {sp['version']}<br>")
                s.append(f"DB error: {e}<br>")
                return True
            # This ensures prior containers listed in this release are gone
            sql = f"DELETE FROM release_containers \
                    WHERE release_id = {release_id}"
            try:
                cdb.execute(sql)
                ldb.commit()
            except Exception as e:
                ldb.rollback()
                s.append("error: failed to remove container reference " +
                         f"for release {sp['version']}<br>")
                s.append(f"DB error: {e}<br>")
                return True
            # This adds the references to all the containers
            for ref in containers:
                cref = {"rid": release_id, "cid": relations[ref]}
                sql = "INSERT INTO release_containers \
                              (release_id, container_id) \
                       VALUES (%(rid)s, %(cid)s) \
                       ON CONFLICT DO NOTHING"
                try:
                    cdb.execute(sql, cref)
                    ldb.commit()
                except Exception as e:
                    ldb.rollback()
                    s.append("error: failed to add release " +
                             f"{sp['version']} container {ref}<br>")
                    s.append(f"DB error: {e}<br>")
                    return True
            # This adds the references to all the binary packages
            # FIXME: More duplicate code below
            for nvr in bin_packages:
                binpkg = {"rid": release_id, "nvr": nvr, "source": 0}
                sql = "INSERT INTO release_packages \
                              (release_id, package_nvr, source) \
                       VALUES (%(rid)s, %(nvr)s, %(source)s) \
                       ON CONFLICT DO NOTHING"
                try:
                    cdb.execute(sql, binpkg)
                    ldb.commit()
                except Exception as e:
                    ldb.rollback()
                    s.append("error: failed to add release " +
                             f"{sp['version']} bin_package NVR {nvr}<br>")
                    s.append(f"DB error: {e}<br>")
                    return True
            # This adds the references to all the source packages
            for nvr in src_packages:
                srcpkg = {"rid": release_id, "nvr": nvr, "source": 1}
                sql = "INSERT INTO release_packages \
                              (release_id, package_nvr, source) \
                       VALUES (%(rid)s, %(nvr)s, %(source)s) \
                       ON CONFLICT DO NOTHING"
                try:
                    cdb.execute(sql, srcpkg)
                    ldb.commit()
                except Exception as e:
                    ldb.rollback()
                    s.append("error: failed to add release " +
                             f"{sp['version']} src_package NVR {nvr}<br>")
                    s.append(f"DB error: {e}<br>")
                    return True
            return False                # Successful release import
        else:
            return False                # Successful release import check

    # SOURCE CONTAINER JSON IMPORT
    elif "scnt" in js:
        # print("json source container import")
        sp = js["scnt"]
        for key, value in sp.items():
            if not key in ["name", "fetch_url"]:
                s.append(f"error: bad key for source cont import: {key}<br>")
                return True
            if not isinstance(value, str):
                s.append(f"error: value for key {key} is not a string<br>")
                return True
        # Minimally, need at least a source container name and one other item
        if not "name" in sp:
            s.append("error: missing source container name (required)<br>")
            return True
        if not "fetch_url" in sp:
            s.append("error: missing source container fetch_url (required)<br>")
            return True
        dsp = dict()                    # Need these for DB insert
        dsp["name"] = sp["name"]
        dsp["type"] = "scnt"
        dsp["fetch"] = sp["fetch_url"]
        # print(f"Source container import")
        # print(f"Fetch: {dsp['fetch_url']}")
        # We have done the basic data checks.  As analysis proceeds, other
        # errors might be caught.
        if cdb != None:                 # This block can get skipped
            sql = "INSERT INTO sources (name, fetch_info, type) \
                   VALUES (%(name)s, %(fetch)s, %(type)s)"
            try:
                cdb.execute(sql, dsp)
                ldb.commit()
                s.append(f"Successfully inserted src_cont {sp['name']}<br>")
            except Exception as e:
                ldb.rollback()
                s.append(f"error: failed to add src_cont {sp['name']}<br>")
                s.append(f"DB error: {e}<br>")
                return True

            # Try to kick off the analyze subprocess
            temp = subprocess.Popen(["python3", analysis_program])
            s.append("Kicked off the package analysis program<br>")
            return False                # Successful source import
        else:
            return False                # Successful source import check

    # SOURCE JSON IMPORT
    # FIXME: This is not very well error-checked right now.  Some of the
    # parsing has been deferred to analyze.py, and we don't want to check
    # errors here and parse them there.  (That creates a less-supportable
    # code structure.)
    elif "source" in js:
        # print("json source import")
        sp = js["source"]
        for key, value in sp.items():
            if not key in ["name", "custom", "srpm"]:
                s.append(f"error: bad key for source import: {key}<br>")
                return True
            if key == "name":
                if not isinstance(value, str):
                    s.append(f"error: value for key {key} is not a string<br>")
                    return True
            else:
                type = key              # Capture the import type along the way
                if not isinstance(value, dict):
                    s.append(f"error: value for key {key} is not a struct<br>")
                    return True
        # Minimally, need at least a source name and one other item
        if not "name" in sp:
            s.append("error: missing source name (required)<br>")
            return True
        if len(sp) != 2:
            s.append("error: need both source name and an upload type<br>")
            return True
        dsp = dict()                    # Need these for DB insert
        dsp["name"] = sp["name"]
        dsp["type"] = type
        dsp["fetch"] = json.dumps(sp[type])
        # print(f"Source import type {type}")
        # print(f"Fetch: {dsp['fetch']}")
        # We have done the basic data checks.  As analysis proceeds, other
        # errors might be caught.
        if cdb != None:                 # This block can get skipped
            sql = "INSERT INTO sources (name, fetch_info, type) \
                   VALUES (%(name)s, %(fetch)s, %(type)s)"
            try:
                cdb.execute(sql, dsp)
                ldb.commit()
                s.append(f"Successfully inserted source {sp['name']}<br>")
            except Exception as e:
                ldb.rollback()
                s.append(f"error: failed to add source {sp['name']}<br>")
                s.append(f"DB error: {e}<br>")
                return True

            # Try to kick off the analyze subprocess
            temp = subprocess.Popen(["python3", analysis_program])
            s.append("Kicked off the package analysis program<br>")
            return False                # Successful source import
        else:
            return False                # Successful source import check

    # Binary to Source Mapping JSON IMPORT
    elif "binary" in js:
        # print("json binary-to-source mapping import")
        sp = js["binary"]
        for key, value in sp.items():
            if not key in ["name", "source", "license"]:
                s.append(f"error: bad key for binary-to-source import: \
                          {key}<br>")
                return True
            if not isinstance(value, str): # All values must be strings
                s.append(f"error: value for key {key} is not a string<br>")
                return True
        # All three values are required
        if (not "name" in sp) or (not "source" in sp) or (not "license" in sp):
            s.append("error: missing required binary-to-source parameter \
                     (requires 'name', 'source', and 'license')<br>")
            return True

        # We have done the basic data checks.  Insert the binary-to-source
        # mapping entry.  Note that the insert can still fail if we don't
        # have the corresponding source table entry.
        if cdb != None:                 # This block can get skipped
            # Ensure "source" exists in the sources table (remembering the ID)
            # Note that we're allowing "source" to be either the name (n-v-r> or
            # the checksum (SWID) field.  I'm reasonably sure that there's no
            # overlap between these values, so rather than create different
            # named entries in the json structure, we will match on either.
            sql = "SELECT id from sources \
                   WHERE name = %(source)s OR \
                         checksum = %(source)s"
            try:
                cdb.execute(sql, sp)
                rows = cdb.fetchall()
                if len(rows) != 1:
                    s.append("error: failed to uniquely locate source name " +
                             f"{sp['source']}; this matched " +
                             f"{len(rows)} rows in the database<br>")
                    return True
                sp["source_id"] = rows[0][0]
            except Exception as e:
                s.append("error: failed to find source name " +
                         f"{sp['source']}<br>")
                s.append(f"DB error: {e}<br>")
                return True
            print(f"Found source id {sp['source_id']}")

            # This is the actual packages table DB insert
            sql = "INSERT INTO packages (nvr, source_id, sum_license, source) \
                   VALUES (%(name)s, %(source_id)s, %(license)s, 0) \
                   ON CONFLICT (nvr, source) DO UPDATE \
                       SET (source_id, sum_license) = \
                           (%(source_id)s, %(license)s)"
            try:
                cdb.execute(sql, sp)
                ldb.commit()
                s.append(f"Successfully inserted binary package entry \
                           {sp['name']}<br>")
                return False            # Successful binary-to-source import
            except Exception as e:
                ldb.rollback()
                s.append(f"error: failed to add binary-to-source mapping entry \
                           {sp['name']}<br>")
                s.append(f"DB error: {e}<br>")
                return True
        else:
            return False                # Successful binary-to-source check


    else:
        # FIXME: What's the right way to get the only dictionary entry?
        for key in js.keys():
            s.append(f"error: unknown json upload type {key}<br>")
        return True

    return True


# These are the virtual web pages that can be supplied
@app.route("/")
def base():
    s = []
    s.append(f"<h3>Open Source License Compliance Reporting System</h3>")

    cdb = ldb.open(DBdatabase, DBhost, DBport, DBuser, DBpassword)
    if cdb == None:
        s.append("Bummer...the database isn't connected")

    else:
        # Currently, the initial page shows available products
        sql = "SELECT id, name, description, displayname, family \
               FROM products ORDER BY family, displayname, name;"
        try:
            cdb.execute(sql)
            rows = cdb.fetchall()
        except Exception as e:
            s.append("<br>Failed to execute product list query")
            s.append("<br>Error: " + e.args[0])
            return render_template("base.html", content=s, em=EM)

        # Return the results
        s.append("<p><b>Available Products:</b></p>")
        s.append('<table id="full" class="display" style="width:100%">')
        s.append('<thead><tr>')
        s.append('<th>Group</th><th>Product</th><th>Description</th>')
        s.append('</tr></thead>')
        last = ""
        for row in rows:
            if last == row[4]:
                s.append('<tr><td>&nbsp;</td>')
            else:
                s.append(f'<tr><td valign=top>{row[4]}</td>')
                last = row[4]
            s.append(f'<td valign=top><a href="product?id={row[0]}">')
            if row[3] == None:
                s.append(f'{row[1]}</a></td>')
            else:
                s.append(f'{row[3]}</a></td>')
            s.append(f'<td>{row[2]}</td></tr>')
        s.append("</table>")

        # Close the DB
        ldb.close()
        # print("Successful close of database")

    return render_template("base.html", content=s, em=EM)


@app.route("/about")
def about():
    # The about page content can be read from a file called about.html, one
    # directory above the current working directory.  If this file doesn't
    # exist, then some default text is provided.
    try:
        with open("../about.html", "r") as infile:
            s = infile.readlines()
    except Exception as e:
        s = ["<p><b>Open Source License Compliance Reporting System</b></p>",
             "<p>The contents of this page can be customized.  To do so,",
             "please create an HTML-formatted file named 'about.html' in",
             "the subdirectory above the oslcrs application,",
             "i.e. '../about.html'.</p>"]

    return render_template("base.html", content=s, em=EM)


@app.route("/product", methods=["GET"])
def product():
    s = []
    cdb = ldb.open(DBdatabase, DBhost, DBport, DBuser, DBpassword)
    if cdb == None:
        s.append("Bummer...the database isn't connected")

    else:
        id = request.args.get("id")
        # print("Got id as", id)

        # We'll need the product name as part of the page output
        sql = f"SELECT name FROM products WHERE id = {id};"
        try:
            cdb.execute(sql)
            row = cdb.fetchone()
            product_name = row[0]
        except Exception as e:
            s.append("<br>Failed to execute product name query")
            s.append("<br>Error: " + e.args[0])
            return render_template("base.html", content=s, em=EM)

        # Obtain releases for this product
        sql = f"SELECT releases.id, releases.version, releases.notes \
                FROM releases \
                JOIN products ON releases.product_id = products.id \
                WHERE products.id = {id} \
                ORDER BY releases.version;"
        try:
            cdb.execute(sql)
            rows = cdb.fetchall()
        except Exception as e:
            s.append("<br>Failed to execute releases list query")
            s.append("<br>Error: " + e.args[0])
            return render_template("base.html", content=s, em=EM)

        # Return the results
        s.append(f"<p><b>{product_name} releases:</b></p>")
        s.append('<table id="full" class="display" style="width:100%">')
        s.append('<thead><tr>')
        s.append('<th>Release</th><th>Report Notes</th>')
        s.append('</tr></thead>')
        for row in rows:
            s.append('<tr><td valign=top>')
            s.append(f'<a href="release?id={row[0]}">{row[1]}</a></td>')
            s.append(f'<td>{row[2]}</td></tr>')
        s.append("</table>")

        # Close the DB
        ldb.close()
        # print("Successful close of database")

    return render_template("base.html", content=s, em=EM)


@app.route("/release", methods=["GET"])
def release():
    s = []
    cdb = ldb.open(DBdatabase, DBhost, DBport, DBuser, DBpassword)
    if cdb == None:
        s.append("Bummer...the database isn't connected")

    else:
        id = request.args.get("id")
        # print("Got id as", id)

        # Get base product and release information
        sql = f"SELECT products.name, releases.version FROM products \
                JOIN releases ON releases.product_id = products.id \
                WHERE releases.id = {id};"
        try:
            cdb.execute(sql)
            row = cdb.fetchone()
            product = row[0]            # Product name
            release = row[1]            # Release name
        except Exception as e:
            s.append("<br>Failed to execute release id query")
            s.append("<br>Error: " + e.args[0])
            return render_template("base.html", content=s, em=EM)

        # How many containers are part of this release?
        sql = f"SELECT COUNT(DISTINCT release_containers.container_id) \
                FROM release_containers \
                JOIN releases ON release_containers.release_id = releases.id \
                WHERE releases.id = {id};"
        try:
            cdb.execute(sql)
            row = cdb.fetchone()
            num_containers = row[0]
        except Exception as e:
            s.append("<br>Failed to execute containers-release query")
            s.append("<br>Error: " + e.args[0])
            return render_template("base.html", content=s, em=EM)

        # How many packages are part of this release?
        sql = f"SELECT COUNT(DISTINCT package_nvr) FROM packages_per_release \
                WHERE release_id = {id};"
        try:
            cdb.execute(sql)
            row = cdb.fetchone()
            num_packages = row[0]
        except Exception as e:
            s.append("<br>Failed to execute packages-per-release query")
            s.append("<br>Error: " + e.args[0])
            return render_template("base.html", content=s, em=EM)

        # Are there packages in the product release manifest that have not
        # been analyzed?
        sql = f"SELECT COUNT(DISTINCT package_nvr) \
                FROM packages_per_release rp \
                WHERE release_id = {id} AND \
                      NOT EXISTS ( \
                          SELECT 1 FROM packages ap \
                          WHERE rp.package_nvr = ap.nvr);"
        try:
            cdb.execute(sql)
            row = cdb.fetchone()
            missing_packages = row[0]
        except Exception as e:
            s.append("<br>Failed to execute missing packages-per-release query")
            s.append("<br>Error: " + e.args[0])
            return render_template("base.html", content=s, em=EM)

        # Return the results
        s.append("<p><b>Release Details</b></p>")
        s.append('<table id="basic" class="display" style="width:100%">')
        s.append(f'<tr><td>Product:</td><td colspan=2>{product}</td></tr>')
        s.append(f'<tr><td>Release:</td><td colspan=2>{release}</td></tr>')
        s.append(f'<tr><td>Containers:</td><td colspan=2><a href="containers?release={id}">{num_containers}</a></td></tr>')
        s.append(f'<tr><td>Packages:</td><td colspan=2><a href="report?release={id}">{num_packages}</a></td></tr>')
        s.append(f'<tr><td>Missing Packages:</td><td colspan=2><a href="missing?release={id}">{missing_packages}</a></td></tr>')
        s.append("</table>")

        # Close the DB
        ldb.close()
        # print("Successful close of database")

    return render_template("base.html", content=s, em=EM)


@app.route("/containers", methods=["GET"])
def containers():
    s = []
    cdb = ldb.open(DBdatabase, DBhost, DBport, DBuser, DBpassword)
    if cdb == None:
        s.append("Bummer...the database isn't connected")

    else:
        id = request.args.get("release")
        # print("Got release as", id)

        # FIXME:
        # Containers need a way to indicate packages that are missing from
        # analysis.  Where do I add this?

        # Get base product and release information
        sql = f"SELECT products.name, releases.version FROM products \
                JOIN releases ON releases.product_id = products.id \
                WHERE releases.id = {id};"
        try:
            cdb.execute(sql)
            row = cdb.fetchone()
            product = row[0]            # Product name
            release = row[1]            # Release name
        except Exception as e:
            s.append("<br>Failed to execute release id query")
            s.append("<br>Error: " + e.args[0])
            return render_template("base.html", content=s, em=EM)

        # Grab a list of containers in this release
        sql = f"SELECT DISTINCT containers.id, containers.reference \
                FROM release_containers \
                JOIN containers ON containers.id = \
                                   release_containers.container_id \
                WHERE release_containers.release_id = {id} \
                ORDER BY containers.reference;"
        try:
            cdb.execute(sql)
            rows = cdb.fetchall()
        except Exception as e:
            s.append("<br>Failed to execute release containers query")
            s.append("<br>Error: " + e.args[0])
            return render_template("base.html", content=s, em=EM)

        # Return the results
        s.append(f"<h2>Product: {product}, release: {release}</h2>")
        s.append("<b>Container List</b><p>")
        for row in rows:
            s.append(f'<a href="report?container={row[0]}">{row[1]}</a><br>')

        # Close the DB
        ldb.close()
        # print("Successful close of database")

    return render_template("base.html", content=s, em=EM)


@app.route("/report", methods=["GET"])
def report():
    s = []
    cdb = ldb.open(DBdatabase, DBhost, DBport, DBuser, DBpassword)
    if cdb == None:
        s.append("Bummer...the database isn't connected")

    else:
        id = request.args.get("release")
        cont_id = request.args.get("container")
        columns = [ request.args.get(f"C{i}") for i in range(1,8) ]
        rep_format = request.args.get("format")
        # print("Got release as", id)
        # print("Got container as", cont_id)
        # print("Got columns as", columns)
        # print("Got format as", rep_format)
        if columns[0] == None:
            columns = [ "NVR", "S", "U", "L", "", "", "" ] # Default format
        if rep_format == None:
            rep_format = "html"         # Default format is html
        # Do we need to query for copyrights?
        copyrights = 0
        for field in columns:
            if field == "C":
                copyrights = 1
        # print("Copyrights is", copyrights)

        # Define possible column contents for error checking and operation
        cnames = dict()
        cnames['N'] = { "label": "Package Name", "jlabel": "PackageName" }
        cnames['V'] = { "label": "Version", "jlabel": "PackageVersion" }
        cnames['R'] = { "label": "Release", "jlabel": "PackageRelease" }
        cnames['NV'] = { "label": "Package Name-Version", "jlabel": "PackageNameVersion" }
        cnames['VR'] = { "label": "Version-Release", "jlabel": "PackageVersionRelease" }
        cnames['NVR'] = { "label": "Package NVR", "jlabel": "PackageName" }
        cnames['S'] = { "label": "Source Package NVR", "jlabel": "SourcePackage" }
        cnames['U'] = { "label": "Upstream URL", "jlabel": "URL" }
        cnames['L'] = { "label": "Summary License", "jlabel": "PackageDeclaredLicense" }
        cnames['C'] = { "label": "Package Copyright Notices", "jlabel": "PackageCopyrights" }
        cnames['E'] = { "label": "Edit Report", "jlabel": "EditReport" }

        # Insist that column definitions are present in the array
        for column in columns:
            if column != None and column != "" and column not in cnames:
                s.append(f"Error: {column} is not a valid column contents \
                           selection choice<br>")
                s.append("Valid choices are:<br>")
                s.append("<table border=1 cellpadding=100>")
                for cn in cnames:
                    s.append("<tr>")
                    s.append(f"<td>{cn}</td><td>{cnames[cn]['label']}</td>")
                    s.append("</tr>")
                s.append("</table>")
                s.append("<p> Use your browser's back button to try again.</p>")
                ldb.close()
                return render_template("base.html", content=s, em=EM)

        # Get base product and release information
        if cont_id == None:
            sql = f"SELECT products.name, releases.version FROM products \
                    JOIN releases ON releases.product_id = products.id \
                    WHERE releases.id = {id};"
        else:
            sql = f"SELECT reference FROM containers \
                    WHERE id = {cont_id};"
        try:
            cdb.execute(sql)
            row = cdb.fetchone()
            product = row[0]            # Product or container name
            if cont_id == None:
                release = row[1]        # Release name
        except Exception as e:
            s.append("<br>Failed to execute release id query")
            s.append("<br>Error: " + e.args[0])
            return render_template("base.html", content=s, em=EM)

        # Grab the summary license information for the packages in this release
        if cont_id == None:
            if copyrights == 0:         # Skip copyrights (expensive)
                sql = f"SELECT DISTINCT packages.id, packages.nvr, \
                                        sources.url, \
                                        packages.sum_license, \
                                        sources.name, \
                                        null, \
                                        overrides.id, overrides.url, \
                                        overrides.sum_license \
                        FROM packages_per_release \
                        JOIN packages ON packages_per_release.package_nvr = \
                                         packages.nvr \
                        JOIN sources ON packages.source_id = sources.id \
                        LEFT JOIN overrides ON packages.id = \
                                         overrides.package_id \
                        WHERE release_id = {id} AND \
                              packages.source = packages_per_release.source \
                        ORDER BY packages.nvr;"
            else:
                sql = f"SELECT DISTINCT packages.id, packages.nvr, \
                                        sources.url, \
                                        packages.sum_license, \
                                        sources.name, \
                                        package_copyrights.copyright, \
                                        overrides.id, overrides.url, \
                                        overrides.sum_license \
                        FROM packages_per_release \
                        JOIN packages ON packages_per_release.package_nvr = \
                                         packages.nvr \
                        JOIN sources ON packages.source_id = sources.id \
                        LEFT JOIN package_copyrights ON packages.id = \
                                         package_copyrights.package_id \
                        LEFT JOIN overrides ON packages.id = \
                                         overrides.package_id \
                        WHERE release_id = {id}  AND \
                              packages.source = packages_per_release.source \
                        ORDER BY packages.nvr;"
        else:
            if copyrights == 0:         # Skip copyrights (expensive)
                sql = f"SELECT DISTINCT packages.id, packages.nvr, \
                                        sources.url, \
                                        packages.sum_license, \
                                        sources.name, \
                                        null, \
                                        overrides.id, overrides.url, \
                                        overrides.sum_license \
                        FROM container_packages \
                        JOIN packages ON container_packages.package_nvr = \
                                         packages.nvr \
                        JOIN sources ON packages.source_id = sources.id \
                        LEFT JOIN overrides ON packages.id = \
                                         overrides.package_id \
                        WHERE container_packages.container_id = {cont_id} AND \
                              packages.source = container_packages.source \
                        ORDER BY packages.nvr;"
            else:
                sql = f"SELECT DISTINCT packages.id, packages.nvr, \
                                        sources.url, \
                                        packages.sum_license, \
                                        sources.name, \
                                        package_copyrights.copyright, \
                                        overrides.id, overrides.url, \
                                        overrides.sum_license \
                        FROM container_packages \
                        JOIN packages ON container_packages.package_nvr = \
                                         packages.nvr \
                        JOIN sources ON packages.source_id = sources.id \
                        LEFT JOIN package_copyrights ON packages.id = \
                                         package_copyrights.package_id \
                        LEFT JOIN overrides ON packages.id = \
                                         overrides.package_id \
                        WHERE container_packages.container_id = {cont_id} AND \
                              packages.source = container_packages.source \
                        ORDER BY packages.nvr;"
        try:
            cdb.execute(sql)
            rows = cdb.fetchall()
        except Exception as e:
            s.append("<br>Failed to execute report query")
            s.append("<br>Error: " + e.args[0])
            return render_template("base.html", content=s, em=EM)

        # Return the results
        # Note that we collect a json data structure, in case it's being
        # requested.  This is a bit wasteful, but makes the code easier.
        retjson = dict()
        
        # Report header

        # Report option selection
        if cont_id == None:
            s.append(f"<h2>Product: {product} &nbsp;&nbsp;&nbsp;&nbsp;")
            s.append(f"Release: {release}</h2>")
            s.append('<p>Source code licenses: ')
            s.append(f'<a href="licenses?rel_id={id}">All</a> or ')
            s.append(f'<a href="licenses?rel_id={id}&unapp=1">Unapproved</a>')
            s.append(' (warning: slow queries)</p>')
            s.append('<p>Special report options:')
            s.append(f'<a href="source_mapping?release={id}">')
            s.append('source package mapping</a>')
            s.append('or')
            s.append(f'<a href="report?{urlencode(request.args)}&format=json">')
            s.append('json format data only</a>')
            s.append('</p>')
        else:
            s.append(f"<h2>Container: {product}</h2>")
            s.append('<p>Source code licenses: ')
            s.append(f'<a href="licenses?cont_id={cont_id}">All</a> or ')
            s.append(f'<a href="licenses?cont_id={cont_id}&unapp=1">')
            s.append('Unapproved</a> (warning: slow queries)</p>')
            s.append('<p>Special report options:')
            s.append(f'<a href="source_mapping?container={cont_id}">')
            s.append('source package mapping</a>')
            s.append('or')
            s.append(f'<a href="report?{urlencode(request.args)}&format=json">')
            s.append('json format data only</a>')
            s.append('</p>')

        # Report column definition
        s.append('<p><form>')
        if cont_id == None:
            s.append(f'<input type=hidden name=release value={id}>')
        else:
            s.append(f'<input type=hidden name=container value={cont_id}>')
        s.append('Report columns: ')
        s.append('&nbsp;&nbsp;&nbsp;')
        # s.append('<label for="C1">C1</label>')
        for i in range(1,8):
            s.append(f'<input type=text name=C{i} maxlength=3 size=3 \
                       value={columns[i-1]}>')
        s.append('&nbsp;&nbsp;&nbsp;')
        s.append('<input type=submit value=Update>')
        s.append('&nbsp;&nbsp;&nbsp;')
        s.append('(warning: copyrights are slow)')
        s.append('</form></p>')

        # Report column headings
        s.append('<table id="full" class="display" style="width:100%">')
        s.append('<thead><tr>')
        for column in columns:
            if column != None and column != "":
                s.append(f"<th>{cnames[column]['label']}</th>")
        s.append('</tr></thead>')
        for row in rows:
            # First, parse the potential data that might be displayed.  The
            # first version of this considered only RPM packages.  Then, we
            # encountered the tarballs present in source containers.  You'll
            # see some special case code below for those cases, but it would
            # be good to rethink and redesign all of this.
            data = dict()
            data['PID'] = row[0]
            data['NVR'] = row[1]
            data['U'] = row[2]
            data['L'] = row[3]
            data['S'] = row[4]
            data['C'] = row[5]
            # Parse apart the NVR.  Special-casing the tarball names for now.
            if data['NVR'][-7:] == ".tar.gz":
                data['N'] = data['NVR']
                data['V'] = ""
                data['R'] = ""
                data['NV'] = data['NVR']
                data['VR'] = ""
            else:
                parts = data['NVR'].split('-')
                data['N'] = '-'.join(parts[0:-2])
                data['V'] = parts[-2]
                data['R'] = parts[-1]
                data['NV'] = '-'.join(parts[0:-1])
                data['VR'] = '-'.join(parts[-2:])
            # The option to edit this row is special
            data['E'] = f'<a href="override?id={data["PID"]}">EDIT</a>'
            # Do we have any override values?
            if row[6] is not None:
                data['U'] = row[7]
                data['L'] = row[8]
            # This is only for the json data structure
            nvr = row[1]                # This shorthand helps the json code
            retjson[nvr] = dict()
            # This is the new row of data
            s.append('<tr>')
            # Loop over the requested columns
            for c in range(7):
                # Leave loop once we get to an empty column
                if columns[c] == None or columns[c] == "":
                    break
                # Avoid problems with empty data
                if data[columns[c]] == None:
                    s.append('<td>&nbsp;</td>')
                    retjson[nvr][cnames[columns[c]]['jlabel']] = ""
                # First column (package ID) needs to be clickable
                elif c == 0:
                    s.append(f"<td><a href=\"package?id={data['PID']}\">{data[columns[c]]}</a></td>")
                    retjson[nvr][cnames[columns[c]]['jlabel']] = data[columns[c]]
                # URLs need to be clickable
                elif columns[c] == "U":
                    s.append(f"<td><a href=\"{data['U']}\">{data['U']}</a></td>")
                    retjson[nvr][cnames[columns[c]]['jlabel']] = data[columns[c]]
                # Copyrights need <pre>
                elif columns[c] == "C":
                    s.append(f"<td><pre>{data['C']}</pre></td>")
                    retjson[nvr][cnames[columns[c]]['jlabel']] = data[columns[c]]
                # All other columns are more-or-less normal
                else:
                    s.append(f"<td>{data[columns[c]]}</td>")
                    retjson[nvr][cnames[columns[c]]['jlabel']] = data[columns[c]]
            s.append('</tr>')
        s.append("</table>")

        # Close the DB
        ldb.close()
        # print("Successful close of database")

    # In the json report format, return the json structure we built
    if rep_format == "json":
        return jsonify(retjson)

    # Otherwise, return the web page we built
    return render_template("base.html", content=s, em=EM)


@app.route("/paths", methods=["GET"])
def paths():
    s = []
    cdb = ldb.open(DBdatabase, DBhost, DBport, DBuser, DBpassword)
    if cdb == None:
        s.append("Bummer...the database isn't connected")

    else:
        id = request.args.get("pkg_id")
        # print("Got pkg_id as", id)

        # Get base package information
        sql = f"SELECT packages.nvr, sources.url, \
                     packages.sum_license \
                FROM packages \
                JOIN sources on packages.source_id = sources.id \
                WHERE packages.id = {id};"
        try:
            cdb.execute(sql)
            row = cdb.fetchone()
            # print(f"Trying to gather row info from {len(row)} list")
            pkg_nvr = row[0]            # Package nvr
            pkg_url = row[1]            # Package upstream URL
            pkg_sum_lic = row[2]        # Package summary license
        except Exception as e:
            s.append("<br>Failed to execute package info query")
            s.append("<br>Error: " + e.args[0])
            return render_template("base.html", content=s, em=EM)

        # Collect the file paths information for this package
        sql = f"SELECT DISTINCT files.swh, paths.path \
                FROM files \
                JOIN paths on files.id = paths.file_id \
                JOIN sources on paths.source_id = sources.id \
                JOIN packages on packages.source_id = sources.id \
                WHERE packages.id = {id} \
                ORDER BY path;"
        try:
            cdb.execute(sql)
            rows = cdb.fetchall()
        except Exception as e:
            s.append("<br>Failed to execute package file paths query")
            s.append("<br>Error: " + e.args[0])
            return render_template("base.html", content=s, em=EM)

        # Return the results
        s.append(f"<h2>Package: {pkg_nvr}</h2>")
        s.append("<br>Upstream URL: ")
        s.append(f'<a href="{pkg_url}">{pkg_url}</a>')
        s.append(f"<br>Package Summary License: {pkg_sum_lic}")
        s.append("<h4>&nbsp;</h4>")
        s.append('<table id="export_srch" class="display" style="width:100%">')
        s.append('<thead><tr>')
        s.append('<th>Source File Path</th>')
        s.append('</tr></thead>')
        for row in rows:
            # row[0] is the SWH UUID
            # row[1] is the file path
            # FIXME: This currently points to the external SWH, not our
            # internal version.
            swhurl = f"https://archive.softwareheritage.org/{row[0]}"
            s.append(f'<tr><td><a href="{swhurl}">{row[1]}</a></td></tr>')
        s.append("</table>")

        # Close the DB
        ldb.close()
        # print("Successful close of database")

    return render_template("base.html", content=s, em=EM)


@app.route("/summary_license_files", methods=["GET"])
def summary_license_files():
    s = []
    cdb = ldb.open(DBdatabase, DBhost, DBport, DBuser, DBpassword)
    if cdb == None:
        s.append("Bummer...the database isn't connected")

    else:
        id = request.args.get("pkg_id")
        # print("Got pkg_id as", id)

        # Get base package information
        sql = f"SELECT packages.nvr, sources.url, \
                     packages.sum_license \
                FROM packages \
                JOIN sources on packages.source_id = sources.id \
                WHERE packages.id = {id};"
        try:
            cdb.execute(sql)
            row = cdb.fetchone()
            # print(f"Trying to gather row info from {len(row)} list")
            pkg_nvr = row[0]            # Package nvr
            pkg_url = row[1]            # Package upstream URL
            pkg_sum_lic = row[2]        # Package summary license
        except Exception as e:
            s.append("<br>Failed to execute package info query")
            s.append("<br>Error: " + e.args[0])
            return render_template("base.html", content=s, em=EM)

        # Collect the file paths information for this package
        sql = f"SELECT DISTINCT files.swh, paths.path, \
                                license_detects.lic_name, \
                                license_detects.score, \
                                license_detects.start_line, \
                                license_detects.end_line \
                FROM files \
                JOIN paths on files.id = paths.file_id \
                JOIN sources on paths.source_id = sources.id \
                JOIN packages on packages.source_id = sources.id \
                JOIN license_detects on files.id = license_detects.file_id \
                WHERE packages.id = {id} and ( "
        first = True
        for term in summary_license_file_patterns:
            if not first:
                sql += "or "
            sql += f"paths.path ~ '{term}' "
            first = False
        sql = sql + ") ORDER BY path;"
        try:
            cdb.execute(sql)
            rows = cdb.fetchall()
        except Exception as e:
            s.append("<br>Failed to execute package file paths query")
            s.append("<br>Error: " + e.args[0])
            return render_template("base.html", content=s, em=EM)

        # Return the results
        s.append(f"<h2>Package: {pkg_nvr}</h2>")
        s.append("<br>Upstream URL: ")
        s.append(f'<a href="{pkg_url}">{pkg_url}</a>')
        s.append(f"<br>Package Summary License: {pkg_sum_lic}")
        s.append("<h4>&nbsp;</h4>")
        s.append('<table id="export_srch" class="display" style="width:100%">')
        s.append('<thead><tr>')
        s.append('<th>Score</th>')
        s.append('<th>License Name</th>')
        s.append('<th>License File Paths</th>')
        s.append('</tr></thead>')
        for row in rows:
            # row[0] is the SWH UUID
            # row[1] is the file path
            # row[2] is the license name
            # FIXME: This currently points to the external SWH, not our
            # internal version.
            if row[4] == row[5]:            # Single line needs different URL
                swhurl = f"https://archive.softwareheritage.org/{row[0]}" + \
                         f";lines={row[4]}"
            else:
                swhurl = f"https://archive.softwareheritage.org/{row[0]}" + \
                         f";lines={row[4]}-{row[5]}"
            whereurl = f"where_lic?pkg_id={id}&lic={row[2]}"
            s.append(f'<tr><td>{row[3]}</td>')
            s.append(f'<td><a href="{whereurl}">{row[2]}</a></td>')
            s.append(f'<td><a href="{swhurl}">{row[1]}</a></td></tr>')
        s.append("</table>")

        # Close the DB
        ldb.close()
        # print("Successful close of database")

    return render_template("base.html", content=s, em=EM)


@app.route("/missing", methods=["GET"])
def missing():
    s = []
    cdb = ldb.open(DBdatabase, DBhost, DBport, DBuser, DBpassword)
    if cdb == None:
        s.append("Bummer...the database isn't connected")

    else:
        id = request.args.get("release")
        cont_id = request.args.get("container")
        rep_format = request.args.get("format")
        # print("Got release as", id)
        # print("Got container as", cont_id)
        # print("Got format as", rep_format)
        if rep_format == None:
            rep_format = "0"            # Default format

        # Get base product and release information
        if cont_id == None:
            sql = f"SELECT products.name, releases.version FROM products \
                    JOIN releases ON releases.product_id = products.id \
                    WHERE releases.id = {id};"
        else:
            sql = f"SELECT reference FROM containers \
                    WHERE id = {cont_id};"
        try:
            cdb.execute(sql)
            row = cdb.fetchone()
            product = row[0]            # Product or container name
            if cont_id == None:
                release = row[1]        # Release name
        except Exception as e:
            s.append("<br>Failed to execute release id query")
            s.append("<br>Error: " + e.args[0])
            return render_template("base.html", content=s, em=EM)

        # Grab a list of packages that are manifested as part of this release
        # or container but have not been analyzed.
        if cont_id == None:
            sql = f"SELECT DISTINCT package_nvr \
                    FROM packages_per_release rp \
                    WHERE release_id = {id} AND \
                          NOT EXISTS ( \
                              SELECT 1 FROM packages ap \
                              WHERE rp.package_nvr = ap.nvr AND \
                                    rp.source = ap.source) \
                    ORDER BY package_nvr;"
        else:
            # FIXME: This code path doesn't have a UI...need to add something
            sql = f"SELECT DISTINCT rp.package_nvr \
                    FROM containers \
                    JOIN container_packages rp ON containers.id = \
                                rp.container_id \
                    WHERE containers.id = {cont_id} AND \
                          NOT EXISTS ( \
                              SELECT 1 FROM packages ap \
                              WHERE rp.package_nvr = ap.nvr AND \
                                    rp.source = ap.source) \
                    ORDER BY package_nvr;"
        try:
            cdb.execute(sql)
            rows = cdb.fetchall()
        except Exception as e:
            s.append("<br>Failed to execute missing packages report query")
            s.append("<br>Error: " + e.args[0])
            return render_template("base.html", content=s, em=EM)

        # Return the results
        # This is special code, in case the user wants a json-formatted file
        # of the results
        if rep_format == "json":
            # Collect the data in a single dictionary
            # The "rows" structure is a reasonable thing to return, but there
            # are some extra columns and the data is not labled.  I'll waste
            # the memory to create a new structure that better suits a user
            # that wants to download this data.
            # return jsonify(retjson)
            retarray = []
            for row in rows:
                # Aggregate the data...FIXME probably a more Pythonic way
                retarray.append(row[0]) # Otherwise, each element is an array
            return Response(json.dumps(retarray), mimetype='application/json')
            s.append("<br>The json file has been offered to the browser")
            return render_template("base.html", content=s, em=EM)
        if cont_id == None:
            s.append(f"<h2>Product: {product} &nbsp;&nbsp;&nbsp;&nbsp;")
            s.append(f"Release: {release}</h2>")
            s.append("<h2>Missing Packages Report</h2>")
            if rep_format == "0":
                s.append('<p>Special report download option:')
                s.append(f'<a href="missing?release={id}&format=json">')
                s.append('json format data only</a>')
                s.append('</p>')
        else:
            s.append(f"<h2>Container: {product}</h2>")
            s.append("<h2>Missing Packages Report</h2>")
            if rep_format == "0":
                s.append('<p>Special report download option:')
                s.append(f'<a href="missing?container={cont_id}&format=json">')
                s.append('json format data only</a>')
                s.append('</p>')
        s.append('<table id="full" class="display" style="width:100%">')
        s.append('<thead><tr>')
        s.append('<th>Package N-V-R</th>')
        s.append('</tr></thead>')
        for row in rows:
            s.append('<tr>')
            s.append(f'<td>{row[0]}</td>')
            s.append('</tr>')
        s.append("</table>")

        # Close the DB
        ldb.close()
        # print("Successful close of database")

    return render_template("base.html", content=s, em=EM)


@app.route("/source_mapping", methods=["GET"])
def source_mapping():
    s = []
    cdb = ldb.open(DBdatabase, DBhost, DBport, DBuser, DBpassword)
    if cdb == None:
        s.append("Bummer...the database isn't connected")

    else:
        id = request.args.get("release")
        cont_id = request.args.get("container")
        rep_format = request.args.get("format")
        # print("Got release as", id)
        # print("Got container as", cont_id)
        if rep_format == None:
            rep_format = "0"            # Default format

        # Get base product and release information
        if cont_id == None:
            sql = f"SELECT products.name, releases.version FROM products \
                    JOIN releases ON releases.product_id = products.id \
                    WHERE releases.id = {id};"
        else:
            sql = f"SELECT reference FROM containers \
                    WHERE id = {cont_id};"
        try:
            cdb.execute(sql)
            row = cdb.fetchone()
            product = row[0]            # Product or container name
            if cont_id == None:
                release = row[1]        # Release name
        except Exception as e:
            s.append("<br>Failed to execute release id query")
            s.append("<br>Error: " + e.args[0])
            return render_template("base.html", content=s, em=EM)

        # Grab the summary license information for the packages in this release
        if cont_id == None:
            sql = f"SELECT DISTINCT packages.id, packages.nvr, \
                                    sources.name \
                    FROM packages_per_release \
                    JOIN packages ON packages_per_release.package_nvr = \
                                     packages.nvr \
                    JOIN sources ON packages.source_id = sources.id \
                    WHERE release_id = {id} AND \
                          packages.source = packages_per_release.source \
                    ORDER BY packages.nvr;"
        else:
            sql = f"SELECT DISTINCT packages.id, packages.nvr, \
                                    sources.name \
                    FROM container_packages \
                    JOIN packages ON container_packages.package_nvr = \
                                     packages.nvr \
                    JOIN sources ON packages.source_id = sources.id \
                    WHERE container_packages.container_id = {cont_id} AND \
                          packages.source = container_packages.source \
                    ORDER BY packages.nvr;"
        try:
            cdb.execute(sql)
            rows = cdb.fetchall()
        except Exception as e:
            s.append("<br>Failed to execute source_mapping query")
            s.append("<br>Error: " + e.args[0])
            return render_template("base.html", content=s, em=EM)

        # Return the results
        # This is special code, in case the user wants a json-formatted file
        # of the results
        if rep_format == "json":
            # Collect the data in a single dictionary
            # The "rows" structure is a reasonable thing to return, but there
            # are some extra columns and the data is not labled.  I'll waste
            # the memory to create a new structure that better suits a user
            # that wants to download this data.
            retjson = dict()
            for row in rows:
                # Aggregate the data
                nvr = row[1]
                retjson[nvr] = ({"SourcePackage": row[2]})
            return jsonify(retjson)
            s.append("<br>The json file has been offered to the browser")
            return render_template("base.html", content=s, em=EM)
        if cont_id == None:
            s.append(f"<h2>Product: {product} &nbsp;&nbsp;&nbsp;&nbsp;")
            s.append(f"Release: {release}</h2>")
            s.append('<p>Source code licenses: ')
            s.append(f'<a href="licenses?rel_id={id}">All</a> ')
            s.append(f'<a href="licenses?rel_id={id}&unapp=1">Unapproved</a>')
            s.append(' (warning: slow queries)</p>')
            if rep_format == "0":
                s.append('<p>Special report options:')
                s.append(f' <a href="source_mapping?release={id}&format=json">')
                s.append('json format data only</a>')
                s.append('</p>')
        else:
            s.append(f"<h2>Container: {product}</h2>")
            s.append('<p>Source code licenses: ')
            s.append(f'<a href="licenses?cont_id={cont_id}">All</a> ')
            s.append(f'<a href="licenses?cont_id={cont_id}&unapp=1">')
            s.append('Unapproved</a> (warning: slow queries)</p>')
            if rep_format == "0":
                s.append('<p>Special report options:')
                s.append(f' <a href="source_mapping?container={cont_id}')
                s.append('&format=json">')
                s.append('json format data only</a>')
                s.append('</p>')
        s.append('<table id="full" class="display" style="width:100%">')
        s.append('<thead><tr>')
        s.append('<th>Package N-V-R</th>')
        s.append('<th>Source Package</th>')
        s.append('</tr></thead>')
        for row in rows:
            s.append('<tr>')
            # N-V-R needs to be clickable
            s.append(f'<td><a href="package?id={row[0]}">{row[1]}</a></td>')
            s.append(f'<td>{row[2]}</td>')
            s.append('</tr>')
        s.append("</table>")

        # Close the DB
        ldb.close()
        # print("Successful close of database")

    return render_template("base.html", content=s, em=EM)


@app.route("/override", methods=["GET"])
def override():
    s = []
    cdb = ldb.open(DBdatabase, DBhost, DBport, DBuser, DBpassword)
    if cdb == None:
        s.append("Bummer...the database isn't connected")

    else:
        id = request.args.get("id")
        # print("Got id as", id)

        # This page will be called when a user saves edited values, and when
        # that happens, those values will become extra page GET parameters.
        # Do we have any of those?
        p_oid = request.args.get("oid")
        p_responsible = request.args.get("responsible")
        if p_responsible != None:
            p_responsible = p_responsible.strip()
        p_url = request.args.get("url")
        if p_url != None:
            p_url = p_url.strip()
        p_sum_lic = request.args.get("sum_lic")
        if p_sum_lic != None:
            p_sum_lic = " ".join(p_sum_lic.split())
        p_action = request.args.get("action")
        # print("Parameters:", p_action, p_oid, p_responsible, p_url, p_sum_lic)

        # We need a dictionary of values for database inserts
        sp = {
                "id": id,
                "responsible": p_responsible,
                "url": p_url,
                "sum_lic": p_sum_lic
             }

        # Before doing anything else, process any database updates based on
        # the extra GET parameters captured above.

        # This is error checking, because we want to record the person doing
        # the edit.
        if p_action == "Save" and \
           (p_responsible == None or len(p_responsible) < 2):
            s.append("<h4><font color=red>")
            s.append("Error: You must include your name to save any changes")
            s.append("</font></h4>")
            p_action = None             # Ignore the request

        # This is for deleting the override record
        if p_action == "Delete" and p_oid != "None":
            sql = f"DELETE from overrides \
                    WHERE id = {p_oid};"
            try:
                cdb.execute(sql)
                ldb.commit()
                print("Deleted overrides ID", p_oid)
            except Exception as e:
                ldb.rollback()
                s.append("<br>Failed to delete overrides table record")
                s.append("<br>Error: " + e.args[0])
                return render_template("base.html", content=s, em=EM)

        # This is for inserting a new overrides record
        if p_action == "Save" and p_oid == "None":
            sql = "INSERT INTO overrides \
                          (package_id, url, sum_license, responsible) \
                   VALUES (%(id)s, %(url)s, %(sum_lic)s, \
                           %(responsible)s) \
                   ON CONFLICT (package_id) DO UPDATE \
                       SET (url, sum_license, responsible) = \
                           (%(url)s, %(sum_lic)s, %(responsible)s);"
            try:
                cdb.execute(sql, sp)
                ldb.commit()
                print("Inserted new overrides record")
            except Exception as e:
                ldb.rollback()
                s.append("<br>Failed to insert overrides table record")
                s.append("<br>Error: " + e.args[0])
                return render_template("base.html", content=s, em=EM)

        # This is for updating an existing overrides record
        if p_action == "Save" and p_oid != "None":
            sql = f"UPDATE overrides \
                    SET (url, sum_license, responsible, timestamp) = \
                        (%(url)s, %(sum_lic)s, %(responsible)s, now()) \
                    WHERE id = {p_oid};"
            try:
                cdb.execute(sql, sp)
                ldb.commit()
                print("Updated overrides record", p_oid)
            except Exception as e:
                ldb.rollback()
                s.append("<br>Failed to update overrides record")
                s.append("<br>Error: " + e.args[0])
                return render_template("base.html", content=s, em=EM)

        # Get base package information
        sql = f"SELECT packages.nvr, sources.url, \
                     packages.sum_license, \
                     overrides.id, overrides.url, overrides.sum_license, \
                     overrides.timestamp, overrides.responsible \
                FROM packages \
                JOIN sources on packages.source_id = sources.id \
                LEFT JOIN overrides ON \
                     overrides.package_id = packages.id \
                WHERE packages.id = {id};"
        try:
            cdb.execute(sql)
            row = cdb.fetchone()
            # print(f"Trying to gather row info from {len(row)} list")
            pkg_nvr = row[0]            # Package nvr
            pkg_url = row[1]            # Package upstream URL
            pkg_sum_lic = row[2]        # Package summary license
            o_id = row[3]               # Override table ID
            o_url = row[4]              # Override URL value
            o_lic = row[5]              # Override summary license
            o_time = row[6]             # Override last modified
            o_resp = row[7]             # Override responsible party
        except Exception as e:
            s.append("<br>Failed package info query")
            s.append("<br>Error: " + e.args[0])
            return render_template("base.html", content=s, em=EM)

        # Obtain the computed summary license value
        c_sum_lic = summary_licenses(id, cdb)

        # Set reasonable default values for this form
        if p_responsible == None:
            p_responsible = ""
        if o_url == None:
            o_url = pkg_url
        if o_lic == None:
            o_lic = pkg_sum_lic
        
        # Display the editing page.  First, the header warning and instructions.
        s.append("<strong>Warning: This page is NOT intended for general use. \
                  </strong><br>")
        s.append("<p>This page is able to override both the upstream URL and ")
        s.append("summary license fields of any single package. The ")
        s.append("modification applies to one specific NVR, so it will not ")
        s.append("affect other versions of the package, but it will affect ")
        s.append("any report that makes use of this specific version of this ")
        s.append("package.</p> ")
        s.append("<p>The override is kept in a separate data structure, so ")
        s.append("the original package data is still available.  It is only ")
        s.append('masked by these override values. The "Delete" button below ')
        s.append("will remove the override for this package NVR, allowing the ")
        s.append("original package values to be displayed in any report.</p>")
        s.append("<p>Please do not use this page without specific permission ")
        s.append("and instruction.  Inadvertent use will produce errors in ")
        s.append("reports being provided to important customers.</p> ")

        # This is the package information.
        s.append(f"<h4>Package: {pkg_nvr}</h4>")
        s.append("<p><strong>Original Upstream URL:</strong> ")
        s.append(f'<a href="{pkg_url}">{pkg_url}</a><br>')
        s.append("<strong>Original Summary License:</strong> ")
        s.append(f"{pkg_sum_lic}<br>")
        s.append("<strong>Computed Summary License:</strong> ")
        s.append(f"{c_sum_lic}</p>")

        # These are some automatic editing controls
        s.append('<script>')
        s.append('  function update(choice) {')
        s.append('    switch(choice) {')
        s.append('    case "o_url":')
        s.append(f'      document.getElementById("url").value = \
                         "{pkg_url}"; break;')
        s.append('    case "o_sum":')
        s.append(f'      document.getElementById("sum_lic").value = \
                         "{pkg_sum_lic}"; break;')
        s.append('    case "c_sum":')
        s.append(f'      document.getElementById("sum_lic").value = \
                         "{c_sum_lic}"; break;')
        s.append('    }')
        s.append('  }')
        s.append('</script>')
        s.append('<form>')
        s.append('<button type=button onclick=update("o_url") \
                  >Fill Original URL</button>')
        s.append('<button type=button onclick=update("o_sum") \
                  >Fill Original License</button>')
        s.append('<button type=button onclick=update("c_sum") \
                  >Fill Computed License</button>')
        s.append('</form>')

        # This supports saving the user's name, so it doesn't need to be
        # entered every time
        s.append('<script>')
        s.append('  function save_user() {')
        s.append('    document.cookie = "username=" + \
                      document.getElementById("responsible").value;')
        s.append('  }')
        s.append('  function set_user() {')
        s.append("    let cookies = decodeURIComponent(document.cookie).split(';');")
        s.append('    for (let i = 0; i < cookies.length; i++) {')
        s.append('      let c = cookies[i];')
        s.append("      while (c.charAt(0) == ' ') {")
        s.append('        c = c.substring(1);')
        s.append('      }')
        s.append('      if (c.indexOf("username") == 0) {')
        s.append('        document.getElementById("responsible").value = \
                          c.substring("username=".length, c.length);')
        s.append('      }')
        s.append('    }')
        s.append('  }')
        s.append('</script>')

        # This is where people can make changes/edits
        s.append('<p><form>')
        s.append(f'<input type=hidden name=id value={id}>')
        s.append(f'<input type=hidden name=oid value={o_id}>')
        s.append('<p><strong>Your Name</strong> (required): ')
        s.append('<br>')
        s.append(f'<input type=text name=responsible id=responsible \
                   maxlength=128 size=92 value="{p_responsible}" \
                   onChange=save_user()></p>')
        s.append('<p><strong>Upstream URL:</strong> ')
        s.append(f'<input type=text name=url id=url \
                   maxlength=512 size=92 value={o_url}></p>')
        s.append('<p><strong>Summary License:</strong> ')
        s.append(f'<textarea name=sum_lic id=sum_lic maxlength=4096 \
                   rows=10 cols=91>{o_lic}</textarea></p>')
        s.append('<input type=submit name=action value=Save>')
        s.append('<input type=reset value=Reset>')
        s.append('<input type=submit name=action value=Delete>')
        s.append('</form></p>')

        # And this tries to set the user's name once the page loads
        s.append('<script>')
        s.append('  window.onload = set_user();')
        s.append('</script>')

        # Close the DB
        ldb.close()
        # print("Successful close of database")

    return render_template("base.html", content=s, em=EM)


@app.route("/package", methods=["GET"])
def package():
    s = []
    cdb = ldb.open(DBdatabase, DBhost, DBport, DBuser, DBpassword)
    if cdb == None:
        s.append("Bummer...the database isn't connected")

    else:
        id = request.args.get("id")
        # print("Got id as", id)

        # Get base package information
        sql = f"SELECT packages.nvr, sources.url, \
                     packages.sum_license, \
                     package_copyrights.copyright \
                FROM packages \
                JOIN sources on packages.source_id = sources.id \
                LEFT JOIN package_copyrights ON \
                     package_copyrights.package_id = packages.id \
                WHERE packages.id = {id};"
        try:
            cdb.execute(sql)
            row = cdb.fetchone()
            # print(f"Trying to gather row info from {len(row)} list")
            pkg_nvr = row[0]            # Package nvr
            pkg_url = row[1]            # Package upstream URL
            pkg_sum_lic = row[2]        # Package summary license
            pkg_copyrights = row[3]     # Package collected copyrights
        except Exception as e:
            s.append("<br>Failed to package info query")
            s.append("<br>Error: " + e.args[0])
            return render_template("base.html", content=s, em=EM)

        # We're experimenting with this computed value; display it here
        c_sum_lic = summary_licenses(id, cdb)

        # Collect the source license information for this package
        sql = f"SELECT DISTINCT lic_name, score \
                FROM license_detects \
                JOIN paths on license_detects.file_id = paths.file_id \
                JOIN sources on paths.source_id = sources.id \
                JOIN packages on packages.source_id = sources.id \
                WHERE packages.id = {id} \
                ORDER BY lic_name ASC, score DESC;"
        try:
            cdb.execute(sql)
            rows = cdb.fetchall()
        except Exception as e:
            s.append("<br>Failed to execute package license query")
            s.append("<br>Error: " + e.args[0])
            return render_template("base.html", content=s, em=EM)

        # Return the results
        s.append(f"<h2>Package: {pkg_nvr}</h2>")
        s.append("<br>Upstream URL: ")
        s.append(f'<a href="{pkg_url}">{pkg_url}</a>')
        s.append(f"<br>Package Summary License: {pkg_sum_lic}")
        s.append(f"<br>Package Computed Summary License: ")
        s.append(f'<a href="summary_license_files?pkg_id={id}">{c_sum_lic}</a>')
        s.append("<br>Package Source Licenses: &nbsp;")
        s.append(f'<a href="licenses?pkg_id={id}">All</a>&nbsp;&nbsp;')
        s.append(f'<a href="licenses?pkg_id={id}&unapp=1">Unapproved</a>')
        s.append(f'<br>Package <a href="paths?pkg_id={id}">Source Files</a>')
        s.append("<h2>&nbsp;</h2>")
        s.append('<table id="export" class="display" style="width:100%">')
        s.append('<thead><tr>')
        s.append('<th>Package Summary Copyright Statements</th>')
        s.append('</tr></thead>')
        s.append(f'<tr><td><pre>{pkg_copyrights}</pre></td></tr>')
        s.append("</table>")
        s.append("<h2>&nbsp;</h2>")
        s.append('<table id="full" class="display" style="width:100%">')
        s.append('<thead><tr>')
        s.append('<th>Source Code Licenses</th>')
        s.append('<th>Score</th>')
        s.append('</tr></thead>')
        last = ""
        for row in rows:
            if last != row[0]:          # Skip dup license rows w/ diff scores
                s.append('<tr>')
                for num, item in enumerate(row):
                    # First column is license name
                    if num == 0:

                        parms = urlencode({'pkg_id':id, 'lic':item},
                                          quote_via=quote_plus)
                        s.append(f'<td><a href="where_lic?{parms}">')
                        s.append(f'{item}</a></td>')
                        last = item
                    else:
                        s.append(f'<td>{item}</td>')
                s.append('</tr>')
        s.append("</table>")

        # Close the DB
        ldb.close()
        # print("Successful close of database")

    return render_template("base.html", content=s, em=EM)


@app.route("/licenses", methods=["GET"])
def licenses():
    s = []
    cdb = ldb.open(DBdatabase, DBhost, DBport, DBuser, DBpassword)
    if cdb == None:
        s.append("Bummer...the database isn't connected")

    else:
        package_id = request.args.get("pkg_id")
        cont_id = request.args.get("cont_id")
        release_id = request.args.get("rel_id")
        product_id = request.args.get("prod_id")
        unapproved = request.args.get("unapp")
        # print("Got pkg_id as", package_id)
        # print("Got cont_id as", cont_id)
        # print("Got rel_id as", release_id)
        # print("Got prod_id as", product_id)
        # print("Got unapproved as", unapproved)


        # This is the top of any page
        if unapproved == "1":
            s.append(f"<h2>Unapproved Source Code Licenses</h2>")
        else:
            s.append(f"<h2>Source Code Licenses</h2>")


        if cont_id != None:
            # This section handles licenses on a per-container basis
            sql = f"SELECT reference FROM containers \
                    WHERE id = {cont_id};"
            try:
                cdb.execute(sql)
                row = cdb.fetchone()
                s.append(f'<p><b>Container: {row[0]}</b></p>')
            except Exception as e:
                s.append("<br>Failed to execute container info query")
                s.append("<br>Error: " + e.args[0])
                return render_template("base.html", content=s, em=EM)
            # Collect licenses found in this container
            sql = f"SELECT DISTINCT COUNT(license_detects.file_id), \
                                    license_detects.lic_name, \
                                    MAX(license_detects.score), \
                                    COALESCE(licenses.approved, 3) \
                    FROM container_packages \
                    JOIN packages on container_packages.package_nvr = \
                         packages.nvr \
                    JOIN sources on packages.source_id = sources.id \
                    JOIN paths on paths.source_id = sources.id \
                    JOIN license_detects ON license_detects.file_id = \
                         paths.file_id \
                    LEFT JOIN licenses ON license_detects.lic_name = \
                                          licenses.key \
                    WHERE container_packages.container_id = {cont_id} AND \
                          packages.source = container_packages.source"
            if unapproved == "1":
                sql += " AND COALESCE(licenses.approved, 3) != 1"
            sql += " GROUP BY license_detects.lic_name, \
                              COALESCE(licenses.approved, 3) \
                     ORDER BY license_detects.lic_name;"
            # s.append(f"<br>SQL: {sql}")

        elif release_id != None:
            # This section handles licenses on a per-release basis
            sql = f"SELECT products.name, releases.version FROM products \
                    JOIN releases ON releases.product_id = products.id \
                    WHERE releases.id = {release_id};"
            try:
                cdb.execute(sql)
                row = cdb.fetchone()
                product = row[0]        # Product name
                release = row[1]        # Release name
                s.append(f'<p><b>Product: {row[0]}, release: {row[1]}</b></p>')
            except Exception as e:
                s.append("<br>Failed to execute release info query")
                s.append("<br>Error: " + e.args[0])
                return render_template("base.html", content=s, em=EM)
            # Collect licenses found in this release
            sql = f"SELECT DISTINCT COUNT(license_detects.file_id), \
                                    license_detects.lic_name, \
                                    MAX(license_detects.score), \
                                    COALESCE(licenses.approved, 3) \
                    FROM packages_per_release \
                    JOIN packages on packages_per_release.package_nvr = \
                                     packages.nvr \
                    JOIN sources on packages.source_id = sources.id \
                    JOIN paths on paths.source_id = sources.id \
                    JOIN license_detects ON license_detects.file_id = \
                         paths.file_id \
                    LEFT JOIN licenses ON license_detects.lic_name = \
                                          licenses.key \
                    WHERE packages_per_release.release_id = {release_id} AND \
                          packages.source = packages_per_release.source"
            if unapproved == "1":
                sql += " AND COALESCE(licenses.approved, 3) != 1 "
            sql += " GROUP BY license_detects.lic_name, \
                              COALESCE(licenses.approved, 3) \
                     ORDER BY license_detects.lic_name;"
            # s.append(f"<br>SQL: {sql}")

        elif package_id != None:
            # This section handles licenses on a per-package basis
            sql = f"SELECT packages.nvr \
                    FROM packages \
                    WHERE id = {package_id};"
            try:
                cdb.execute(sql)
                row = cdb.fetchone()
                s.append(f'<p><b>Package: {row[0]}')
                s.append("</b></p>")
            except Exception as e:
                s.append("<br>Failed to execute package query")
                s.append("<br>Error: " + e.args[0])
                return render_template("base.html", content=s, em=EM)
            # Collect licenses found in this package
            sql = f"SELECT DISTINCT COUNT(license_detects.file_id), \
                                    license_detects.lic_name, \
                                    MAX(license_detects.score), \
                                    COALESCE(licenses.approved, 3) \
                    FROM license_detects \
                    JOIN paths ON license_detects.file_id = paths.file_id \
                    JOIN sources on paths.source_id = sources.id \
                    JOIN packages on sources.id = packages.source_id \
                    LEFT JOIN licenses ON license_detects.lic_name = \
                                          licenses.key \
                    WHERE packages.id = {package_id}"
            if unapproved == "1":
                sql += " AND COALESCE(licenses.approved, 3) != 1 "
            sql += " GROUP BY license_detects.lic_name, \
                              COALESCE(licenses.approved, 3) \
                     ORDER BY license_detects.lic_name;"
            # s.append(f"<br>SQL: {sql}")
        else:                           # Query that fails to request anything
            s.append("<br>Unimplemented code (licenses all products)")
            return render_template("base.html", content=s, em=EM)


        # For all different types of queries, do the database query
        try:
            cdb.execute(sql)
            rows = cdb.fetchall()
        except Exception as e:
            s.append("<br>Failed to execute licenses query")
            s.append("<br>Error: " + e.args[0])
            return render_template("base.html", content=s, em=EM)


        # For all different types of queries, return the results
        s.append('<table id="full" class="display" style="width:100%">')
        s.append('<thead><tr>')
        s.append('<th>Count</th>')
        s.append('<th>Score</th>')
        s.append('<th>Status</th>')
        s.append('<th>Scancode License Key</th>')
        s.append('</tr></thead>')
        for row in rows:
            if release_id != None:
                parms = urlencode({'rel_id':release_id, 'lic':row[1]},
                                   quote_via=quote_plus)
            elif cont_id != None:
                parms = urlencode({'cont_id':cont_id, 'lic':row[1]},
                                   quote_via=quote_plus)
            elif package_id != None:
                parms = urlencode({'pkg_id':package_id, 'lic':row[1]},
                                   quote_via=quote_plus)
            s.append(f'<tr><td>{row[0]}</td>')
            s.append(f'<td>{row[2]}</td>')
            s.append(f'<td>{legend[row[3]]}</td>')
            s.append(f'<td><a href="where_lic?{parms}">{row[1]}</a></td></tr>')
        s.append("</table>")

        # Close the DB
        ldb.close()
        # print("Successful close of database")

    return render_template("base.html", content=s, em=EM)


@app.route("/where_lic", methods=["GET"])
def where_lic():
    s = []
    cdb = ldb.open(DBdatabase, DBhost, DBport, DBuser, DBpassword)
    if cdb == None:
        s.append("Bummer...the database isn't connected")

    else:
        license = request.args.get("lic")
        package_id = request.args.get("pkg_id")
        cont_id = request.args.get("cont_id")
        release_id = request.args.get("rel_id")
        product_id = request.args.get("prod_id")
        # print("Got lic as", license)
        # print("Got pkg_id as", package_id)
        # print("Got cont_id as", cont_id)
        # print("Got rel_id as", release_id)
        # print("Got prod_id as", product_id)


        # This is the top of this page
        sql = f"SELECT pelc_link FROM licenses WHERE key = '{license}';"
        try:
            cdb.execute(sql)
            row = cdb.fetchone()
            s.append(f'<h2>License: <a href="{row[0]}">{license}</a></h2>')
        except Exception as e:
            s.append(f'<h2>License: {license} (not in PELC license table)</h2>')


        if release_id != None:
            # This section handles where-used on a per-release basis
            sql = f"SELECT products.name, releases.version FROM products \
                    JOIN releases ON releases.product_id = products.id \
                    WHERE releases.id = {release_id};"
            try:
                cdb.execute(sql)
                row = cdb.fetchone()
                s.append(f'<p><b>Product: {row[0]}, release: {row[1]}</b></p>')
            except Exception as e:
                s.append("<br>Failed to execute release info query")
                s.append("<br>Error: " + e.args[0])
                return render_template("base.html", content=s, em=EM)
            # Collect file paths where this license is found
            sql = f"SELECT DISTINCT paths.path, license_detects.score, \
                        license_detects.start_line, license_detects.end_line, \
                        packages.id, packages.nvr, files.swh \
                    FROM packages_per_release \
                    JOIN packages on packages_per_release.package_nvr = \
                                     packages.nvr \
                    JOIN sources on packages.source_id = sources.id \
                    JOIN paths on paths.source_id = sources.id \
                    JOIN files on paths.file_id = files.id \
                    JOIN license_detects ON license_detects.file_id = \
                         paths.file_id \
                    WHERE packages_per_release.release_id = {release_id} AND \
                          license_detects.lic_name = '{license}' AND \
                          packages.source = packages_per_release.source \
                    ORDER BY license_detects.score DESC;"
        elif cont_id != None:
            # This section handles where-used on a per-container basis
            sql = f"SELECT reference FROM containers WHERE id = {cont_id};"
            try:
                cdb.execute(sql)
                row = cdb.fetchone()
                s.append(f'<p><b>Container: {row[0]}</b></p>')
            except Exception as e:
                s.append("<br>Failed to execute container info query")
                s.append("<br>Error: " + e.args[0])
                return render_template("base.html", content=s, em=EM)
            # Collect file paths where this license is found
            sql = f"SELECT DISTINCT paths.path, \
                        license_detects.score, \
                        license_detects.start_line, license_detects.end_line, \
                        packages.id, packages.nvr, files.swh \
                    FROM container_packages \
                    JOIN packages on container_packages.package_nvr= \
                         packages.nvr \
                    JOIN sources on packages.source_id = sources.id \
                    JOIN paths on paths.source_id = sources.id \
                    JOIN files on paths.file_id = files.id \
                    JOIN license_detects ON license_detects.file_id = \
                         paths.file_id \
                    WHERE container_packages.container_id = {cont_id} AND \
                          license_detects.lic_name = '{license}' AND \
                          packages.source = container_packages.source \
                    ORDER BY license_detects.score DESC;"
        elif package_id != None:
            # This section handles where-used on a per-package basis
            sql = f"SELECT packages.nvr \
                    FROM packages \
                    WHERE id = {package_id};"
            try:
                cdb.execute(sql)
                row = cdb.fetchone()
                s.append(f'<p><b>Package: {row[0]}')
                s.append("</b></p>")
            except Exception as e:
                s.append("<br>Failed to execute package query")
                s.append("<br>Error: " + e.args[0])
                return render_template("base.html", content=s, em=EM)
            # Collect file paths where this license is found
            sql = f"SELECT DISTINCT paths.path, license_detects.score, \
                        license_detects.start_line, license_detects.end_line, \
                        packages.id, packages.nvr, files.swh \
                    FROM packages \
                    JOIN sources on packages.source_id = sources.id \
                    JOIN paths on paths.source_id = sources.id \
                    JOIN files on paths.file_id = files.id \
                    JOIN license_detects ON paths.file_id = \
                         license_detects.file_id \
                    WHERE packages.id = {package_id} AND \
                          license_detects.lic_name = '{license}' \
                    ORDER BY license_detects.score DESC;"
        else:                           # Query that fails to request anything
            s.append("<br>Unimplemented code (where-license all products)")
            return render_template("base.html", content=s, em=EM)


        # For all different types of queries, do the database query
        try:
            cdb.execute(sql)
            rows = cdb.fetchall()
        except Exception as e:
            s.append("<br>Failed to execute where license query")
            s.append("<br>Error: " + e.args[0])
            return render_template("base.html", content=s, em=EM)


        # For all different types of queries, return the results
        s.append('<table id="full" class="display" style="width:100%">')
        s.append('<thead><tr>')
        s.append('<th>Score</th>')
        s.append('<th>Package</th>')
        s.append('<th>File Path</th>')
        s.append('</tr></thead>')
        for row in rows:
            # row[6] is the SWH UUID
            # FIXME: This currently points to the external SWH, not our
            # internal version.
            if row[2] == row[3]:            # Single line needs different URL
                swhurl = f"https://archive.softwareheritage.org/{row[6]}" + \
                         f";lines={row[2]}"
            else:
                swhurl = f"https://archive.softwareheritage.org/{row[6]}" + \
                         f";lines={row[2]}-{row[3]}"
            s.append(f'<tr><td>{row[1]}</td>')
            s.append(f'<td><a href="package?id={row[4]}">{row[5]}</a></td>')
            if row[2] == row[3]:
                lines = f"(line {row[2]})"
            else:
                lines = f"(lines {row[2]}-{row[3]})"
            s.append(f'<td><a href="{swhurl}">{row[0]} {lines}</a></td></tr>')
        s.append("</table>")

        # Close the DB
        ldb.close()
        # print("Successful close of database")

    return render_template("base.html", content=s, em=EM)


@app.route("/import", methods=["GET"])
def data_import():
    s = []
    cdb = ldb.open(DBdatabase, DBhost, DBport, DBuser, DBpassword)
    if cdb == None:
        s.append("Bummer...the database isn't connected")

    else:
        # There are two main imports: manifests and packages
        # However, the json itself handles telling us what's there
        # type = request.args.get("type")

        s.append("<b>Listen up!</b><p><p>")
        s.append("Importing *stuff* into this system is a work in progress.")
        s.append("Eventually, there will be an API, but for now,")
        s.append("we have the ability to import an arbitrary json file.")
        s.append("The contents of the json file completely controls what gets")
        s.append("imported.")
        s.append("<p>")
        s.append("There are six main types of json import structures right")
        s.append("now:")
        s.append("<ol>")
        s.append("<li>")
        s.append("Product Entry: This is an item on the oslcrs home page.")
        s.append("Product entries are grouped by product family.")
        s.append("</li>")
        s.append("<li>")
        s.append("Container Entry: This defines the contents of a container.")
        s.append("Containers have identifiers so that they can be referenced,")
        s.append("and also include a list of packages that are part of the")
        s.append("container.")
        s.append("</li>")
        s.append("<li>")
        s.append("Release Entry: This item shows up on the page corresponding")
        s.append("to the product.")
        s.append("Releases define a specific set of open source packages")
        s.append("and/or containers, and these sets of packages/containers")
        s.append("form the basis for a report.")
        s.append("</li>")
        s.append("<li>")
        s.append("Package Analysis Request: Each open source package that may")
        s.append("be the subject of a report must be analyzed.")
        s.append("The json structure identifies the location of the")
        s.append("source code, as well as providing certain metadata,")
        s.append("if the source code itself does not provide this metadata.")
        s.append("Currently, the following source archive types are supported:")
        s.append("<ul>")
        s.append("<li>")
        s.append("srpm: Source RPM")
        s.append("</li>")
        s.append("<li>")
        s.append("custom: Custom entry allows all necessary metadata fields")
        s.append("to be supplied by the json import structure")
        s.append("</li>")
        s.append("</ul>")
        s.append("</li>")
        s.append("<li>")
        s.append("Source Container Import: Source Containers are special")
        s.append("objects of particular interest to Red Hat. Because")
        s.append("container-based products are so common, it makes sense to")
        s.append("implement functionality to directly import and analyze the")
        s.append("contents of any source container. This json structure")
        s.append("instructs oslcrs to analyze the contents of a source")
        s.append("container, and make that container available in the list of")
        s.append("known containers. This json structure does not add the")
        s.append("container to any specific product release.")
        s.append("</li>")
        s.append("<li>")
        s.append("Binary Package Mapping Entry: oslcrs allows reporting on")
        s.append("both source and binary package manifests.  However, only")
        s.append("source packages are imported and analyzed.  If you intend")
        s.append("to be able to index reports to binary packages, the system")
        s.append("needs to know how source and binary packages are related.")
        s.append("This import supplies the source-binary package mapping.")
        s.append("</li>")
        s.append("</ol>")
        s.append("<p>")
        s.append("Each of the above json structures can be imported")
        s.append("individually, and arrays (lists) of these structures")
        s.append("can be imported as part of the same json file.")
        s.append("Examples of these json structures can be found in the")
        s.append('"examples" subdirectory of the source code for this')
        s.append("program.")
        s.append("<p>")
        s.append("If we can detect errors, we'll do nothing.")
        s.append("But there are probably cases where we will get part-way")
        s.append("through a DB insert and error out.  This is a")
        s.append("problem that this system can't fix on it's own.")
        s.append("<p>")
        s.append("As much as possible, re-upload of the same data will")
        s.append("OVERWRITE the previous contents for items 1-3 above.")
        s.append("If you find this not to be the case for a specific")
        s.append("situation, please let us know.")
        s.append("Re-upload of the same source package (4) WILL NOT re-analyze")
        s.append("the package.  This is intentional.")
        s.append("There is much duplication in open source,")
        s.append("and it's necessary to avoid re-scanning source as well as")
        s.append("duplication of license/copyright results.")
        s.append("<p>&nbsp;<p>")
        s.append('<form action="upload" ')
        s.append(' method="POST" enctype="multipart/form-data">')
        s.append('<b>Select json file to upload:</b>')
        s.append('<input type=file name=file>')
        s.append('<input type=submit value="Upload">')
        s.append("</form>")

        # Close the DB
        ldb.close()
        # print("Successful close of database")

    return render_template("base.html", content=s, em=EM)


@app.route("/upload", methods=["POST"])
def upload_manifest():
    s = []
    cdb = ldb.open(DBdatabase, DBhost, DBport, DBuser, DBpassword)
    if cdb == None:
        s.append("Bummer...the database isn't connected")

    else:
        if request.method == 'POST':
            # Here is where we get the uploaded json manifest file
            try:
                # print(request.files)
                f = request.files['file']
                js = json.load(f)
                # print(js)
            except Exception as e:
                print("Import error:", e)
                s.append("Failed to import/parse json file")
                s.append(e)
                ldb.close()
                return render_template("base.html", content=s, em=EM)
            s.append(f"Imported json file {f.filename}<br>")

            # Now, we need to parse the json and handle the various import
            # cases.  One awkward thing is that we'd rather not make any DB
            # changes until/unless we know the json is all correct.  Especially
            # with user-generated structures, we don't know what someone will
            # send to us.
            #
            # Now, this poses a coding problem.  The code to check the json
            # structure is pretty much the same code to handle the database
            # updates.  I'd hate to have two copies of pretty much the same
            # code, but separated by some number of lines.  Perhaps there's
            # some clever Python library to check json, but I'm unaware of it.
            # One approach is to execute the same code twice, the first time
            # skipping DB changes, and the second time, doing them.  It's just
            # an idea, and I don't know how the code will play out.  Here
            # goes:
            if parse_json(js, None, s):     # Skip passing DB handle this pass
                # Non-zero return code is an error
                s.append("Failed to make sense of json import request<br>")
                s.append("No action has been taken")
                ldb.close()
                return render_template("base.html", content=s, em=EM)
            else:
                if parse_json(js, cdb, s):  # DB handle pass causes DB update
                    s.append("Failed to update database<br>")
                    ldb.close()
                    return render_template("base.html", content=s, em=EM)
                else:
                    s.append("Successful json upload<br>")

        # Close the DB
        ldb.close()
        # print("Successful close of database")

    return render_template("base.html", content=s, em=EM)


# Show the current analysis status
@app.route("/analysis_status")
def analysis_status():
    s = []
    cdb = ldb.open(DBdatabase, DBhost, DBport, DBuser, DBpassword)
    if cdb == None:
        s.append("Bummer...the database isn't connected")

    else:
        # Gather overall queue size information, useful for the page header.
        try:
            sql = "SELECT COUNT(name) FROM sources \
                   where state != 9;"
            cdb.execute(sql)
            q_size = cdb.fetchone()[0]
            sql = f"SELECT COUNT(name) FROM sources \
                    where state != 9 AND retries = {RETRIES};"
            cdb.execute(sql)
            q_failed = cdb.fetchone()[0]
            sql = "SELECT COUNT(name) FROM sources \
                   where state != 9 AND type = 'scnt';"
            cdb.execute(sql)
            q_scnt = cdb.fetchone()[0]
        except Exception as e:
            s.append("<br>Failed to gather overall queue size information")
            s.append("<br>Error: " + e.args[0])
            return render_template("base.html", content=s, em=EM)

        # Obtain analysis queue contents.  Basically, this is all the
        # sources table entries who's analysis state is != 9 (current
        # terminal state)
        sql = "SELECT name, state, retries, type, fetch_info, error, status \
               FROM sources \
               where state != 9 \
               ORDER BY id;"
        try:
            cdb.execute(sql)
            rows = cdb.fetchall()
        except Exception as e:
            s.append("<br>Failed to execute package analysis queue query")
            s.append("<br>Error: " + e.args[0])
            return render_template("base.html", content=s, em=EM)

        # Return the results
        s.append("<p><b>Package Analysis Queue:</b>")
        s.append(f"Size: {q_size}, Failed: {q_failed},")
        s.append(f"Source Containers: {q_scnt}</p>")
        s.append('<table id="full" class="display" style="width:100%">')
        s.append('<thead><tr>')
        s.append('<th>Status</th><th>Type</th><th>Name</th>')
        s.append('<th>Retries</th><th>Error Message</th><th>Info</th>')
        s.append('</tr></thead>')
        for row in rows:
            s.append(f'<tr>')
            s.append(f'<td valign=top>{row[6]}')
            s.append(f'<td valign=top>{row[3]}')
            s.append(f'<td valign=top>{row[0]}')
            s.append(f'<td valign=top>{row[2]}')
            s.append(f'<td valign=top>{row[5]}')
            s.append(f'<td valign=top>{row[4]}')
            s.append(f'</tr>')
        s.append("</table>")

        # Close the DB
        ldb.close()
        # print("Successful close of database")

    return render_template("base.html", content=s, em=EM)


# [Re]Start the analysis task
@app.route("/restart_analysis")
def restart_analysis():
    s = []

    temp = subprocess.Popen(["python3", analysis_program])
    s.append("Kicked off the package analysis program<br>")

    return render_template("base.html", content=s, em=EM)


# Clean up the analysis queue.  Basically, this involves removing entries
# from the DB "sources" table, where the analysis is not complete.
@app.route("/clean_analysis")
def clean_analysis():
    s = []
    cdb = ldb.open(DBdatabase, DBhost, DBport, DBuser, DBpassword)
    if cdb == None:
        s.append("Bummer...the database isn't connected")

    else:
        # FIXME: currently using "9" rather than 1000
        sql = "DELETE FROM sources WHERE state != 9;"
        try:
            cdb.execute(sql)
            ldb.commit()
            s.append("Successfully cleaned source package analysis queue<br>")
        except Exception as e:
            ldb.rollback()
            s.append(f"error: failed to clean source pkg analysis queue<br>")
            s.append(f"DB error: {e}<br>")

        # Close the DB
        ldb.close()

    return render_template("base.html", content=s, em=EM)


@app.route("/search", methods=["GET"])
def search():
    s = []
    cdb = ldb.open(DBdatabase, DBhost, DBport, DBuser, DBpassword)
    if cdb == None:
        s.append("Bummer...the database isn't connected")

    else:
        # At this point, the page doesn't have any GET parameters
        # We could in the future, for example searching within the context
        # of the page we're displaying at the time.
        type = request.args.get("type")

        s.append(f"{type} search page goes here...sorry, not implemented yet")


        # Close the DB
        ldb.close()
        # print("Successful close of database")

    return render_template("base.html", content=s, em=EM)


#
# CORGI PROTOTYPE SECTION
# This section of code is under development.  Basically, the idea is to begin
# to obtain manifest information from Corgi rather than feeding manifests in
# by hand.
#

global corgi_url                        # Where is Corgi? (value set in main())


@app.route("/corgi")
def corgi():                            # What products are available in Corgi?
    s = []
    s.append(f"<h3>Open Source License Compliance Reporting System</h3>")
    s.append(f"<h4 style=color:red>Corgi Integration Prototype</h4>")

    if corgi_url == None:
        s.append("Bummer...no Corgi URL environment variable")
    else:
        # The initial page shows available Corgi products
        try:
            corgi = requests.get(f"{corgi_url}products?limit=10000")
            # corgi = requests.get(f"{corgi_url}products")
        except Exception as e:
            s.append("<br>Failed to execute Corgi product list query")
            s.append("<br>Error: " + e.args[0])
            s.append(f"<br>HTTP status code: {corgi.status_code}")
            return render_template("base.html", content=s, em=EM)
        try:
            # Pull just the fields I need
            c_products = corgi.json()
            v = []
            for p in c_products["results"]:
                # v.append({"group": p["meta_attr"]["business_unit"],
                #           "name": p["name"],
                #           "ofuri": p["ofuri"],
                #           "description": p["description"]})
                v.append({"name": p["name"],
                          "ofuri": p["ofuri"],
                          "description": p["description"]})
        except Exception as e:
            s.append("<br>Failed to parse Corgi json result")
            s.append("<br>Error: " + e.args[0])
            s.append(f"<br>HTTP status code: {corgi.status_code}")
            return render_template("base.html", content=s, em=EM)

        # Return the results
        s.append("<p><b>Available Corgi Products:</b></p>")
        s.append('<table id="full" class="display" style="width:100%">')
        s.append('<thead><tr>')
        # s.append('<th>Group</th><th>Product</th><th>Description</th>')
        s.append('<th>Product</th><th>Description</th>')
        s.append('</tr></thead>')
        last = ""
        # for product in sorted(v, key=lambda i: (i["group"], i["name"])):
        for product in sorted(v, key=lambda i: (i["description"], i["name"])):
            # if last == product["group"]:
            #     s.append('<tr><td>&nbsp;</td>')
            # else:
            #     s.append(f'<tr><td valign=top>{product["group"]}</td>')
            #     last = product["group"]
            s.append('<tr>')
            s.append(f'<td valign=top><a href="c_prod?id={product["ofuri"]}">')
            s.append(f'{product["name"]}</a></td>')
            s.append(f'<td>{product["description"]}</td></tr>')
        s.append("</table>")

    return render_template("base.html", content=s, em=EM)


@app.route("/c_prod", methods=["GET"])
def c_prod():                           # Corgi version of /product
    s = []

    if corgi_url == None:
        s.append("Bummer...no Corgi URL environment variable")
    else:
        id = request.args.get("id")
        # print("Got id as", id)

        # Obtain releases for this product
        try:
            corgi = requests.get(f"{corgi_url}products?ofuri={id}")
        except Exception as e:
            s.append(f"<br>Failed to execute Corgi product query for {id}")
            s.append("<br>Error: " + e.args[0])
            s.append(f"<br>HTTP status code: {corgi.status_code}")
            return render_template("base.html", content=s, em=EM)
        try:
            # Pull just the fields I need
            c_product = corgi.json()
            product_name = c_product["name"]
            product_description = c_product["description"]
            v = []
            for ver in c_product["product_versions"]:
                v.append({"name": ver["name"],
                          "ofuri": ver["ofuri"]})
        except Exception as e:
            s.append("<br>Failed to parse Corgi product json result")
            s.append("<br>Error: " + e.args[0])
            s.append(f"<br>HTTP status code: {corgi.status_code}")
            return render_template("base.html", content=s, em=EM)

        # Return the results
        s.append(f"<p><b>{product_description} ({product_name}) versions:</b></p>")
        s.append('<table id="full" class="display" style="width:100%">')
        s.append('<thead><tr>')
        s.append('<th>Version</th>')
        s.append('</tr></thead>')
        for version in sorted(v, key=lambda i: (i["name"])):
            s.append('<tr><td valign=top>')
            s.append(f'<a href="c_stream?id={version["ofuri"]}">{version["name"]}</a></td></tr>')
        s.append("</table>")

    return render_template("base.html", content=s, em=EM)


@app.route("/c_stream", methods=["GET"])
def c_stream():                          # Corgi version of /product streams
    s = []

    if corgi_url == None:
        s.append("Bummer...no Corgi URL environment variable")
    else:
        id = request.args.get("id")
        # print("Got id as", id)

        # Obtain streams for this product
        try:
            corgi = requests.get(f"{corgi_url}product_versions?ofuri={id}")
        except Exception as e:
            s.append(f"<br>Failed to execute Corgi product version query for {id}")
            s.append("<br>Error: " + e.args[0])
            s.append(f"<br>HTTP status code: {corgi.status_code}")
            return render_template("base.html", content=s, em=EM)
        try:
            # Pull just the fields I need
            c_product = corgi.json()
            product_name = c_product["name"]
            product_description = c_product["description"]
            vs = []
            for stream in c_product["product_streams"]:
                vs.append({"name": stream["name"],
                           "ofuri": stream["ofuri"]})
        except Exception as e:
            s.append("<br>Failed to parse Corgi product streams json result")
            s.append("<br>Error: " + e.args[0])
            s.append(f"<br>HTTP status code: {corgi.status_code}")
            return render_template("base.html", content=s, em=EM)

        # Return the results
        s.append(f"<p><b>{product_description} ({product_name}) streams:</b></p>")
        s.append('<table id="full" class="display" style="width:100%">')
        s.append('<thead><tr>')
        s.append('<th>Streams</th>')
        s.append('<th>Griffon Report</th>')
        s.append('</tr></thead>')
        for stream in sorted(vs, key=lambda i: (i["name"])):
            s.append('<tr><td valign=top>')
            s.append(f'<a href="c_manifest?id={stream["ofuri"]}">{stream["name"]}</a></td>')
            s.append(f'<td valign=top>griffon service report-license \"{stream["name"]}\"</td>')
            s.append('</tr>')
        s.append("</table>")

    return render_template("base.html", content=s, em=EM)


@app.route("/c_manifest", methods=["GET"])
def c_manifest():                   # Corgi top-level /report
    s = []

    if corgi_url == None:
        s.append("Bummer...no Corgi URL environment variable")
    else:
        id = request.args.get("id")
        # print("Got id as", id)

        # Obtain the components list for this ofuri
        try:
            # corgi = requests.get(f"{corgi_url}components?ofuri={id}&view=summary&limit=10000")
            corgi = requests.get(f"{corgi_url}components?ofuri={id}&limit=10000")
        except Exception as e:
            s.append(f"<br>Failed to execute Corgi component query for {id}")
            s.append("<br>Error: " + e.args[0])
            s.append(f"<br>HTTP status code: {corgi.status_code}")
            return render_template("base.html", content=s, em=EM)
        try:
            # Pull the initial field I need
            c_comp = corgi.json()
            c_count = c_comp["count"]
        except Exception as e:
            s.append("<br>Failed to parse Corgi product streams json result")
            s.append("<br>Error: " + e.args[0])
            s.append(f"<br>HTTP status code: {corgi.status_code}")
            return render_template("base.html", content=s, em=EM)

        # Return the results
        s.append(f"<p><b>Corgi reports {c_count} top-level components for ofuri {id}</b></p>")
        s.append('<table id="full" class="display" style="width:100%">')
        s.append('<thead><tr>')
        s.append('<th>Component NVR</th>')
        s.append('<th>Type</th>')
        s.append('<th>Arch</th>')
        s.append('<th>Upstream URL</th>')
        s.append('<th>Summary License</th>')
        s.append('</tr></thead>')
        for item in sorted(c_comp["results"], key=lambda i: (i["nvr"])):
            # s.append('<tr><td valign=top>')
            s.append('<tr><td>')
            s.append(f'<a href=\"{item["link"]}\">{item["nvr"]}</a></td>')
            s.append(f'<td>{item["type"]}</td>')
            s.append(f'<td>{item["arch"]}</td>')
            s.append(f'<td>{item["related_url"]}</td>')
            s.append(f'<td>{item["license_declared"]}</td>')
            s.append('</tr>')
        s.append("</table>")

    return render_template("base.html", content=s, em=EM)


#
# END OF CORGI PROTOTYPE SECTION
#


if __name__ == "__main__":
    # Obtain database connection information
    db_success = 0                      # FIXME: Not used
    DBhost = os.environ['DB_HOST']
    DBuser = os.environ['DB_USER']
    DBpassword = os.environ['DB_PASSWD']
    DBdatabase = os.environ['DB_NAME']
    DBport = os.environ['DB_PORT']
    print("Connection information:")
    print("  Host:", DBhost)
    print("  Port:", DBport)
    print("  DB:  ", DBdatabase)
    print("  User:", DBuser)

    EM = os.environ['OSLCRS_CONTACT_EMAIL']

    # The source container import functionality requires that we have access
    # to the "tools" subproject scripts, specifically the "source-container"
    # script.  This shell variable determines the full pathname to the
    # subdirectory containing this tool.  Failing to define the path will
    # result in source container import errors later on.
    try:
        TOOLSDIR = os.environ['OSLCRS_TOOLS']
    except:
        TOOLSDIR = os.getcwd() + "/tools" 
        os.environ['OSLCRS_TOOLS'] = TOOLSDIR # Set the value for any children

    # If the Flask application has a requested port, use it
    try:
        FLASKport = os.environ['OSLCRS_PORT']
    except:
        FLASKport = 5000

    # If the user has configured a Corgi URL, use that
    try:
        corgi_url = os.environ['CORGI_API_URL'] + "/api/v1/"
    except:
        corgi_url = None


    # Manifest and package uploads require a temporary working directory that
    # needs to exist.  Ensure we have this subdirectory.
    print("Creating tmp directory for uploads and analysis work...")
    output = subprocess.run(["/bin/rm", "-rf", "/tmp/oslcrs"],
                            capture_output=True)
    # print(output)
    if output.returncode != 0:
        print("  Failed to remove existing tmp directory")
        exit(1)
    output = subprocess.run(["/bin/mkdir", "/tmp/oslcrs"], capture_output=True)
    # print(output)
    if output.returncode != 0:
        print("  Failed to create tmp directory")
        exit(1)
    print("...done")
    tmpinteger = 0                      # Uploaded manifests get integer names


    # Postgres changed sometime between version 9 and 11.  UPDATE SQL requires
    # a ROW() in version 11, where it was illegal in version 9.  This code
    # determines when it's necessary and sets a global variable
    cdb = ldb.open(DBdatabase, DBhost, DBport, DBuser, DBpassword)
    if cdb == None:
        print("Bummer...the database isn't connected")
        print("Can't run the oslcrs script")
        exit(1)
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
    ldb.close()
    if int(db_version[0]) > 9:
        need_row = "ROW"
    else:
        need_row = ""
    # print("need_row is", need_row)


    # Run the Flask application to serve up http pages
    app.run(host='0.0.0.0', port=FLASKport)
