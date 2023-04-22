--
-- PostgreSQL database dump
--

-- Dumped from database version 11.16 (Debian 11.16-0+deb10u1)
-- Dumped by pg_dump version 13.8 (Debian 13.8-0+deb11u1)

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- Name: OSLC; Type: DATABASE; Schema: -; Owner: -
--

CREATE DATABASE "OSLC" WITH TEMPLATE = template0 ENCODING = 'UTF8' LOCALE = 'en_US.utf8';


\connect "OSLC"

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- Name: DATABASE "OSLC"; Type: COMMENT; Schema: -; Owner: -
--

COMMENT ON DATABASE "OSLC" IS 'Open Source License Compliance Reporting Database';


SET default_tablespace = '';

--
-- Name: container_packages; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.container_packages (
    container_id bigint NOT NULL,
    package_nvr character varying(512) NOT NULL,
    source smallint DEFAULT 0 NOT NULL
);


--
-- Name: TABLE container_packages; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.container_packages IS 'packages in each container';


--
-- Name: COLUMN container_packages.container_id; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.container_packages.container_id IS 'reference to a container';


--
-- Name: COLUMN container_packages.package_nvr; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.container_packages.package_nvr IS 'reference to a package (nvr)';


--
-- Name: COLUMN container_packages.source; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.container_packages.source IS 'non-zero if this package corresponds to the entire source, rather than an actual binary package';


--
-- Name: containers; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.containers (
    id integer NOT NULL,
    reference text NOT NULL
);


--
-- Name: TABLE containers; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.containers IS 'containers that we know about; be cautious about ever allowing these to be deleted since this action silently removes containers from a release';


--
-- Name: COLUMN containers.id; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.containers.id IS 'unique container ID';


--
-- Name: COLUMN containers.reference; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.containers.reference IS 'reference to a container';


--
-- Name: containers_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.containers_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: containers_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.containers_id_seq OWNED BY public.containers.id;


--
-- Name: copyrights; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.copyrights (
    file_id bigint,
    copyright text,
    detector character(32),
    false_positive boolean DEFAULT false NOT NULL,
    start_line integer,
    end_line integer
);


--
-- Name: TABLE copyrights; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.copyrights IS 'per-file copyright detections';


--
-- Name: COLUMN copyrights.file_id; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.copyrights.file_id IS 'reference to a file';


--
-- Name: COLUMN copyrights.copyright; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.copyrights.copyright IS 'copyright text';


--
-- Name: COLUMN copyrights.detector; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.copyrights.detector IS 'copyright detector version; must allow for compares';


--
-- Name: COLUMN copyrights.false_positive; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.copyrights.false_positive IS 'True if this detection has been determined to be false positive';


--
-- Name: COLUMN copyrights.start_line; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.copyrights.start_line IS 'beginning of copyright match';


--
-- Name: COLUMN copyrights.end_line; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.copyrights.end_line IS 'end of copyright match';


--
-- Name: exclude_path; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.exclude_path (
    id integer NOT NULL,
    fragment text,
    comment text
);


--
-- Name: TABLE exclude_path; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.exclude_path IS 'list of path name fragments that result in license false positives';


--
-- Name: COLUMN exclude_path.id; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.exclude_path.id IS 'not used, but gives elements of this table a handle for reference';


--
-- Name: COLUMN exclude_path.fragment; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.exclude_path.fragment IS 'path name fragment';


--
-- Name: COLUMN exclude_path.comment; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.exclude_path.comment IS 'reason this poses a problem';


--
-- Name: exclude_path_comment_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.exclude_path_comment_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: exclude_path_comment_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.exclude_path_comment_seq OWNED BY public.exclude_path.comment;


--
-- Name: exclude_path_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.exclude_path_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: exclude_path_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.exclude_path_id_seq OWNED BY public.exclude_path.id;


--
-- Name: files; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.files (
    id bigint NOT NULL,
    swh character(50)
);


--
-- Name: TABLE files; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.files IS 'all files we''ve seen; basically links a unique file ID with a SWH file UUID';


--
-- Name: COLUMN files.id; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.files.id IS 'file ID within oslcrs';


--
-- Name: COLUMN files.swh; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.files.swh IS 'swh UUID, type cnt';


--
-- Name: files_id_seq1; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.files_id_seq1
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: files_id_seq1; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.files_id_seq1 OWNED BY public.files.id;


--
-- Name: license_detects; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.license_detects (
    file_id bigint NOT NULL,
    lic_name character varying(128) NOT NULL,
    score real,
    rule text,
    start_line integer,
    end_line integer,
    false_positive boolean DEFAULT false NOT NULL,
    detector character varying(32)
);


--
-- Name: TABLE license_detects; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.license_detects IS 'license detection artifacts';


--
-- Name: COLUMN license_detects.file_id; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.license_detects.file_id IS 'reference to a file';


--
-- Name: COLUMN license_detects.lic_name; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.license_detects.lic_name IS 'PELC (DejaCode) license key name (future reference to licenses table)';


--
-- Name: COLUMN license_detects.score; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.license_detects.score IS 'scancode license match score (0 - 100%)';


--
-- Name: COLUMN license_detects.rule; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.license_detects.rule IS 'scancode matched rule name';


--
-- Name: COLUMN license_detects.start_line; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.license_detects.start_line IS 'starting line number of matched license text';


--
-- Name: COLUMN license_detects.end_line; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.license_detects.end_line IS 'ending line number of matched license text';


--
-- Name: COLUMN license_detects.false_positive; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.license_detects.false_positive IS 'True if this detection has been determined to be false positive';


--
-- Name: COLUMN license_detects.detector; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.license_detects.detector IS 'license detector version; must allow for compares';


--
-- Name: licenses; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.licenses (
    key character varying(128) NOT NULL,
    approved integer NOT NULL,
    legacy boolean,
    bad boolean,
    local boolean,
    url character varying(512),
    pelc_link character varying(128),
    long_name character varying(256),
    short_name character varying(128),
    spdx character varying(128),
    text text
);


--
-- Name: TABLE licenses; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.licenses IS 'copy of PELC license table, used for reference information and license approval status';


--
-- Name: COLUMN licenses.key; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.licenses.key IS 'PELC/DejaCode/scancode license key';


--
-- Name: COLUMN licenses.approved; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.licenses.approved IS 'PELC approval state';


--
-- Name: COLUMN licenses.legacy; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.licenses.legacy IS 'True if this is a PELC legacy license';


--
-- Name: COLUMN licenses.bad; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.licenses.bad IS 'True if PELC has this license marked bad';


--
-- Name: COLUMN licenses.local; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.licenses.local IS 'True if this license is locally uploaded to PELC';


--
-- Name: COLUMN licenses.url; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.licenses.url IS 'Upstream license reference URL';


--
-- Name: COLUMN licenses.pelc_link; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.licenses.pelc_link IS 'URL of license within PELC system';


--
-- Name: COLUMN licenses.long_name; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.licenses.long_name IS 'Long license name';


--
-- Name: COLUMN licenses.short_name; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.licenses.short_name IS 'Short license name';


--
-- Name: COLUMN licenses.spdx; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.licenses.spdx IS 'SPDX license identifier';


--
-- Name: COLUMN licenses.text; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.licenses.text IS 'Full license text, if available';


--
-- Name: overrides_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.overrides_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: overrides; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.overrides (
    id bigint DEFAULT nextval('public.overrides_id_seq'::regclass) NOT NULL,
    package_id bigint NOT NULL,
    url text,
    sum_license text,
    "timestamp" timestamp with time zone DEFAULT clock_timestamp() NOT NULL,
    responsible text NOT NULL
);


--
-- Name: TABLE overrides; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.overrides IS 'contains manual report override information on a per-package basis';


--
-- Name: COLUMN overrides.id; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.overrides.id IS 'override ID';


--
-- Name: COLUMN overrides.package_id; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.overrides.package_id IS 'link to packages table';


--
-- Name: COLUMN overrides.url; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.overrides.url IS 'new upstream URL value';


--
-- Name: COLUMN overrides.sum_license; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.overrides.sum_license IS 'new summary license text expression';


--
-- Name: COLUMN overrides."timestamp"; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.overrides."timestamp" IS 'the time/date this correction was entered or last changed';


--
-- Name: COLUMN overrides.responsible; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.overrides.responsible IS 'Name or other ID of the person who added or last changed this override';


--
-- Name: packages; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.packages (
    id bigint NOT NULL,
    nvr character varying(512) NOT NULL,
    source_id bigint NOT NULL,
    sum_license text,
    source smallint DEFAULT 0
);


--
-- Name: TABLE packages; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.packages IS 'source and binary packages';


--
-- Name: COLUMN packages.id; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.packages.id IS 'package ID';


--
-- Name: COLUMN packages.nvr; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.packages.nvr IS 'package nvr';


--
-- Name: COLUMN packages.source_id; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.packages.source_id IS 'source package pointer';


--
-- Name: COLUMN packages.sum_license; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.packages.sum_license IS 'package declared summary license expression';


--
-- Name: COLUMN packages.source; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.packages.source IS 'non-zero if this package corresponds to the entire source, rather than an actual binary package';


--
-- Name: paths; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.paths (
    source_id bigint NOT NULL,
    file_id bigint NOT NULL,
    path text NOT NULL
);


--
-- Name: TABLE paths; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.paths IS 'organizes files within packages';


--
-- Name: COLUMN paths.source_id; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.paths.source_id IS 'pointer to source package';


--
-- Name: COLUMN paths.file_id; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.paths.file_id IS 'pointer to file';


--
-- Name: COLUMN paths.path; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.paths.path IS 'file path within source package';


--
-- Name: sources; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.sources (
    id bigint NOT NULL,
    checksum character(50),
    name character varying(512),
    url character varying(512),
    fetch_info text,
    state smallint DEFAULT 0 NOT NULL,
    swh character(50),
    fossology character varying(512),
    error text DEFAULT ''::text NOT NULL,
    type character varying(8) NOT NULL,
    retries integer DEFAULT 0,
    status text DEFAULT ''::text NOT NULL
);


--
-- Name: TABLE sources; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.sources IS 'source packages that have been submitted for analysis';


--
-- Name: COLUMN sources.id; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.sources.id IS 'unique source ID';


--
-- Name: COLUMN sources.checksum; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.sources.checksum IS 'checksum (or other) for this package';


--
-- Name: COLUMN sources.name; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.sources.name IS 'name of this package';


--
-- Name: COLUMN sources.url; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.sources.url IS 'upstream project URL';


--
-- Name: COLUMN sources.fetch_info; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.sources.fetch_info IS 'fetch parameters (json dict structure)';


--
-- Name: COLUMN sources.state; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.sources.state IS 'used to track package analysis status';


--
-- Name: COLUMN sources.swh; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.sources.swh IS 'SWH package UUID';


--
-- Name: COLUMN sources.fossology; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.sources.fossology IS 'Fossology package analysis URL';


--
-- Name: COLUMN sources.error; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.sources.error IS 'error message from analysis';


--
-- Name: COLUMN sources.type; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.sources.type IS 'type of archive';


--
-- Name: COLUMN sources.retries; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.sources.retries IS 'number of analysis failures';


--
-- Name: COLUMN sources.status; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.sources.status IS 'As analysis proceeds, gets filled in with the status of the analysis';


--
-- Name: package_copyrights; Type: VIEW; Schema: public; Owner: -
--

CREATE VIEW public.package_copyrights AS
 SELECT packages.id AS package_id,
    string_agg(DISTINCT copyrights.copyright, '
'::text ORDER BY copyrights.copyright) AS copyright
   FROM (((public.packages
     JOIN public.sources ON ((packages.source_id = sources.id)))
     JOIN public.paths ON ((paths.source_id = sources.id)))
     JOIN public.copyrights ON ((copyrights.file_id = paths.file_id)))
  GROUP BY packages.id;


--
-- Name: VIEW package_copyrights; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON VIEW public.package_copyrights IS 'List of distinct copyright statements, per binary package';


--
-- Name: packages_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.packages_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: packages_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.packages_id_seq OWNED BY public.packages.id;


--
-- Name: release_containers; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.release_containers (
    release_id integer,
    container_id bigint
);


--
-- Name: TABLE release_containers; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.release_containers IS 'containers as part of a release';


--
-- Name: COLUMN release_containers.release_id; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.release_containers.release_id IS 'reference to a release';


--
-- Name: COLUMN release_containers.container_id; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.release_containers.container_id IS 'reference to a container';


--
-- Name: release_packages; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.release_packages (
    release_id integer NOT NULL,
    package_nvr character varying(512) NOT NULL,
    source smallint DEFAULT 0 NOT NULL
);


--
-- Name: TABLE release_packages; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.release_packages IS 'packages within each release';


--
-- Name: COLUMN release_packages.release_id; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.release_packages.release_id IS 'reference to a release';


--
-- Name: COLUMN release_packages.package_nvr; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.release_packages.package_nvr IS 'reference to a package (nvr)';


--
-- Name: COLUMN release_packages.source; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.release_packages.source IS 'non-zero if this package corresponds to the entire source, rather than an actual binary package';


--
-- Name: releases; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.releases (
    id integer NOT NULL,
    product_id smallint NOT NULL,
    version character varying(128) NOT NULL,
    notes text
);


--
-- Name: TABLE releases; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.releases IS 'releases of each product';


--
-- Name: COLUMN releases.id; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.releases.id IS 'unique product release ID';


--
-- Name: COLUMN releases.product_id; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.releases.product_id IS 'reference to product';


--
-- Name: COLUMN releases.version; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.releases.version IS 'release version information that will be displayed';


--
-- Name: COLUMN releases.notes; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.releases.notes IS 'comments, such as the source of this manifest data';


--
-- Name: packages_per_release; Type: VIEW; Schema: public; Owner: -
--

CREATE VIEW public.packages_per_release AS
 SELECT releases.id AS release_id,
    release_packages.package_nvr,
    release_packages.source
   FROM (public.releases
     JOIN public.release_packages ON ((release_packages.release_id = releases.id)))
UNION
 SELECT releases.id AS release_id,
    container_packages.package_nvr,
    container_packages.source
   FROM (((public.releases
     JOIN public.release_containers ON ((release_containers.release_id = releases.id)))
     JOIN public.containers ON ((containers.id = release_containers.container_id)))
     JOIN public.container_packages ON ((container_packages.container_id = containers.id)));


--
-- Name: VIEW packages_per_release; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON VIEW public.packages_per_release IS 'generates a list of packages (nvr) for any release';


--
-- Name: products; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.products (
    id integer NOT NULL,
    name text NOT NULL,
    description text,
    displayname text,
    family text
);


--
-- Name: TABLE products; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.products IS 'Red Hat products';


--
-- Name: COLUMN products.id; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.products.id IS 'unique product ID';


--
-- Name: COLUMN products.name; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.products.name IS 'product name (short, unique name)';


--
-- Name: COLUMN products.description; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.products.description IS 'short product description';


--
-- Name: COLUMN products.displayname; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.products.displayname IS 'when non-null, this name is displayed in place of the short name';


--
-- Name: COLUMN products.family; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.products.family IS 'product family; provides one level of product organization';


--
-- Name: products_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.products_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: products_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.products_id_seq OWNED BY public.products.id;


--
-- Name: releases_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.releases_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: releases_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.releases_id_seq OWNED BY public.releases.id;


--
-- Name: sources_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.sources_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: sources_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.sources_id_seq OWNED BY public.sources.id;


--
-- Name: containers id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.containers ALTER COLUMN id SET DEFAULT nextval('public.containers_id_seq'::regclass);


--
-- Name: exclude_path id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.exclude_path ALTER COLUMN id SET DEFAULT nextval('public.exclude_path_id_seq'::regclass);


--
-- Name: files id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.files ALTER COLUMN id SET DEFAULT nextval('public.files_id_seq1'::regclass);


--
-- Name: packages id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.packages ALTER COLUMN id SET DEFAULT nextval('public.packages_id_seq'::regclass);


--
-- Name: products id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.products ALTER COLUMN id SET DEFAULT nextval('public.products_id_seq'::regclass);


--
-- Name: releases id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.releases ALTER COLUMN id SET DEFAULT nextval('public.releases_id_seq'::regclass);


--
-- Name: sources id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sources ALTER COLUMN id SET DEFAULT nextval('public.sources_id_seq'::regclass);


--
-- Name: container_packages container_packages_container_id_package_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.container_packages
    ADD CONSTRAINT container_packages_container_id_package_id_key UNIQUE (container_id, package_nvr);


--
-- Name: containers containers_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.containers
    ADD CONSTRAINT containers_pkey PRIMARY KEY (id);


--
-- Name: containers containers_reference_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.containers
    ADD CONSTRAINT containers_reference_key UNIQUE (reference);


--
-- Name: copyrights copyrights_file_id_copyright_start_line_end_line_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.copyrights
    ADD CONSTRAINT copyrights_file_id_copyright_start_line_end_line_key UNIQUE (file_id, copyright, start_line, end_line);


--
-- Name: release_containers ensure no duplicate container links; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.release_containers
    ADD CONSTRAINT "ensure no duplicate container links" UNIQUE (release_id, container_id);


--
-- Name: release_packages ensure no duplicate package links; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.release_packages
    ADD CONSTRAINT "ensure no duplicate package links" UNIQUE (release_id, package_nvr);


--
-- Name: exclude_path exclude_path_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.exclude_path
    ADD CONSTRAINT exclude_path_pkey PRIMARY KEY (id);


--
-- Name: files files_pkey1; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.files
    ADD CONSTRAINT files_pkey1 PRIMARY KEY (id);


--
-- Name: license_detects license_detects_file_id_lic_name_score_rule_start_line_end__key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.license_detects
    ADD CONSTRAINT license_detects_file_id_lic_name_score_rule_start_line_end__key UNIQUE (file_id, lic_name, score, rule, start_line, end_line);


--
-- Name: licenses licenses_key_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.licenses
    ADD CONSTRAINT licenses_key_key UNIQUE (key);


--
-- Name: overrides overrides_package_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.overrides
    ADD CONSTRAINT overrides_package_id_key UNIQUE (package_id);


--
-- Name: overrides overrides_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.overrides
    ADD CONSTRAINT overrides_pkey PRIMARY KEY (id);


--
-- Name: packages packages_nvr_source_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.packages
    ADD CONSTRAINT packages_nvr_source_key UNIQUE (nvr, source);


--
-- Name: packages packages_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.packages
    ADD CONSTRAINT packages_pkey PRIMARY KEY (id);


--
-- Name: paths paths_source_id_file_id_path_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.paths
    ADD CONSTRAINT paths_source_id_file_id_path_key UNIQUE (source_id, file_id, path);


--
-- Name: products products_name_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.products
    ADD CONSTRAINT products_name_key UNIQUE (name);


--
-- Name: products products_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.products
    ADD CONSTRAINT products_pkey PRIMARY KEY (id);


--
-- Name: releases releases_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.releases
    ADD CONSTRAINT releases_id_key UNIQUE (id);


--
-- Name: releases releases_product_id_version_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.releases
    ADD CONSTRAINT releases_product_id_version_key UNIQUE (product_id, version);


--
-- Name: sources sources_checksum_name_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sources
    ADD CONSTRAINT sources_checksum_name_key UNIQUE (checksum, name);


--
-- Name: sources sources_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sources
    ADD CONSTRAINT sources_pkey PRIMARY KEY (id);


--
-- Name: sources sources_swh_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sources
    ADD CONSTRAINT sources_swh_key UNIQUE (swh);


--
-- Name: file_swh_index; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX file_swh_index ON public.files USING hash (swh);


--
-- Name: packages_package_id; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX packages_package_id ON public.overrides USING btree (package_id);


--
-- Name: container_packages container_packages_container_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.container_packages
    ADD CONSTRAINT container_packages_container_id_fkey FOREIGN KEY (container_id) REFERENCES public.containers(id) ON DELETE CASCADE;


--
-- Name: copyrights copyrights_file_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.copyrights
    ADD CONSTRAINT copyrights_file_id_fkey FOREIGN KEY (file_id) REFERENCES public.files(id) ON DELETE CASCADE;


--
-- Name: license_detects license_detects_file_id_fkey1; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.license_detects
    ADD CONSTRAINT license_detects_file_id_fkey1 FOREIGN KEY (file_id) REFERENCES public.files(id) ON DELETE CASCADE;


--
-- Name: overrides overrides_package_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.overrides
    ADD CONSTRAINT overrides_package_id_fkey FOREIGN KEY (package_id) REFERENCES public.packages(id) ON DELETE CASCADE;


--
-- Name: packages packages_source_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.packages
    ADD CONSTRAINT packages_source_id_fkey FOREIGN KEY (source_id) REFERENCES public.sources(id) ON DELETE CASCADE;


--
-- Name: paths paths_file_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.paths
    ADD CONSTRAINT paths_file_id_fkey FOREIGN KEY (file_id) REFERENCES public.files(id) ON DELETE CASCADE;


--
-- Name: paths paths_source_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.paths
    ADD CONSTRAINT paths_source_id_fkey FOREIGN KEY (source_id) REFERENCES public.sources(id) ON DELETE CASCADE;


--
-- Name: release_containers release_containers_container_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.release_containers
    ADD CONSTRAINT release_containers_container_id_fkey FOREIGN KEY (container_id) REFERENCES public.containers(id) ON DELETE CASCADE;


--
-- Name: release_containers release_containers_release_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.release_containers
    ADD CONSTRAINT release_containers_release_id_fkey FOREIGN KEY (release_id) REFERENCES public.releases(id) ON DELETE CASCADE;


--
-- Name: release_packages release_packages_release_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.release_packages
    ADD CONSTRAINT release_packages_release_id_fkey FOREIGN KEY (release_id) REFERENCES public.releases(id) ON DELETE CASCADE;


--
-- Name: releases releases_product_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.releases
    ADD CONSTRAINT releases_product_id_fkey FOREIGN KEY (product_id) REFERENCES public.products(id) ON DELETE CASCADE;


--
-- Name: DATABASE "OSLC"; Type: ACL; Schema: -; Owner: -
--

GRANT ALL ON DATABASE "OSLC" TO oslc;


--
-- Name: TABLE container_packages; Type: ACL; Schema: public; Owner: -
--

GRANT ALL ON TABLE public.container_packages TO oslc;


--
-- Name: TABLE containers; Type: ACL; Schema: public; Owner: -
--

GRANT ALL ON TABLE public.containers TO oslc;


--
-- Name: SEQUENCE containers_id_seq; Type: ACL; Schema: public; Owner: -
--

GRANT ALL ON SEQUENCE public.containers_id_seq TO oslc;


--
-- Name: TABLE copyrights; Type: ACL; Schema: public; Owner: -
--

GRANT ALL ON TABLE public.copyrights TO oslc;


--
-- Name: TABLE exclude_path; Type: ACL; Schema: public; Owner: -
--

GRANT ALL ON TABLE public.exclude_path TO oslc;


--
-- Name: SEQUENCE exclude_path_comment_seq; Type: ACL; Schema: public; Owner: -
--

GRANT ALL ON SEQUENCE public.exclude_path_comment_seq TO oslc;


--
-- Name: SEQUENCE exclude_path_id_seq; Type: ACL; Schema: public; Owner: -
--

GRANT ALL ON SEQUENCE public.exclude_path_id_seq TO oslc;


--
-- Name: TABLE files; Type: ACL; Schema: public; Owner: -
--

GRANT ALL ON TABLE public.files TO oslc;


--
-- Name: SEQUENCE files_id_seq1; Type: ACL; Schema: public; Owner: -
--

GRANT ALL ON SEQUENCE public.files_id_seq1 TO oslc;


--
-- Name: TABLE license_detects; Type: ACL; Schema: public; Owner: -
--

GRANT ALL ON TABLE public.license_detects TO oslc;


--
-- Name: TABLE licenses; Type: ACL; Schema: public; Owner: -
--

GRANT ALL ON TABLE public.licenses TO oslc;


--
-- Name: SEQUENCE overrides_id_seq; Type: ACL; Schema: public; Owner: -
--

GRANT ALL ON SEQUENCE public.overrides_id_seq TO oslc;


--
-- Name: TABLE overrides; Type: ACL; Schema: public; Owner: -
--

GRANT ALL ON TABLE public.overrides TO oslc;


--
-- Name: TABLE packages; Type: ACL; Schema: public; Owner: -
--

GRANT ALL ON TABLE public.packages TO oslc;


--
-- Name: TABLE paths; Type: ACL; Schema: public; Owner: -
--

GRANT ALL ON TABLE public.paths TO oslc;


--
-- Name: TABLE sources; Type: ACL; Schema: public; Owner: -
--

GRANT ALL ON TABLE public.sources TO oslc;


--
-- Name: TABLE package_copyrights; Type: ACL; Schema: public; Owner: -
--

GRANT ALL ON TABLE public.package_copyrights TO oslc;


--
-- Name: SEQUENCE packages_id_seq; Type: ACL; Schema: public; Owner: -
--

GRANT ALL ON SEQUENCE public.packages_id_seq TO oslc;


--
-- Name: TABLE release_containers; Type: ACL; Schema: public; Owner: -
--

GRANT ALL ON TABLE public.release_containers TO oslc;


--
-- Name: TABLE release_packages; Type: ACL; Schema: public; Owner: -
--

GRANT ALL ON TABLE public.release_packages TO oslc;


--
-- Name: TABLE releases; Type: ACL; Schema: public; Owner: -
--

GRANT ALL ON TABLE public.releases TO oslc;


--
-- Name: TABLE packages_per_release; Type: ACL; Schema: public; Owner: -
--

GRANT ALL ON TABLE public.packages_per_release TO oslc;


--
-- Name: TABLE products; Type: ACL; Schema: public; Owner: -
--

GRANT ALL ON TABLE public.products TO oslc;


--
-- Name: SEQUENCE products_id_seq; Type: ACL; Schema: public; Owner: -
--

GRANT ALL ON SEQUENCE public.products_id_seq TO oslc;


--
-- Name: SEQUENCE releases_id_seq; Type: ACL; Schema: public; Owner: -
--

GRANT ALL ON SEQUENCE public.releases_id_seq TO oslc;


--
-- Name: SEQUENCE sources_id_seq; Type: ACL; Schema: public; Owner: -
--

GRANT ALL ON SEQUENCE public.sources_id_seq TO oslc;


--
-- PostgreSQL database dump complete
--

