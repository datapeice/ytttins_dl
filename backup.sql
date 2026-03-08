--
-- PostgreSQL database dump
--

\restrict 95hhZnmHybgwqvRPugLYVDmNrzxek2jkdp0LdyfjeKmX23ZHVKWca716GIK36y8

-- Dumped from database version 17.6
-- Dumped by pg_dump version 17.9

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET transaction_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- Name: _heroku; Type: SCHEMA; Schema: -; Owner: -
--

CREATE SCHEMA _heroku;


--
-- Name: public; Type: SCHEMA; Schema: -; Owner: -
--

-- *not* creating schema, since initdb creates it


--
-- Name: SCHEMA public; Type: COMMENT; Schema: -; Owner: -
--

COMMENT ON SCHEMA public IS '';


--
-- Name: pg_stat_statements; Type: EXTENSION; Schema: -; Owner: -
--

CREATE EXTENSION IF NOT EXISTS pg_stat_statements WITH SCHEMA public;


--
-- Name: EXTENSION pg_stat_statements; Type: COMMENT; Schema: -; Owner: -
--

COMMENT ON EXTENSION pg_stat_statements IS 'track planning and execution statistics of all SQL statements executed';


--
-- Name: create_ext(); Type: FUNCTION; Schema: _heroku; Owner: -
--

CREATE FUNCTION _heroku.create_ext() RETURNS event_trigger
    LANGUAGE plpgsql SECURITY DEFINER
    AS $$

DECLARE

  schemaname TEXT;
  databaseowner TEXT;

  r RECORD;

BEGIN
  IF tg_tag OPERATOR(pg_catalog.=) 'CREATE EXTENSION' THEN
    PERFORM _heroku.validate_search_path();

    FOR r IN SELECT * FROM pg_catalog.pg_event_trigger_ddl_commands()
    LOOP
        CONTINUE WHEN r.command_tag != 'CREATE EXTENSION' OR r.object_type != 'extension';

        schemaname := (
            SELECT n.nspname
            FROM pg_catalog.pg_extension AS e
            INNER JOIN pg_catalog.pg_namespace AS n
            ON e.extnamespace = n.oid
            WHERE e.oid = r.objid
        );

        databaseowner := (
            SELECT pg_catalog.pg_get_userbyid(d.datdba)
            FROM pg_catalog.pg_database d
            WHERE d.datname = pg_catalog.current_database()
        );
        --RAISE NOTICE 'Record for event trigger %, objid: %,tag: %, current_user: %, schema: %, database_owenr: %', r.object_identity, r.objid, tg_tag, current_user, schemaname, databaseowner;
        IF r.object_identity = 'address_standardizer_data_us' THEN
            PERFORM _heroku.grant_table_if_exists(schemaname, 'SELECT, UPDATE, INSERT, DELETE', databaseowner, 'us_gaz');
            PERFORM _heroku.grant_table_if_exists(schemaname, 'SELECT, UPDATE, INSERT, DELETE', databaseowner, 'us_lex');
            PERFORM _heroku.grant_table_if_exists(schemaname, 'SELECT, UPDATE, INSERT, DELETE', databaseowner, 'us_rules');
        ELSIF r.object_identity = 'amcheck' THEN
            -- Grant execute permissions on amcheck functions (bt_*, gin_*, and verify_*)
            PERFORM _heroku.grant_function_execute_for_extension(r.objid, schemaname, databaseowner, ARRAY['bt_%', 'gin_%', 'verify_%'], NULL);
        ELSIF r.object_identity = 'dblink' THEN
            -- Grant execute permissions on dblink functions, excluding dblink_connect_u()
            -- which allows unauthenticated connections and should remain superuser-only
            PERFORM _heroku.grant_function_execute_for_extension(r.objid, schemaname, databaseowner, ARRAY['dblink%'], 'dblink_connect_u%');
            -- Explicitly revoke permissions on dblink_connect_u functions as a safety measure
            -- in case they were granted by default or in a previous version
            BEGIN
                EXECUTE pg_catalog.format('REVOKE EXECUTE ON FUNCTION %I.dblink_connect_u(text) FROM %I;', schemaname, databaseowner);
            EXCEPTION WHEN OTHERS THEN
                -- Function might not exist, continue
                NULL;
            END;
            BEGIN
                EXECUTE pg_catalog.format('REVOKE EXECUTE ON FUNCTION %I.dblink_connect_u(text, text) FROM %I;', schemaname, databaseowner);
            EXCEPTION WHEN OTHERS THEN
                -- Function might not exist, continue
                NULL;
            END;
        ELSIF r.object_identity = 'dict_int' THEN
            EXECUTE pg_catalog.format('ALTER TEXT SEARCH DICTIONARY %I.intdict OWNER TO %I;', schemaname, databaseowner);
        ELSIF r.object_identity = 'pg_prewarm' THEN
            -- Grant execute permissions on pg_prewarm and autoprewarm functions
            PERFORM _heroku.grant_function_execute_for_extension(
                r.objid, schemaname, databaseowner, ARRAY['pg_prewarm%', 'autoprewarm%'], NULL
            );
        ELSIF r.object_identity = 'pg_partman' THEN
            PERFORM _heroku.grant_table_if_exists(schemaname, 'SELECT, UPDATE, INSERT, DELETE', databaseowner, 'part_config');
            PERFORM _heroku.grant_table_if_exists(schemaname, 'SELECT, UPDATE, INSERT, DELETE', databaseowner, 'part_config_sub');
            PERFORM _heroku.grant_table_if_exists(schemaname, 'SELECT, UPDATE, INSERT, DELETE', databaseowner, 'custom_time_partitions');
        ELSIF r.object_identity = 'pg_stat_statements' THEN
            -- Grant execute permissions on pg_stat_statements functions
            PERFORM _heroku.grant_function_execute_for_extension(
                r.objid, schemaname, databaseowner, ARRAY['pg_stat_statements%'], NULL
            );
        ELSIF r.object_identity = 'postgres_fdw' THEN
            -- Grant USAGE on the foreign data wrapper (required for creating foreign servers and user mappings)
            EXECUTE pg_catalog.format('GRANT USAGE ON FOREIGN DATA WRAPPER postgres_fdw TO %I;', databaseowner);
            -- Grant execute permissions on all postgres_fdw functions
            PERFORM _heroku.grant_function_execute_for_extension(r.objid, schemaname, databaseowner, ARRAY['postgres_fdw%'], NULL);
        ELSIF r.object_identity = 'postgis' THEN
            PERFORM _heroku.postgis_after_create();
        ELSIF r.object_identity = 'postgis_raster' THEN
            PERFORM _heroku.postgis_after_create();
            PERFORM _heroku.grant_table_if_exists(schemaname, 'SELECT', databaseowner, 'raster_columns');
            PERFORM _heroku.grant_table_if_exists(schemaname, 'SELECT', databaseowner, 'raster_overviews');
        ELSIF r.object_identity = 'postgis_topology' THEN
            PERFORM _heroku.postgis_after_create();
            EXECUTE pg_catalog.format('ALTER SCHEMA topology OWNER TO %I;', databaseowner);
            EXECUTE pg_catalog.format('GRANT USAGE ON SCHEMA topology TO %I;', databaseowner);
            EXECUTE pg_catalog.format('GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA topology TO %I;', databaseowner);
            PERFORM _heroku.grant_table_if_exists('topology', 'SELECT, UPDATE, INSERT, DELETE', databaseowner);
            EXECUTE pg_catalog.format('GRANT USAGE, SELECT, UPDATE ON ALL SEQUENCES IN SCHEMA topology TO %I;', databaseowner);
        ELSIF r.object_identity = 'postgis_tiger_geocoder' THEN
            PERFORM _heroku.postgis_after_create();
            EXECUTE pg_catalog.format('ALTER SCHEMA tiger OWNER TO %I;', databaseowner);
            EXECUTE pg_catalog.format('GRANT USAGE ON SCHEMA tiger TO %I;', databaseowner);
            EXECUTE pg_catalog.format('GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA tiger TO %I;', databaseowner);
            PERFORM _heroku.grant_table_if_exists('tiger', 'SELECT, UPDATE, INSERT, DELETE', databaseowner);
            EXECUTE pg_catalog.format('ALTER SCHEMA tiger_data OWNER TO %I;', databaseowner);
            EXECUTE pg_catalog.format('GRANT USAGE ON SCHEMA tiger_data TO %I;', databaseowner);
            EXECUTE pg_catalog.format('GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA tiger_data TO %I;', databaseowner);
            PERFORM _heroku.grant_table_if_exists('tiger_data', 'SELECT, UPDATE, INSERT, DELETE', databaseowner);
        END IF;
    END LOOP;
  END IF;
END;
$$;


--
-- Name: drop_ext(); Type: FUNCTION; Schema: _heroku; Owner: -
--

CREATE FUNCTION _heroku.drop_ext() RETURNS event_trigger
    LANGUAGE plpgsql SECURITY DEFINER
    AS $$

DECLARE

  schemaname TEXT;
  databaseowner TEXT;

  r RECORD;

BEGIN
  IF tg_tag OPERATOR(pg_catalog.=) 'DROP EXTENSION' THEN
    PERFORM _heroku.validate_search_path();

    FOR r IN SELECT * FROM pg_catalog.pg_event_trigger_dropped_objects()
    LOOP
      CONTINUE WHEN r.object_type != 'extension';

      databaseowner := (
            SELECT pg_catalog.pg_get_userbyid(d.datdba)
            FROM pg_catalog.pg_database d
            WHERE d.datname = pg_catalog.current_database()
      );

      --RAISE NOTICE 'Record for event trigger %, objid: %,tag: %, current_user: %, database_owner: %, schemaname: %', r.object_identity, r.objid, tg_tag, current_user, databaseowner, r.schema_name;

      IF r.object_identity = 'postgis_topology' THEN
          EXECUTE pg_catalog.format('DROP SCHEMA IF EXISTS topology');
      END IF;
    END LOOP;

  END IF;
END;
$$;


--
-- Name: extension_before_drop(); Type: FUNCTION; Schema: _heroku; Owner: -
--

CREATE FUNCTION _heroku.extension_before_drop() RETURNS event_trigger
    LANGUAGE plpgsql SECURITY DEFINER
    AS $$

DECLARE

  query TEXT;

BEGIN
  query := (SELECT pg_catalog.current_query());

  -- RAISE NOTICE 'executing extension_before_drop: tg_event: %, tg_tag: %, current_user: %, session_user: %, query: %', tg_event, tg_tag, current_user, session_user, query;
  -- skip this validation if executed by an rds_superuser
  IF tg_tag OPERATOR(pg_catalog.=) 'DROP EXTENSION' AND NOT pg_catalog.pg_has_role(session_user, 'rds_superuser', 'MEMBER') THEN
    PERFORM _heroku.validate_search_path();

    -- DROP EXTENSION [ IF EXISTS ] name [, ...] [ CASCADE | RESTRICT ]
    IF (pg_catalog.regexp_match(query, 'DROP\s+EXTENSION\s+(IF\s+EXISTS)?.*(plpgsql)', 'i') IS NOT NULL) THEN
      RAISE EXCEPTION 'The plpgsql extension is required for database management and cannot be dropped.';
    END IF;
  END IF;
END;
$$;


--
-- Name: grant_function_execute_for_extension(oid, text, text, text[], text); Type: FUNCTION; Schema: _heroku; Owner: -
--

CREATE FUNCTION _heroku.grant_function_execute_for_extension(extension_oid oid, schemaname text, databaseowner text, name_patterns text[] DEFAULT NULL::text[], exclude_pattern text DEFAULT NULL::text) RETURNS void
    LANGUAGE plpgsql SECURITY DEFINER
    AS $$

DECLARE
    func_rec RECORD;

BEGIN
    PERFORM _heroku.validate_search_path();

    -- Dynamically grant execute permissions on extension functions.
    -- Finds functions belonging to the extension via pg_depend and grants execute permissions.
    FOR func_rec IN
        SELECT p.oid::regprocedure::text as func_sig
        FROM pg_catalog.pg_depend d
        JOIN pg_catalog.pg_proc p ON d.objid = p.oid
        JOIN pg_catalog.pg_namespace n ON p.pronamespace = n.oid
        WHERE d.refclassid = 'pg_catalog.pg_extension'::regclass
          AND d.refobjid = extension_oid
          AND d.deptype = 'e'
          AND n.nspname = schemaname
          AND (name_patterns IS NULL OR p.proname LIKE ANY(name_patterns))
          AND (exclude_pattern IS NULL OR p.proname NOT LIKE exclude_pattern)
    LOOP
        BEGIN
            EXECUTE pg_catalog.format('GRANT EXECUTE ON FUNCTION %s TO %I;', func_rec.func_sig, databaseowner);
        EXCEPTION WHEN OTHERS THEN
            -- Function might not exist or already granted, continue
            NULL;
        END;
    END LOOP;
END;
$$;


--
-- Name: grant_table_if_exists(text, text, text, text); Type: FUNCTION; Schema: _heroku; Owner: -
--

CREATE FUNCTION _heroku.grant_table_if_exists(alias_schemaname text, grants text, databaseowner text, alias_tablename text DEFAULT NULL::text) RETURNS void
    LANGUAGE plpgsql SECURITY DEFINER
    AS $$

BEGIN
  PERFORM _heroku.validate_search_path();

  IF alias_tablename IS NULL THEN
    EXECUTE pg_catalog.format('GRANT %s ON ALL TABLES IN SCHEMA %I TO %I;', grants, alias_schemaname, databaseowner);
  ELSE
    IF EXISTS (SELECT 1 FROM pg_catalog.pg_tables WHERE pg_tables.schemaname = alias_schemaname AND pg_tables.tablename = alias_tablename) THEN
      EXECUTE pg_catalog.format('GRANT %s ON TABLE %I.%I TO %I;', grants, alias_schemaname, alias_tablename, databaseowner);
    END IF;
  END IF;
END;
$$;


--
-- Name: postgis_after_create(); Type: FUNCTION; Schema: _heroku; Owner: -
--

CREATE FUNCTION _heroku.postgis_after_create() RETURNS void
    LANGUAGE plpgsql SECURITY DEFINER
    AS $$
DECLARE
    schemaname TEXT;
    databaseowner TEXT;
BEGIN
    PERFORM _heroku.validate_search_path();

    schemaname := (
        SELECT n.nspname
        FROM pg_catalog.pg_extension AS e
        INNER JOIN pg_catalog.pg_namespace AS n ON e.extnamespace = n.oid
        WHERE e.extname = 'postgis'
    );
    databaseowner := (
        SELECT pg_catalog.pg_get_userbyid(d.datdba)
        FROM pg_catalog.pg_database d
        WHERE d.datname = pg_catalog.current_database()
    );

    EXECUTE pg_catalog.format('GRANT EXECUTE ON FUNCTION %I.st_tileenvelope TO %I;', schemaname, databaseowner);
    EXECUTE pg_catalog.format('GRANT SELECT, UPDATE, INSERT, DELETE ON TABLE %I.spatial_ref_sys TO %I;', schemaname, databaseowner);
END;
$$;


--
-- Name: sanitize_search_path(text); Type: FUNCTION; Schema: _heroku; Owner: -
--

CREATE FUNCTION _heroku.sanitize_search_path(unsafe_search_path text DEFAULT NULL::text) RETURNS text
    LANGUAGE plpgsql
    AS $$
DECLARE
  search_path_parts TEXT[];
  safe_search_path TEXT;
BEGIN
  IF unsafe_search_path IS NULL THEN
    unsafe_search_path := pg_catalog.current_setting('search_path');
  END IF;

  search_path_parts := pg_catalog.string_to_array(unsafe_search_path, ',');
  search_path_parts := (
    SELECT pg_catalog.array_agg(TRIM(schema_name::text))
    FROM pg_catalog.unnest(search_path_parts) AS schema_name
    WHERE TRIM(schema_name::text) OPERATOR(pg_catalog.!~~) 'pg_temp%'
  );
  search_path_parts := (SELECT pg_catalog.array_remove(search_path_parts, 'pg_catalog'));
  search_path_parts := (SELECT pg_catalog.array_append(search_path_parts, 'pg_temp'));
  SELECT pg_catalog.array_to_string(search_path_parts, ',') INTO safe_search_path;
  RETURN safe_search_path;
END;
$$;


--
-- Name: validate_extension(); Type: FUNCTION; Schema: _heroku; Owner: -
--

CREATE FUNCTION _heroku.validate_extension() RETURNS event_trigger
    LANGUAGE plpgsql SECURITY DEFINER
    AS $$

DECLARE

  schemaname TEXT;
  r RECORD;

BEGIN
  IF tg_tag OPERATOR(pg_catalog.=) 'CREATE EXTENSION' THEN
    PERFORM _heroku.validate_search_path();

    FOR r IN SELECT * FROM pg_catalog.pg_event_trigger_ddl_commands()
    LOOP
      CONTINUE WHEN r.command_tag != 'CREATE EXTENSION' OR r.object_type != 'extension';

      schemaname := (
        SELECT n.nspname
        FROM pg_catalog.pg_extension AS e
        INNER JOIN pg_catalog.pg_namespace AS n
        ON e.extnamespace = n.oid
        WHERE e.oid = r.objid
      );

      IF schemaname = '_heroku' THEN
        RAISE EXCEPTION 'Creating extensions in the _heroku schema is not allowed';
      END IF;
    END LOOP;
  END IF;
END;
$$;


--
-- Name: validate_search_path(); Type: FUNCTION; Schema: _heroku; Owner: -
--

CREATE FUNCTION _heroku.validate_search_path() RETURNS void
    LANGUAGE plpgsql SECURITY DEFINER
    AS $$
DECLARE

  current_search_path TEXT;
  safe_search_path TEXT;
  current_schemas TEXT[];
  pg_catalog_index INTEGER;

BEGIN

  current_search_path := pg_catalog.current_setting('search_path');
  current_schemas := (SELECT pg_catalog.current_schemas(true));
  safe_search_path := _heroku.sanitize_search_path(current_search_path);

  IF current_schemas[1] OPERATOR(pg_catalog.~~) 'pg_temp%' THEN
    RAISE EXCEPTION 'Unable to perform this operation with current schema configuration. Try: SET search_path TO %.', safe_search_path;
  END IF;

  IF ('pg_catalog' OPERATOR(pg_catalog.=) ANY(current_schemas)) THEN
    SELECT pg_catalog.array_position(current_schemas, 'pg_catalog') INTO pg_catalog_index;
    IF pg_catalog_index OPERATOR(pg_catalog.!=) 1 THEN
      RAISE EXCEPTION 'Unable to perform this operation with current schema configuration. Try: SET search_path TO %.', safe_search_path;
    END IF;
  END IF;
END;
$$;


SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: active_users; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.active_users (
    id integer NOT NULL,
    user_id bigint,
    date character varying
);


--
-- Name: active_users_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.active_users_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: active_users_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.active_users_id_seq OWNED BY public.active_users.id;


--
-- Name: cookies; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.cookies (
    id integer NOT NULL,
    content character varying,
    updated_at timestamp without time zone
);


--
-- Name: cookies_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.cookies_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: cookies_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.cookies_id_seq OWNED BY public.cookies.id;


--
-- Name: download_history; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.download_history (
    id integer NOT NULL,
    user_id bigint,
    username character varying,
    platform character varying,
    content_type character varying,
    url character varying,
    title character varying,
    "timestamp" timestamp without time zone
);


--
-- Name: download_history_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.download_history_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: download_history_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.download_history_id_seq OWNED BY public.download_history.id;


--
-- Name: download_stats; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.download_stats (
    content_type character varying NOT NULL,
    count integer
);


--
-- Name: whitelisted_users; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.whitelisted_users (
    username character varying NOT NULL,
    added_at timestamp without time zone
);


--
-- Name: active_users id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.active_users ALTER COLUMN id SET DEFAULT nextval('public.active_users_id_seq'::regclass);


--
-- Name: cookies id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.cookies ALTER COLUMN id SET DEFAULT nextval('public.cookies_id_seq'::regclass);


--
-- Name: download_history id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.download_history ALTER COLUMN id SET DEFAULT nextval('public.download_history_id_seq'::regclass);


--
-- Data for Name: active_users; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.active_users (id, user_id, date) FROM stdin;
1	6299330933	2025-12-20
2	6299330933	2025-12-21
3	1022079796	2025-12-21
4	6299330933	2025-12-22
5	1022079796	2025-12-23
6	6299330933	2025-12-23
7	6299330933	2025-12-24
8	6299330933	2025-12-25
9	6299330933	2025-12-26
10	1022079796	2025-12-26
11	1022079796	2025-12-27
12	6299330933	2025-12-27
13	5331446232	2025-12-27
14	6299330933	2025-12-28
15	1022079796	2025-12-28
16	5707480536	2025-12-28
17	5707480536	2025-12-29
18	6299330933	2025-12-29
19	1022079796	2025-12-29
20	6299330933	2025-12-30
21	1022079796	2025-12-30
22	6299330933	2025-12-31
23	5707480536	2025-12-31
24	6299330933	2026-01-01
25	6299330933	2026-01-02
26	1022079796	2026-01-02
27	6299330933	2026-01-03
28	6299330933	2026-01-04
29	6299330933	2026-01-05
30	1022079796	2026-01-05
31	6299330933	2026-01-06
32	6299330933	2026-01-07
33	6299330933	2026-01-08
34	1022079796	2026-01-08
35	6299330933	2026-01-09
36	6299330933	2026-01-10
37	6299330933	2026-01-11
67	6299330933	2026-01-12
68	1022079796	2026-01-12
100	6299330933	2026-01-13
133	6299330933	2026-01-14
134	6299330933	2026-01-15
135	6299330933	2026-01-16
166	6299330933	2026-01-17
167	5707480536	2026-01-17
168	6299330933	2026-01-18
169	6299330933	2026-01-19
199	6299330933	2026-01-20
232	6299330933	2026-01-21
265	6299330933	2026-01-22
266	6299330933	2026-01-23
267	6299330933	2026-01-24
268	1022079796	2026-01-24
269	6299330933	2026-01-25
270	6299330933	2026-01-26
271	1022079796	2026-01-26
272	6299330933	2026-01-27
273	6299330933	2026-01-28
274	6299330933	2026-01-29
275	6299330933	2026-01-30
298	6299330933	2026-01-31
299	6299330933	2026-02-01
300	6299330933	2026-02-02
301	6299330933	2026-02-03
302	1022079796	2026-02-03
331	6679299852	2026-02-04
332	6299330933	2026-02-04
333	6299330933	2026-02-05
364	6299330933	2026-02-06
365	1022079796	2026-02-06
366	6299330933	2026-02-07
367	6299330933	2026-02-08
368	5707480536	2026-02-08
369	6299330933	2026-02-09
370	5782116557	2026-02-09
371	6299330933	2026-02-10
372	1022079796	2026-02-10
373	5331446232	2026-02-10
374	6299330933	2026-02-11
375	6613424054	2026-02-11
376	5331446232	2026-02-11
377	6679299852	2026-02-11
378	6299330933	2026-02-12
379	1022079796	2026-02-12
397	8232490379	2026-02-12
398	6299330933	2026-02-13
399	1022079796	2026-02-13
400	8232490379	2026-02-13
401	6299330933	2026-02-14
402	8232490379	2026-02-14
403	5331446232	2026-02-14
404	7809554925	2026-02-15
405	6299330933	2026-02-15
406	5331446232	2026-02-15
407	6299330933	2026-02-16
408	5331446232	2026-02-16
409	6299330933	2026-02-17
410	1022079796	2026-02-17
411	7908177327	2026-02-17
412	7809554925	2026-02-17
413	6299330933	2026-02-18
414	1022079796	2026-02-18
415	8232490379	2026-02-18
416	6299330933	2026-02-19
417	1022079796	2026-02-19
418	8232490379	2026-02-19
419	6299330933	2026-02-20
420	7809554925	2026-02-20
421	1022079796	2026-02-20
422	5331446232	2026-02-20
430	6299330933	2026-02-21
431	6453575758	2026-02-22
432	6299330933	2026-02-22
433	1022079796	2026-02-22
434	6299330933	2026-02-23
435	6453575758	2026-02-23
436	7957396621	2026-02-23
437	7579210619	2026-02-23
438	8232490379	2026-02-23
439	6299330933	2026-02-24
440	1022079796	2026-02-24
441	8351348456	2026-02-24
442	6453575758	2026-02-25
443	6299330933	2026-02-25
444	8232490379	2026-02-26
445	6299330933	2026-02-26
446	8351348456	2026-02-26
463	6299330933	2026-02-27
464	5782116557	2026-02-27
465	6453575758	2026-02-28
466	8351348456	2026-02-28
467	6299330933	2026-02-28
468	1602649791	2026-02-28
469	5331446232	2026-02-28
470	6299330933	2026-03-01
471	8232490379	2026-03-01
472	5331446232	2026-03-01
473	6299330933	2026-03-02
474	6453575758	2026-03-02
475	5331446232	2026-03-02
476	6299330933	2026-03-03
477	1022079796	2026-03-03
478	1022079796	2026-03-04
479	6299330933	2026-03-04
496	6299330933	2026-03-05
529	6299330933	2026-03-06
530	1022079796	2026-03-06
562	5246431453	2026-03-06
563	6453575758	2026-03-07
564	6299330933	2026-03-07
565	6299330933	2026-03-08
\.


--
-- Data for Name: cookies; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.cookies (id, content, updated_at) FROM stdin;
100	# Netscape HTTP Cookie File\n# http://curl.haxx.se/rfc/cookie_spec.html\n# This file was generated by Cookie-Editor\n#HttpOnly_.reddit.com\tTRUE\t/\tTRUE\t1770720269\ttoken_v2\teyJhbGciOiJSUzI1NiIsImtpZCI6IlNIQTI1NjpzS3dsMnlsV0VtMjVmcXhwTU40cWY4MXE2OWFFdWFyMnpLMUdhVGxjdWNZIiwidHlwIjoiSldUIn0.eyJzdWIiOiJ1c2VyIiwiZXhwIjoxNzcwNzIwMjY5LjUzNjY1NSwiaWF0IjoxNzcwNjMzODY5LjUzNjY1NSwianRpIjoicEtLYUdnNERjZG1TelkxcFpVTlZERmgzcHVmYU5RIiwiY2lkIjoiMFItV0FNaHVvby1NeVEiLCJsaWQiOiJ0Ml8xdmk4NG10NWdyIiwiYWlkIjoidDJfMXZpODRtdDVnciIsImF0IjoxLCJsY2EiOjE3NTQ5ODcyOTM0MDYsInNjcCI6ImVKeGtrZEdPdERBSWhkLUZhNV9nZjVVX20wMXRjWWFzTFFhb2szbjdEVm9jazcwN2NENHBIUDlES29xRkRDWlhncW5BQkZnVHJUREJSdVQ5bkxtM2cyaU5lOHRZc1puQ0JGbXdGRHJrbUxHc2lRUW1lSklheXhzbW9JTE55Rnl1dEdOTkxUMFFKcWhjTXJlRkhwYzJvYmtiaTU2ZEdGVzVyRHlvc1ZmbDB0akdGTFlueGpjYnF3MnB1QzZuTWtuTFF2a3NYdlRqTjlXMzl2bXpfU2EwSjhPS3F1bUIzaGxKQ0c0c2ZwaW0zZDlUazU2dEN4YTE5M3FRMnVkNjNLNTkxaXcwTzdlZjZfbHJJeG1YWTJoLUp2dDMxeS1oQTQ4OEx6UHFBRWFzNFVjWmRtUWRfbFVIVUxtZ0pHTUo0dE1JNU1ybDIzOEp0bXZUdjhidEV6OThNLUttTl96V0ROUnpDZUxRcF9IMUd3QUFfXzhRMWVUUiIsInJjaWQiOiJZRHZpT1NVeU1iSnhrU3V4ZXFTaVdGUHFBRVU4MTFrLW9YRVNaSDd6VEJjIiwiZmxvIjoyfQ.LIv9hXIZ9wMsWO0eXv7DEPS2zt0cpCSlkTlaDCRyY84Nag69hydyhYS7W7zxVby-Qi6EODJOhP9n_N8lnk_lKP04zNub-zl0GZsMfdDH3gyBQlcepPdeO2UVDjnX6E3S2onQqMeFC1Sz6RYwRLfY9LHb934ZGk8IS1TWhE5SfMWKHuyCaJyLJMkh8VFqXdsmRJIcvoryDIpY4S8Es1JrzXA8onUV2-FdbPsMf1LxVSh7nsiuwdK-2McTPp3afvLkajYhrlIu3J_y5kR0ny0CvCP_5t4wKa_vEOGAWnyrS2U-tCn78dd_1kBf7-CNq8oL7N4-Jb2St1C7dDtKXXpE9Q\n.reddit.com\tTRUE\t/\tTRUE\t1805069959\tcsv\t2\n.reddit.com\tTRUE\t/\tTRUE\t1770720308\tsession_tracker\tcbbcjejnqfhfndcmoa.0.1770633898168.Z0FBQUFBQnBpYnFxSEhLYk9VbFA5T3FpWUxkYmFtdUVDSE9KbGZlWWZIM2FTb3JkUGtpcE42QW81LUsxbUlsdjk1aEFwY21oTkRQdV9zY21XQ1hsdFhPUkx5SDUwOHpYTkl5dTlhcTJOaUtkQTlPc2tYbGVKMGYwS3lLZ0JhVElJRXljZnl4ZmVwenQ\nwww.reddit.com\tFALSE\t/\tFALSE\t1786185870\tg_state\t{"i_l":0,"i_ll":1770633870567,"i_e":{"enable_itp_optimization":16},"i_b":"p7DVnACJcD8kDEqrjZb1k6Myt8UhBp1zVzMOQCXwprY"}\nwww.reddit.com\tFALSE\t/\tFALSE\t1770720308\treddit_chat_path\t/room/!KQyXyxwETUaE2PEQJRs_6w%253Areddit.com\n#HttpOnly_.reddit.com\tTRUE\t/\tTRUE\t1786272268\treddit_session\teyJhbGciOiJSUzI1NiIsImtpZCI6IlNIQTI1NjpsVFdYNlFVUEloWktaRG1rR0pVd1gvdWNFK01BSjBYRE12RU1kNzVxTXQ4IiwidHlwIjoiSldUIn0.eyJzdWIiOiJ0Ml8xdmk4NG10NWdyIiwiZXhwIjoxNzg2MjcyMjY5LjIxMzY5OSwiaWF0IjoxNzcwNjMzODY5LjIxMzY5OSwianRpIjoiOUxCSk5zN1V0NkptWE5tWVg5SkVtZGxESWVreGtRIiwiYXQiOjEsImNpZCI6ImNvb2tpZSIsImxjYSI6MTc1NDk4NzI5MzQwNiwic2NwIjoiZUp5S2pnVUVBQURfX3dFVkFMayIsImZsbyI6MywiYW1yIjpbInNzbyJdfQ.mvMpLA9adHiAGWym2VAAu0bQa8zku540kTaFU6YVED8OPcHbuY-cJPx_7a_1-Ebsb2BdpvIttFTJMPx-lONMsV_7nuTuDbJCPNUj7NOLFoM20A1evLlRUqDvuVMbYvSIY3A7g47m4LL3IT3MNi9ldUPpL8lG_9Q7YNeU5tBVJjtJkNI-GC0gW3FCmbvN-ABkG2k5lGfd-WLrK8AIokoLTQDoFiO8w5ooek8b09l7_s0YDTJFTiVDoVMbKKZApMomaSos4hbG7VOdIQDj_vgZk1T3Ia55g45ppMDmLP-XNJZbWVhcI1mDw1VRK8R8P4N2lQPndI2FXn7wPR7_i_tl8g\n.reddit.com\tTRUE\t/\tTRUE\t1805069959\tedgebucket\tCZEezjloENWnJUPWu0\n.reddit.com\tTRUE\t/\tTRUE\t1770720308\tcsrf_token\ta55f62ae486b6388e4e52c69f94c767c\nwww.reddit.com\tFALSE\t/\tFALSE\t1805193870\teu_cookie\t{%22opted%22:true%2C%22nonessential%22:true}\n.reddit.com\tTRUE\t/\tTRUE\t1805193869\tloid\t000000001vi84mt5gr.2.1754987293406.Z0FBQUFBQnBpYnFOcWIyM05SNG5TbFZIQ05ZQmpMWHlXejBsSk9ORUxzdjdFWmlsemlmUzZYLUNjMENEellWbDhrTTBuRV9PMGNaS0dVRUFNMzlaeVJIOGFhd3c2VzQ2X2dGZTFrbjlfUmhvTU9FaFh1TUNIVmdvSXRVTVR4QmR5WVR2akRKNDdfckk\nwww.reddit.com\tFALSE\t/\tFALSE\t1770720308\treddit_chat_view\tclosed\n.reddit.com\tTRUE\t/\tFALSE\t1802169870\tt2_1vi84mt5gr_recentclicks3\tt3_1muwhk3\n	2026-02-09 10:45:53.221826
\.


--
-- Data for Name: download_history; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.download_history (id, user_id, username, platform, content_type, url, title, "timestamp") FROM stdin;
1	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNR2Aodcf/	humvee_diesels_fyp_viral_blowthisup_military	2025-12-20 23:50:43.78091
2	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNR2AntKN/	...	2025-12-20 23:54:08.625278
3	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNR2DLmcU/	trio_dance_fyp_niqab_funnyvideo	2025-12-21 00:08:44.231097
4	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNR2Dhths/	_	2025-12-21 00:13:48.929101
5	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNR2D2KLc/	_	2025-12-21 00:38:01.478571
6	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNR2DRHxa/	I_originally_made_this_just_for_a_fun_post_but_after_the_crazy_amoun...	2025-12-21 00:41:22.119294
7	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNR2DLHRs/	CapCut_h264	2025-12-21 00:55:49.219293
8	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNR2DLHRs/	CapCut_h264	2025-12-21 01:04:17.663166
9	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNR2DSQMw/	Vatrushki	2025-12-21 01:04:22.610846
10	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNR2DSy9a/	Bros_Roblox_GF_really_cooked_him_roblox_robloxedit_robloxgaming_g...	2025-12-21 01:11:17.849809
11	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNR2UXae6/	Knight_and_prince_and_67_luziwei_Meme_knight_love_67	2025-12-21 08:19:03.933455
12	1022079796	lendspele	tiktok	Video	https://vm.tiktok.com/ZMDLG3Fog/	TikTok_video_7570954894006291713	2025-12-21 11:05:33.788176
13	6299330933	datapeice	tiktok	Video	https://www.tiktok.com/@superyurchik777/video/7487640180774554887	fake_all_fyp	2025-12-21 13:32:46.448531
14	1022079796	lendspele	tiktok	Video	https://vm.tiktok.com/ZMDLWAtnp/	_	2025-12-21 13:52:04.64128
15	1022079796	lendspele	tiktok	Video	https://vm.tiktok.com/ZMDLWmScH/	zov	2025-12-21 13:52:17.746546
16	1022079796	lendspele	tiktok	Video	https://vt.tiktok.com/ZSPsuxKHT/	cat_brainrot_CapCut_imposter	2025-12-21 20:33:38.821389
17	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNR2spYys/	_	2025-12-22 18:34:06.85309
18	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNR2GdqsL/	2025	2025-12-22 19:04:58.363965
19	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNR2tLjxJ/	Robot_fly_for	2025-12-22 20:02:02.649276
20	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNR2tsm93/	Gimme_6_and_we_re_cool..._blender_b3d_Blender_b3d_Blender3D_3d...	2025-12-22 20:58:48.343136
21	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNR2tXL4V/	creatorsearchinsights_...	2025-12-22 21:01:26.218824
22	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNR2ndmk8/	A_Very_Supernatural_Christmas_Supernatural_Christmas_4K_s...	2025-12-22 22:27:35.831916
23	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNR2nyGx7/	metroexodus_us_...	2025-12-22 23:04:06.076374
24	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNR2nHsCp/	edit_rec_fypp_editor_recomm...	2025-12-22 23:09:06.704457
25	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNR2nubd1/	Metro_2033_edit_metrolastlight_metro2033_metroexodus	2025-12-22 23:11:00.919626
26	1022079796	lendspele	tiktok	Video	https://vm.tiktok.com/ZMDN5L5Ds/	...	2025-12-23 02:46:01.627886
27	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNR2oX5pB/	_	2025-12-23 15:30:50.161571
28	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNR2o9p5U/	TikTok_video_7586607616923618580	2025-12-23 15:47:01.695359
29	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNR2oaVHY/	TikTok_video_7586630446818151710	2025-12-23 15:48:38.792404
30	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNR2oQmbu/	D_kujeme_eskoslovensku_za_vyrobenou_serii_elektrickych_lokomotiv_S2...	2025-12-23 15:51:05.447685
31	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRjer5X3/	ua_ukraine_russia_ru	2025-12-23 19:31:13.679813
32	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRjdHfyC/	._fyp	2025-12-23 21:18:16.362633
33	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRjdXUoq/	newpeople	2025-12-23 22:10:52.898832
34	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRjd7hs2/	_	2025-12-23 22:14:55.968615
35	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRjd3P7n/	durov_telegram_paveldurov	2025-12-23 22:15:45.113366
36	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRjd3o77/	25_hassleo...	2025-12-23 22:15:58.289766
37	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRjdw79P/	_	2025-12-23 22:16:24.016751
38	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRjdwd63/	cod_codmw3_meme_telegr...	2025-12-23 22:17:20.61538
39	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRjdE37g/	fyp_recommendations	2025-12-23 22:18:07.819803
40	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRjdxnww/	freedurov_freepavel_fyp_viral_trending_challenge_funny_pov_...	2025-12-23 22:18:54.593638
41	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRjdWsg6/	thatypeshit	2025-12-23 22:25:12.501484
42	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRjRWN8b/	chat_cat_humour_ringcam_ia	2025-12-24 00:11:23.687806
43	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRjRQtee/	spn_...	2025-12-24 00:12:02.488716
44	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRjkbNDv/	exodus_metroexodus_Game_metro_metroredux...	2025-12-24 21:50:23.647157
45	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRjkf1eH/	@VIKING_METROLASTLIGHT_...	2025-12-24 21:51:54.3314
46	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRjBeasg/	Route_66_route66_usa_america_roadtrip_travel	2025-12-24 22:20:32.059857
47	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRjBNtyn/	Santa_died_for_a_sec_santa_flightradar24_ukraine_missile	2025-12-24 22:26:44.370742
48	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRjkwswm/	lick_lick_Just_a_little_fox_doing_fox_things~_Gotta_lick_my_fur_ke...	2025-12-24 23:47:06.505982
49	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRjBs7fP/	nie_jest_to_jaki_super_hiper_edit_jak_ostatnio_bo_nie_mia_em_tak_du_...	2025-12-24 23:57:26.835598
50	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRjBSvGx/	Prosz_zostaw_follow._poprzednie_konto_zosta_o_zhakowane._Dzi_kuj_k...	2025-12-25 00:10:43.883677
51	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRjBBP5u/	Prosz_zostaw_follow._poprzednie_konto_zosta_o_zhakowane._Jestem_za_a...	2025-12-25 00:16:41.170156
52	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRjBfq6W/	MouseDataQueueSize_KeyboardDataQueueSize_Win32PrioritySeparation_...	2025-12-25 01:00:33.514801
53	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRjBH5f9/	cyberpunk_cyberpunk2077_cyberpunkedit_cyberpunk2077edit_cyberpu...	2025-12-25 01:08:09.759785
54	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRjPCTqJ/	bcs_bettercallsaul_bettercallsauledit_saulgoodman_jimmymcgill_t...	2025-12-25 21:55:09.168988
55	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRjPfnM1/	Route_66_route66_country_roadtrip_viral_fyp	2025-12-25 22:06:40.669
56	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRjPavMn/	...	2025-12-25 22:14:25.529527
57	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRjPXCx9/	csharp_python_java	2025-12-25 22:42:14.291159
58	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRjHucbV/	...	2025-12-26 11:31:14.977985
59	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRjCAjhu/	Meme_MemeCut_gta	2025-12-26 18:38:28.570027
60	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRj4N7T3/	...	2025-12-26 21:50:06.135029
61	1022079796	lendspele	tiktok	Video	https://vm.tiktok.com/ZMDFwER8G/	it	2025-12-26 22:02:08.722207
62	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRjXWoFf/	TikTok_video_7569593347694808342	2025-12-26 22:24:53.341836
63	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRjXcVGe/	_	2025-12-26 22:39:51.757393
64	1022079796	lendspele	tiktok	Video	https://vm.tiktok.com/ZMDY8p7CF/	ManyGames	2025-12-27 10:04:58.206789
65	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRjscc5C/	creatorsearchinsights_...	2025-12-27 13:04:25.271589
66	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRjGep6p/	gaidulean	2025-12-27 13:19:10.265399
67	1022079796	lendspele	tiktok	Video	https://vm.tiktok.com/ZMDYrpEm5/	...	2025-12-27 18:37:07.188703
68	6299330933	datapeice	youtube	Video	https://youtu.be/CQ3tUyV4aTI	Невероятно депрессивная японка снова курит_CQ3tUyV4aTI_h264	2025-12-27 21:20:46.640214
69	6299330933	datapeice	youtube	Music	https://youtu.be/Jb0of6t6vmY	Японка курит под пост-панк на стриме._Jb0of6t6vmY	2025-12-27 21:24:21.520903
70	5331446232	True_Jentelmen	youtube	Video	https://youtu.be/IhXSShyb19Y	OiOi111 Forsaken animation forsaken animation forsakenroblox_IhXSShyb19Y_h264	2025-12-27 21:24:38.500673
71	6299330933	datapeice	youtube	Music	https://youtu.be/We_DLCYDaYw	Metallica - Ride The Lightning HD_We_DLCYDaYw	2025-12-27 21:25:39.686548
72	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRj7bkWb/	bocchi the smoke🌿 #fyp #preset #alightmotion #drf411 _7335013175215082757_8ae9	2025-12-27 21:41:51.855921
73	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNR2DLHRs/	#CapCut #киевскаярусь #вещийолег #константинополь _7299509270612036870_908b	2025-12-27 21:43:55.510568
74	6299330933	datapeice	youtube	Video	https://youtu.be/zugV9moE28A	Жириновский о походе в гей-клуб_zugV9moE28A_h264	2025-12-27 21:47:53.608049
75	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRj7q9tK/	На 60 тищ лайков прода 😉#рекомендации #дослободыдоеду #fyp #rge #слоб..._7560360013307350328_0d58	2025-12-27 21:53:41.889545
76	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRjve1Sq/	Тоже перезалив(этому видео 4 месяца) #доза #сверхъестественное #спн #..._7588627349420264711_625d	2025-12-27 21:54:56.027345
77	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRjv15eT/	volvo 850 strikes again #volvo #t5 #bb234T5  #bmw #850 _7585557998697860374_6584	2025-12-27 22:01:38.883053
78	6299330933	datapeice	instagram	Video	https://www.instagram.com/reel/DRMZS4DgBW1/?igsh=MW5rcG9iNHRsdnp0NQ==	Video by hbomaxau_DRMZS4DgBW1_h264	2025-12-27 22:04:50.108567
79	6299330933	datapeice	youtube	Music	https://youtu.be/DVOImtJY7po	Ride The Lightning Remastered_DVOImtJY7po	2025-12-27 22:10:06.860337
80	6299330933	datapeice	youtube	Video	https://youtu.be/qXo2GwzksvI	Terry Davis dances to hava nagila_qXo2GwzksvI_h264	2025-12-27 22:13:24.235833
81	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRjvm7QT/	A new part of drinking water _7588564846594018590_9f8f	2025-12-27 23:31:14.9645
82	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRjvPYMC/	SpongeBob playing smell like teen spirit 🔥😭 #spongebobsquarepants #sp..._7569652487016189239_9060	2025-12-27 23:34:54.165156
83	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRjvHaLn/	who will gru be tonight that’s the question… ｜ #despicableme #despica..._7586057527960374541_7d92	2025-12-27 23:44:25.644938
84	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRjvnXst/	Туалет под туалетом #рек #юмор как тебе такое Илон Маск？_7588106045990391061_9f46	2025-12-28 00:03:09.108807
85	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNR2DLHRs/	#CapCut #киевскаярусь #вещийолег #константинополь _7299509270612036870_e3fd	2025-12-28 00:12:14.306103
86	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRjvsfrn/	#peppapig #cartoon #fpy #fortou #tiktok_7588076811003661570_86ca	2025-12-28 00:17:17.986724
87	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRjvtbUb/	#mimi #typh #typhmimi _7587725868663835916_60df	2025-12-28 00:23:55.253967
88	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRjvcaRb/	#Evangelion #Евангелион #eva #евангелион #Ева #Евангелион _7588575309922831629_528e	2025-12-28 00:27:23.648529
89	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRjvs8TR/	Разоблачение илонмаск россия cyberpunk2077 рек новости _7584152504825449735_h264	2025-12-28 00:46:57.747006
90	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRjvgnw6/	#pantera #metal #trashmetal #metalhead #metalcore _7562122351358381343_2e5e	2025-12-28 00:54:20.556676
91	6299330933	datapeice	youtube	Video	https://youtu.be/Ofz29Vn10sQ	Нарезка фраз Олега Тинькова_Ofz29Vn10sQ_h264	2025-12-28 01:10:36.965567
92	6299330933	datapeice	youtube	Video	https://youtu.be/Ofz29Vn10sQ	Нарезка фраз Олега Тинькова_Ofz29Vn10sQ_h264	2025-12-28 01:12:22.921341
93	6299330933	datapeice	youtube	Video	https://youtu.be/PF8d1r-jTN8	Сомнительно но окей_PF8d1r-jTN8_h264	2025-12-28 01:13:28.893816
94	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNR2DLHRs/	#CapCut #киевскаярусь #вещийолег #константинополь _7299509270612036870_e96c	2025-12-28 12:06:04.452678
95	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNR2DLHRs/	#CapCut #киевскаярусь #вещийолег #константинополь _7299509270612036870_c1cd	2025-12-28 12:55:09.875465
96	6299330933	datapeice	youtube	Video	https://youtu.be/Ofz29Vn10sQ	Нарезка фраз Олега Тинькова_Ofz29Vn10sQ_h264	2025-12-28 12:56:39.726036
97	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRjTo4yF/	Смотрите что нашел_7588513966427475211_b32e	2025-12-28 13:09:08.822514
98	1022079796	lendspele	youtube	Video	https://youtu.be/YwGn_FAXpeg?si=79xGmBhQuT0PakS6	Как Джесси Пинкман менял свою внешность и поведение в сериале Во все тяжкие_YwGn_FAXpeg_h264	2025-12-28 13:19:39.801449
99	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRjw2Hrn/	it’s november 5th .. 💔 ｜  i wanted to try a diff style but this is sh..._7569366399089446174_9c9d	2025-12-28 13:34:05.977465
100	6299330933	datapeice	youtube	Video	https://youtu.be/YwGn_FAXpeg?si=79xGmBhQuT0PakS6	Как Джесси Пинкман менял свою внешность и поведение в сериале Во все тяжкие_YwGn_FAXpeg_h264	2025-12-28 13:41:08.81973
101	1022079796	lendspele	youtube	Music	youtube.com/watch?v=Ucrcz77bRZo	Rain Spotter_Ucrcz77bRZo	2025-12-28 14:06:32.540892
102	1022079796	lendspele	youtube	Music	youtube.com/watch?v=UmIsYjoFoP4	snowfall feat. mt. fujitive_UmIsYjoFoP4	2025-12-28 14:09:42.48752
103	1022079796	lendspele	youtube	Music	https://www.youtube.com/watch?v=B1ElJGOfUuc&list=RDB1ElJGOfUuc&start_radio=1	Snowfall_B1ElJGOfUuc	2025-12-28 14:12:16.95575
104	6299330933	datapeice	youtube	Video	https://youtu.be/YT0hDqzYPRU	TOP CRINGE MOMENTS OF VITALIK BUTERIN Super awkward..._YT0hDqzYPRU_h264	2025-12-28 19:27:08.734854
105	5707480536	Paranollk	tiktok	Video	https://vm.tiktok.com/ZNR61aWrj/	#кейон #качанчик🥬 #тгк_в_описании #k_on #аниме _7564616659617516822_e14c	2025-12-28 22:30:00.649137
106	5707480536	Paranollk	tiktok	Video	https://vm.tiktok.com/ZNR6JQDbg/	House of villians ⧸⧸ #velocityedit #villains #aftereffectsedits #velo..._7496560341266992406_79b8	2025-12-29 01:43:02.256007
107	6299330933	datapeice	youtube	Video	https://youtu.be/YT0hDqzYPRU	TOP CRINGE MOMENTS OF VITALIK BUTERIN Super awkward..._YT0hDqzYPRU_h264	2025-12-29 12:40:43.418206
108	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNR629LdD/	TikTok video 7588963937509543180_7588963937509543180_h264	2025-12-29 14:38:31.677425
109	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNR6j9YhX/	pov： never ever use a sitting toilet in Berlin🤣🤣 #livioundthomas #vir..._7584077598951591190_e2e1	2025-12-29 15:40:03.442348
110	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNR6jq15r/	At least the ambulance is already there… #charlykirk #crash#cops #fun..._7583701233278455062_0282	2025-12-29 15:48:52.005708
111	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNR6MB5DP/	#fyp#fypppp#anime#zootopia2#famous_7586754013413018910_c394	2025-12-29 17:23:45.25994
112	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNR6MrE9x/	Рок группа ＂Невменяй＂ Наши песни на всех площадках!  ТЛГ： НевиNew ＊Сс..._7588884284883111181_6e88	2025-12-29 17:27:50.903221
113	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNR6hfJe3/	#обучение #образование #gpt #нейронка #университет_7589338965409402144_12d8	2025-12-29 18:38:32.267118
114	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNR6hV1FE/	I top my last costume every year but this might be the final boss #ha..._7567520297272888583_322e	2025-12-29 19:00:19.183041
115	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNR6hsr9X/	Это Non stop ) #nonstop#stalker2heartofchernobyl#stalkercallofpripyat..._7570303202558496011_6c63	2025-12-29 19:00:45.547486
116	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNR6hvEnq/	Cat shows doggy how to do offroad #catdogbesties #offroadtiktok #funn..._7588478117769989390_dd6c	2025-12-29 19:18:28.65173
117	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNR6hVT58/	Ranking Craziest Farts 😂 #prank #fart #ranking #charcmusic #fyp _7567944111899053343_2419	2025-12-29 19:26:57.280467
118	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNR6kSAku/	A new part of my cooking ｜ 10_7584177676978572575_8675	2025-12-29 20:18:12.024067
119	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNR6kk7we/	УГРОЗА ЧЕЛОВЕЧЕСТВУ 😳 Больше новостей у меня в телеграм： УТКА_7588890367232199992_8cf3	2025-12-29 20:21:09.565661
120	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNR6kCeLH/	Majster Grzesiek melduje się na robocie! 🧰 Trochę krzywo？ To się „dop..._7588713407512153366_9f43	2025-12-29 20:40:44.519393
121	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNR6kmak4/	Больше таких новогодних аватарок по Сталкер 2 находится в моем Тгк - ..._7578946062543555896_c9f3	2025-12-29 20:49:20.798843
122	6299330933	datapeice	youtube	Music	https://youtu.be/X8OeBZQn3_w	Creeping Death Remastered_X8OeBZQn3_w	2025-12-29 20:57:53.752681
123	6299330933	datapeice	instagram	Video	https://www.instagram.com/reel/DSx-uY8EaEH/?igsh=MWRldnBlajR3MnA4aQ==	Video by _stelkai__DSx-uY8EaEH_h264	2025-12-29 21:05:10.729834
124	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNR6kbbhT/	“I HAVE DIVINE INTELLECT!” - Terry Davis  #terrydavis #templeos #terr..._7588986344303627542_e396	2025-12-29 21:15:02.715672
125	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNR6k7qBC/	Легендарное время.... #Kreosan #KREOSAN #Креосан #Припять #Припять198..._7556196532484132103_07e9	2025-12-29 21:21:48.728259
126	1022079796	lendspele	tiktok	Video	https://vm.tiktok.com/ZNR6kpD4e/	#myfavoritegame #indie #fyp #hollowknightsilksong #hollowknight _7584088960213863701_d6d1	2025-12-29 21:24:18.053911
127	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNR6kvQrH/	#креосан #Чернобыль #эдит _7586808948087328056_8803	2025-12-29 21:28:53.780037
128	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNR6BLj6d/	Вот и решена проблема, хаха. #заболевание #онкология #рак #волосы #бо..._7589282851103804680_ebe3	2025-12-29 22:02:02.233435
129	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNR6BHK5Q/	kendall😭😭😭roy😭😭😭 #kendallroy #succession #successionhbo #kendallroyed..._7492129921473596694_a8a7	2025-12-29 23:17:39.260278
130	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNR6SLrGp/	Pavel Durov edit😉 #paveldurov #viral #fyp #elbruso #edit #telegram #t..._7588907983644445964_fe52	2025-12-29 23:28:30.557101
131	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNR6S26tv/	Це я перевдітий, це не той актор з фільму. Знаю дуже крутий грим вийш..._7573245282385759500_a7d4	2025-12-29 23:31:21.868588
132	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNR6S6Q2C/	Goated Duo #siliconvalley #erlichbachman #richardhendricks #siliconva..._7380407987174755626_ab1e	2025-12-30 00:16:03.951855
133	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNR6BtAQu/	Китаец создал гениальное приложение🔥 ｜ Кремниевая Долина ｜ #фильмы #к..._7449642977602833697_98f4	2025-12-30 00:17:31.392402
134	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNR6S8hFB/	Кремниевая долина 3 ч. #кремниеваядолина #комедия #сериал #силиконова..._7392175918820642053_efde	2025-12-30 00:18:08.696196
135	1022079796	lendspele	tiktok	Video	https://vm.tiktok.com/ZMD2hApoq/	😔#fyp #moldova🇲🇩 #chisinaumoldova🇲🇩 #дизайнногтей #дизайн _7574320123851328779_beb3	2025-12-30 10:39:31.719603
136	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNR6ueomj/	TikTok video #7577332543825939767_7577332543825939767_6b59	2025-12-30 14:50:44.89766
137	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNR69r82q/	merry Christmas #christmas #mimi #typh #mimityph #presents _7589541420961254677_0a79	2025-12-30 18:14:42.538141
138	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNR6xUCxD/	Obserwuj po więcej. #polskiedrogi #viral #dlaciebie _7569653999050181910_dcec	2025-12-30 19:03:20.488113
315	6299330933	datapeice	youtube	Video	https://youtu.be/YOtf5zDZc5s	Jingle Bells_YOtf5zDZc5s_h264	2026-01-15 22:03:32.256823
139	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNR6x9GKV/	Нового года не будет, Дед Мороз принял Ислам! #врек #Ислам #новогонеб..._6792073007046167813_1b24	2025-12-30 20:27:10.267002
140	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNR6xTBus/	#новыйгодбудетдедморозпринялхристианство#дедмороз#смурфик#рекоменндац..._7308799997867330849_2eb7	2025-12-30 20:27:26.930463
141	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNR6xnExb/	я думала умею по польски балакать_7589413326287834390_954c	2025-12-30 20:38:46.025359
142	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNR6Q6WeB/	SOMETHING IS MISSING, BUT WHAT？  #anime #wibu _7579589308819049748_4cbe	2025-12-30 20:43:41.483455
143	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNR6QydX8/	jugg edit Minecraft #добрыня #jugg #juggedit #minecraft #edit #minecr..._7589006904454614292_5085	2025-12-30 20:45:43.291095
144	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNR6QH4HE/	Class 37 starts up in a cold morning. #trains #fyp #TrainSpotting #st..._7577553354096659734_8ce2	2025-12-30 21:48:16.660362
145	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNR6QCX8M/	АукцЫон — Дорога #metroexodus #metrolastlight #metro2033 _7584054464647040311_d217	2025-12-30 21:56:18.099159
146	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNR6CsDRh/	#arasaka #arasakatower #cyberpunk #cyberpunk2077 _7589348747856153864_77c8	2025-12-31 00:42:49.719498
147	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNR6gB5Ge/	Happy new year to everyone  #supernatural#happynewyear#jaredpadalecki..._7589688761022156039_dba3	2025-12-31 11:30:08.516278
148	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNR6paTe8/	TARANTALLEGRA é o nome de um feitiço que força as pernas de uma pesso..._7563779493844880647_2d9a	2025-12-31 12:21:30.213556
149	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNR6GXnko/	#ахахаха #миньон #FPV #DRONE #rec #безхештегов #кзн #ПВО_7589753164396629255_c708	2025-12-31 14:29:35.417063
150	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNR6GcXn2/	It has a good tone surprisingly #deftones #numetal #chinomoreno #adre..._7589096313145363743_df7b	2025-12-31 14:31:09.778077
151	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNR6GvHtJ/	Те самые распросы за столом😭 #роблокс #roblox #реки _7584105098117123341_630a	2025-12-31 14:35:04.154047
152	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNR6tN7CG/	#ets2 #s24u #samsung _7589760040022592790_b90b	2025-12-31 15:29:39.068521
153	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNR6nFHgY/	Праздник праздник... #рецептпеченья #рек #fyp #Рекомендации #Интерны ..._7589942798590446904_5e08	2025-12-31 17:07:02.222317
154	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNR6nAYkW/	Life isn’t easy for Kendall after season 4 💀 #succession #kendallroy ..._7300563911126813985_eecc	2025-12-31 17:16:49.245843
155	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNR6nnqGh/	#kendallroy #succession #kendallroyedit #fyp #foryou _7571557914226461959_c3c2	2025-12-31 17:32:32.099559
156	6299330933	datapeice	instagram	Video	https://www.instagram.com/reel/DRMZS4DgBW1/?igsh=MW5rcG9iNHRsdnp0NQ==	Video by hbomaxau_DRMZS4DgBW1_h264	2025-12-31 17:40:22.278351
157	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNR6nTPPd/	TikTok video #7590007494848613652_7590007494848613652_2555	2025-12-31 18:24:13.460696
158	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNR6WLtwu/	TikTok video #7590038904451943700_7590038904451943700_ac21	2025-12-31 18:29:42.922395
159	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNR67KBFE/	How it feels going to school with no sleep｜ CREDIT YOUTUBE： GetOutDud..._7584088833973816599_294b	2025-12-31 21:34:35.621188
160	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNR67GMaW/	ГАЗ？ #вангоу _7590083990644641044_da70	2025-12-31 21:44:37.495211
161	5707480536	Paranollk	tiktok	Video	https://vm.tiktok.com/ZNR67qayV/	6 часов делал, надеюсь норм ｜｜ ORIGINAL CONTENT #ghostoftsushima #jin..._7545587792101788934_4475	2025-12-31 22:09:52.760114
162	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNR67wp4H/	Der epische Kampf gegen Rockwood genießt es vorallem der Schluss 🧙🔥#h..._7577029591278030102_3bd8	2025-12-31 22:21:36.997299
163	5707480536	Paranollk	tiktok	Video	https://vm.tiktok.com/ZNR6vFnxG/	Honour #edit #fyp #ghostoftsushima #jinsakai #f #dontletthisflop #don..._7507050520691870998_62d9	2025-12-31 23:27:54.299065
164	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNR6v2vta/	nostalgic year it was. ｜｜ #edit #nostaliga #2025 #fyp _7588116278045609239_f7f8	2025-12-31 23:39:12.305903
165	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNR6vxTTs/	TikTok video #7588915012148858143_7588915012148858143_1d7c	2026-01-01 00:49:29.444435
166	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNR6vsThD/	Belarus Edit🇧🇾 #based #edit #lukashenko #belarus @[🇧🇾]𝐂𝐫𝐮𝐧𝐜𝐡⚔️ @𝐀𝐛𝐮 𝐀..._7590188577213041940_a455	2026-01-01 00:53:18.579261
167	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNR6vbEQM/	#CapCut #femboy #agartha #astolfo #judaism _7565313310237723926_ad8b	2026-01-01 01:10:19.599648
168	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNR6K6SXG/	From a small bakery to the whole world 🌍❤️ We never planned this. We ..._7586637274427821334_b723	2026-01-01 17:52:45.960745
169	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRM1kBjP/	Нейронка Илона Маска vs Илон Маск _7575921326213451030_51f7	2026-01-01 23:07:26.259841
170	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNR6oo1Sf/	nie martw się… #viral _7586277472417762582_fa53	2026-01-01 23:13:03.98395
171	6299330933	datapeice	instagram	Video	https://www.instagram.com/reel/DPL3nELkojM/?igsh=bGN6azc0d3N0eWMw	Video by raj.aitech__DPL3nELkojM_h264	2026-01-02 00:25:21.389262
172	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRMLbcvQ/	Update drivers and firmware to get the best performance. #datacenter ..._7590139879753911565_5b65	2026-01-02 13:03:02.961967
173	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRMLAsAr/	#газпром #ркн#джонисильверхенд #киберпанк2077 #свобода _7460344442558369054_04b4	2026-01-02 13:15:37.323538
174	1022079796	lendspele	tiktok	Video	https://vm.tiktok.com/ZMDjV2UeT/	my favs 😭🫶#thefragrantflowerbloomswithdignity #wagurikaoruko #tsumugi..._7527107441654238471_4d68	2026-01-02 17:39:11.08598
175	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRMYuHvn/	Twitch： evelone2004 #evelone #ivanzolo2004_7590749596696071480_89d7	2026-01-02 17:50:19.07726
176	6299330933	datapeice	instagram	Video	https://www.instagram.com/reel/DS-WmUrjCzX/?igsh=MWxubTYzOW5qcG5uNw==	Video by avishkaarrrr_DS-WmUrjCzX_h264	2026-01-02 18:21:49.105943
177	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRM6PNfS/	Дим Димыч — один из главных персонажей мультсериала «Фиксики», обычны..._7589062798831914262_1f27	2026-01-02 23:50:08.755104
178	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRMACmuV/	дави на газ громче бас #ikea #ai #sora #sora2 #wow #reki #fyp #elbrus..._7590928667342015774_6529	2026-01-03 12:39:47.307433
179	6299330933	datapeice	youtube	Video	https://youtube.com/shorts/ZNojwCP92dg?si=59hpJX7odGj8j0jb	Полицейский подумал что его уволят но лейтенант сделал другое shorts_ZNojwCP92dg_h264	2026-01-03 15:48:02.381259
180	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRM5V9mJ/	Saul ⚖️ & Hitori 🎸 ｜｜ Bocchi the rock! ｜｜ Better call Saul ｜｜ EDIT ｜｜..._7588876410991774987_da62	2026-01-04 00:08:27.797429
181	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRM5x3gj/	ХАХАХААХ ПРОСТИТЕ ПЖЛСТ  #samwinchester #deanwinchester #сериал #supe..._7590848299565894923_7daa	2026-01-04 00:51:12.348204
182	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRM5tUtG/	You don’t rush someone who knows exactly what they’re doing 😤 A 2025 ..._7589110684554775821_1152	2026-01-04 00:58:14.173877
183	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRMmCv4J/	crafting the GOLDEN AGE 🔥_7589735972003171639_d3cd	2026-01-04 10:04:12.306481
184	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRMmb8ES/	TikTok video #7591395953588948246_7591395953588948246_7c24	2026-01-04 10:10:45.35286
185	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRMmabqF/	Breaking： Donald Block abducts Emeraldzuelas President! (This fr btw)..._7591281580493016342_1195	2026-01-04 10:13:52.054597
186	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRMCbRst/	p1000 install in lenovo m720q #movie #amd #5090 #pcbuild #pcrepair #m..._7464117584506473734_6487	2026-01-04 22:05:14.932926
187	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRMCbRst/	p1000 install in lenovo m720q #movie #amd #5090 #pcbuild #pcrepair #m..._7464117584506473734_517e	2026-01-04 22:05:33.864375
188	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRMCWLNG/	W końcu coś po polsku. 😜 . . . #harrypotteredit #harrypotterpolska #s..._7583409953503907074_a4af	2026-01-04 23:17:53.232088
189	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRMCcf25/	lost in this song by Jensen Ackles😌#jensenackles #drowning #radiocomp..._7542465523615911199_7a9b	2026-01-04 23:30:46.316418
190	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRMXFk8g/	31.10.1981 {＊} ｜｜ Lili-#ENEJ ‎‎‎‎‎‎‎‎‎‎ᅠ‎‎‎‎‎‎‎‎‎‎ᅠ‎‎‎‎‎‎‎‎‎‎ᅠ‎‎‎‎‎‎‎..._7567387939341258006_c0d5	2026-01-05 00:01:06.585248
191	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRMX1hH1/	Jak zbudują to kasyno w Emiratach to jedziemy tam! Proszę zostaw foll..._7591585349730585878_e88e	2026-01-05 00:02:40.199441
192	1022079796	lendspele	tiktok	Video	https://vm.tiktok.com/ZMD6qk1Ld/	#joegoldbergedit#актив #joegoldbergedit#joegoldbergedit#joegoldberged..._7588819094225472775_2568	2026-01-05 09:32:02.117746
193	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRMGedUo/	окак вот так и наперекосяк 🙂‍↔️ #окак #сверхъестественное #supernatur..._7585666939754745099_a1c5	2026-01-05 13:19:49.184476
194	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRMGEj2G/	тгк： обществознание и котики 🐈‍⬛ #егэ #огэ #оик #стадикэтс #обществоз..._7591523972693462279_ea38	2026-01-05 14:10:28.4937
195	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRMtjt4v/	#meme #lol #wtf #рек #пуститеврек _7591870981526916382_45c2	2026-01-05 14:25:59.223833
196	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRMtNSD7/	Народная песня Белоруссии-Касіў Ясь канюшыну . (Люблю вас Белорусы ❤️..._7590430347121200397_e1c8	2026-01-05 14:42:51.157385
197	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRMtXGNK/	#Aptweld #evolution _7591131889105128716_67f4	2026-01-05 15:18:20.37375
198	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRMnMnsh/	IM THE ELDEST BOY #succession #successionhbo #kendallroy #ltotheog #j..._7296215036526185760_9a65	2026-01-05 15:23:13.068902
199	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRMv9o67/	Лyдка колдуна  корольишут киш горшок куклаколдуна горшокжив _7591948277076053268_h264	2026-01-05 19:38:26.72009
200	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRMvpxSe/	я обожаю свои концерты_7591849769832598805_h264	2026-01-05 20:56:58.747523
201	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRMvQPAn/	6-7 запретили в США  67 рекомендации вреки fypシviral usa _7591812478028303636_h264	2026-01-05 21:12:39.907219
202	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRMcMor9/	Когда доверила мужу выбор занавески в ванную муждизайнервдуше альт..._7591171518374169878_h264	2026-01-05 21:15:57.786545
203	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRMcRBsh/	Надо было про Алешку снимать - было бы не так больно _7591472303754480903_h264	2026-01-05 21:33:02.677246
204	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRMckr2k/	 meme  _7591488713822096673_h264	2026-01-05 21:55:21.127958
205	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRMcd1u4/	Ranking arab backpack prank arabfunnymoments prank rankingbackpack _7583035487342972182_h264	2026-01-05 22:01:01.929812
206	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRMcrp1y/	roblox fyp robloxfyp voicechat  trolling _7584649786880511287_h264	2026-01-05 22:14:32.601615
207	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRMcrp1y/	#roblox #fyp #robloxfyp #voicechat  #trolling _7584649786880511287_fe12	2026-01-05 22:16:04.201368
208	6299330933	datapeice	instagram	Video	https://www.instagram.com/reel/DTINOe4kk0V/?igsh=Z2EzN240Y3ZoNWJl	Video by 0x1security_DTINOe4kk0V_h264	2026-01-05 22:40:18.431552
209	6299330933	datapeice	instagram	Video	https://www.instagram.com/reel/DSs_CS9klQc/?igsh=aGJ3aGx1N3hja2Fn	Video by 2xfarhad__DSs_CS9klQc_h264	2026-01-05 22:53:21.756443
210	6299330933	datapeice	instagram	Video	https://www.instagram.com/reel/DRvB-l7jAGQ/?igsh=NWJham9maXBwd3d1	Video by alwayswithintent_DRvB-l7jAGQ_h264	2026-01-05 22:57:17.509121
211	6299330933	datapeice	instagram	Video	https://www.instagram.com/reel/DSpM1QpDPMX/?igsh=MWZ6NTRjcTB4b2p4bQ==	Video by lolek_2222_DSpM1QpDPMX_h264	2026-01-05 23:25:25.897726
212	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRM3AMEx/	кто не понял, это кас#супернатуралы #сверхи #сверхъестественное #каст..._7591923264348261639_4624	2026-01-05 23:25:33.194664
213	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRr8UWuv/	5 часть острова Эпштейна! Скоро финал!？_7591895140005088514_b805	2026-01-06 19:08:52.044413
214	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRMEg2nV/	My secret is that I hardcode all of my secrets... . . . #softwareengi..._7591741111211773206_6518	2026-01-06 19:08:57.91246
316	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRkrTp9u/	#fyp #goth #gothgirl #fuck #foryou 	2026-01-15 22:24:16.208511
215	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRr8gkFg/	IShowSpeed got so excited finally coming back to his home 😭❤️‍🩹 #isho..._7591464872358006038_8fea	2026-01-06 20:21:39.341933
216	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRrLayvj/	Мне плевать что вы подумаете, я в любом случае буду сиять! тгк：gaidulean_7592336684793187591_7bcb	2026-01-06 21:38:53.189777
217	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRrNSamb/	sorry if it’s a bit off beat 🙏🏻 it took me ages to finish 😭 #foryou #..._7592216772711943446_a078	2026-01-06 23:55:25.096317
218	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRrSxLde/	Meet the @exteraGram ｜ тгк： kstaaqs ＜3 #graphicdesign #telegram #диза..._7590871156530433336_8e53	2026-01-07 16:41:18.121451
219	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRrSBDTF/	@nyan.mp3 - я занят ｜ тгк： kstaaqs ｜ lyrics edit в стиле интерфейса с..._7581181194004466955_acb5	2026-01-07 16:41:53.26485
220	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRrSxLde/	Meet the @exteraGram ｜ тгк： kstaaqs ＜3 #graphicdesign #telegram #диза..._7590871156530433336_7915	2026-01-07 16:41:54.394895
221	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRrAcowg/	The Beauty of supernatural #fyp #castiel #supernatural #viral #deanwi..._7584068671086103810_c9c1	2026-01-07 18:30:00.624555
222	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRrAVGXS/	Survival in forest #bushcraft #camping #outdoors _7585901247207623966_ba64	2026-01-07 18:31:40.320193
223	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRrDNowA/	тг в шапке профиля 😁_7592532301486034206_639a	2026-01-07 18:45:54.71517
224	6299330933	datapeice	instagram	Video	https://www.instagram.com/reel/DSF5EptiEL1/?igsh=eG9hdTVjZGd4c3Jx	Video by brutalpoland_DSF5EptiEL1_h264	2026-01-07 20:24:36.202401
225	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRry85vD/	Season 5＞ All ｜｜ {4K} Supernatural best season #deanwinchester #samwi..._7591946993304423700_40f2	2026-01-07 22:09:28.039165
226	6299330933	datapeice	instagram	Video	https://www.instagram.com/reel/DQEBOFNjH_2/?igsh=MTZobWJ6MjNjMHZ1cA==	Video by victimofpleasure_DQEBOFNjH_2_h264	2026-01-08 07:57:38.200863
227	6299330933	datapeice	instagram	Video	https://www.instagram.com/reel/DP7RV3njeBD/?igsh=MW9jdzl2enBzMzYyNA==	Video by nateriversoff_DP7RV3njeBD_h264	2026-01-08 08:15:11.59122
228	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRrugJat/	#venezuela🇻🇪 #donaldtrump2024 #instagramstories #tiktokn #unitedstates _7592497826039483670_7bb6	2026-01-08 12:12:52.097509
229	6299330933	datapeice	instagram	Video	https://www.instagram.com/reel/DTJAyH4EgBu/?igsh=MTNyZ3I5OXRhbGM1OA==	Video by seattlebuiltpcs_DTJAyH4EgBu_h264	2026-01-08 12:14:15.094659
230	6299330933	datapeice	instagram	Video	https://www.instagram.com/reel/DSQPtN2gcOi/?igsh=MmwwcDNxdjg4OGQ2	Video by crackalackinttv_DSQPtN2gcOi_h264	2026-01-08 12:21:00.139929
231	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRruXgLo/	#venezuela🇻🇪 #donaldtrump2024 #instagramstories #tiktokn #unitedstates _7592497826039483670_7d5f	2026-01-08 12:21:12.685105
232	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRrC9gmA/	легенда дмитрокомаров едит комаровдмитрий комаров fupシ _7576724176631762188_h264	2026-01-08 18:50:58.522679
233	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRrCa1E7/	мирнаизнанку kotaiter_7055590834732928257_h264	2026-01-08 19:03:02.830384
234	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRrCGeqx/	наввипередки світнавиворіт комаров дімакомаров мирнаизнанку едіт..._7488408025351408951_h264	2026-01-08 19:06:02.57543
235	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRrCP9sT/	Ассимиляция идёт полным ходом  Комаров эдит dinoaponchik Capcut e..._7486453418043690295_h264	2026-01-08 19:06:41.43341
236	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRrCf7as/	Мир наизнанку  мирнаизнанку эдит дмитрийкомаров дмитрий комаров..._7478723827875220752_h264	2026-01-08 19:07:18.038455
237	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRrXNM5h/	и рассказал князь..._7552069150609362194_h264	2026-01-08 19:21:12.590486
238	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRrX2fxL/	 икона детства   fake all  fake body I rm jinxilli бенихолли э..._7511967857421356293_h264	2026-01-08 19:23:07.491783
239	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRrC3goq/	edit fypシ foryoupage foryou fyp rec recomendation эдит князь..._7338545231014464811_h264	2026-01-08 19:23:16.386781
240	1022079796	lendspele	tiktok	Video	https://www.tiktok.com/@nasukha144/video/7573344581555703047?is_from_webapp=1&sender_device=pc&web_id=7476564257216464406]	Priest edit #edit #foryou #roblox #priest #gutsandblackpowderroblox _7573344581555703047_9812	2026-01-08 20:09:43.272461
241	1022079796	lendspele	tiktok	Video	https://www.tiktok.com/@unknown_anonymousq0/video/7541905787619233079?is_from_webapp=1&sender_device=pc&web_id=7476564257216464406	｜｜ Charge Callouts of Nations ｜｜ tags： #roblox #gutsandblackpowder #g..._7541905787619233079_4024	2026-01-08 20:12:21.077182
242	1022079796	lendspele	tiktok	Video	https://www.tiktok.com/@nasukha144/video/7584082588499709191?is_from_webapp=1&sender_device=pc&web_id=7476564257216464406	gnb edit  thanks for 10k followers guyss  edit gutsandblackpowd..._7584082588499709191_h264	2026-01-08 20:12:33.238271
243	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRrXoY1a/	RAHH SKELETON SONNE MASHUP rahh skeletonraaah rammsteinsonne мист..._7591751685178002699_h264	2026-01-08 21:33:53.602751
244	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRr4MY5u/	POV you just started your first hackthebox course - call me anonymous _7480125438359031062	2026-01-08 21:59:08.512154
245	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRrV1WsS/	беларусскаямузыка музыка Беларусь без политики пожалуйста. _7588911831138323768_h264	2026-01-08 23:11:31.727922
246	6299330933	datapeice	instagram	Video	https://www.instagram.com/reel/DTRDGkuER69/?igsh=MTcxczlkbDk1anN5ZA==	Video by soskarpova_DTRDGkuER69_h264	2026-01-08 23:35:15.066617
247	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRr4WY7b/	Я заметилсверхъестественное динвинчестер supernatural edit _7591910633864482104_h264	2026-01-09 00:07:31.413255
248	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRrsxfRS/	#spn #дестиэль #супернатуралы #сверхъестественное _7593049275769048341_cb19	2026-01-09 12:03:56.352719
249	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRrtTevd/	Наутилус Слøтилиус    #музыка #русскийрок #наутилуспомпилиус #брат2 #..._7593355719018089749_fd17	2026-01-09 15:46:34.859815
250	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRrnFtbu/	😳 #t2x2 #тоха #twitch #твич #89squad #нарезка #стрим #стример #игра #..._7593026846464396564_a998	2026-01-09 15:51:23.526897
251	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRrnrtSG/	Сэм чет в себя поверил #supernatural #сверхъестественное #rec #мем #а..._7593068779999874326_9534	2026-01-09 15:57:03.167422
252	6299330933	datapeice	instagram	Video	https://www.instagram.com/reel/DScMHQujeEs/?igsh=aW85OTBxdjJkbnQz	Video by babazptakiem_DScMHQujeEs_h264	2026-01-10 20:16:11.782804
253	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRhLGJac/	вот так как то (три богатыря edit) #АлёшаПопович #ДобрыняНикитич #Иль..._7575440640536890654_7e39	2026-01-11 00:46:44.996462
254	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRhLf7CN/	I Три Богатыря эдит I  #эдит #мультик #реки #богатырь #фип #подписчик..._7575644879171144973_e797	2026-01-11 00:48:37.721732
265	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRhjh8VV/	😭😭😭#Repost #fyp #on #школа  поставьте лайк на прошлое видео в профиле 🙏🏻_7593789153255443745_d873	2026-01-11 15:34:02.442546
266	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRhjXHqe/	Grzegorz Braun pozdrawia Johna Porka #johnpork #pork #john #grzegorzb..._7503191015931596054_27e5	2026-01-11 16:19:34.771265
267	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRhjpeKy/	Pozdrowienia od Nawrockiego dla Johna Porka #prezydent #wybory #polit..._7502059827338677526_f1cd	2026-01-11 16:20:49.786134
268	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRhMQwQk/	хз что-то сделал от скуки_7593308389661232392_1bd5	2026-01-11 19:51:13.895586
269	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRhhSCLh/	first ever java edit #java #kotlin #programming #coding @shyan 🇩🇪 _7574290627890859286_a02d	2026-01-11 23:48:53.000573
270	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRhBQ4Ys/	TikTok video #7594191404620844299_7594191404620844299_e828	2026-01-12 08:38:12.213569
271	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRhBvQ5m/	Действительно странно #рекомендации #мем #рек #рофл #ии _7586042004132400440_947f	2026-01-12 09:10:06.882102
272	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRhD5Jb7/	ОТВЕТЫ НА ОГЭ ｜ ЕГЭ ТУТ ： ТГ - @otvetna_ogeege2026#биология _7584825130346368277_3782	2026-01-12 11:16:35.376255
273	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRh56gX6/	bsd unix_7552451066818759954	2026-01-12 17:18:08.596537
274	1022079796	lendspele	tiktok	Video	https://vm.tiktok.com/ZMDhxBHTp/	Фотоаппарат – это не просто инструмент для создания фотографий, это н..._7593100893965454612_8a50	2026-01-12 17:26:13.713528
275	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRh5o4SG/	тг dahi_404_7594393062441225502_653d	2026-01-12 17:58:14.800699
276	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRhaYbkn/	Вот так и радуй любимых 😁🇩🇪🇺🇦 #мужнемец #українцівнімеччині #завтрак ..._7581098259985255692_c585	2026-01-12 18:07:08.134903
277	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRhawhuw/	#schlittenfahren 🛷💨@Ifa_schrauber @Trecker Maik @nadollfabian _7593790943363386656_5be5	2026-01-12 18:37:28.277867
278	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRhaCbqu/	thank u Ian #onlinefriends #08 _7573498352562687263_72d2	2026-01-12 18:47:52.730102
298	6299330933	datapeice	instagram	Video	https://www.instagram.com/reel/DRaa98sAv3g/?igsh=cmN5a3J6Y2Y1NThr	Video by memes_from_agartha_DRaa98sAv3g_h264	2026-01-13 22:31:49.246991
299	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRhtXQdE/	Jak morsuję zawsze woda jest zimna, ale myślę, że wytrzymanie mentaln..._7594863216727985430_ab2a	2026-01-13 22:45:56.141854
300	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRhtWHSy/	TikTok video #7594954711292235030_7594954711292235030_d678	2026-01-13 22:55:41.749692
301	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRht3Lev/	Im gonna find it! #pirates #pirateslife #comedy _7594459641464098070_107b	2026-01-13 23:05:19.116324
302	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRhtnegG/	Кац как всегда как Кац Все должны зиговать🥀🥀🥀 #Максимкац #Кац #katz #..._7585242822819826965_3140	2026-01-13 23:36:36.461069
303	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRht9HPr/	Say the Word on the Beat Challenge IMPOSSIBLE! 🇺🇸 Cheat sheet：  Cap a..._7594979039224401165_5af0	2026-01-13 23:54:30.713619
304	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRhKKVJU/	TikTok video #7580089488370666759_7580089488370666759_dedb	2026-01-14 15:39:15.577685
305	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRhK3qUj/	הגעתי היום לבקו״ם לפגוש את המתגייסים החדשים לחיל ההנדסה הקרבית. שמחתי..._7579271163503791371_71b9	2026-01-14 15:43:49.927041
306	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRhELpJ5/	#foryoupagee #traktorkalife #kourimjenkdyzpiju #foryou #liveforthecha..._7594806859358342422_9932	2026-01-14 15:59:22.286966
307	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRkJcEVq/	Они приучили медведя и приняли в армию  #факт #интересно #рил #понятно _7594895902800661782_efc6	2026-01-14 21:49:55.054449
308	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRkL3sEU/	Школьная дискатека #липсинг #тренд _7589341959253282069_a4b8	2026-01-15 10:28:46.856831
309	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRkr5bXR/	#gothic #alternativefashion #korn #alttiktok #metalhead _7582174410812017928_6e4a	2026-01-15 19:21:16.758158
310	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRkr9XB7/	This song is actually on my playlist 😭 #cyberpunk2077 #cyberpunk #pha..._7538205453638044958_1453	2026-01-15 19:26:28.01315
311	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRkru1hk/	#эпштеин _7595556096471797010_f657	2026-01-15 19:28:35.680648
312	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRkh5NsV/	yes it's a candel  #homelab #homelabbing _7595199734617230614_93f5	2026-01-15 20:29:32.115232
313	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRkhjsM8/	And then I go on every pirate site ever to watch movies and shows #fy..._7577813313002704150_509e	2026-01-15 20:44:36.69247
314	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRkhCHkE/	thanks @Manjaro.. ok for the idea BSD stands for Berkeley Software Distribution. It is a family of Unix-like operating systems that originated at the University of California, Berkeley in the late 1970s and 1980s. BSD introduced many features that enhanced the original Unix, such as networking support and improved file systems. Popular BSD variants include FreeBSD, OpenBSD, NetBSD, and DragonFly BSD, each with different focuses like performance, security, or portability. BSD can also refer to the BSD license, which is a permissive open-source license. It allows software to be used, modified, and redistributed freely, including in proprietary software, without requiring derivative works to also be open source. #linux #unix #apple #monsterenergy	2026-01-15 22:02:01.754591
317	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNHoBQGhTqVwf-EexA1/	TikTok video #7595678826022128918_7595678826022128918_c1ed6d3d	2026-01-15 22:44:15.200891
318	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRkk6BAA/	Город Осака ( Япония : Osaka City ;  Ōsaka-shi (北海市:  Ōsaka-shi ) — второй по величине город в экономике и третий по численности населения в Японии. Это также крупнейший город из трех городов Кэйхансин, расположенный в регионе Кансай на острове Хонсю в префектуре Осака. Это один из немногих городов, имеющих статус государственного мегаполиса. Население Осаки составляет около 2,7 миллиона человек, но в рабочее время это число увеличивается до 3,7 миллиона, уступая только Токио. Соотношение дневного и ночного населения составляет 141 процент. Город расположен в устье реки Ёдо, залива Осака и Внутреннего Японского моря . Осака — важный город в истории . Как торговый, так и культурный один из городов Японии называют кухней нации ( яп .天下の台所;  ромадзи :  Tenka no Daidokoro ), потому что Со времен периода Эдо он был центром торговли рисом в Японии .#israel🇮🇱 #palestine #foryou #fpyシ #based 	2026-01-15 22:47:03.520796
319	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRkkrU9V/	Группа ДДП  ‼️ полный трек в тгк  #музыка #ддт #русскийрок #мелстрой _7587103051761061140_1f7c65ec	2026-01-15 22:47:19.00361
320	6299330933	datapeice	youtube	Music	https://youtu.be/QagOVDONqCc	Хенде Хох MEINE KLEINE_QagOVDONqCc	2026-01-15 22:48:05.570049
321	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRkhEBek/	Day 123 of playing War Thunder #warthunder #history #hoi4memes _7595334748403256598_dcab8dcb	2026-01-15 22:58:40.607742
322	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRkkSPeq/	Volkswagen Phaeton 3.0 TDI #pourtoi #foryou #keşfet #tdi #vw #phaeton 	2026-01-15 23:02:07.467227
323	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRkkvBFj/	@IPTelefonija_official #iptelefonija _7595105367328181526_51742aba	2026-01-16 00:44:44.880372
324	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRkkmd2h/	#бабазиназвониттелефонтрезвонит #бабазиназвонит  #бабазина	2026-01-16 00:46:49.4035
325	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRkkb6Jp/	#tiktok _7594351721384643848_014d90b0	2026-01-16 00:52:55.722802
326	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRkknSrY/	#реки 	2026-01-16 01:01:00.366817
327	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRkkm6RK/	ちょっと前に流行ったよね😊 #kissmeagain #kissme #livephoto #livephototrend #ライブフォト 	2026-01-16 01:12:17.163576
328	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRkkbVML/	zesram sie jak to zobaczy nmg😭 on bedzie taki zly jak odkryje ze to j..._7595565202943380758_f3f1e1b7	2026-01-16 01:15:02.333681
329	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRkkXm4s/	HEEEEEELP #russianlanguage #learningrussian #russian_7590395627188555030_110e5b16	2026-01-16 01:25:35.459622
330	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRkD4XTM/	#jewish #judiasm #viral #fyp #israelpalestine 	2026-01-16 10:37:19.798691
331	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRkDp9Kc/	Але куда фурри #фурри #игорьгофман #мадуро _7595694874360433940_bb281fd9	2026-01-16 10:37:49.894023
332	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRkDcHqJ/	не спать боец ｜ #metroexodus #метроисход #мельник #fyp _7595532054431829304_87fbcb31	2026-01-16 10:45:16.83957
333	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRkUUyKB/	Papaya gang _7595195398474534151_c030f976	2026-01-16 11:26:08.66285
334	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRkU7Yk2/	Как Вы думаете как относятся к гетеросексуалам в СШАИсточник ..._7595555545931730209_h264	2026-01-16 11:44:58.166008
335	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRkUgm5A/	My Capcut was bugginn  should I keep this cc  Song Name  Montagem..._7576051518286073110_h264	2026-01-16 12:26:17.16325
336	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRkyHpgL/	#НоваяМузыка #МузыкальныеТренды  #Хиты 2023 #русскаямузыка  #ТикТокМузыка  #Клип #Премьера #МолодежнаяМузыка  #Песня2023  #Тренд  #Суперхит  #Музыка  #Слушай #Популярное  #Эмоции  #СловаПесни  #МузыкаВдуше  #АлгоритмыТикТок  #Лайки  #Подписывайтесь #капсиииииииииииииииииииииииииииииииииииииииииииииз #полматери #тт #рек #оооооооооооооооооооооооооооооооооооо  Валентин Стрыкало - в первую очередь сольный музыкальный проект украинского певца и автора песен Олега Михайлюты. Несмотря на то что иногда его называют группой, официально это не коллектив в классическом понимании, а именно сольный исполнитель с сессионными музыкантами. - Проект стартовал в середине 2000-х годов и быстро набрал популярность в интернете благодаря нестандартному сочетанию рок-музыки с сатирическими и ироничными текстами. - Основатель и единственный постоянный участник - Олег Михайлюта (Валентин Стрыкало), которого часто сопровождают разные музыканты и звукорежиссёры для живых выступлений и записи треков. - Чётко сформированного "штабного" состава группы нет. - Музыка сочетает альтернативный и поп-рок с юмористическими, порой провокационными текстами. - Темы часто касаются повседневной жизни, отношений, политических и социальных аспектов, поданных с иронией. - Валентин Стрыкало стал заметным явлением в украинской и российской музыкальной культуре середины 2000-х - начала 2010-х благодаря вирусным клипам и запоминающимся синглам. - Его формат породил интерес к жанру альтернативной лирической сатиры в музыке. Таким образом, Валентин Стрыкало - это прежде всего сольный артист с постоянным имиджем и музыкальной концепцией, который использует в записи и на сцене разных музыкантов, но не является классической группой.	2026-01-16 12:32:27.179133
337	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRkyXQ7a/		2026-01-16 12:33:30.050938
338	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRkf2QGt/	#рекомендации #дискриминант #подпишись 	2026-01-16 13:07:13.77188
339	6299330933	datapeice	instagram	Video	https://www.instagram.com/reel/DTYR8uNE_dh/?igsh=MXJoNnVqbWZpamJ1OA==	Video by askgpts_DTYR8uNE_dh_h264	2026-01-16 13:46:17.161354
340	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRkf517g/	#bird #foryou #fyp #fy 	2026-01-16 13:47:24.534989
341	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRkPVEvo/	Тг： mimi1doll @Your NekoGirl ＜з #goth #gothgirl #romanticgoth #jfashi..._7498760284639726903_4cdb86f5	2026-01-16 15:28:27.212585
342	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRkP7vc8/	🤷‍♀️🤷‍♀️🇺🇸 @EF Utveksling @EF High School Exchange Year  #halfway #ef..._7594985650961517879_5288d22c	2026-01-16 15:29:48.667647
343	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRkP7vc8/	🤷‍♀️🤷‍♀️🇺🇸 @EF Utveksling @EF High School Exchange Year  #halfway #ef..._7594985650961517879_cf640d3e	2026-01-16 15:44:15.639201
344	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRk5eSye/	#bird #cocktil	2026-01-16 15:45:24.152671
345	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRkP7vc8/	Exchange student in America EF Utveksling EF High School Exchan..._7594985650961517879_h264	2026-01-16 16:08:27.394676
346	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRk58G9w/	My new legsballet pointeshoes balettdancer fyp typ _7595260778396110102_h264	2026-01-16 16:11:15.544392
347	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRk5fpCt/	Metallica- Master of Puppetswith drums - Cat Piano Cover  metallic..._7586762180708601143_h264	2026-01-16 16:16:29.440731
348	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRkP7vc8/	Exchange student in America EF Utveksling EF High School Exchan..._7594985650961517879_h264	2026-01-16 16:20:39.400577
349	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRk5M6MN/	  dieselpower w201 belarus classiccar дизель_7595602371627978040_h264	2026-01-16 16:26:47.38878
350	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRk5M6MN/	  dieselpower w201 belarus classiccar дизель_7595602371627978040_h264	2026-01-16 16:31:18.335564
351	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRk5M6MN/	  dieselpower w201 belarus classiccar дизель_7595602371627978040_h264	2026-01-16 16:40:54.293857
352	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRk5bcg8/		2026-01-16 17:28:36.060001
353	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRk5M6MN/	  dieselpower w201 belarus classiccar дизель_7595602371627978040_h264	2026-01-16 17:42:27.666284
354	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRk5M6MN/	  dieselpower w201 belarus classiccar дизель_7595602371627978040_h264	2026-01-16 17:47:39.295787
355	6299330933	datapeice	instagram	Video	https://www.instagram.com/reel/DTgFboqDIAW/?igsh=MWdibGI5djVzOXRjYg==	Video by zespol_adhd_DTgFboqDIAW_h264	2026-01-16 18:12:56.946502
356	6299330933	datapeice	instagram	Video	https://www.instagram.com/reel/DTgFboqDIAW/?igsh=MWdibGI5djVzOXRjYg==	Video by zespol_adhd_DTgFboqDIAW_h264	2026-01-16 18:32:57.280546
357	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRka9VSf/	tiktok_c0be48dc	2026-01-16 18:36:26.135983
358	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRkmWajy/	tiktok_1336e1f1	2026-01-16 19:50:16.529458
359	6299330933	datapeice	instagram	Video	https://www.instagram.com/reel/DRWsDp4k0Le/?igsh=N3NpdmN2bnhpb20x	Video by patrick_tosto_DRWsDp4k0Le_h264	2026-01-16 19:51:44.430298
360	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRkmpjoA/	tiktok_2afb3518	2026-01-16 19:51:46.6073
361	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRkmEgB2/	Зове Динара, као некада… 🇷🇸❤️ Своју мајицу или дукс можете поручити н..._7595216954646957323_7a8ba0b2	2026-01-16 20:10:48.44526
362	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRkmw89v/	jebać mikrotika #mikrotik #halohalotulondyn #technikimformatyk #gothm..._7595511308741512470_0ada7fdf	2026-01-16 20:12:09.075608
363	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRkurU1x/	Dipper i Mabel chcą się zabawić z dzifgami 🚩#gravityfalls #edit #rema..._7595903911752469782_018cc3fe	2026-01-16 20:17:18.813529
364	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRkuRH1q/	#fyp #moots #viral #dc _7595236110180322583_3bb2d8d5	2026-01-16 20:20:10.153298
365	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRkuFUSD/	☀️#рекомендации #fypシ゚ #лето #деревня #foryou _7594931772320779532_e1782512	2026-01-16 20:45:44.919129
366	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRkuC3EE/	#dc #dlaciebie #fyp #mimi #szkoła _7595530235546717462_4c2b27a4	2026-01-16 20:50:25.845652
367	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRkuCPNo/	#назар_7565548329908653324_66de0e23	2026-01-16 21:12:37.955851
368	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRkusA6c/	Ответ пользователю @user6410733599008 #авитодоставка #можноврек #можн..._7043751625252441345_fcb449c2	2026-01-16 21:12:54.292245
369	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRkuA1X9/	Indovina chi ci è cascato #goth #gothbaby #gothgirl #trap  #gothtok _7594063113222098178_1547f209	2026-01-16 21:20:24.80727
370	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRkuUVNv/	сынок у нас умер папа ему было 67 лет #sora #sora2 #fyp #рек #димдимыч _7591948499072077076_9a400395	2026-01-16 21:46:37.377095
371	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRkumQRy/	#жириновскийлучшее #лдпр #севастополь   Владимир Вольфович Жириновский (при рождении — Эйдельштейн) — советский и российский политический деятель, основатель и председатель Либерально-демократической партии России (ЛДПР).	2026-01-16 21:50:42.613106
372	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRkuT17F/	tiktok_00dd8c70	2026-01-16 21:59:24.609109
373	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRkH6TK3/	#fy #fyp #relatable #Relationship #xyzbca 	2026-01-16 22:04:47.857348
374	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRku3EA5/	tiktok_a0797d32	2026-01-16 22:18:03.795237
375	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRkHdRNo/	#plock #krakow #fyp _7596027801069735190_0384a3f2	2026-01-16 22:26:55.570815
376	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRkHraU1/	The General Dynamics (now Lockheed Martin) F-16 Fighting Falcon is an American single-engine supersonic multirole fighter aircraft under production by Lockheed Martin Designed as an air superiority day fighter, it evolved into a successful all-weather multirole aircraft with over 4,600 built since 1976. Although no longer purchased by the United States Air Force (USAF), improved versions are being built for export. As of 2025, it is the world's most common fixed-wing aircraft in military service, with 2,084 F-16s operational. #f16 #secret #secretdocument #вартанде #warthunder @Mr.Napalm 	2026-01-16 23:05:48.978764
377	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRkHmDww/	Он так чувствует 🤌 А как бы вы переименовали банк？ #тиньков #тбанк #о..._7377662126501956871_df21467c	2026-01-16 23:32:04.183688
378	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRkHBMYL/	Шаблон мема с Олегом #олегтиньков #рек _7301437210434211073_6293d929	2026-01-16 23:35:45.016104
379	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRkHuCuh/	tiktok_75186ae1	2026-01-17 00:05:40.85072
380	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRkH5jRk/	#рофл #реки #матеша 	2026-01-17 00:45:21.318938
381	5707480536	Paranollk	tiktok	Video	https://vm.tiktok.com/ZNRkHtoS6/	ГИФКУ НУЖНО КАЧАТЬ В МОЕМ ТГК #geraltofrivia #ведьмак #thewitcher3 #t..._7584527158186495243_62b16e1a	2026-01-17 02:00:29.700869
382	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRkQGWmA/	#картошка #рекомендаци 	2026-01-17 09:50:51.715713
383	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRkbTrBo/	#latskap #3dprint #bambulab_7596087086558579990_da19ea2f	2026-01-17 18:39:17.940193
384	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRksMK64/	average #linux experience #halflife #halflifememes #halflifemods _7577897576431701270_73a95bdf	2026-01-18 01:16:09.036841
385	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRkshTT3/	tiktok_4e5875db	2026-01-18 01:36:47.712629
386	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRksQa6u/	I made a historical meme _7592033473582419221_5acd7d07	2026-01-18 01:37:38.119228
387	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRksY3st/	the pyramids from Poland😱 trust #longdistancephotography #distancetok 	2026-01-18 01:41:58.489477
388	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRksHfE8/	tiktok_1a203528	2026-01-18 01:44:42.396228
389	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRksaW8K/	tiktok_b7de29a1	2026-01-18 01:48:41.348133
390	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRksSXwH/	tiktok_d4202671	2026-01-18 01:50:21.209733
391	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRkGWqCP/	fun time with bird #birds #animals #africa @cheema4us _7594890367590288670_63646606	2026-01-18 09:28:26.999803
392	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRkGxBwy/	#recommendations #тиньков _7575666368557714696_8845a1f9	2026-01-18 09:30:37.872322
393	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRkGtqsk/	олег тиньков💗💗 #vibe #tinkoff #real #swag #rafsimons _7582645944722754872_dcfa510f	2026-01-18 09:49:51.214544
394	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRktxh3X/	идея @cool boy872 #supernatural #deanwinchester #samwinchester #bobby..._7537928655851326738_2270c96b	2026-01-18 10:53:05.600693
395	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRktxsbW/	FAKE ALL !! извинитесь, я фамилию не так написала ибо не расслышала п..._7596132096473697554_9492d473	2026-01-18 10:55:47.607671
396	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRktqfQu/	#рек #рекомендации #россия #втораямироваявойна#ww2 #великаяотечествен..._6934747342629358849_c582ca41	2026-01-18 11:30:14.38104
397	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRktppmN/	#banane #pourtoi 	2026-01-18 11:37:24.710022
398	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRktanMv/		2026-01-18 11:40:24.193739
399	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRktuauL/	#pigeon #witch #christmas #fyp #bird _7582851741293497631_45ddb881	2026-01-18 11:42:34.038163
400	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRktWmKy/	Nev Tank in World of Tanks #viral #worldoftanksblitz #Tank #cat #foryoupage 	2026-01-18 11:42:49.488536
401	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRktG5Rq/	se que esta en algun lado🫩, #paratiiiiiiiiiiiiiiiiiiiiiiiiiiiiiii #fyp #nein #hola #unvideomas	2026-01-18 11:45:01.353868
402	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRktEnYv/	#fyp #mem #tiktok #recommendations 	2026-01-18 11:51:25.782857
403	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRkWwqXf/	По́льша (пол. Polska МФА： [ˈpɔlska]о файле), официальное название — Р..._7594937039913569544_091fdc70	2026-01-18 15:18:48.756026
404	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRkWTS2s/	#tiktok #Viral #polandtiktok #usa🤮 #trump2024 _7596466224083602710_b74d4beb	2026-01-18 15:18:55.545594
405	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRkWn9hR/	🔴 A group of Spanish carnival performers have paid tribute to Stephen..._7596067339074866454_9e0cc871	2026-01-18 15:21:22.429885
406	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRk7NoJF/		2026-01-18 15:22:33.523145
407	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRk71jTh/		2026-01-18 15:40:19.119474
408	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRk7pDrm/	studniówka ntyczny napaleniec what？？_7596348702080453910_0ee85bac	2026-01-18 18:02:16.080677
409	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRk7p7qn/	мой тгк： chazzy cheese 🧀 _7574918927810186508_03db4f5a	2026-01-18 18:04:10.303513
410	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRkv5gu4/	#gaza #israel🇮🇱 #foryou #fpyシ 	2026-01-18 18:08:04.916038
411	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRkvDEv1/	Остановите это пожалуйста #нападение #робот #живая #детройт _7596643736377953556_bc6750fb	2026-01-18 18:25:41.439565
412	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRkcUNQX/	⧸⧸Олесь Шевчук – лишь о нём и говорят⧸⧸ #рекомендации #чтоспетьсоседу..._7580461177763876108_24a1afba	2026-01-18 19:24:48.211361
413	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRkcm1gF/	Little bit of a fan XD #boykisser #fyp #boykissercat #stickers 	2026-01-18 19:43:57.911145
414	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRkcMJdS/	#rabbit #fyp 	2026-01-18 20:17:42.030146
415	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRkcGoxx/	tiktok_21586c82	2026-01-18 20:27:48.268305
416	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRkcbnny/	tiktok_e944e2ee	2026-01-18 20:31:05.612595
417	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRkcCnC6/	tiktok_ddb93d02	2026-01-18 20:46:06.941637
418	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRkcCdxG/	#animefyp #anime #animeedit _7590075260016332054_5bb90a1a	2026-01-18 20:57:24.249553
419	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRkcuddd/	#PavelDurov 	2026-01-18 21:11:07.002067
420	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRk36Laj/	The relationship between the French Emperor Napoleon Bonaparte and th..._7581868307574279446_777eb061	2026-01-18 21:29:04.090732
421	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRk3SjM6/	#usatoday #poland🇵🇱 #greenland 	2026-01-18 22:14:41.336544
422	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRk3gUMD/	Industrial loft “From factory floors to penthouse doors – enjoying the fruits of hard work.” #dream #arcitecturedesign #loft #luxury #viral	2026-01-18 23:10:03.625362
423	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRk3Cp67/	#физика #школа #рекомендация	2026-01-18 23:15:16.87428
424	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRkw6XpH/	studniówka ntyczny napaleniec what？？_7596348702080453910_38464537	2026-01-19 06:26:34.853008
425	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRBdousH/	эпштэйн,чудо остров 🏝️#эпштейн #врекомендациии 	2026-01-19 15:01:35.351925
426	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRBRBkQy/	👑Ⲕⲏяⳅь Ⲕυⲉⲃⲥⲕυύ👑 #обои #dberidze #wallpaper #трибогатыря #князькиевск..._7065992300073061634_cf4e7b13	2026-01-19 15:42:01.636963
427	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRB8KxoJ/	#foryoupage #fypシ #fy #fyp #gothicdecor #goth #gothic #gothicstyle #g..._7575606686463888670_3a7f00fc	2026-01-19 18:06:34.691674
428	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRBYadMT/	i will never get over the early seasons #fyp #editsgreysq #supernatur..._7594412838634933526_31b9eca6	2026-01-19 23:21:23.311232
429	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRBY6RhY/	lil edit of the sexiest car ever ：p ｜ #impala67 #supernatural #supern..._7527441896986234143_f02be819	2026-01-19 23:28:32.206555
430	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRBYC4e1/	Родной Днепр❤️ #virał #elbruso #днепр #днепр #город #жизнь #рекоменда..._7525079642139544888_17d98bcb	2026-01-20 00:59:30.202117
431	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRBYtSxQ/	#dnepr #днепр #днепропетровск #дніпро _7432833222611848453_7872acfb	2026-01-20 01:00:00.82149
432	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRBjACEH/	pkp.	2026-01-20 07:08:47.977717
433	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRBjMyeW/	#idk #foryou #chicken 	2026-01-20 07:12:36.649683
434	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRBj8MDk/	#рекомендации #epstein #иванзоло2004 #зеленский #трамп 	2026-01-20 07:16:04.726005
435	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRBjBome/	#idk #foryoupage #chicken #blackchicken 	2026-01-20 07:16:51.916723
436	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRBMpB9r/	сон важнее #доза #сверхъестественное #supernatural #рекомендации #rec..._7536911499491806487_10493d5a	2026-01-20 10:55:57.385375
437	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRBM3qJR/	just stop. Thats it. #fyp #deanwinchester #jensenackles #67 #supernat..._7597173253911710998_3e3b3047	2026-01-20 11:08:30.254956
438	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRBhupT4/	Final result for a space ship @ruihuang_art_rt_ #3d #3danimation  #3d..._7554378237573401864_78c41368	2026-01-20 13:00:05.684143
439	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRBhXr3S/	No AI, I made this in Blender #b3d #blenderanimation #blendercommunit..._7496819683291712790_aaa0214f	2026-01-20 13:02:56.397808
440	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRBBYfok/	w 2020* Do wypadku doszło kilka minut po godz. 8 w pobliżu lotniska w Krośnie. Wstępnie ustalono, że pilot małego samolotu silnikowego, chwilę po starcie stwierdził, że doszło do awarii silnika. Zdecydował o awaryjnym lądowaniu. Samolot uderzył w latarnię i garaż znajdujący się na posesji przy ul. Zręcińskiej, sąsiadującej z lotniskiem. Garaż i stojący przy nim samochód uległy uszkodzeniu, uszkodzony jest też samolot. 69-letni pilot wyszedł o własnych siłach. Leciał sam. Mężczyzna był trzeźwy, został przewieziony do szpitala. @PMWM wiem że prosiłeś więc zrobiłem :) 	2026-01-20 14:13:09.948987
441	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRBSJcdP/	New Balance («Нью Бэланс») — американский производитель спортивной одежды и обуви, базирующийся в Бостоне (штат Массачусетс, США). Компания была основана в 1906 году, с 1972 года принадлежит Джиму Дейвису. Деятельность Компании принадлежит 7 обувных фабрик, 6 из них находятся в США (штаты Мэн, Массачусетс и Нью-Гемпшир), 1 в Великобритании; на них в сумме работает 1600 человек[12]. Они выпускают часть продукции, продаваемой в США и странах Западной Европы. Остальной товар изготавливают независимые контрактные производители; в 2023 году у компании было 163 поставщика готовой продукции и 275 поставщиков материалов и комплектующих; фабрики находятся во Вьетнаме, Камбодже, Индонезии и Мексике[13]. Спонсорство New Balance стала официальным партнёром футбольного клуба «Мельбурн», выступающего в Австралийской футбольной лиге[14]. New Balance спонсирует игроков в крикет, среди них Стив Смит, Ник Мэдиссон, Гэри Балланс, Джонатан Тротт, Пэт Кумминс, Бен Стокса, Джеймс Паттинсон, Аарон Финч и Дейл Стейн[15]. После официального запуска в июле 2011 года, New Balance является спонсором системы совместного использования велосипедов, Нью Бэланс Хабвей[16][17]. New Balance оказывает поддержку канадскому теннисисту Милошу Раоничу[18]. New Balance начала свой футбольный бизнес через дочернюю компанию Warrior Sports в 2012 году, подписав спонсорский контракт с «Ливерпулем» на 40 млн долларов в год. В феврале 2015 года компания объявила о переходе спонсорства на бренд NB[19]. Среди других спонсорируемых клубов были «Эмелек», «Сток Сити», «Порту», «Севилья», «Селтик»[20], «Бери», «Рубин»[21] и «Динамо (футбольный клуб, Киев)», а также национальные сборные, такие как Сборная Коста-Рики и Сборная Панамы[22][23]. Спонсорские контракты заключались и с отдельными игроками, такими как Венсан Компани, Маруан Феллайни, Тим Кэхилл и Никица Елавич[24]. В марте 2015 года, компания подписала персональные рекламные контракты с футбольными звёздами, среди них Аарон Рэмзи, Аднан Янузай, Самир Насри, Фернандо Режес, Венсан Компани, Хесус Навас и Маруан Феллайни[25]. В феврале 2019 года компания New Balance стала официальным партнёром команды Формулы-1 Alfa Romeo Racing (бывшая Sauber F1 Team). В состав команды входили пилоты Кими Райкконен и Антонио Джовинацци. На июль 2023 года New Balance была техническим спонсором следующих футбольных клубов: «Лилль» (Франция), «Атлетик Бильбао» (Испания), «Порту» (Португалия), «Динамо» Киев (Украина), «Кардифф Сити» (Уэльс).  Литература New Balance Athletic Shoe, Inc. // International Directory of Company Histories (англ.) / Tina Grant. — Детройт: St. James Press, 2005. — Vol. 68. — ISBN 1558625437.	2026-01-20 15:40:00.839879
442	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRBSBmdT/	Most protein I’ve ever had #mimityph #bodybuilding #edit #fyppppppppp..._7596845384845053214_08a241d5	2026-01-20 16:13:29.516619
443	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRBAaFNQ/	should i drop some of my ae presets when i reach 3k 😂🙏 ｜ cc, ac, qual..._7544517091370601783_39d4c339	2026-01-20 17:44:26.243028
444	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRBDMcew/		2026-01-20 18:43:06.873673
445	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRBDb4wk/	wagner #school #dance #breakdance #recomendation #fyp _7594096083454758166_e63a6032	2026-01-20 19:01:58.587374
446	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRBDvY83/	First, don't be fooled. Ridicule only works when you react. You get a..._7595615531198106910_673e7f3c	2026-01-20 19:09:17.928389
447	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRBDtRcd/	#bird #healthy #viral 	2026-01-20 19:14:56.716181
448	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRBU4qEG/	#переписка #переписки #мем_7597452522495708436_8129f565	2026-01-20 21:07:05.22567
449	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRBU5vvF/	розы за Петровича его жизнь для живца была достаточно долгой🌹🌹_7597134999401303352_50ff3106	2026-01-20 21:08:13.560041
450	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRBUqaJm/	#meme #dailyroutine #funnyanimals #fypシ゚ #animetiktok _7597254244349054239_62d7edf3	2026-01-20 21:09:47.325661
451	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRByek9f/	#сша #америка #мем #яроняюзапад #chillburger @Kenny⚽️ _7580059681608043790_e119b02b	2026-01-20 21:15:22.626626
452	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRByMbrF/	Кастіель і Кроулі працюють разом  це як ангел охоронець та демон-мене..._7575972889833327892_e0f5ed86	2026-01-20 21:23:32.238618
453	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRBy2u78/	#pilosmleko #mleko #milk #pilos #polska _7597284619230137611_a50932aa	2026-01-20 21:31:07.278759
454	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRBy6T5A/	well well well 🥀🥀 FAAAAAAAAAAAAAAH 🗣 #femboy  #warthunder #fyp #femboysupremacy 	2026-01-20 21:46:31.741428
455	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRBydWM5/	я не умею нормально делать  видео..#supernatural#сверхи  #spncharlie#..._7595278209399131404_27cf5211	2026-01-20 22:08:13.739734
456	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRBySEqP/	I miss charlie so much, she was the best woman character 😔 [scp： deax..._7286483800832412929_d36affcb	2026-01-20 22:09:11.70806
457	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRByAQuE/	#сверхъестественное #чарлибрэдбери #клэрновак #винчестеры #кастиэль _7581433546489777421_c26d691e	2026-01-20 22:10:24.205758
458	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRByfcjU/	хрю балуется #грю #сергейбурунов #гадкийя #эдит #fyp _7588123256905911570_dd27dba7	2026-01-20 22:20:30.50077
459	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRBy4x7m/	Ютуб и тг ： meta striker 🧬 #fyp #виар #игры #такси #sixseven _7594049285730356483_56de6abd	2026-01-20 22:29:48.52054
460	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRByGpys/	#ForUSViewers #UScontent_7595546816838520095_25c7ba59	2026-01-20 22:31:58.952594
461	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRByuJUJ/	#prank #funny #fyp #tiktok  _7592193157568269623_0e375c8a	2026-01-20 22:37:36.988388
462	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRByntTQ/	TikTok video #7589742320749186326_7589742320749186326_6bb47e1b	2026-01-20 22:44:36.375991
463	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRBfFC18/	Название трека： Саня Автор： френк？_7579696090656689438_e6a92ed7	2026-01-20 23:40:38.016086
464	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRB9pSah/	@KORTY помогите актив вернуть на основу 🙏#deanwinchester #samwinchest..._7582223577353571605_e1b21d98	2026-01-21 13:43:04.21497
506	6299330933	datapeice	youtube	Video	https://youtu.be/d4HwO3ZUCUw	Kitten Sneeze d4HwO3ZUCUw	2026-01-23 19:54:54.557443
465	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRB9v9F6/	I’m going to be one of them lol #polonez #rally #dirt4 #racing #lanci..._7397157100486544673_aabddb64	2026-01-21 13:45:09.004331
466	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRB9cSHy/	orig edit： @vanela  #mrrobot #fsociety #python #linux #elliotalderson _7597730778625150220_f356cc19	2026-01-21 13:47:35.491263
467	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRB9scFH/	много песен мы... #прощаниеславянки #врекомендации #футажстекстом #во..._7498793453510298888_54355830	2026-01-21 14:02:24.190048
468	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRBx1EVu/	#romania #romaniaslander #meme #fyp #fypシ #lego #legotiktok _7204531880987839786_8eb86180	2026-01-21 14:08:44.709661
469	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRBVwByw/	#stalker  #stalker2  #stalkermem #stalkermemes  #stalkerrp         _7596775155259559180_c2a68df3	2026-01-21 23:15:35.297978
470	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRBVcCkL/	ТГК — Учу Инглиш： Бот #английский _7597498334802087180_8f87d0af	2026-01-21 23:29:32.333938
471	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRBcnXhA/	растения тоже живые!!! веганы жестокие!!! #веганство #веган #животные..._7589215048761953566_e5b35311	2026-01-22 20:00:27.398135
472	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRBcXXgg/	lil edit of the sexiest car ever ：p ｜ #impala67 #supernatural #supern..._7527441896986234143_d5a76ed8	2026-01-22 20:03:58.287483
473	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRBcbWuC/	Потужно？_7598265050167577878_c5155150	2026-01-22 20:08:16.307783
474	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRB36Cj2/	9🍋 полигонов норм？ #3d #blender3d #3dmodel #3дпечать #моделирование _7597372678793727265_ca07c206	2026-01-22 20:18:11.212342
475	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRB3MGMn/	#иван#женя#ждуподпискуилайки#гот#сваты_7596048325107846456_17873093	2026-01-22 20:19:15.084239
476	6299330933	datapeice	instagram	Video	https://www.instagram.com/reel/DTxMJkyDx8X/?igsh=MWN4aXEycmx4b3phdg==	Video by monashchessclub_DTxMJkyDx8X_h264	2026-01-22 20:19:36.929122
477	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRB3NVrB/	Все имена и события в этом ролике вымышлены, но что точно не вымышлен..._7597776003024342280_a91f84ab	2026-01-22 20:22:04.104654
478	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRB3kUFM/	Он ещё и узкий    #музыкадлядуши #шаман #shaman #ярусский #сво _7597833838416497941_7d6b5ab3	2026-01-22 20:37:32.145476
479	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRB3pdDE/	#потужно #magerdev1 _7597415994692226326_587b1d9c	2026-01-22 21:12:17.635763
480	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRB3qhCa/	My summer car 🤩 #mysummercar #майсаммеркар #мск #msc #рекомендации #m..._7466364321950387462_00b0f6c7	2026-01-22 22:07:54.287992
481	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRBT174k/	my wife from suomi #finland #suomi #mika #girlsundpanzer _7597045948421770552_c24321c8	2026-01-22 22:12:21.032646
482	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRB3KGCa/	#lego #vinted #epstein 	2026-01-22 23:10:36.3084
483	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRBTRfBk/	теперь будем знать что происходит по картам #рек #рекомендации #актив..._7597488215066529044_40a7b492	2026-01-22 23:26:29.866989
484	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRB3TGPj/	отмечай своих друзей #учеба #друзья #жиза #fyr #rek _7598088046080298262_b672b3e2	2026-01-22 23:27:30.412151
485	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRBTepPR/	TikTok video #7595227701875674389_7595227701875674389_2eae024a	2026-01-22 23:33:44.660651
486	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRBT9e2J/	👁️ТЫ НЕ ВЫБИРАЛ BLENDER 3D #blender3d #3danimation #3dmodeling #3D_7585253604773072149_2f3a733b	2026-01-22 23:46:12.438665
487	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRS1fwFh/	КТО КРУЧЕ？ Пиши в комментарии! 🇷🇺🇺🇦 #simpledimple #симплдимпл #попит ..._6980712184342908165_e5ef07e3	2026-01-23 12:05:20.465435
488	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRSJ2y9W/		2026-01-23 12:30:22.783406
489	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRSJVd9t/	#deken #freelance #blender #motiondesign #3d _7578155361459309880_2a8dfe60	2026-01-23 13:16:26.240375
490	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRSJ9DUw/	@NESCAFÉ Arabia what is it？ Нет нацизму! #сургут86 #сургут #fly #meme..._7598239903205313810_b4dcabbf	2026-01-23 13:17:19.421097
491	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRSdk3to/	Booo, a job application….. how SCARY #funny #fyp #jobapplication #mem..._7506749398597127446_3aa58619	2026-01-23 15:21:09.569601
492	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRSdtU7J/	Павел Дуров про Java #java #jvm #kotlin #дуров #программирование #про..._7528482236815953153_566d7b2b	2026-01-23 15:56:05.289769
493	6299330933	datapeice	youtube	Video	https://youtu.be/PHkqQdJj2VY	𓍢𓋴𓇌𓄿𓏤𓊪𓂋𓄿𓂻𓂧𓄿𓏤𓂋𓋴𓎡𓂋𓉔𓍢𓄿𓎛𓂋𓋴𓇌𓄿𓏤𓆙𓊃𓂧𓎛𓋴𓏤𓇋𓏤𓋴𓎛𓎼𓍯𓂧𓈖𓇌𓂝 PHkqQdJj2VY	2026-01-23 19:06:42.858746
494	6299330933	datapeice	youtube	Video	https://youtu.be/d4HwO3ZUCUw	Kitten Sneeze d4HwO3ZUCUw	2026-01-23 19:08:04.147657
495	6299330933	datapeice	youtube	Video	https://youtu.be/d4HwO3ZUCUw	Kitten Sneeze d4HwO3ZUCUw	2026-01-23 19:13:41.584
496	6299330933	datapeice	instagram	Video	https://www.instagram.com/reel/DTqEY0ZAQ3f/?igsh=MTMzOTZtN3U2M3hyag==	Video by nitesxap DTqEY0ZAQ3f	2026-01-23 19:17:52.510932
497	6299330933	datapeice	youtube	Video	https://youtu.be/d4HwO3ZUCUw	Kitten Sneeze d4HwO3ZUCUw	2026-01-23 19:23:06.118109
498	6299330933	datapeice	youtube	Video	https://youtu.be/d4HwO3ZUCUw	Kitten Sneeze d4HwO3ZUCUw	2026-01-23 19:30:32.001775
499	6299330933	datapeice	youtube	Video	https://youtu.be/d4HwO3ZUCUw	Kitten Sneeze d4HwO3ZUCUw	2026-01-23 19:37:57.868808
500	6299330933	datapeice	instagram	Video	https://www.instagram.com/reel/DTqEY0ZAQ3f/?igsh=MTMzOTZtN3U2M3hyag==	Video by nitesxap DTqEY0ZAQ3f	2026-01-23 19:39:24.395467
501	6299330933	datapeice	instagram	Video	https://www.instagram.com/reel/DTzIl27COqt/?igsh=MW9vZ3FzdHlmcHZnYQ==	Video by ssaxmike DTzIl27COqt	2026-01-23 19:39:43.847023
502	6299330933	datapeice	instagram	Video	https://www.instagram.com/reel/DTzIl27COqt/?igsh=MW9vZ3FzdHlmcHZnYQ==	Video by ssaxmike DTzIl27COqt	2026-01-23 19:42:03.412217
503	6299330933	datapeice	youtube	Video	https://youtu.be/d4HwO3ZUCUw	Kitten Sneeze d4HwO3ZUCUw	2026-01-23 19:42:52.91678
504	6299330933	datapeice	youtube	Video	https://youtu.be/d4HwO3ZUCUw	Kitten Sneeze d4HwO3ZUCUw	2026-01-23 19:47:40.422015
505	6299330933	datapeice	youtube	Video	https://youtu.be/d4HwO3ZUCUw	Kitten Sneeze d4HwO3ZUCUw	2026-01-23 19:50:50.195912
507	6299330933	datapeice	instagram	Video	https://www.instagram.com/reel/DTzIl27COqt/?igsh=MW9vZ3FzdHlmcHZnYQ==	Video by ssaxmike DTzIl27COqt	2026-01-23 19:56:21.217934
508	6299330933	datapeice	instagram	Video	https://www.instagram.com/reel/DTzIl27COqt/?igsh=MW9vZ3FzdHlmcHZnYQ==	Video by ssaxmike DTzIl27COqt	2026-01-23 20:00:36.861449
509	6299330933	datapeice	youtube	Video	https://youtu.be/d4HwO3ZUCUw	Kitten Sneeze d4HwO3ZUCUw	2026-01-23 20:01:15.722301
510	6299330933	datapeice	instagram	Video	https://www.instagram.com/reel/DTzIl27COqt/?igsh=MW9vZ3FzdHlmcHZnYQ==	Video by ssaxmike DTzIl27COqt	2026-01-23 20:07:34.756023
511	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRSNfSgd/	THIS is the longest CITY BOY ever Pt.2 #cityboy #meme #what #longest ..._7596087439794441502_0750b46e	2026-01-23 21:33:09.614648
512	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRSNVfbb/	Skill issues editing： (запостил ради поста) #programming #программиро..._7569274128700656903_2f9d844d	2026-01-23 21:47:16.061478
513	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRSN4FTx/	tiktok_1dc62cc8	2026-01-23 22:26:45.727556
514	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRSNt6EN/	TikTok video #7597385332379667767_7597385332379667767_8ea81aab	2026-01-23 23:03:10.83119
515	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRSFLjuc/		2026-01-23 23:58:09.747817
516	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRSMdujR/	tiktok_aa80e35f	2026-01-24 12:02:07.306373
517	1022079796	lendspele	tiktok	Video	https://vt.tiktok.com/ZSaDHK7de/	#viral #FYP #fyp #Foryou #hollowknight _7582209482374106390_9e80fd5e	2026-01-24 13:00:37.947267
518	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRSB1cJy/	tiktok_f993b4bc	2026-01-24 18:09:13.466256
519	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRSBkRwA/	tiktok_33c11dfe	2026-01-24 18:35:48.213302
520	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRSBagj2/	tiktok_927cd8d4	2026-01-24 19:13:49.899821
521	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRSBowG6/	#penguin #mountain #gothgirl #femboy #vinland 	2026-01-24 19:38:42.72531
522	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRSB7cMT/	tiktok_2a698b3e	2026-01-24 19:39:08.052597
523	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRSBtG8J/	tiktok_156e2f85	2026-01-24 19:51:01.903088
524	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRSSMuNH/	tiktok_37fea02f	2026-01-24 19:57:20.018957
525	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRSA1qNQ/	Z-образный шов в хирургии_7598240293749591314_b4a54778	2026-01-24 22:55:07.4318
526	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRSARTUB/	🌸🦷🌟💿 #soft #musictok #vibes #aesthetic #artist _7567856066436812087_07619612	2026-01-24 23:03:07.391838
527	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRSACD7y/	какая озвучка самая лучшая？ #soulgoodman #edit #bettercallsaul #fyp #..._7593722257302768914_1160956d	2026-01-24 23:20:17.444521
528	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRSAatUh/	@fingees #рекомендации #сша #майнкрафт #foryoupage❤️❤️ #Minecraft _7598728412345306391_71332a48	2026-01-24 23:23:44.936607
529	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRSAyygb/	Tag ＂Z＂ Initials #fyp #initials #Love#tagthem_7565505127059033399_20aff8a9	2026-01-24 23:33:38.527064
530	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRSAmdH6/	In my dreams bcs he is my ex ❤️ #ex #fyp #fake #z _7538276074908585234_26cf81a2	2026-01-24 23:34:10.005427
531	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRSAXJfg/	Aesthetic Z #z #Z #з #aesthetic #зима _7588055172593569079_35a3196f	2026-01-24 23:34:40.458865
532	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRSA2Qhp/	#Z#crush #initial #bf #gf #fypppppppppppppppppppppppp _7445778102602468613_0eec18d1	2026-01-24 23:36:15.320565
533	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRSAHTAm/	Perfect signature 😦 @Rubbin’ is Racing (via：@𝓒𝓪𝓭𝓮) _7517126710379253006_0d391809	2026-01-24 23:39:08.732826
534	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRSyeDr6/	bro summoned the whole earth  #slideshow #funny #humor _7598820451883683079_29186dc7	2026-01-25 11:40:27.802727
535	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRSy2G9E/	Один из вас мой напарник а второй лживий ухилянт вопрос хто є хто? #потужно #тцк #ухилянт #детройт #конор 	2026-01-25 12:29:21.676893
536	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRSfLJBT/	POV： What Polish soldiers see at the border every day 🥀_7598923748854484227_304a6aac	2026-01-25 14:13:26.584123
537	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRSyENMy/	#onthisday _7597952537706106143_645e58c0	2026-01-25 14:16:40.294993
538	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRSfEKYk/	Asmr food 🤤 #asmr #kitchen #relaxing #food #cooking _7598884308467600662_325dd668	2026-01-25 16:20:08.026399
539	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRSPXo71/	#blackrock #intership #meme #trumpet _7571453772203904278_6e8cc374	2026-01-25 16:23:17.246686
540	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRSPsxNM/	#fyp _7593369762403536158_3275ca4d	2026-01-25 17:44:11.213121
541	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRSPsxNM/	#fyp _7593369762403536158_1824eba9	2026-01-25 17:44:21.288522
542	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRS5LHhd/	Кар карыч-нарцыстический тип личности. Вот и все. #смешарики #карыч #..._7548890602067201302_98808c81	2026-01-25 17:47:21.328272
543	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRSaBrbT/	Є проблеми про які не говорять. #жарти #дружба #гумор #пародія#хеклери _7598962137188420871_7859705e	2026-01-25 20:08:38.33696
544	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRSajKck/	#boykisser #cat	2026-01-25 20:09:15.081921
545	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRSa5rdW/	#eltigrefly #cessna188 #fumigacionesaereas #agriculturasinaloa #gpssa..._7595794343059819796_52f8898c	2026-01-25 20:13:30.80409
546	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRSa3seF/	Она меня отшила,потому что я слишком идеален. Не забываем записыватьс..._7595930989881249036_78296ba7	2026-01-25 20:40:20.40849
547	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRSaWBCT/	City boys Haircut #cityboys  #meme #funny #fyp #viral 	2026-01-25 20:53:53.72247
548	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRSagtJa/	#рофл #fyp #щитпост #xyzbcafypシ #xycba _7598345828452879637_3d75a9cd	2026-01-25 21:00:01.608052
549	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRSaTTkH/	🙄#буржуї#королева#сказочнаярусь#тренд#мемчик _7594182361844043041_3906ae55	2026-01-25 21:00:16.834226
550	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRSmcqeU/	tiktok_acb64b92	2026-01-26 01:10:07.404973
551	6299330933	datapeice	instagram	Video	https://www.instagram.com/reel/DTsgyMPCF2C/?igsh=ZTM0ZmgxaTkyc2Vu	Video by jetbrains DTsgyMPCF2C	2026-01-26 01:11:24.770867
552	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRSuq45q/	tiktok_287a13a6	2026-01-26 02:10:50.016484
553	1022079796	lendspele	tiktok	Video	https://vt.tiktok.com/ZSaPUkhvU/	tiktok_c59c1dec	2026-01-26 10:00:41.920303
554	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRS42xRM/	tiktok_d7972af3	2026-01-26 13:15:52.825034
555	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRS46U6K/	Tokyo became the first city in Asia to host the Summer Olympics and Paralympics, in 1964 and then in 2021. It also hosted three G7 summits, in 1979, 1986, and 1993. Tokyo is an international hub of research and development and an academic center, with several major universities, including the University of Tokyo, the top-ranking university in Japan.[11][12] Tokyo Station is the central hub for the Shinkansen, the country's high-speed railway network; and the city's Shinjuku Station is the world's busiest train station. Tokyo Skytree is the world's tallest tower.[13] The Tokyo Metro Ginza Line, which opened in 1927, is the oldest underground metro line in the Asia–Pacific region.[14] Tokyo's nominal gross domestic output was 113.7 trillion yen (US$1.04 trillion) in FY2021 and accounted for 20.7% of the country's total economic output, which converts to 8.07 million yen or US$73,820 per capita.[15] Including the Greater Tokyo Area, Tokyo is the second-largest metropolitan economy in the world after New York, with a 2022 gross metropolitan product estimated at US$2.08 trillion.[16] Although Tokyo's status as a leading global financial hub has diminished with the Lost Decades since the 1990s—when the Tokyo Stock Exchange (TSE) was the world's largest, with a market capitalization about 1.5 times that of the NYSE[17]—the city is still a large financial hub, and the TSE remains among the world's top five major stock exchanges.[18] Tokyo is categorized as an Alpha+ city by the Globalization and World Cities Research Network. The city is also recognized as one of the world's most livable ones; it was ranked fourth in the world in the 2021 edition of the Global Livability Ranking.[19] Tokyo has also been ranked as the safest city in the world in multiple international  #meme #mem #rec #мемы #мем #mems #fyp 	2026-01-26 13:32:38.726809
556	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRSVP4sX/	tiktok_3a35cc2f	2026-01-26 14:26:34.226613
557	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRSbUefP/	tiktok_9ab0b6cd	2026-01-26 16:41:15.527454
558	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRSbW3Jx/	video	2026-01-26 17:24:20.444934
559	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRSb9yBh/	video	2026-01-26 17:25:12.118406
560	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRSpCWxx/	#рек #мояидея _7599648292275866902_29e37af1	2026-01-26 19:28:33.121177
561	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRSb9yBh/	video	2026-01-26 19:28:57.822933
562	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRSpBmrQ/	tiktok_7fed18b3	2026-01-26 19:29:25.334214
563	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRSs7QBD/	tiktok_a60bbb05	2026-01-26 21:42:03.154123
564	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRSGUa3U/	#crowley #crowleyspn #supernatural #spnfandom #spnfamily 	2026-01-26 23:50:27.391597
565	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRSG8ScV/	Ужасный мастер маникюра! #английский #english #маникюр #eng #manicure _7594013850186321163_b4ac686a	2026-01-26 23:53:15.395797
566	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRStWTPw/	#audit #foryou #copsoftiktok #fyp #policeofficer _7582516672003689758_7067b2a7	2026-01-27 06:41:31.27508
567	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRStcEev/	tiktok_9e1b4aa7	2026-01-27 07:02:11.586356
568	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRSnFuGE/	CITY BOY #cityboy #anime @dekocar _7595731796378275085_e2c79021	2026-01-27 07:46:43.792232
569	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRSWJpeD/	Day 9 scripting in Roblox😭 #funny #programmingmemes #fpy #viral #robl..._7593414778719161607_8948edf4	2026-01-27 08:34:08.094849
570	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRSWFX78/	#япония #россия  #тренд #fypシ #fyp трендик	2026-01-27 08:34:56.307866
571	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRSE9M3p/	basic🇨🇿🤝🇵🇱 #kofola #tymbark #poland #czech #europa #firm #maoers #fyp..._7513753238185708822_9d9a601a	2026-01-27 18:59:05.450567
572	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRSEcNWV/	edit： @elizabeth #castiel #supernatural #angel #winchesters #recommen..._7600116192417795349_0738c9a4	2026-01-27 19:00:26.732932
573	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRSEKXaX/	TikTok video #7598601644216945950_7598601644216945950_adee5891	2026-01-27 19:02:01.020473
574	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRAFwVdR/	вы бы знали на сколько это старый ролик..._7600014613287079175_8a01a857	2026-01-28 13:50:56.210026
575	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRAFoN2h/	#fyp #смехуятина #supernatural #destiel #deanwinchester #castiel #све..._7600059082266955026_9ba87be1	2026-01-28 13:54:06.038247
576	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRAYjURR/	#апвоут #истории упоуниягяяв5гчоу6ш3535шг5уг5у5гугу5и6шкттнлантоавнот..._7599880582654332191_25aa9546	2026-01-28 14:01:23.660155
577	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRAYyBLj/	He got so serious😭🙏 #roblox #trolling #parrot #funny #prank _7600150447692860702_eb1ee445	2026-01-28 14:05:09.287568
578	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRA2PLpP/	What is going on in Romania🥀🥀🥀 #romanian #fyp #roblox #robloxfyp #tuff _7599787857129114902_272fb2e8	2026-01-28 15:13:36.766622
579	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRA2qSuE/	My name is Gustavo, but you can call me Gus.  #breakingbad  #betterca..._7309546364139048198_9e51fb26	2026-01-28 15:59:36.818193
580	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRA2vskD/	Gus.. #breakingbad #breakingbadedit #gustavofring #gus #gustavofringe..._7478996960481955079_88452aab	2026-01-28 16:01:45.96737
581	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRA2H3Jw/	#gustavofring ★ ｜ what a respectable and accomplished businessman! #b..._7553335637542325526_cca4e66b	2026-01-28 16:03:08.96759
582	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRA2snJD/	Los Pollos Hermanos edit #breakingbad #gusfring #breakingbadedit #gus..._7575544707724496150_6d4ff9e9	2026-01-28 16:03:32.590265
583	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRAM5wDK/	#RUBYLUCAS she’s so underrated🐺 cc@ℛ𝒾𝓏𝓊𝓃𝒶 ☾ #redridinghood #rubylucas..._7533363046345886998_ae5f65df	2026-01-28 19:27:49.367475
584	6299330933	datapeice	tiktok	Video	https://vt.tiktok.com/ZSaxM5xrw/	#дрип #ресейл #русскийресейл #авито #продажа 	2026-01-29 15:44:51.979861
585	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRA5tf6M/	#жириновский #мем #рекомендации 	2026-01-29 16:29:56.961805
586	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRAaqjV3/	Impossible Magic! ✨ #arnaldomangini #magic #comedy _7580798706132421910_716f1162	2026-01-29 17:37:50.133363
587	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRAaK2bQ/	Кто хотел этот трек？    #музыка #наутилуспомпилиус #скованные #русски..._7600776866550664469_e5c59286	2026-01-29 17:47:16.669626
588	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRAa9A8Q/	tiktok_147b96ab	2026-01-29 17:49:34.978773
589	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRAa4HKr/	Taka o to sytuacja. 👀_7600437182595108118_b58b8163	2026-01-29 17:53:56.946755
590	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRAua5gR/	#фейс #переговоры #яроняюзапад _7471347550189063467_db33dba9	2026-01-29 19:21:58.50471
591	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRAugqgt/	Утешил) #сверхъестественное #динвинчестер #supernatural #edit _7600445534276619538_47b94069	2026-01-29 19:35:51.354807
592	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRAHd6jw/	another try 🙏🏼 regular skeleton and wither skeleton  #witherskeleton #skeleton #humanization #Minecraft #art #fyp 	2026-01-29 20:29:53.647712
593	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRAHmfS8/	#сессия #экзамены #физика #зачёт #смешарики _7600475589895589141_84ebfea9	2026-01-29 21:14:50.304776
594	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRA9eh7G/	tiktok_1d6d6c9d	2026-01-29 21:34:30.016609
595	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRA9FJ9a/	tiktok_76b804e1	2026-01-29 21:43:37.174566
596	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRAHGDXc/	Все самое дорогое тебе 🤗💛 #1с #программирование #it #бизнес _7600704574697114887_6b183dbc	2026-01-29 21:59:08.850262
597	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRAHs45a/	Кто какую версию смотрел Белоснежки ？#надприродне #сверхъестественное..._7600022126866730247_00a9eca8	2026-01-29 22:02:03.069278
598	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRA99Mco/	#металлика #металликаговно #мегадет #metalica #megadeth #металика _7467878071681518868_93cfe02b	2026-01-29 22:53:13.446037
599	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRA9UaDn/	Виталик, купи носки! @newsinshorts_7600781842073013526_37247d2d	2026-01-29 22:58:11.865471
600	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRA9rGLq/	7 Min edit👑🔥 #breakingbad #breakingbadedit #bettercallsaul #bettercal..._7599351186394729750_cfbb1c70	2026-01-29 23:02:35.625213
601	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRA9fB8a/	Возвращение умного профессора #baginette1#gravityfalls#гравитифолз#bi..._7600504666614533396_c6e5e33d	2026-01-29 23:12:14.936719
602	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRA96vhw/	Bad Piggies Theme #piano #metronome #badpiggies #angrybirds #fyp _7600820069769284897_2349fb22	2026-01-29 23:15:41.683561
603	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRAQpFCB/	Когда Мина увольняют с работы и совсем не хватает денег на оплату квартиры, то ему ничего не остаётся, кроме того, как довериться зову брошенной афиши – его единственного шанса на нормальную жизнь, без беготни и безработицы.  Но что делать, когда в цирке его не считают своим, новенькие пропадают быстро и незаметно, а шатер скрывает за собой нечто темное, о чем не хотят говорить даже самые старшие члены цирка? #цирк #Circus #писательство #фикбук #фанфики	2026-01-30 08:30:55.044206
604	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRA9rGLq/	7 Min edit👑🔥 #breakingbad #breakingbadedit #bettercallsaul #bettercal..._7599351186394729750_0e24c59e	2026-01-30 09:00:49.302574
628	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRAgv79M/	tiktok_d8d967e1	2026-01-30 17:52:36.829724
629	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRApeENY/	tiktok_1a0074b3	2026-01-30 17:55:35.504187
630	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRAp4o3m/	Kreosusrad prime... #kreosan #fyp #fypシ #foryou #foryoupage _7599202120096582933_89c4b405	2026-01-30 18:23:08.726815
631	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRAsqvfd/	hear me out это их песня💅 #лучшезвонитесолу #kimwexler #jimmymcgill  ..._7599356405757349127_7726816a	2026-01-30 19:40:17.726362
632	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRAs3wqk/	#наутилуспомпилиус #связаныеоднойцелью #наутилус #бутусов #зима #зима..._7291768780647091461_eb853fe6	2026-01-30 20:26:34.264835
633	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRAGKEom/	TikTok video #7600709897981873439_7600709897981873439_f2a25597	2026-01-30 21:46:02.59327
634	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRAGvWAm/	At least the song is catchy. #supernatural #spn #spnfamily #winchester #winchesterbrothers 	2026-01-30 21:48:45.315681
635	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRAtNacW/	I’m CEO,Bitch. #fyp #fy ##business #facebook #meta #markzuckerberg #t..._7478804805922688278_e7675147	2026-01-30 22:27:20.018246
636	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRAo8xRH/	#babybiyoutefulviralvideos _7600955725430394142_db5cc110	2026-01-31 18:49:03.366597
637	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRD1BMFW/	тгк：влюбленные в природу_7600925351161859348_0e900825	2026-01-31 21:07:43.973197
638	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRD1whxD/	Google is cooking. #ai #agi #gamer #vr #3d_7601198040313007415_5f4919f6	2026-01-31 23:49:36.986177
639	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRDJ2q2N/	#ai #gaming #aigaming #genie3 #google _7600844851587976470_a496044c	2026-01-31 23:57:14.928953
640	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRDNS4sJ/	хочешь миллион？..｜ тестирую метод на качество ｜ song：MONTAGEM VOZES E..._7601795136934153502_232007cf	2026-02-01 18:31:42.456745
641	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRDNrfkq/	tiktok_9d5e5887	2026-02-01 18:47:48.657938
642	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRDNGUPG/	Привіт Максиме! #usa #usa🇺🇸 #epstein #epsteinisland #зднемнародження _7601814514094312725_e68ba5de	2026-02-01 19:10:06.416006
643	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRDNtvYt/	tiktok_8ff3bc4f	2026-02-01 19:43:53.96162
644	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRDYEaoo/	OLX： Tanie_rzeczy01 Bratek nawet nie oznaczył #vinted #foryou #dc #fy..._7599745641945763094_8ee78f0b	2026-02-01 23:40:05.146026
645	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRDkKBV4/	CITY BOI, CITY BOOIII 🗣🚓🌲 #cityboy #meme #gravityfalls #edit #droopl _7595408023636462869_2b590da8	2026-02-02 12:43:41.638712
904	8232490379	/	instagram	Video	https://www.instagram.com/reel/DUnzmNDDewY/?igsh=dXI3dnd2eDZnNXM2	instagram_DUnzmNDDewY	2026-02-14 08:42:20.791458
646	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRDkTGMT/	PUNK ROCKERR!!! #charliebradbury #edit #superman #supernatural #spn _7532506414158318870_69010b5a	2026-02-02 12:55:42.422508
647	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRDB1fVx/	charlie bradbury appreciation post!! 😌 #charliebradburyedit #charlieb..._7560388651104898326_f7aff756	2026-02-02 13:00:13.381088
648	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRDB4TX6/	Спанч Летов #летов #гражданскаяоборона #панк #музыка #мем_7601618262106983702_93bba24b	2026-02-02 13:13:52.845418
649	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRDB5ehQ/	#cityboy #cityboycityboy #funny #niche	2026-02-02 13:30:02.909097
650	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRDyNuWE/	#fyp #рекомендациях #tiktokprank _7593648495706361110_449c9a27	2026-02-02 19:03:44.556753
651	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRDyNFn6/	#SAMIFER #samwinchester #lucifer #сэмифер #сэмиферыканон  #йоу #сэмви..._7602214198965194004_f65f988e	2026-02-02 19:12:15.149648
652	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRDyqLDU/	This video never gets old 😂🔥 #edm #edmmusic #electronicdancemusic #dj..._7601705742780878135_6ae94017	2026-02-02 19:14:21.073308
653	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRDPjfn8/	✍🏻✍🏻 #roman #succession #finance #internship #fyp _7561065717815119126_a74409d2	2026-02-02 21:58:36.141387
654	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRDmHhLx/	чуть шлемак не улетел _7601215693857574165_5fbec5c5	2026-02-03 08:33:53.324631
655	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRDmWP2C/	Вот такие вот пироги #Z #apple _7602283677023866130_f250aae6	2026-02-03 08:39:28.196841
656	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRDuE2Dd/	#epsteinisland #jeffreyepstein #JeffreyEpstein	2026-02-03 09:45:58.850324
657	1022079796	lendspele	tiktok	Video	https://vt.tiktok.com/ZSaGS5drc/	#chara #undertale #deltarune #tobyfox #indiegames 	2026-02-03 12:25:04.191022
658	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRDVBcRg/	This video never gets old 😂🔥 #edm #edmmusic #electronicdancemusic #dj..._7601705742780878135_6c9e29ed	2026-02-03 18:17:58.209276
659	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRDVgSGw/	набор во флуд открыт 🍃 научим всех читать что угодно но только не инф..._7602669934962871560_a693d9e7	2026-02-03 18:31:22.051223
660	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRDV3Q4S/	EVERY COMPANY SELLS YOU OUT_7601721560340155662_25475f91	2026-02-03 18:37:17.496445
661	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRDb1Qs8/	Say hi to King ｜｜ {4K} Supernatural #supernatural #supernaturaledit #..._7602427322465062164_db47736f	2026-02-03 20:57:28.840229
662	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRDbVpDP/	#сессия #экзамены #физика #зачёт #смешарики _7600475589895589141_d6745d64	2026-02-03 21:52:44.377359
663	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRDgecnb/	TikTok video #7595191530395110676_7595191530395110676_af3114bd	2026-02-03 23:33:54.018222
664	6679299852	cogorn	tiktok	Video	https://vt.tiktok.com/ZSaW1TVnc	😍 Amazing Anime Girl 😘 4K Wallpapers #animeart #animegirl #animefyp #animewallpaper #animefan 	2026-02-04 15:52:31.341509
665	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRDTUUSL/	мои любимые дни #чудоостров #эпштейн #остров #мечты #2017 	2026-02-04 17:34:39.410645
666	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRDTCTF9/	#эпштейн #Epstein #подписаться #yilevarak #остров _7587868515965750550_d7d38177	2026-02-04 17:36:28.641559
667	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRDTa3uL/	How Many Did You Get Right ？ #college #interview #fyp _7601205603159018765_d6f0f7be	2026-02-04 17:41:51.129149
668	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRDoRtDV/		2026-02-05 00:02:23.899449
669	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRDoRtDV/		2026-02-05 00:02:51.56373
670	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRUME9rT/	#granicazbialorusia #uchodzcy #nachodzcy #imigrants _7603351961471257858_23d8b915	2026-02-05 21:07:49.695608
671	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRUrugjS/	Это мы летом с Ваней зажигали на Иссык-Куле🎶_7601215792583036167_e80620f6	2026-02-05 22:29:48.985388
672	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRUrqW6W/	дед кас #сверхъестественное #кастиэль #мишаколлинз #доза _7603081196259642631_13a02f2a	2026-02-05 23:02:49.319795
673	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRUr7P4M/	Jeffrey Epstein Pizza Party School Of Rock #epstein #epsteinfiles #je..._7602522786195590430_f5c01d7e	2026-02-05 23:11:29.76809
674	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRUrGwWr/	#світнавиворіт #димакомаров #2010 #рекомендации #edit _7600163983986838806_1572a092	2026-02-05 23:46:40.381166
675	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRUkT77b/	Райан Гослинг известный канадский актер и одна из самых талантливых звезд современного Голливуда. Его карьера показывает, как актер может вырасти из ребенка-исполнителя в международную икону. Гослинг начал свою карьеру в 1990-х годах на шоу Disney Channel The Mickey Mouse Club. Там он работал вместе с другими молодыми исполнителями, которые впоследствии стали звездами, такими как Джастин Тимберлейк и Бритни Спирс. После этого он появился в нескольких телевизионных шоу, прежде чем перейти в кино. Его первое серьезное признание пришло с фильмом "Верующий" (2001), где он сыграл сложного и противоречивого персонажа. Поворотным моментом в его карьере стал "Дневник памяти" (2004). Эта романтическая драма сделала его популярным во всем мире и создала его образ обаятельного и эмоционального актера. Позже Гослинг доказал свой талант в более серьезных ролях. Например, в "Половине Нельсона" (2006) он сыграл учителя, борющегося с зависимостью, и получил свою первую номинацию на "Оскар". Еще одна необычная роль была в "Ларсе и настоящей девушке" (2007), где он изображал одинокого человека с чувствительностью и глубиной. В 2010-х Райан Гослинг стал одним из самых уважаемых актеров своего поколения. Он снялся в "Драйве" (2011), Мартовские иды (2011) и романтическая комедия "Безумная, глупая, любовь" (2011). Эти фильмы показали его универсальность: он мог быть драматическим, политическим или комедийным. Позже он появился в фильмах "Место за соснами" (2012) и "Большая коротка" (2015). Его наибольший успех пришел с мюзиклом "Ла-Ла Ленд". (2016), где сыграл джазового пианиста. Фильм полюбился как критикам, так и зрителям, а Гослинг получил вторую номинацию на "Оскар". После этого он продолжил амбициозные проекты, такие как "Бегущий по лезвию 2049" (2017) и "Первый человек" (2018), доказав свою способность справляться с серьезными и артистическими ролями. Сегодня Райан Гослинг считается не только звездой Голливуда, но и актером с широким артистическим диапазоном. Его карьера демонстрирует самоотверженность, талант и способность постоянно развиваться. #ryangosling #recommendations #real #fyp #миротворец #райангослинг #yanpexxc #бойцовскийклуб 	2026-02-06 08:05:14.727985
676	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRUSLNqo/	Дина любят больше#динвинчестер #фильмы #сверхъестественное #рекоменда..._7602206819158641940_c71672f8	2026-02-06 09:17:22.139349
677	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRUSfMbC/	TikTok video #7603498505264549142_7603498505264549142_07c230d3	2026-02-06 09:32:42.997599
678	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRUDNYb8/	song： MalardD - Tricky #phonk #memes _7585491950070025494_acf28bcd	2026-02-06 11:16:48.731047
679	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRUDrmuF/	#epsteinisland #67 #fyp_7583001165110070550_cbd134ea	2026-02-06 11:17:19.314273
680	1022079796	lendspele	tiktok	Video	https://vt.tiktok.com/ZSaTLq9pD/	#foryoupage #viral #viralvideo #Lion #animals _7601099840713510175_02b00897	2026-02-06 12:38:50.007531
681	1022079796	lendspele	tiktok	Video	https://vt.tiktok.com/ZSaTLw9a6/	Tmr ;V #senderodeldolor #hollowknight #juegos #hollow #dificil _7603446358682389780_bc86e0d3	2026-02-06 12:38:52.488013
682	1022079796	lendspele	tiktok	Video	https://vt.tiktok.com/ZSaTNDqbT/	Eso me hizo tiltear bastante #hollowknight #random #game #fyp #viral _7603195678549921042_f69732db	2026-02-06 12:41:00.134778
683	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRUUTv2j/	#absolutecinema #trentwins #dexter #you #breakingbad	2026-02-06 12:50:31.630272
684	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRUUuRPE/	#avocado 	2026-02-06 12:56:15.656367
685	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRUU3uj5/	DISORDER • Pleasure Point • January 2026 • #systemofadown #lyrics #sa..._7602736738343128351_6b2c061f	2026-02-06 13:00:50.18968
686	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRUUxXJg/	#charliekirk #fyp #viral #blowup #piano _7596762595957247262_309adf66	2026-02-06 13:01:37.935827
687	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRUyhbR8/	I'm from London. #английский #английскийязык #британскийанглийский #e..._7582399560161578258_d3009a33	2026-02-06 13:33:08.774432
688	1022079796	lendspele	tiktok	Video	https://vt.tiktok.com/ZSaTkeE2p/	ip mc.cavecity.space #cavecity #pvp #minecraft #mc #mace _7601411892837371150_1bc647c1	2026-02-06 13:50:24.15852
689	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRU52RsX/	завтра что то нормальное выложу, обещаю #mishacollins #supernatural #..._7601863925377846536_434428f7	2026-02-06 18:18:14.650812
690	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRUaApHK/	A little bottle of water (BrE) #английский #английскийязык #британски..._7601691812805463304_52c82cbc	2026-02-06 19:05:14.998917
691	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRUaSTne/	#эпштейн #остров #островэпштейна #epstein 	2026-02-06 19:12:50.369847
692	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRUar9Ej/	Учительница английского #английский #английскийязык #американскийангл..._7583399838386081032_9181ad89	2026-02-06 19:16:17.50286
693	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRUaHH8m/	#funny #żart _7595986536504708374_f6c42bac	2026-02-06 20:08:01.486424
694	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRUmTfLy/	#comunism #algorithm #sorting # algorithms #sortingalgorithm #sorting..._7484419949730024726_39063535	2026-02-06 23:17:30.646999
695	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRUuXpgH/	#redhat #cybersecurity #linux #fpy #fpyシ _7602650980282404118_cfd04e3f	2026-02-07 00:40:15.430982
696	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRUCoE3q/	Нейронки Эдыт #gimini #google #ai #slop #veo #chatgpt #sora #openai #..._7592604549957864759_171edcda	2026-02-07 12:05:47.81685
697	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRUXjU6c/	Gemini neyronka edit ahah #fyp #gemini #google #genius_7580814722077904149_59b75233	2026-02-07 12:11:49.06526
698	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRUXaj2k/	EVERY COMPANY SELLS YOU OUT_7601721560340155662_9009c566	2026-02-07 12:14:11.734546
699	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRUb6X69/	TikTok video #7604034697894595861_7604034697894595861_17389d0a	2026-02-07 17:50:08.147331
700	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRUph6TP/	https://twitch.tv/dima_shukar #реки #островмечты #эпштейн #обучение #recommendations #папа @rebingnot 	2026-02-07 21:37:38.607797
701	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRUpBnDh/	запомните - макс максбетов никогда не шутит... #максбетов #мем #прикол _7603839154065067277_14242fe6	2026-02-07 22:01:28.976241
702	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRUnhp2H/	TikTok video #7604377489762307345_7604377489762307345_bc920348	2026-02-08 12:34:26.538335
703	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRUnwJUh/	Czy wy jesteście normalni？ 😭_7604103700281330966_07af599e	2026-02-08 14:22:33.217847
704	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRUWxmnJ/	2 Инцидент - Контрольное взвешивание_7604138865212837128_77b23b66	2026-02-08 15:13:42.622269
705	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRUW5cLr/	🇺🇸🦅 #америка #сша #fyp _7602865884863991070_19b204c7	2026-02-08 15:19:15.497716
706	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRUWWatJ/	Английский меня удивляет! #английский #английскийязык #английскийдлян..._7587901808694037791_5f5b57de	2026-02-08 16:20:58.374356
707	5707480536	Paranollk	tiktok	Video	https://vm.tiktok.com/ZNRU7ARqK/	TikTok video #7603827141809163527_7603827141809163527_81c5e030	2026-02-08 17:11:11.088817
708	5707480536	Paranollk	tiktok	Video	https://vm.tiktok.com/ZNRU7ARqK/	TikTok video #7603827141809163527_7603827141809163527_59b578e6	2026-02-08 17:11:19.72123
709	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRU7MoP5/	тгк：gaidulean _7603825697035013383_f9853986	2026-02-08 17:28:50.970542
710	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRU7pBRa/	Дедушка научил 😁 #фильм #сериал #моменты_7604122107814939934_bc17d740	2026-02-08 17:42:57.343699
711	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRU7cLM7/	Ответ пользователю @lisa627642 #supernatural, #сверхъестественное, #d..._7603094352432336136_1b938f1e	2026-02-08 17:43:17.776487
712	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRU7pkmX/	Звук оченб подошёл мне кажется #supernatural #deanwinchester #spnfami..._7604265464742694165_c5cce742	2026-02-08 17:47:21.020179
713	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRU7sweU/	(#DESTIEL) #deanwinchester #castiel #mishacollins #jensenackles #spn ..._7534008535936519446_d10bbd97	2026-02-08 17:56:46.859887
714	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRU7gnV6/	#supernatural #сверхъестественное #castiel #DeanWinchester #дастиэль ..._7581730361508498702_20d1f8b6	2026-02-08 17:57:33.831356
715	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRUvR5on/	село молочное💜 #сверхъестественное #supernatural #spn #кастиэль #лайм _7599390591910202645_505f6abf	2026-02-08 18:03:47.175853
905	8232490379	/	instagram	Video	https://www.instagram.com/reel/DSm2o8ukoj_/?igsh=MTZobzgwMWZzZnA3Zw==	instagram_DSm2o8ukoj_	2026-02-14 09:30:20.229965
716	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRU7bVP9/	Ostatnia nocka - Maciej Maleńczuk English translation #xyzabc #poland..._7568737005799099670_2347e25a	2026-02-08 18:05:27.627757
717	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRUvjQd7/	nie taki zły ten kraj #dlaciebie #fyp #poland #dc #foryou _7598911848225705218_e6aadf7a	2026-02-08 18:28:51.004232
718	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRUvrWcb/	#Olympia  #Olympia2026  #OlympischeSpiele #Sport  #Opening _7604274067683806486_f52cb6b3	2026-02-08 18:41:24.543709
719	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRUvuXKd/	Watch through to the end. #fyp #foryou #foryoupage #ice #politics _7603829576300514573_4ea16040	2026-02-08 18:42:57.247073
720	6299330933	datapeice	tiktok	Video	https://www.tiktok.com/@asya_.235/video/7604150110171254037?_r=1&u_code=e93ci44g0c3e23&preview_pb=0&sharer_language=en&_d=el3f40k4mb6l28&share_item_id=7604150110171254037&source=h5_m&timestamp=1770586223&user_id=7257128984390157338&sec_user_id=MS4wLjABAAAAPrSC4RfpYnxvNqljY4Zyg9yIj5IA0HjlyJoWUChHtEYtG11590IcFOJToPwVASgL&item_author_type=2&social_share_type=0&utm_source=copy&utm_campaign=client_share&utm_medium=android&share_iid=7603615938587739926&share_link_id=209e3e40-28f2-4e69-8cd3-e11b138eeaf0&share_app_id=1233&ugbiz_name=MAIN&ug_btm=b2001&link_reflow_popup_iteration_sharer=%7B%22click_empty_to_play%22%3A1%2C%22dynamic_cover%22%3A1%2C%22follow_to_play_duration%22%3A-1.0%2C%22profile_clickable%22%3A1%7D&enable_checksum=1	слішкам стрьомнувато там #львів #fyp #vibe #core #recommendations _7604150110171254037_57622f66	2026-02-08 21:30:32.355096
721	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRUcGbCd/	#tiktoklive #livehighlights _7587104427429891342_ec1f9e5a	2026-02-08 21:32:21.273222
722	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRUcGKms/	SPIDERMAN JOINS THE FIGHT #tiktoklive #livehighlights _7601572638238068023_d333a6d1	2026-02-08 21:42:32.385002
723	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRU3mPvS/	думаю я ЧУДО ✨ ｜｜ - Dean Winchester 🥵 #сверхъестественное #deanwinche..._7598122817326009611_92ad6248	2026-02-08 23:10:54.194941
724	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRUWxmnJ/	tiktok_52d8999d	2026-02-09 00:09:56.320246
725	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRU3KVQP/	#epstein #epsteinisland #fyp #epsteinedit #jeffreyepstein _7592437472466865415_08beace3	2026-02-09 00:53:12.141204
726	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRUTB4Rs/	my life is a party 🥳 ⧸⧸ #jeffreyepstein #epstein #epsteinisland #jeff..._7600434497556876566_b3db3b3a	2026-02-09 01:01:14.150906
727	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRUTeco7/	TikTok video #7604202741031898388_7604202741031898388_11a962d2	2026-02-09 02:52:42.818599
728	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRUTeco7/	tiktok_kyrohki_tv_7604202741031898388	2026-02-09 09:53:44.964209
729	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRU3KVQP/	tiktok_noxlite_1_7592437472466865415	2026-02-09 09:54:39.572661
730	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRU3KVQP/	#epstein #epsteinisland #fyp #epsteinedit #jeffreyepstein _7592437472466865415_dbd8fce8	2026-02-09 10:01:30.35965
731	6299330933	datapeice	youtube	Video	https://youtu.be/mEVl0NS0vu8	That's AI (2026) - Short Film_mEVl0NS0vu8_d91ad478	2026-02-09 10:02:19.529569
732	6299330933	datapeice	youtube	Music	https://youtu.be/mEVl0NS0vu8	That's AI (2026) - Short Film_mEVl0NS0vu8_e1e18edb	2026-02-09 10:04:26.246414
733	6299330933	datapeice	youtube	Video	https://youtu.be/mEVl0NS0vu8	That's AI (2026) - Short Film_mEVl0NS0vu8_1bf1f8cc	2026-02-09 10:08:45.674094
734	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRUWxmnJ/	tiktok_8b4e3d18	2026-02-09 10:10:56.482732
735	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRUWxmnJ/	tiktok_94ca922e	2026-02-09 10:13:03.08215
736	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRUWxmnJ/	tiktok_7ee68923	2026-02-09 10:14:14.874449
737	6299330933	datapeice	instagram	Video	https://www.instagram.com/reel/DUZCPVHjEMz/?igsh=MXBhaWNudGUyYzhpNg==	Video by aureliaasol_DUZCPVHjEMz_1d91802e	2026-02-09 10:15:47.618589
738	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRU3KVQP/	#epstein #epsteinisland #fyp #epsteinedit #jeffreyepstein _7592437472466865415_705ebf7c	2026-02-09 10:17:58.204938
739	6299330933	datapeice	instagram	Video	https://www.instagram.com/reel/DUZCPVHjEMz/?igsh=MXBhaWNudGUyYzhpNg==	Video by aureliaasol_DUZCPVHjEMz_24cc7ecc	2026-02-09 10:19:34.046266
740	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRUWxmnJ/	tiktok_d09c2520	2026-02-09 10:20:23.256632
741	6299330933	datapeice	twitter	Video	https://x.com/i/status/2019317569057091636	Declaration of Memes - Wizard vs. Knight, the classic showdown! 😎😎😎_2019195383134449664_d8ca0de6	2026-02-09 10:25:58.592664
742	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRUWxmnJ/	tiktok_bea881a2	2026-02-09 10:31:38.528383
743	6299330933	datapeice	youtube	Video	https://youtu.be/S5S9LIT-hdc	My First Line of Code： Linus Torvalds_S5S9LIT-hdc_fec9d7bc	2026-02-09 10:48:03.761367
744	6299330933	datapeice	instagram	Video	https://www.instagram.com/reel/DUZCPVHjEMz/?igsh=MXBhaWNudGUyYzhpNg==	instagram_DUZCPVHjEMz	2026-02-09 10:55:15.286673
745	6299330933	datapeice	youtube	Video	https://youtu.be/S5S9LIT-hdc	My First Line of Code： Linus Torvalds_S5S9LIT-hdc_95154e5f	2026-02-09 10:59:15.19862
746	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRyJqgtK/	#евреи #zанаших #израиль #z #ПредсидательXiмойКумир	2026-02-09 11:02:33.441112
747	6299330933	datapeice	instagram	Video	https://www.instagram.com/reel/DUZCPVHjEMz/?igsh=MXBhaWNudGUyYzhpNg==	Video by aureliaasol_DUZCPVHjEMz_8e9d36d6	2026-02-09 11:06:48.76882
748	6299330933	datapeice	twitter	Video	https://x.com/i/status/2019317569057091636	Declaration of Memes - Wizard vs. Knight, the classic showdown! 😎😎😎_2019195383134449664_314f4b6d	2026-02-09 11:07:13.750467
749	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRyJVunr/	#usa🇺🇸 #donpollo #animalsoftiktok #memestiktok #foryoupage _7604159238331550990_e999ce53	2026-02-09 11:10:20.279038
750	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRyJVunr/	#usa🇺🇸 #donpollo #animalsoftiktok #memestiktok #foryoupage _7604159238331550990_019c75d4	2026-02-09 11:33:48.463473
751	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRyeMppa/	Мод на бедрок майнкрафт _7604139267694021906_963e99da	2026-02-09 12:00:26.903882
752	6299330933	datapeice	youtube	Video	https://youtu.be/YZ5tOe7y9x4	Software engineer interns on their first day be like..._YZ5tOe7y9x4_3a010869	2026-02-09 12:04:02.39495
753	6299330933	datapeice	reddit	Video	https://www.reddit.com/r/AltGirls/comments/1qtlqjj/shes_a_10_but_she_likes_getting_her_toes_sucked_on/?share_id=yUO81r4wDDesFgHVPQfHh&utm_content=1&utm_medium=android_app&utm_name=androidcss&utm_source=share&utm_term=1	she’s a 10 but she likes getting her toes sucked on_opaquesturdystingray_909042cc	2026-02-09 13:37:09.089386
754	6299330933	datapeice	reddit	Video	https://www.reddit.com/r/AltGirls/s/X1vRvstLaV	she’s a 10 but she likes getting her toes sucked on_opaquesturdystingray_f6fabf18	2026-02-09 13:41:44.097262
755	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRyR8dWp/	Лучший человека который создал лучший мессенжер которым пользуются Бо..._7596794618046336273_fecebdb8	2026-02-09 13:46:16.593263
756	6299330933	datapeice	instagram	Video	https://www.instagram.com/reel/DTo3-nbEwaf/?igsh=ZG9oeGVidW5hNjhm	Video by lunalionora_DTo3-nbEwaf_a5fced6f	2026-02-09 13:48:18.092886
757	6299330933	datapeice	twitter	Video	https://x.com/i/status/2020714272482046265	Declaration of Memes - Checkmate 😎_2020684934025814016_90373330	2026-02-09 13:50:44.229707
758	6299330933	datapeice	vk	Video	https://m.vk.com/clip-228687402_456239117?list=26b72d3e4761513c80&from=wall-228687402_303	Clip by @drochyalt_-228687402_456239117_de29a285	2026-02-09 13:57:30.713064
759	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRyRQawC/	#fyp #alt #goth #vampire #altoutfit 	2026-02-09 14:01:38.712174
760	6299330933	datapeice	video	Video	https://rutube.ru/shorts/c4f742af4fbd2dcef53cd1e05076ad4c/	Ульяновск, Московское шоссе, ДТП, очередь из машин на ТЦ АкваМолл, уборка снега. 8 марта 2024 г._c4f742af4fbd2dcef53cd1e05076ad4c_f9907ea7	2026-02-09 14:18:58.349977
761	6299330933	datapeice	instagram	Video	https://www.instagram.com/reel/DTo3-nbEwaf/?igsh=ZG9oeGVidW5hNjhm	Video by lunalionora_DTo3-nbEwaf_aea105f4	2026-02-09 14:29:14.731321
762	6299330933	datapeice	reddit	Video	https://www.reddit.com/r/AltGirls/s/X1vRvstLaV	she’s a 10 but she likes getting her toes sucked on_opaquesturdystingray_6a31d83c	2026-02-09 14:45:34.57379
763	6299330933	datapeice	reddit	Video	https://www.reddit.com/r/AltGirls/s/jqPvxg538o	my boobs love to be out 24⧸7_fastjaggedcaecilian_ab5638f5	2026-02-09 14:48:53.896354
764	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRyLBGng/	pov： to twój ostatni odbiór we wtorek #viral #fyp #pov #trendingnow #..._7604267797094452502_cabad6c8	2026-02-09 15:29:21.854431
765	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRyLR7mt/	#рек #глобальныерек #fyp #куки #мем _7601942988918426893_bede8c09	2026-02-09 15:44:48.891515
766	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRyLht2d/	#fyp #коломойский #тюрьма #україна #политика _7584231309984206136_81368f4f	2026-02-09 15:50:18.195388
767	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRyN157T/	кстати мы тут завтра собираемся напасть на #артемийлебедев #мем #рек_7604551942831951112_e24666f8	2026-02-09 16:59:02.209487
768	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRyLKhAo/	dui or not？ #adesrt #roblox #fyp #dui_7604474636046175510_100dfbcf	2026-02-09 17:03:59.889757
769	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRyLKhAo/	dui or not？ #adesrt #roblox #fyp #dui_7604474636046175510_d9928c25	2026-02-09 17:34:53.724381
770	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRyNkt6r/	EDITMAS DAY 2： WE ARE JOLLY GOOD #jollytok #edit #christmas _7585887359858691342_fbacb57b	2026-02-09 17:35:04.946779
771	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRyFmbmd/	#польская #альтушка😫🥺💍 _7604921399555280150_75394151	2026-02-09 18:47:57.698269
772	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRyFxcmt/	два бидона браги #mysummercar_7509768399128415494_7df1ce69	2026-02-09 18:54:46.250827
773	6299330933	datapeice	youtube	Video	https://youtu.be/CWrwtl_GkpM	НЕРЕАЛЬНЫЕ ТРЕБОВАНИЯ к ДЖУНАМ в 2026 году_CWrwtl_GkpM_bbf79f52	2026-02-09 18:59:49.019911
774	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRyFn5AQ/	TikTok video #7604613705283669266_7604613705283669266_82d0e2bd	2026-02-09 19:02:21.928968
775	6299330933	datapeice	reddit	Video	https://www.reddit.com/r/bigtiddygothgf/s/rHXcnzywfB	Would you pay a visit if I sent you this_fumblingsupportiveanteater_12574e46	2026-02-09 19:08:33.008066
776	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRyFcrBd/	Why is the radio station playing EFN？ #EFN #fypppppppoppppppppppppppp..._7590714141967502622_baf96cac	2026-02-09 19:20:44.166813
777	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRy2DChT/	MY LIL BRO @tolik537 #roblox #robloxfyp #rblx #роблокс _7585253433876172039_aceb9c32	2026-02-09 21:24:32.336224
778	5782116557	egor_smileeey	video	Video	https://www.xv-ru.com/video.okivldb8373/25_	25 сантиметровый член трахает меня ЖЕСТКО_25__ee552e7c	2026-02-09 21:47:00.731043
779	6299330933	datapeice	video	Video	https://sex-studentki.live/video/418108-potryasayushaya-malyshka-zasunula-chlen-mezhdu-sisek-i-pomogla-konchit	Потрясающая малышка засунула член между сисек и помогла кончить (1)_418108-potryasayushaya-malyshka-zasunula-chlen-mezhdu-sisek-i-pomogla-konchit-1_59082012	2026-02-09 22:33:30.049274
780	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRy2m5Yh/	EFN #fyp #guitar #guitartok #epstein #efn _7599234174519643399_b722aec8	2026-02-09 22:39:01.082652
781	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRy2QJF3/	Once upon a time aesthetic #onceuponatimeedit #ouat #ouatedit #onceup..._7491744831769709846_e317ca6f	2026-02-09 22:44:57.302085
782	6299330933	datapeice	youtube	Video	https://youtu.be/dtb0LL0JYgI	Installing Arch Linux as a femboy every day until I find a boyfriend - Day 505_dtb0LL0JYgI_2f6098c0	2026-02-09 22:49:11.052166
783	6299330933	datapeice	youtube	Video	https://youtu.be/CJFUN6BrkGE	КАК РАБОТАЕТ СЖАТИЕ？_CJFUN6BrkGE_1fb3404a	2026-02-09 22:50:07.77777
784	6299330933	datapeice	tiktok	Video	https://www.tiktok.com/@agadada221/video/7604913711840578838?_r=1&u_code=e93ci44g0c3e23&preview_pb=0&sharer_language=en&_d=el3f40k4mb6l28&share_item_id=7604913711840578838&source=h5_m&timestamp=1770677384&user_id=7257128984390157338&sec_user_id=MS4wLjABAAAAPrSC4RfpYnxvNqljY4Zyg9yIj5IA0HjlyJoWUChHtEYtG11590IcFOJToPwVASgL&item_author_type=2&social_share_type=0&utm_source=copy&utm_campaign=client_share&utm_medium=android&share_iid=7603615938587739926&share_link_id=40d680c4-d1a5-4557-8228-5a4709db81ab&share_app_id=1233&ugbiz_name=MAIN&ug_btm=b2001&link_reflow_popup_iteration_sharer=%7B%22click_empty_to_play%22%3A1%2C%22dynamic_cover%22%3A1%2C%22follow_to_play_duration%22%3A-1.0%2C%22profile_clickable%22%3A1%7D&enable_checksum=1	#стинт #stintik #t2x2 #т2х2 #твич #дрейк #дрейк24 #дрейктвич #drakeof..._7604913711840578838_04e685d0	2026-02-09 22:50:09.170227
785	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRy2We2h/	О нет,шутки про ситибой #доза #сверхъестественное #спн #динвинчестер _7604817229749767432_ec8f01e6	2026-02-09 22:53:06.324073
786	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRy2Qmy3/	Shepherd of Fire🔥 #avengedsevenfold #a7x #lyrics_songs #foryoupage❤️❤..._7515580909308087559_f7cadfe0	2026-02-09 23:03:13.983621
787	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRy2nhPL/	скелет под некую музыкальную композицию #скелет #мем #огонь #yeule #ю..._7547750431498308895_18b7c30e	2026-02-09 23:12:48.754773
788	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRy2TtyG/	DOOM ETERNAL ｜ THE ONLY THING THEY FEAR IT'S YOU #games #music #sound..._7372443785541750048_f7b28386	2026-02-09 23:18:49.209554
789	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRy2cMck/	hell yea core #hellyeah #2000s #linkinpark @Robbie ✡︎ _7512224083740871967_0a49cd23	2026-02-09 23:21:05.753676
790	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRy24Kv4/	MENACE TO SOCIETY! ｜｜ #cyberpunk2077 #cyberpunkedit #johnnysilverhand..._7403395728594242847_a70b70c6	2026-02-09 23:24:24.013227
791	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRy2g6ru/	my mind when I hear this song： #song #fyp #metallica #viral #ridethel..._7590132028440333588_832408bf	2026-02-09 23:29:45.866538
792	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRy249MW/	RAHHHH🇺🇲🇺🇲🦅🦅🦅🇺🇲🦅🇺🇲 ｜｜ Test edit ｜｜ #car #race #nascar #usa_tiktok #us..._7463837455859387670_37c5c35d	2026-02-09 23:31:04.127141
793	6299330933	datapeice	instagram	Video	https://www.instagram.com/reel/DT5WIUGClDw/?igsh=emduNmJycGEzMTB3	Video by silent.ackles_DT5WIUGClDw_8098a038	2026-02-09 23:45:40.418463
794	6299330933	datapeice	instagram	Video	https://www.instagram.com/reel/DTZrKrrjIi7/?igsh=MTF6eTF0YXUxYWlsZw==	Video by bhainhihuaesthetic_DTZrKrrjIi7_c6049bec	2026-02-09 23:48:51.152736
795	6299330933	datapeice	instagram	Video	https://www.instagram.com/reel/DT14pDtjUOg/?igsh=MXZvbnFuYTkwdGszZg==	Video by twinzart_jc_nomi_DT14pDtjUOg_36e172ae	2026-02-09 23:51:38.787122
796	6299330933	datapeice	instagram	Video	https://www.instagram.com/reel/DT6-mSvEg-O/?igsh=MXh3NGdkZHV4MmY2	Video by spn_fan_edit_DT6-mSvEg-O_e498be0d	2026-02-09 23:54:31.595377
797	6299330933	datapeice	instagram	Video	https://www.instagram.com/reel/DTWCu20ElBF/?igsh=dTFheDYxaHA3OXQ0	Video by enochianwardingsigil_DTWCu20ElBF_8119eb7c	2026-02-10 00:12:57.227814
798	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRyjNhbx/	Emma Myers Memes #emmamyers #emmamyersedits #enidsinclair #fypシ #vide..._7544782477475302664_b15ec8b0	2026-02-10 00:21:17.227009
799	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRyjJCnH/	TikTok video #7604480911110917396_7604480911110917396_a93ab5ed	2026-02-10 00:25:17.24877
800	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRyjNE6g/	twitch：meowh0cki #meowh0cki #twitchmeowh0cki #твич #twitch #рек_7604453712794225933_abfae2b0	2026-02-10 00:37:10.6802
801	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRyrPbqA/	we both failed.                                     #epstein #physics..._7591360673620266247_f88fdd5b	2026-02-10 09:17:52.437128
802	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRyrfutb/	#dc #fyp #foryou #viral #zyrardow _7597580299173776662_ba965fc2	2026-02-10 09:22:08.831453
803	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRyrr25E/	#dc#żyrardów #milano _7577436716244454678_df829fc4	2026-02-10 09:22:35.464779
804	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRyro7vq/	Arasaka tower be like： #arasakatower #arasaka #tower #johnnysilverhan..._7285066642692902190_39758e0d	2026-02-10 09:46:12.685468
805	6299330933	datapeice	twitter	Video	https://x.com/i/status/2020857717687210245	Declaration of Memes - Wait, which men's section？ 😏_2020763894612910080_7e675b7b	2026-02-10 11:06:44.581752
806	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRykLuf2/	Вторжение 2004 года в Ромашковую Долину на карте #смешарики #хроника ..._7605186354237951254_04b4f538	2026-02-10 11:12:47.707936
807	1022079796	lendspele	tiktok	Video	https://vt.tiktok.com/ZSmRfTVWB/	тгк： mama_shalfeyca ⧸⧸ 🫣_7605167771860733206_cc8a1a20	2026-02-10 11:25:16.753512
808	6299330933	datapeice	youtube	Video	https://youtu.be/wn9_hikpBz8	NEGATIVE Stack of Lime Wool Speedrun_wn9_hikpBz8_8fcaac0b	2026-02-10 11:28:01.87892
809	5331446232	True_Jentelmen	youtube	Video	https://youtu.be/EHpUtZ7yiYc	Five Nights at Skeleton's 2 (It's Been so RAAAH)_EHpUtZ7yiYc_44e98959	2026-02-10 11:44:16.534855
810	1022079796	lendspele	video	Video	https://www.xv-ru.com/video.okivldb8373/25_	25 сантиметровый член трахает меня ЖЕСТКО_25__842f5639	2026-02-10 13:01:27.244734
811	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRyU1gMs/	#газпром #ркн#джонисильверхенд #киберпанк2077 #свобода _7460344442558369054_908fcbf5	2026-02-10 15:46:20.000602
812	1022079796	lendspele	tiktok	Video	https://vt.tiktok.com/ZSmRT1CQK/	Три полоски #рекомендации _7604685066324692245_3d730612	2026-02-10 16:00:27.999654
813	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRyPNgKp/	TikTok video #7600437245706997012_7600437245706997012_4d37dd3b	2026-02-10 19:58:26.291663
814	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRyP2Jdf/	twitch： meowh0cki #meowh0cki_7605130938514705687_45678274	2026-02-10 20:14:21.069247
815	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRy52R5P/	TikTok video #7605168195393211655_7605168195393211655_5b8ae431	2026-02-10 22:49:25.05728
816	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRy5rc85/	credits to 3Blue1Brown #epstein #edit #viral #physics #math _7584315897611898130_cf331dab	2026-02-10 23:46:51.689064
817	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRy5xV5P/	🙏🏻Для всех геймеров💒_7605324269333073160_5543787d	2026-02-11 00:04:43.734616
818	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRy5xV5P/	🙏🏻Для всех геймеров💒_7605324269333073160_0e566433	2026-02-11 00:17:13.222207
819	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRy5ggC9/	Aha dobry trend #dc #dlaciebie #szklanka _7605210092014669078_4cd7e04a	2026-02-11 00:59:27.714581
820	6613424054	nafij123456789	youtube	Video	https://youtu.be/S1Ya823sUTU?si=63ys0Or2on0FyHKn	Waz video editing tutorial Islamic status video editing in InShot_S1Ya823sUTU_86649c01	2026-02-11 05:57:40.498951
821	6613424054	nafij123456789	youtube	Video	https://youtu.be/y5wGlpdbVE8?si=F1IW9oLNjKCG1KcO	Dil Lagana Mana Tha (Official MV) Krish & Kishore Mondal ｜ Kunaal V, Devv S ｜ Sanam Johar Ashi Singh_y5wGlpdbVE8_d68aef28	2026-02-11 06:07:01.50304
822	6613424054	nafij123456789	youtube	Video	https://youtu.be/cW4jkbcD7p4?si=6GFP4bimO7Ct2bqF	রোজা রেখেও অনেক মুসলমান জাহান্নামে যাবে ｜ Anisur Rahman Ashrafi ｜ anisur rahman ashrafi waz 2026_cW4jkbcD7p4_a6532235	2026-02-11 06:15:10.203858
823	6613424054	nafij123456789	youtube	Video	https://youtu.be/cW4jkbcD7p4?si=6GFP4bimO7Ct2bqF	রোজা রেখেও অনেক মুসলমান জাহান্নামে যাবে ｜ Anisur Rahman Ashrafi ｜ anisur rahman ashrafi waz 2026_cW4jkbcD7p4_b0d75828	2026-02-11 06:32:45.503832
824	6613424054	nafij123456789	youtube	Music	https://youtu.be/3nIuj5MYZEo?si=Sql8hrSzAnQieEM3	Islamic Background Music Copyright free ｜ No Copyright Background MUSIC Islamic ｜ Best Islamic Music_3nIuj5MYZEo_78328e0c	2026-02-11 06:49:48.570903
825	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRyHTdmU/	#детство #иванзоло #эпштейн #ии #остров _7605375352063429906_29104497	2026-02-11 10:24:04.972203
826	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRy9L6Y1/	#майнкрафт #украина #донбасс _7595966595378302221_2e6ebc8e	2026-02-11 10:25:02.802496
827	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRy9phTF/	Zu schnell gefahren, zu spät gepostet🫣 #team110 #policetok #polizeinrw _7595890900090260768_41bd2f7a	2026-02-11 11:15:53.490837
828	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRyQSN5T/	#ии #штраф #потужно #зов #украина _7587114149759536402_9cfae2bf	2026-02-11 12:20:20.612416
829	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRyQY28X/	hello #roblox #adesrt #fyp #desrt _7605256844260527382_03105992	2026-02-11 12:22:20.10002
830	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRyQQmHF/	🔥💪🇺🇸 _7604994830472613133_039c8a53	2026-02-11 12:47:53.149466
831	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRyQtmXo/	can’t believe they made metallica from fortnite into a real thing #me..._7605302483300273430_0dbbce9f	2026-02-11 12:51:56.57875
832	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRyQss1F/	all fake ⧸ олл факе #смешарики _7582525929482718486_3c6122fa	2026-02-11 12:54:41.513758
833	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRyCFpMv/	Инцидент №50 «Маршрут». Вы ждёте автобус. Когда он подъезжает, сразу ..._7601948185052843286_6e7f28bf	2026-02-11 13:22:22.844322
834	5331446232	True_Jentelmen	youtube	Video	https://youtu.be/PMUlDyNlmKw	more melodies 👾 #ableton #music #synth_PMUlDyNlmKw_1109d281	2026-02-11 14:51:37.966153
835	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRyVxJBL/	I've drunk two bottles of vodka today. #английский #английскийязык #б..._7605648208307555602_2b58bc95	2026-02-11 17:29:20.895636
836	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRyVhEqG/	Bad apple in the files #touhou#anime #fyp_7605448798436887816_2826600d	2026-02-11 17:31:45.954171
837	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRyVm76L/	#польская#альтушки#польский  _7603425164067360022_1f74f74a	2026-02-11 17:36:55.175301
838	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRyVXY78/	ухх#melrivv #сверхъестественное #кастиэль #aftereffects #edit _7604962493408021781_7fc77484	2026-02-11 17:42:11.529255
839	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRyVcJKJ/	#СВЕРХЪЕСТЕСТВЕННОЕ #SUPERNATURAL #хочуврекомендации #Кастиэль #ангел..._7525009427607407879_fbd64950	2026-02-11 17:43:14.993555
840	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRyVvUka/	basic🇨🇿🤝🇵🇱 #kofola #tymbark #poland #czech #europa #firm #maoers #fyp..._7513753238185708822_75a7035e	2026-02-11 17:57:15.916532
841	6679299852	cogorn	tiktok	Video	https://vt.tiktok.com/ZSmNPxNnp	#мобайллегенд #млбб #mlbbcreatorcamp #mlcreatorcamp #mlbb 	2026-02-11 19:22:35.397858
842	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRybFXtj/	Дин с печатью страшный😭😭😭 #Supernatural #сверхьественное #deanwinches..._7597200050644749590_3ba44170	2026-02-11 19:45:09.811273
843	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRybrbWx/	should i drop some of my ae presets when i reach 3k 😂🙏 ｜ cc, ac, qual..._7544517091370601783_c6a3855d	2026-02-11 19:45:17.497848
844	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRybeafF/	#castiel #fyp #spn #supernatural #angel_7604139862027029780_97784506	2026-02-11 19:56:20.32678
845	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRybLTcM/	my world ｜｜ #capcut #supernatural #spn #deanwinchester #samwinchester _7558159973281221918_15d9304a	2026-02-11 20:01:32.445152
846	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRyb5m36/	#adesrt #roblox #viral #dc #fyp _7604842516621380886_120d4588	2026-02-11 20:46:45.145212
847	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRybKYVD/	С новим 2222 роком вас друзі😂❤️ #кличко #fyp #fup #нг2022 #новыйгод #..._7046670559026957574_2c5ad6d3	2026-02-11 21:46:30.966369
848	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRygPwfC/	Teacher's pet🫩🍵 #studyinghard #femboy #фурри #physics #improvement _7604565679408303361_e276819d	2026-02-11 22:28:44.951613
849	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRygfjj3/	подписуню на тгк egorgorbin 🫶_7586748564559105300_e6b39ea1	2026-02-11 23:30:25.108998
850	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRygg8eo/	TikTok video #7604862309101571348_7604862309101571348_7673382d	2026-02-11 23:31:35.445216
851	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRygEXkD/	ГДЕ ГДЕ ОН РАБОТАЕТ？ #сирион #гений #бог #богиня #летающая тарелка _7596302454497545480_b6485b89	2026-02-12 00:39:29.874159
852	1022079796	lendspele	tiktok	Video	https://vt.tiktok.com/ZSmF5wCGT/	Новогодний розыгрыш： tgk： primdonk #donk #донк #teamspirit #spirit _7583368502166293767_0ae23794	2026-02-12 07:07:38.613186
853	6299330933	datapeice	instagram	Video	https://www.instagram.com/reel/DUdxJ1bjNkt/?igsh=MWE4YXBjODFjOG11Zw==	Video by asicaai_DUdxJ1bjNkt_999eea60	2026-02-12 08:52:45.083489
854	6299330933	datapeice	instagram	Video	https://www.instagram.com/reel/DUOMjqgDLRL/?igsh=cXI5bnZ5empiNGo0	Video by deket_ai_DUOMjqgDLRL_7300664c	2026-02-12 09:02:54.072138
855	6299330933	datapeice	instagram	Video	https://www.instagram.com/reel/DUIB4a1CD_6/?igsh=MTY3aHlmY2NhM2J2OA==	Video by fracefroseofficial_DUIB4a1CD_6_227025a6	2026-02-12 09:40:15.952075
856	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRytkv7H/	TikTok video #7602813708057808158_7602813708057808158_a1e1e51e	2026-02-12 09:46:41.98997
857	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRytvjty/	🤯🤯🤯	2026-02-12 09:49:02.798748
858	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRyvno8E/	#גיבור #ישראל #הסברהישראלית #ביחד_ננצח🇮🇱 #הסברה_ישראלית _7604484051914870024_13ce6252	2026-02-12 13:33:33.579401
859	1022079796	lendspele	tiktok	Video	https://vt.tiktok.com/ZSmYYksHS/	@raylanderdrs _7603720191310122247_a9380672	2026-02-12 13:35:17.650699
860	1022079796	lendspele	tiktok	Video	https://vt.tiktok.com/ZSmYY9xMY/	Getting Toasty#fyp#tiktok_7596989158459985173_f8ac41d0	2026-02-12 13:37:32.686445
861	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRycumbm/	тг： труба ржавая. EFN guitar cover#guitar #guitarcover _7605648908588453141_4c95edd8	2026-02-12 13:38:47.732032
862	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRycyRqv/	#спиртоваядробилка #мяу #14 #88 #мемжпг #рек _7584481477266525471_ec8e7143	2026-02-12 13:42:37.666628
863	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRywqWu1/	!!! PROP !!! ☢️☢️ #foryou #tlustyczwartek #fyp #dlaciebie _7605953665215565078_a64653ca	2026-02-12 17:28:39.390292
864	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRywh8VV/	How to say “I love goth femboys” in Chinese？ #DanqiuChinese #UncleDan..._7604344567424453918_ce3b7e7c	2026-02-12 17:41:32.255028
865	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRyK82nW/	KACHOW 🫶 #edit #fyp #lightingmcqueen #cars #viral _7594762515767119124_95a255a9	2026-02-12 17:45:13.063105
866	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRywKbJy/	ДА Я ПО ПРИКОЛУ ЖЕ СКИНУЛА_7603819329955597575_44f726b5	2026-02-12 17:46:20.529521
906	8232490379	/	instagram	Video	https://www.instagram.com/reel/DUhzCN3DPR9/?igsh=M2V6aTR2eHNldHZy	instagram_DUhzCN3DPR9	2026-02-14 09:44:35.284491
867	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRywsnpK/	Дин с печатью страшный😭😭😭 #Supernatural #сверхьественное #deanwinches..._7597200050644749590_89cedc94	2026-02-12 17:48:10.363061
868	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRywpVJE/	Open ur eyes  #alexkarp #palantir #israel #gaza #freegaza _7592311513579343117_1eb68550	2026-02-12 18:07:22.341979
869	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRyKkcyb/	What unites them all？ 🤫 The Western Wall in Jerusalem, Israel is a sa..._7604058432345230605_2db90c19	2026-02-12 18:21:43.404013
870	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRyKEDGa/	#сверхъестественное#spn #сверхи#спнфандом#fyp _7606052359663340821_584f1e5c	2026-02-12 18:50:58.436952
871	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRyKctoV/	#shitpost #robloxfyp #fart _7604939093285293334_e07e6dec	2026-02-12 18:59:35.817469
872	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRyEbL24/	#havanagila #ukulelecover #femboyfriday #femboytiktok _7435348933850729783_5ad315a8	2026-02-12 20:10:13.008219
873	8232490379	No username	tiktok	Video	https://vt.tiktok.com/ZSmYpcqoL	#pennbadgley #joegoldberg #you #edit #fyp _7605418300239039766_fa1c5aab	2026-02-12 20:36:42.273607
874	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRyokGxd/	Ножки в моём тгк ♥️ #рек #рекомендации #fyp #мем #игры _7605985948458863904_9353de81	2026-02-12 21:16:24.056916
875	6299330933	datapeice	tiktok	Video	https://www.tiktok.com/@wififeido/video/7605626658346880278?_r=1&u_code=e93ci44g0c3e23&preview_pb=0&sharer_language=en&_d=el3f40k4mb6l28&share_item_id=7605626658346880278&source=h5_m&timestamp=1770932049&user_id=7257128984390157338&sec_user_id=MS4wLjABAAAAPrSC4RfpYnxvNqljY4Zyg9yIj5IA0HjlyJoWUChHtEYtG11590IcFOJToPwVASgL&item_author_type=2&social_share_type=0&utm_source=copy&utm_campaign=client_share&utm_medium=android&share_iid=7603615938587739926&share_link_id=2b6074d7-bb2a-497b-ab86-d3678e43a489&share_app_id=1233&ugbiz_name=MAIN&ug_btm=b2001&link_reflow_popup_iteration_sharer=%7B%22click_empty_to_play%22%3A1%2C%22dynamic_cover%22%3A1%2C%22follow_to_play_duration%22%3A-1.0%2C%22profile_clickable%22%3A1%7D&enable_checksum=1	#parati#viral#ignion#foryoupagе _7605626658346880278_3044f010	2026-02-12 21:34:29.711238
876	6299330933	datapeice	youtube	Video	https://youtu.be/mEVl0NS0vu8	That's AI (2026) - Short Film_mEVl0NS0vu8_cc81e332	2026-02-12 22:43:25.742189
877	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRyopB2L/	Youtuber Adbuster wybrał pączki zamiast pelletu_7606109842490674454_a04da12e	2026-02-12 22:45:14.886806
878	6299330933	datapeice	instagram	Video	https://www.instagram.com/p/DUjJxykjf-T/?igsh=MTNpNTBodHRkMTE0dw==	instagram_DUjJxykjf-T	2026-02-12 22:45:15.484782
879	6299330933	datapeice	youtube	Video	https://youtu.be/mEVl0NS0vu8	That's AI (2026) - Short Film_mEVl0NS0vu8_0ef3381b	2026-02-12 22:46:07.028304
880	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRyonwrF/	Hi sadie posted this_7604090160350842142_d2e3dc71	2026-02-12 22:49:08.987435
881	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRf16yrn/	Tesla Optimus robot will allow for amazing abundance. #fyp #viral #te..._7602078079015472397_f4ad3a0a	2026-02-13 00:51:00.577686
882	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRf1DdUy/	Kiss me in London 💋_7605655905807486230_2b50d592	2026-02-13 00:53:02.325926
883	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRfJvW8U/	I didn't know what to put and it made me laugh #crowley #supernatural..._7606124584131104022_b9af4ff5	2026-02-13 07:43:39.218125
884	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRfe1vmY/	Эдит взял у @killhack404 #mrrobot #мистерробот_7606033979191512340_8261e4b9	2026-02-13 07:47:40.403166
885	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRfJcEaV/	5 интересных фактов о стране смешариков. Часть 3 #смешарики #интересн..._7598158008111172886_c24bfc89	2026-02-13 08:09:22.651296
886	6299330933	datapeice	instagram	Video	https://www.instagram.com/reel/DN23_wI0ML8/?igsh=aTJuenl2dXZsN2Ey	instagram_DN23_wI0ML8	2026-02-13 09:26:32.674044
887	6299330933	datapeice	instagram	Video	https://www.instagram.com/p/DUjXlZXgC1i/?igsh=aHhwM3pyNnA3OGw1	instagram_DUjXlZXgC1i	2026-02-13 09:26:47.813044
888	6299330933	datapeice	instagram	Video	https://www.instagram.com/reel/DSKXOyMAoGw/?igsh=eDNsdzM5ejh5MXph	instagram_DSKXOyMAoGw	2026-02-13 10:14:23.436152
889	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRfRT3Sg/	#gaming #orbsync #fyp #pcgaming #israil 	2026-02-13 11:00:53.968281
890	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRfRvTGB/	150M FPS question mark #fyp #silentgd #gd #geometrydash #levelgd #hsll _7604262617502240022_225f0cdc	2026-02-13 11:03:02.582069
891	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRf8fuWS/	The Wall of 2000 Snakes and the King of Snakes #スリザリオ #slitherio #sho..._7590949183822286101_91f7b952	2026-02-13 11:12:19.165552
892	1022079796	lendspele	tiktok	Video	https://vt.tiktok.com/ZSmjFBNMX/	ХАХАХАХАХА #рек #врек #школа #вещи #ларек _7605514079217732877_8da86a87	2026-02-13 11:22:33.730579
893	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRf8b6AK/	Искусственный интеллект #искусственныйинтеллект #интеллект #английски..._7592241179345833234_b74c734c	2026-02-13 11:53:38.838384
894	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRfLujmH/	🤫 . #школа #экзамены #физика #абитуриент #егэ _7605694305721666834_6858cdef	2026-02-13 12:37:42.925381
895	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRfFm5dM/	#прикол #memes #рофл _7606356494140869919_5c082a53	2026-02-13 15:10:49.652899
896	8232490379	/	tiktok	Video	https://vt.tiktok.com/ZSmjpKjqN	if this flops i quit ｜｜ #moneyheist #moneyheistedit #berlinmoneyheist..._7597598510313164054_6be93a99	2026-02-13 17:15:50.896867
897	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRf6V1a7/	These guys work tirelessly everyday to make our world a better place 👏🫡 #blackrock #palantir #techtok #ethics101 	2026-02-13 22:22:39.755702
898	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRf6oama/	#africantiktok #africannews #funnyafricanvideos #africa #africancomedy _7588555583721049375_b613835a	2026-02-13 23:12:40.195235
899	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRfM1wDJ/	Toxic #edit #foryoupage #foryou #fypシ #clips_7020139866138725634_80498107	2026-02-13 23:19:13.723368
900	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRf63DdV/	He slays #supernatural #spn #nieztegoświata #spncrowley #crowley #cro..._7606108528163491094_a9cccec4	2026-02-13 23:49:39.07407
901	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRf6KHf1/	Дедский центр в 1930 году /мем/mem	2026-02-14 00:08:41.5269
902	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRfMqFuj/	Creeping Death @metallica @Jason Newsted #metallica #thrashmetal #met..._7594049245011823894_8e6a02c2	2026-02-14 01:10:27.807115
903	8232490379	/	tiktok	Video	https://vt.tiktok.com/ZSm6oBmg9	Тесты1. Какая функция цены в наибольшей мере реализуется с помощью НД..._7606387916083973389_53f1f377	2026-02-14 07:49:08.614298
907	8232490379	/	instagram	Video	https://www.instagram.com/reel/DUajYpriOOw/?igsh=NGNua3diNW41eDVv	instagram_DUajYpriOOw	2026-02-14 10:15:22.986778
908	6299330933	datapeice	instagram	Video	https://www.instagram.com/p/DUWpuobDxTR/?igsh=aTB2NDY1dmtqaHVy	instagram_DUWpuobDxTR	2026-02-14 12:35:20.75779
909	6299330933	datapeice	instagram	Video	https://www.instagram.com/reel/DUqiYpWDFxm/?igsh=MWR2bnNkbmhmc2JoZw==	instagram_DUqiYpWDFxm	2026-02-14 12:35:37.565245
910	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRfAQxjp/	Ответ пользователю @Тгк：Бедный еврей Выглядит классно #смешарики #опе..._7606419152009563413_49d5f44b	2026-02-14 12:40:36.029238
911	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRfAACjm/	#fyp #mommyasmr #school #viral #foryoupage 	2026-02-14 12:46:23.711834
912	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRfAb6Nn/	Две легенды. #олегтинькофф #павелдуров #эдит #тиньков #fyp _7587099761061252407_346fde88	2026-02-14 13:31:23.283637
913	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRfDYXVp/	не винцест прости господи это он сам так пошутил #spn #динмояомега #с..._7606583730647420181_30330c8b	2026-02-14 13:54:28.552732
914	6299330933	datapeice	instagram	Video	https://www.instagram.com/reel/DOigK99EyYB/?igsh=MTcyaXZuaXpweXZkcA==	instagram_DOigK99EyYB	2026-02-14 15:25:33.139574
915	5331446232	True_Jentelmen	youtube	Music	https://www.youtube.com/watch?v=GbvatwV4vqg	King of Kids (The Finale)_GbvatwV4vqg_f684c328	2026-02-14 21:34:33.742818
916	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRfPfo6D/	So happy to announce the job offers I recieved from all these companies. I couldn’t be any happier that my hard work is finally paying off. #whatsnext #fyp #epsteinfiles #lockheed #imevil 	2026-02-14 21:35:31.384566
917	5331446232	True_Jentelmen	youtube	Music	https://www.youtube.com/watch?v=BafolbWf6no	Pedomaxx ｜ Feat. Epstinculius The 3rd (tiktok audio)_BafolbWf6no_910000a7	2026-02-14 21:35:50.982982
918	5331446232	True_Jentelmen	youtube	Music	https://www.youtube.com/watch?v=7FoWLmwNF6U&pp=0gcJCYcKAYcqIYzv	Incredible Dingo Dongo (Scary Shower song) Feat. EDiddy P. (tiktok audio)_7FoWLmwNF6U_9028ff07	2026-02-14 21:36:24.504016
919	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRfPKnoM/	Jeffrey Epstein #fyp #viral #goviral #epsteinisland #jeffreyepstein _7585252351150165304_0c73cbfd	2026-02-14 23:10:58.80766
920	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRfPvggR/	Нельзя так _7606839720789773589_40c93efe	2026-02-14 23:19:12.656575
921	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRfPWRK7/	#fyp #supernatural #сверхъестественное #сверхи #deanwinchester #динви..._7606777069137104146_df5ac739	2026-02-14 23:33:06.191587
922	7809554925	arsema630	youtube	Music	https://youtu.be/aMH8zpYTWZg?si=CN8pWlFS73Iv-109	Dn Tadele begena mezemure(sigefugne)_aMH8zpYTWZg_734732de	2026-02-15 09:48:11.862262
923	7809554925	arsema630	youtube	Music	https://youtu.be/jBXHvAeUJ7M?si=3ZJ25Oel7697GRgG	Alemu Aga playing on the David Harp, the BEGENA from Ethiopia- Tew Simagn Hagere Traditional_jBXHvAeUJ7M_59602871	2026-02-15 09:49:00.233181
924	7809554925	arsema630	youtube	Music	https://youtu.be/tSsOr_894Zc?si=5c-_SjJoFuTsmMt5	Ethiopian Orthodox Tewahedo -Begena ( Dn . Tadele)_tSsOr_894Zc_0679d766	2026-02-15 09:50:01.880323
925	7809554925	arsema630	youtube	Music	https://youtu.be/QAkBRSkDBPY?si=i5MXnUW2TqwvXnRm	Ethiopian Orthodox Tewahedo Begena mezmur Kesis Akalau_QAkBRSkDBPY_cc0e6d98	2026-02-15 09:50:29.284969
926	7809554925	arsema630	youtube	Music	https://youtu.be/N5y9_XrcKkA?si=wLe_umpdL2WkOCWO	Begena tewahedo.org_N5y9_XrcKkA_407183d1	2026-02-15 09:51:53.622585
927	7809554925	arsema630	youtube	Music	https://youtu.be/PAo2JJLmBZk?si=c5Pz75Z8yFpMpQIG	begena yeliel aleku_PAo2JJLmBZk_5be9d45c	2026-02-15 09:52:25.863754
928	7809554925	arsema630	youtube	Music	https://youtu.be/7Xe-DMpGyVY?si=otwvBlCZpxSs6MX7	Ethiopian begena zelessengha new 2012_7Xe-DMpGyVY_7a208ccb	2026-02-15 09:53:14.163192
929	7809554925	arsema630	youtube	Music	https://youtu.be/TggfpDQDI3I?si=ANECIsxzi28lGCBO	Ethiopian Orthodox Tewahedo Begena Mezmur by Kesis Akalu_TggfpDQDI3I_042e71f9	2026-02-15 09:53:26.763192
930	7809554925	arsema630	youtube	Music	https://youtu.be/26J7rs2nvrI?si=Ugbgdr3LUHfygSdW	yetm begena_26J7rs2nvrI_29dd28de	2026-02-15 09:54:12.683871
931	7809554925	arsema630	youtube	Music	https://youtu.be/EepCrche55s?si=4F0iOH9n1nA_fuUI	Zemari Abel Tesfaye Begena Muzmur ＂Seme Dawit＂ ዘማሪ አቤል ተስፋዬ ＂ስሜ ዳዊት＂_EepCrche55s_19cdef91	2026-02-15 09:55:13.539294
932	7809554925	arsema630	youtube	Music	https://youtu.be/g0wd27zokVo?si=PFEd2qX7B9crnmsS	🔴ስሜ ተለዉጦ ⧸  ዳን በገና  ｜  Semay Teleweto by Dan Begena_g0wd27zokVo_7b80a720	2026-02-15 09:57:20.376156
933	7809554925	arsema630	youtube	Music	https://youtu.be/yalLNU74Hig?si=EPSAhPsLn94DJUcA	1 Eyesus Tarede_yalLNU74Hig_f0cc962b	2026-02-15 09:57:46.431121
934	7809554925	arsema630	youtube	Music	https://youtu.be/3NkKbafhX1c?si=rbXz0je5N06wYmAI	2 Lemignilin Dingil_3NkKbafhX1c_4ae30bcb	2026-02-15 09:58:16.577737
935	7809554925	arsema630	youtube	Music	https://youtu.be/SRn2nsCygsw?si=na-EevpBKqaEMous	4 Estifanos_SRn2nsCygsw_dd2de9fe	2026-02-15 09:59:10.423638
936	7809554925	arsema630	youtube	Music	https://youtu.be/dHVfL1x01vo?si=fjXE61kx0XA7vDrF	5 Man Yikom Yihon_dHVfL1x01vo_af480f15	2026-02-15 09:59:26.498268
937	7809554925	arsema630	youtube	Music	https://youtu.be/TnS1NKQeaYs?si=rT_iPulOePKUk8e9	6 Wuha Atechign Alat_TnS1NKQeaYs_927b22a5	2026-02-15 09:59:43.599674
938	7809554925	arsema630	youtube	Music	https://youtu.be/ey-XGvo76RE?si=l1dmWNawDPVk1PWP	7 Endecherinetih Adinen_ey-XGvo76RE_f2d886fd	2026-02-15 10:00:11.565777
939	7809554925	arsema630	youtube	Music	https://youtu.be/xJ5ifTMqDnw?si=P7RfMEUv3bjutv06	8 Alazar Yinesa_xJ5ifTMqDnw_b360ce59	2026-02-15 10:00:28.987822
940	7809554925	arsema630	youtube	Music	https://youtu.be/b7h-iLoZLgM?si=1GPY5YAhcUc1-VDf	9 Enlemin Dingilin_b7h-iLoZLgM_9c001527	2026-02-15 10:00:35.850614
941	7809554925	arsema630	youtube	Music	https://youtu.be/AM3vXeMhH34?si=bBTotsMgvYoTRrG7	Ethiopia 🔴 ንስሃ ዝማሬ- ስለ ቸርነትህ｜ ሊቀ መዘምራን ይልማ ኃይሉ ｜ like mezemran Yilma hailu mezmur_AM3vXeMhH34_5c407490	2026-02-15 10:03:39.963494
942	7809554925	arsema630	youtube	Music	https://youtu.be/_GIhP_zmOiw?si=dqyIdlNEg9rTQdpK	🔴ተለቀቀ ሳይቋረጥ ይሚደመጥ ሙሉ አልበም ሊቀ መዘምራን ይልማ ኃይሉ like mezemran yilma hailu__GIhP_zmOiw_1b2e5794	2026-02-15 10:03:50.614793
943	7809554925	arsema630	youtube	Music	https://youtu.be/GTtyvGDvLLk?si=StUwQUbuGCqdjInD	Ethiopia 🔴 ንስሃ ዝማሬ- በህይወቴ በዘመኔ｜ ሊቀ መዘምራን ይልማ ኃይሉ like mezemran Yilma hailu mezmur_GTtyvGDvLLk_fae4ce81	2026-02-15 10:11:58.823435
944	7809554925	arsema630	youtube	Music	https://youtu.be/AM3vXeMhH34?si=gWCgxERmBofE-hwk	Ethiopia 🔴 ንስሃ ዝማሬ- ስለ ቸርነትህ｜ ሊቀ መዘምራን ይልማ ኃይሉ ｜ like mezemran Yilma hailu mezmur_AM3vXeMhH34_c8ea7e3c	2026-02-15 10:12:14.384763
1013	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRfgw216/	#фог #мытищи #fog_7607113445435051271_a841eb15	2026-02-16 13:47:34.684284
945	7809554925	arsema630	youtube	Music	https://youtu.be/cJcLe4xkSWI?si=98DH_JBWzae3lxbz	Ethiopia 🔴 ንስሃ ዝማሬ- አበው ፀልዩ ｜ ሊቀ መዘምራን ይልማ ኃይሉ ｜ abew tseliyu ｜ like mezemran Yilma hailu_cJcLe4xkSWI_1051a917	2026-02-15 10:14:29.089016
946	7809554925	arsema630	youtube	Music	https://youtu.be/0M3WEszpmuI?si=3voaIEqOVkHKjI-0	Ethiopia 🔴 ንስሃ ዝማሬ- እመቤቴ ማርያም እለምንሻለው｜ ሊቀ መዘምራን ይልማ ኃይሉ ｜ #like_mezemran_Yilma_hailu_mezmur_0M3WEszpmuI_82323d6d	2026-02-15 10:14:56.081129
947	7809554925	arsema630	youtube	Music	https://youtu.be/Hw6M3PC8vtA?si=HBJ9HhvPnorMMZhF	Ethiopia 🔴 ዘለሰኛ ዝማሬ- ዋ እኔን｜ ሊቀ መዘምራን ይልማ ኃይሉ ｜ like mezemran Yilma hailu zelesegna mezmur_Hw6M3PC8vtA_7daf8753	2026-02-15 10:15:27.031965
948	7809554925	arsema630	youtube	Music	https://youtu.be/emQ314D_Udc?si=X0H_1LAPbEUfLTGy	Ethiopia 🔴 ንስሃ ዝማሬ- ከመላዕክት ጋራ｜ ሊቀ መዘምራን ይልማ ኃይሉ ｜ like mezemran Yilma hailu mezmur_emQ314D_Udc_d1aa9683	2026-02-15 10:15:43.050312
949	7809554925	arsema630	youtube	Music	https://youtu.be/YW55D2j3MGM?si=IKFs8CV4vcpBNW1l	ንስሃ ዝማሬ- ከካራን ውጡ｜ ሊቀ መዘምራን ይልማ ኃይሉ ｜ like mezemran Yilma hailu mezmur_YW55D2j3MGM_21a8621f	2026-02-15 10:16:32.776133
950	7809554925	arsema630	youtube	Music	https://youtu.be/L1uDeVf1A0s?si=8CPl3wlX_gMKnYUh	Track 1 ስለ ቤተክርስቲያን ዝም አልልም Like Mezemran Yilma Hailu New Album sile betekrstian_L1uDeVf1A0s_1735e31a	2026-02-15 10:17:05.796638
951	7809554925	arsema630	youtube	Music	https://youtu.be/4okW6WN9Wv4?si=S5MWAlZaegb1-e23	Ethiopia - የሊቀ መዘምራን ይልማ ኃይሉ ቁጥር 1 ንስሃ አልበም ዝማሬዎች like mezemran yilma no.1 mezmur album_4okW6WN9Wv4_66dcece1	2026-02-15 10:17:29.908518
952	7809554925	arsema630	youtube	Music	https://youtu.be/-4KtrlQsxgM?si=iKHPvLWqakUqgg7e	Track 2 በቅድስና Like Mezemran Yilma Hailu New Album bekidisna_-4KtrlQsxgM_d0113370	2026-02-15 10:17:54.753686
953	7809554925	arsema630	youtube	Music	https://youtu.be/t4dpip9YY2E?si=4m3SOjRWkS4xI5fF dz	Track 3 ድሃ ራሱን ላንተ ይተዋል Like Mezemran Yilma Hailu diha rasun_t4dpip9YY2E_58c3a200	2026-02-15 10:18:41.903819
954	7809554925	arsema630	youtube	Music	https://youtu.be/_s3y1EIKovE?si=nyQFpvGrY70OOiz8	Track 4 የገበሬ ሀይማኖት Like Mezemran Yilma Hailu New Album yegebere haymanot__s3y1EIKovE_559d4967	2026-02-15 10:19:10.520353
955	7809554925	arsema630	youtube	Music	https://youtu.be/CSjpAjpGvKk?si=Py_KT09UB-6-65B-	Track 5 ይትባረክ እግዚአብሔር Like Mezemran Yilma Hailu New Album yibarek egziabher_CSjpAjpGvKk_bbf0cbac	2026-02-15 10:20:07.144917
956	7809554925	arsema630	youtube	Music	https://youtu.be/-LogAJsqoqU?si=kA7P_N8ccPsWRzjK	Track 6 ከመቅደሱ ደጃፍ Like Mezemran Yilma Hailu New Album kemekdesu dejaf_-LogAJsqoqU_f83ebe52	2026-02-15 10:20:27.755172
957	7809554925	arsema630	youtube	Music	https://youtu.be/OlaQm9D1FX8?si=W7nw3Fi6Z07ytJyh	Track 7 ፈጥነሽ የምትደርሺ Like Mezemran Yilma Hailu New Album fetnesh yemitdershi_OlaQm9D1FX8_46d2b0ea	2026-02-15 10:21:03.90351
958	7809554925	arsema630	youtube	Music	https://youtu.be/QKzYRGTcQM8?si=M5tMkjxgw49Rvyho	Track 8 እግዚአብሔር እረኛዬ ነው Like Mezemran Yilma Hailu egziabher eregnaye new_QKzYRGTcQM8_02bdc410	2026-02-15 10:21:25.622396
959	7809554925	arsema630	youtube	Music	https://youtu.be/LDbPU5Vnhsg?si=wfklRZYKcRiw71z-	Track 9 አርገ እግዚአብሔር Like Mezemran Yilma Hailu New Album arge egziabher_LDbPU5Vnhsg_aec9e551	2026-02-15 10:22:20.134337
960	7809554925	arsema630	youtube	Music	https://youtu.be/srdnZFiqacU?si=dB1HdojY0Xfb0K4c	Track 10 ምስጋና Like Mezemran Yilma Hailu New Album misgana_srdnZFiqacU_1dfeb3d0	2026-02-15 10:22:40.546728
961	7809554925	arsema630	youtube	Music	https://youtu.be/wxToDj-YpGQ?si=7EFrbIRQ9Q1IsSi8	🔴ፈያታዊ ዘየማን like mezemran ylma hailu_wxToDj-YpGQ_e4bdbbc4	2026-02-15 10:23:07.061479
962	7809554925	arsema630	youtube	Music	https://youtu.be/IvF9vy5JDLs?si=wPZX3Z642TtgFkMp	🔴ማረኝ like mezemran yilma hailu maregn_IvF9vy5JDLs_ccb0a695	2026-02-15 10:23:38.405293
963	7809554925	arsema630	youtube	Music	https://youtu.be/FJDZn3GacGY?si=UukqEmC4J76s4x1c	🔴ኃይልህ ሲገለጥ ከሰማይ like mezemran yilma hailu_FJDZn3GacGY_41a8c56b	2026-02-15 10:23:56.550229
964	7809554925	arsema630	youtube	Music	https://youtu.be/coqCuL6xKTE?si=GuGsYF0yPXQY_kSX	🔴የጴጥሮስን እንባ like mezemran yilma hailu_coqCuL6xKTE_c84af1cc	2026-02-15 10:24:27.932589
965	7809554925	arsema630	youtube	Music	https://youtu.be/7CCtH3TxknQ?si=3ao5NqPHtsqiTLAf	Ethiopia🔴የኤቲሳ እንበሳ like mezmeran yilma hailu_7CCtH3TxknQ_56db15fe	2026-02-15 10:24:59.002997
966	7809554925	arsema630	youtube	Music	https://youtu.be/6AF9ax51ypQ?si=fXULy_gg4xg4TuQI	ethiopia🔴የማህፀን ፀብ ｜｜ like mezmran yilma hailu_6AF9ax51ypQ_172fd2f6	2026-02-15 10:25:10.841691
967	7809554925	arsema630	youtube	Music	https://youtu.be/awEEu-ksbNk?si=Dy9FB65icn9BjYrH	🔴በመከራ ላለው like mezemran yilma hailu_awEEu-ksbNk_b2641deb	2026-02-15 10:26:36.029602
968	7809554925	arsema630	youtube	Music	https://youtu.be/sktHGeNhxu8?si=BMxSJZkAMw74IwFO	ሁነኛ ጓደኛ ｜ ሊቀ መዘምራን ይልማ ኃይሉ ｜ like mezmran yilma hailu_sktHGeNhxu8_9748a716	2026-02-15 10:27:00.312202
969	7809554925	arsema630	youtube	Music	https://youtu.be/36oWXbJeXO4?si=yaFcEE8kc2llFZEw	Ethiopia 🔴የሕማማት ዝማሬ - እውነት ስለሆነ ሊቀ መዘምራን ይልማ ኃይሉ like mezemran Yilma hailu hemamat_36oWXbJeXO4_7b8f2f03	2026-02-15 10:27:10.969561
970	7809554925	arsema630	youtube	Music	https://youtu.be/wNgbPKvY8MQ?si=waaGDpq3tEmjXbNK	🔴በይስሐቅ ፈንታ like mezemran yilma hailu_wNgbPKvY8MQ_3aafe22f	2026-02-15 10:28:01.828646
971	7809554925	arsema630	youtube	Music	https://youtu.be/tjD-KHslulg?si=XGgT23edmrSgLcXJ	🔴በሰው ዘንድ like mezemran yilma hailu_tjD-KHslulg_ae5673ab	2026-02-15 10:28:14.109451
972	7809554925	arsema630	youtube	Music	https://youtu.be/xS3vbKmLEqM?si=fG_UgS2zvpx4gAYb	🔴ያ ድሃ ተጣራ like mezemran yilma hailu_xS3vbKmLEqM_d403cff5	2026-02-15 10:28:27.210335
973	7809554925	arsema630	youtube	Music	https://youtu.be/g9P-WGsJJnc?si=FJl38Vmtmu7nxLyY	🔴አቤቱ ደግ ሰው አልቋልና like mezemran yilma hailu ሊቀ መዘምራን ይልማ ኃይሉ በገና መዝሙር_g9P-WGsJJnc_bfb93737	2026-02-15 10:28:45.5711
974	7809554925	arsema630	youtube	Music	https://youtu.be/9tIuXhOp6Vc?si=9WYrkd2KDyDi4yup	Ethiopia 🔴የሕማማት ዝማሬ - አቤት ፍቅሩ የእግዚአብሔር ሊቀ መዘምራን ይልማ ኃይሉ like mezemran Yilma hailu hemamat_9tIuXhOp6Vc_fa622876	2026-02-15 10:29:21.224378
975	7809554925	arsema630	youtube	Music	https://youtu.be/wDZuQVD5ce4?si=cdpNG3Xd0ssYONcp	እንደ ጴጥሮስ እንደ ዮሀንስ (እንዳትመራመረኝ በጥቂት ነገር ማረኝ) ：በገና መዝሙር_wDZuQVD5ce4_c1f15b69	2026-02-15 10:29:47.900869
976	7809554925	arsema630	youtube	Music	https://youtu.be/PfcQVFhT48A?si=vAhLjl3s9lq_4iJ6	🔴 ነይ ድንግል ዘማሪ ሀኖስ ｜ New orthodox begena mezmure 2025_PfcQVFhT48A_c693c388	2026-02-15 10:30:05.001329
1144	6299330933	datapeice	reddit	Video	https://vm.tiktok.com/ZNR58QPYS/	Your move…_crisptremendouszebra_ce2a3d59	2026-02-22 22:25:06.130694
977	7809554925	arsema630	youtube	Music	https://youtu.be/yX4GoNaQ_eM?si=qv5Fuo-bmb0soJbh	ለኔስ ልዩ ነሽ ድንግል ማርያም.... ተወዳጁ የድንግል ማርያም ዝማሬ ተለቀቀ! ሊቀ መዘምራን ይልማ ኃይሉ በገና ዝማሬ⧸lenes leyu nesh Ethiopia_yX4GoNaQ_eM_c79dc5b3	2026-02-15 10:30:24.492597
978	7809554925	arsema630	youtube	Music	https://youtu.be/Tuiwe_EHTYg?si=HWoBfa8FL_tgCcFi	🔴የብርሃን እናት ነሽና like mezemran yilma hailu_Tuiwe_EHTYg_021d894a	2026-02-15 10:30:41.498539
979	7809554925	arsema630	youtube	Music	https://youtube.com/shorts/p3xUSOvznGw?si=c8DbDiXySCOWeBlV	ደምሴ ደስታ ⧸ Demissie Desta የበገና ድርደራ_p3xUSOvznGw_f42b8e60	2026-02-15 10:33:39.19263
980	7809554925	arsema630	youtube	Music	https://youtu.be/7C4bLfsiZus?si=BJQhmuMzcigoa8r0	አያ ሞት እንግዳ_7C4bLfsiZus_a887b5a0	2026-02-15 10:33:41.750713
981	7809554925	arsema630	youtube	Music	https://youtu.be/BZiifr6zmdg?si=MxoNl1FHUpgFG9Kt	ደምሴ ደስታ፣ ጥንታዊ  የበገና ድርደራ ｜ በገና፣ ሀገር፣ ወኔ፣ ጀግንነት ｜ Old Begena Mezmur, Demsie Desta_BZiifr6zmdg_2b9a0a1b	2026-02-15 10:35:54.490671
982	7809554925	arsema630	youtube	Music	https://youtu.be/qUm_fxq6nVQ?si=EF7zqXaW1oP1Uw4m	የአቶ ደምሴ 'በገና' ደስታ የበገና መዝሙሮች ስብስብ - ethiopian orthodox tewahdo church begena mezmur_qUm_fxq6nVQ_dbef38d7	2026-02-15 10:36:13.414833
983	7809554925	arsema630	youtube	Music	https://youtube.com/shorts/zNBxlmhx_1s?si=ANXJH-WNliv5wpd9	ጋሽ ደምሴ ደስታ 🤎🙏 #begena #kidus_begena #nostalgicbegena #gerf #kidusbegena_zNBxlmhx_1s_129855f4	2026-02-15 10:37:28.622045
984	7809554925	arsema630	youtube	Music	https://youtu.be/yzH5UlA6vjI?si=VpIVtOD5xnsZjz_M	Ethiopian Orthodox Begena Mezmur By Demisse Desta All Tracks   ኢትዮጵያዊ የበገና ድርደራ መዝሙራት   በአቶ ደምሴ ደስታ_yzH5UlA6vjI_9372954a	2026-02-15 10:39:46.155383
985	7809554925	arsema630	youtube	Music	https://youtu.be/rnXZ_nEyjv0?si=xKC4OJOnavllbgkj	ሞቴን አየሁት_rnXZ_nEyjv0_6f59681e	2026-02-15 10:40:42.197855
986	7809554925	arsema630	youtube	Music	https://youtu.be/y5xYpSjjBVM?si=WGGxw0zQ6SwtG2ca	ደምሴ ደስታ በገና ለነፍስ ሀሴት የሚሆን ዝማሬ_y5xYpSjjBVM_bb28317b	2026-02-15 10:40:44.485465
987	7809554925	arsema630	youtube	Music	https://youtu.be/4VsSuqfKuOg?si=M2BpVYN0i1DG3JtP	የቆየ በገና መዝሙሮች Old Begena Ethiopian Orthodox Harp Mezmur_4VsSuqfKuOg_8c9cb2b8	2026-02-15 10:41:11.274824
988	7809554925	arsema630	youtube	Music	https://youtu.be/5P2HQ4hTCkg?si=1g8MDg70edvE7ipk	begena mezimure '' ሞት እንዴት ሰነበትክ''｜ ልዩ የበገና መዝሙር ｜ mot edat senebetk｜_5P2HQ4hTCkg_f3b084dd	2026-02-15 10:41:35.655838
989	7809554925	arsema630	youtube	Music	https://youtu.be/kjvAjJgT5MU?si=hFErIWVJ2fDIxRhH	አዲስ ዝማሬ “ላሐ ማርያም” ｜abel begena laha mariam ｜_kjvAjJgT5MU_7bf3a473	2026-02-15 10:44:08.450318
990	7809554925	arsema630	youtube	Music	https://youtu.be/N5pkB1TfiLE?si=LeSju3K8zYxMA9SN	ሞት እንዴት ሰነበትክ አምባሰል...：በገና መዝሙር_N5pkB1TfiLE_e874db36	2026-02-15 10:46:36.211116
991	7809554925	arsema630	youtube	Music	https://youtu.be/v70-RcFxtFs?si=vFX9f9Z_82a_SAgk	ሞት እንዴት ሰነበትክ_v70-RcFxtFs_23323c6f	2026-02-15 10:47:12.298178
992	7809554925	arsema630	youtube	Music	https://youtu.be/dNDXTS8DtPA?si=B6uX5wO4s9LPjBP2	🔴 ለ2 ሰዓት የማያቋርጥ መንፈስን የሚያድስ የበገና ድርደራ ዜማ 🔴_dNDXTS8DtPA_4bfddccc	2026-02-15 10:48:05.303362
993	7809554925	arsema630	youtube	Music	https://youtu.be/bu09xx1njWo?si=WBzpWAwwMRSB_pVx	ሞት እንዴት ሠነበትክ...：በገና መዝሙር_bu09xx1njWo_2abf637e	2026-02-15 10:49:34.257296
994	7809554925	arsema630	youtube	Music	https://youtu.be/MAut-GzAEL4?si=13sEapi3N78_ZcCL	ሞት እንዴት ..？_MAut-GzAEL4_c8d9450b	2026-02-15 10:50:09.059976
995	7809554925	arsema630	youtube	Music	https://youtu.be/DQeuIVyo0GU?si=q9AB2pkLdkkqT9lh	🔴 ሞት እንዴት ሰንብትሀል ዘማሪ መምህር ክብሮም ኪዳኔ ( Kibrom begena , ክብሮም በገና )_DQeuIVyo0GU_0a396698	2026-02-15 10:51:09.53357
996	7809554925	arsema630	youtube	Music	https://youtu.be/t30dI0UrEmw?si=97ZkFcchO5iBhUNs	የድርብ ድርደራ ልምምድ (ሞት እንዴት ሰነበትክ)_t30dI0UrEmw_602f83a0	2026-02-15 10:54:24.697406
997	7809554925	arsema630	youtube	Music	https://youtu.be/HzRGStgta0g?si=Zce7MwJjByXK5Sh-	ክፍል 55 ：-ሞት እንዴት ሰነበትክ ( በሚዛን ደ⧸ገ⧸ቅ  ማርያም ከነበረኝ አገልግሎት የተወሰደ)_HzRGStgta0g_3d90d7ec	2026-02-15 10:56:21.656967
998	7809554925	arsema630	youtube	Music	https://youtu.be/Dqk6RE_tFKU?si=V2Wv7okQpHOmwI1P	እወርዳለሁ ቆላ፡እወርዳለሁ ደጋ       የጭንቅ አማላጄን ድንግልን ፍለጋ_Dqk6RE_tFKU_e6671f68	2026-02-15 10:56:45.517031
999	6299330933	datapeice	instagram	Video	https://www.instagram.com/p/DUtY-y2gb2X/?igsh=NmZzMnRqOHNhMGwy	instagram_DUtY-y2gb2X	2026-02-15 16:47:35.594796
1000	5331446232	True_Jentelmen	youtube	Music	https://youtu.be/4_fralbNBhs	EST-CE TON ÂME (Artful Noli) - 『Epic Metal Cover』 FORSAKEN OST Cover_4_fralbNBhs_9acd9ae1	2026-02-15 19:15:16.3972
1001	5331446232	True_Jentelmen	youtube	Music	https://youtu.be/hlpLJ_eQX7k	Awaken The Number One_hlpLJ_eQX7k_ba853ad4	2026-02-15 19:16:26.746161
1002	5331446232	True_Jentelmen	youtube	Music	https://youtu.be/0dkRdHkqQbI	Slasher MS4 Chase Theme Layer 4 Only_0dkRdHkqQbI_1c79d792	2026-02-15 19:17:05.657485
1003	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRfxpy2R/	🇺🇸🦅 #америка #сша #fyp _7606951390212066590_bf406be7	2026-02-15 20:52:23.866344
1004	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRfxc2ej/	Cómo se siente prender el xampp 💀 #programming _7559441185870335243_1c7253ad	2026-02-15 21:41:33.84951
1005	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRfx4tga/	#harrypotterpoa  is so comforting.｜ #harrypotterandtheprisonerofazkab..._7270594628653468960_56c1202b	2026-02-15 21:50:12.748247
1006	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRfQffqk/	target audience asf #harrypottertiktok #harrypotteraesthetic #chamber..._7474334278919212330_636d0f4f	2026-02-15 21:50:22.178331
1007	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRfXjwPA/	All Grown 😋😍 #alya #yuki #masha #alyasometimeshidesherfeelingsinrussi..._7607064286321528086_1b3b1b3c	2026-02-16 06:57:08.064175
1008	6299330933	datapeice	instagram	Video	https://www.instagram.com/reel/DUqbvKPjKe-/?igsh=dnN2ZmdzcGswMmNu	instagram_DUqbvKPjKe-	2026-02-16 11:29:56.117444
1009	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRfq45Pj/	@vithpa antworten she never came back #fanatsy_harrypotter #harrypott..._7005555062382578949_595f4229	2026-02-16 11:32:06.73135
1010	6299330933	datapeice	instagram	Video	https://www.instagram.com/reel/DUqHU7BjN3a/?igsh=b3cyODBlNHltb3I0	instagram_DUqHU7BjN3a	2026-02-16 11:36:26.044213
1011	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRfgofkd/	Хахахахаах #мем #прикол #рофл #ванна #стендап #украина_7606821068652760328_dd96bf66	2026-02-16 13:24:28.278295
1012	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRfpjTcP/	#jefferyepstein #edit #epstein #apple #fyp _7605556946657234196_fb8c9c3d	2026-02-16 13:27:02.701833
1014	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRfpa94b/	This is how you build hype 🔥 NASCAR just set the tone for Daytona and..._7606504617546894606_387ec8c9	2026-02-16 13:55:56.665384
1015	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRfpQoF9/	ЭТО ПЕРВЫЙ В МИРЕ БУРГЕР ИЗ ЧЕЛОВЕКА#slivkishow #burger _7607176043115433234_9e90e0fc	2026-02-16 14:06:49.252638
1016	6299330933	datapeice	youtube	Video	https://youtube.com/shorts/xCODQL_n1E8	happy birthday Noli 🎂🎈 #forsaken #forsakenroblox #forsakenmemes_xCODQL_n1E8_c41b7f8a	2026-02-16 14:59:26.592722
1017	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRfsvjju/	Pour une fois mon crâne sert à quelque chose mdr #humour #drole _7606802568609615126_750da9d6	2026-02-16 16:11:48.015246
1018	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRfWN2AU/	TikTok video #7607059152648539400_7607059152648539400_bf215ce3	2026-02-16 20:31:46.865584
1019	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRfWbKU5/	#supernatural #сверхьестественное #samwinchester #edit #deanwincheste..._7604111084361895176_65508e44	2026-02-16 20:52:08.737748
1020	5331446232	True_Jentelmen	youtube	Video	https://youtu.be/VRd_6riulrI?si=s1K7id7XU4JmUfvQ	old film grain overlay ｜ dust, hairs and scratches_VRd_6riulrI_d5511e5d	2026-02-16 20:55:59.189919
1021	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRf7cHxc/	#lebign #epstein #twogoats	2026-02-17 01:31:04.013948
1022	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRf3HxqC/	Сверхъестественное 1 сезон,пересказ за минуту #пересказ #факты ##supe..._7603822630893817110_952cbd8b	2026-02-17 09:12:03.868751
1023	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRfK8pGr/	Оце результат_7607595979964992789_1969d8f9	2026-02-17 11:07:46.205975
1024	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRfKNjG3/	Первое видео,я выбираю быть счастливой☺️#миньоны #вреки #айпадкиды 	2026-02-17 11:10:44.826652
1025	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRfwpHrW/	😭😭🙏 #troll #ip #cctv #webcam #ipcamera _7607253037601590550_03930a2b	2026-02-17 11:11:30.707567
1026	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRfKT9jU/	2006 design 😮‍💨 ｜｜ #lightningmcqueen #pixar #carss #95mcl #phonk _7581595481654971670_3a725187	2026-02-17 12:17:44.576143
1027	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRfKKG97/	How to say “stop gooning to me” in Chinese？ #DanqiuChinese #Danqiu #U..._7601293145648696607_df55d1f4	2026-02-17 12:19:39.73135
1028	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRfEuWJg/	Підтримуй український контент 🙃🇺🇦 #ромафектс #назар #україна_7050055830690909445_6997d331	2026-02-17 12:35:20.273738
1029	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRfEHEpR/	Ответ пользователю @schodinger1 Привет Назар! #эпштейн #островэпштейн..._7603903825786817824_a07d898f	2026-02-17 12:35:21.796707
1030	1022079796	lendspele	youtube	Music	https://youtube.com/watch?v=-SkPMvAaHF0&si=V9LZy9kTfKoXbKyO	JUMPSTYLE PARTY_-SkPMvAaHF0_8cc036f0	2026-02-17 12:50:50.015019
1031	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRfoV8x7/	elliot burgerson #mrrobot #elliotalderson #ramimalek #мистерробот #бу..._7607537944974396693_62bd97b9	2026-02-17 14:04:19.662528
1032	7908177327	ArsitiChinuuu	youtube	Video	https://youtu.be/9g7nYQv-kPM?si=R9cCqRfukWEx2Qe-	The Rules of Volleyball - EXPLAINED!_9g7nYQv-kPM_343cc229	2026-02-17 16:32:26.627281
1033	7809554925	arsema630	youtube	Music	https://youtu.be/36oWXbJeXO4?si=2Cj1IV8sW9o6FTYL	Ethiopia 🔴የሕማማት ዝማሬ - እውነት ስለሆነ ሊቀ መዘምራን ይልማ ኃይሉ like mezemran Yilma hailu hemamat_36oWXbJeXO4_7335c5ae	2026-02-17 18:00:02.11173
1034	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRPRpgwS/	фулл трек в тгк @num217 @тгк： FACE FAMILY @Смешарики #dj #fyp #mashup..._7607799973115202836_aa6fa041	2026-02-17 21:05:30.938501
1035	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRPR4WWV/	🇮🇱👑 #netanyahu #benjaminnetanyahu #israel #edits #fyp _7603856349893561622_8b85a787	2026-02-17 21:13:47.074135
1036	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRPRxU7E/	Peak？ Virus X Peter Griffin #petergriffin #familyguy #meme #darktriad_7607288126435888415_9515127c	2026-02-17 21:20:57.153803
1037	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRPR9LpM/	nie jestem femboyem@. _7607770856743357718_52819e8b	2026-02-17 21:23:27.35699
1038	1022079796	lendspele	video	Video	https://m.soundcloud.com/romanceplanet222/jumpstyle-party1?in=bidu_aml/sets/my-favorite-romance-planet	JUMPSTYLE PARTY_1875372012_ea573a96	2026-02-17 21:26:13.266108
1039	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRPNBheu/	#гренландия #песня #вставайдонбасс _7596398763908812064_7506ab38	2026-02-18 08:12:30.84589
1040	1022079796	lendspele	tiktok	Video	https://vt.tiktok.com/ZS9e17f7uPB6Q-iZDMz/	TikTok video #7591480616248495371_7591480616248495371_1e2fe8b1	2026-02-18 09:35:40.142381
1041	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRPYK6aB/	#3danimation #animals3d #animalsrungame #animals3dusa #funny3danimals _7606692854143978774_afbd472f	2026-02-18 10:13:43.797354
1042	6299330933	datapeice	video	Video	https://m.soundcloud.com/romanceplanet222/jumpstyle-party1?in=bidu_aml/sets/my-favorite-romance-planet	JUMPSTYLE PARTY_1875372012_914458c7	2026-02-18 10:14:50.624348
1043	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRPYxQMW/	Bubba da goat @Bubba Wallace #bubbawallace #viral #nascar #edit #fyp _7551516868511616269_ca655282	2026-02-18 10:18:41.815819
1044	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRPYnM3V/	#политика#политик политика _7607869517791841544_917f440b	2026-02-18 10:22:04.923089
1045	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRPYWvG1/	жиза ахахха #мем #мелл _7606774100970736917_44f6af9b	2026-02-18 10:25:10.572149
1046	8232490379	/	tiktok	Video	https://vt.tiktok.com/ZSmU9YCn8	oh yeah get it Elgatito! #fyp #cat #elgatito #foryou #meme _7607185873905519885_f2b97864	2026-02-18 11:08:48.727835
1047	8232490379	/	tiktok	Video	https://vt.tiktok.com/ZSmUCe4jL	funny edit🫩｜｜ rate this edit #cat #edit #эдит _7607743968859786509_8ef8264c	2026-02-18 11:40:06.719794
1048	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRPjBNWY/	The most necessary thing in my life 🥹😍😂#mimityph #esp32 #arduino _7608114075255541014_8877fb4b	2026-02-18 11:41:57.989576
1049	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRPj6NKg/	идею брали у @Белгород бро  #миньоны#выступление#школа #мем _7602690728149388551_2ffc1030	2026-02-18 11:44:12.098812
1050	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRP2oVjX/	Orange Cat laughing hard Perfomance _7605713291167419668_1a038915	2026-02-18 11:47:26.799663
1051	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRPjbAhq/	опять южный парк да #южныйпарк #southpark #рек #type#рек  _7606634329732615431_d57fd445	2026-02-18 12:00:46.630802
1052	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRPjxjaJ/	хедшот #s1mple #симпл #csgo #csgomoments #edit #fyp #recommendations ..._7607997136755543314_e91ef785	2026-02-18 12:01:23.755976
1053	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRPjfPmM/	я смог её найти...#школа #рек  #венсдей #первоклашки _7607537379766848790_10294e3e	2026-02-18 12:02:27.745251
1054	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRPrHQJa/	ыыыы	2026-02-18 14:57:47.520701
1055	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRP6AqFM/	@AIPAC blessing 🤞 #israel #aipac #telaviv2026	2026-02-18 14:57:53.118166
1056	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRPrxAgN/	дресс ту импресс #fypシ゚viral #cosplay #сигна #косплей #hatsunemiku _7607942062389972245_33678e50	2026-02-18 14:59:54.359552
1057	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRPr9NTc/	big net filled my tummy tdy😵‍💫😵‍💫#drip #israel #netanyahu _7607667346563435807_cb9d13b0	2026-02-18 15:03:07.405085
1058	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRPryPG3/	Go to lunch in a Jewish community ｜ #israel #jew #funny #c350 #m8 _7607606355142184212_21710dd6	2026-02-18 15:13:00.141117
1059	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRPrqQ36/	#fyp #drawingtutorial #mem #пони #fyyyp 	2026-02-18 15:24:56.577948
1060	6299330933	datapeice	tiktok	Video	https://www.tiktok.com/@myltivarka14/video/7604036171064282389?_r=1&u_code=e93ci44g0c3e23&preview_pb=0&sharer_language=en&_d=el3f40k4mb6l28&share_item_id=7604036171064282389&source=h5_m&timestamp=1771433757&user_id=7257128984390157338&sec_user_id=MS4wLjABAAAAPrSC4RfpYnxvNqljY4Zyg9yIj5IA0HjlyJoWUChHtEYtG11590IcFOJToPwVASgL&item_author_type=2&social_share_type=0&utm_source=copy&utm_campaign=client_share&utm_medium=android&share_iid=7606937006011565846&share_link_id=f0d7b5ea-e260-4566-9f8d-de1b36425b4c&share_app_id=1233&ugbiz_name=MAIN&ug_btm=b2001&link_reflow_popup_iteration_sharer=%7B%22click_empty_to_play%22%3A1%2C%22dynamic_cover%22%3A1%2C%22follow_to_play_duration%22%3A-1.0%2C%22profile_clickable%22%3A1%7D&enable_checksum=1	он всегда находит выход тгк-myltivarkin _7604036171064282389_85f2f96a	2026-02-18 16:56:05.439272
1061	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRPhbj9b/	он знает как надо лечить_7603306947634384148_d70a1cfc	2026-02-18 17:01:21.697103
1062	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRPkM5TS/	#жареннаякартошечка #вкусныйужин 	2026-02-18 17:54:31.659588
1063	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRPkTBpU/	🛸 Инопланетяне вышли на связь... 🇺🇦 Зеленский попытался договориться ..._7533521544266452246_19737b30	2026-02-18 19:00:00.339391
1064	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRPBUkhk/	Ми з вами з таборів на півночі Сирії. Слава, Україна, Слава Україні. ..._7604933213605317908_b02c2532	2026-02-18 20:29:21.218408
1065	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRPBtLu3/	+300 Romanian social credit #relateable #romania🇷🇴 #glorytoromania #r..._7578401746255416598_a88beb3a	2026-02-18 20:32:03.129271
1066	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRPB4QxX/		2026-02-18 20:36:15.52702
1067	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRPS8BsK/	ISRAEL I LOVE YOU BENJAMIN NETANYAHU #israel _7599215178932096269_b1a16c8b	2026-02-18 21:34:03.029177
1068	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRPSke81/	#дядяепштейн#бравлстарс#едгар#Саша#привітсофійко_7603005979403324693_11865868	2026-02-18 23:05:31.839322
1069	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRPSXc7U/	#энгрибердс #др #деньрождения #саша _7604144920089087253_499af497	2026-02-18 23:06:19.358658
1070	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRPSBnRo/	Привіт Саша)! #привітсаша #ші #джудіхопс _7606798151504252168_ee63f4fb	2026-02-18 23:06:34.03995
1071	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRPSC6eD/	Саша ну-кончай уже_7403067508225297682_6d330e1b	2026-02-18 23:06:49.017697
1072	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRPSHN1w/	Ответ пользователю @gfgghf5538438538 у у у Саша Саша и и и _7570011801736318264_e857583e	2026-02-18 23:07:02.304689
1073	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRPSxuob/	оригинал мема привет меня зовут Саша и я диктор канала мастерская нас..._7008532610024492289_28d2af10	2026-02-18 23:07:23.917699
1074	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRPSHhpw/	лавкать))0))0)) #саша #лавкатьеговлобик #александр #ялюблюсашу #люблю..._7547062317909953813_678eff6b	2026-02-18 23:08:18.116831
1075	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRPSh212/	#электрика #ярик #мантажник _7566512274282663175_1f405923	2026-02-18 23:15:03.310811
1076	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRPSU2W3/	😣🕊TikTok😰Premium💬😢 #animation #meme #Minecraft #edit _7608281332673727766_a209cb27	2026-02-18 23:20:46.866726
1077	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRPUooFW/	Видео для сдвгшников. #сдвг #мем #прикол_7565590315160063288_971d83ee	2026-02-19 09:45:39.210002
1078	1022079796	lendspele	tiktok	Video	https://vt.tiktok.com/ZSmfTYodQ/	หมุนเดือยออกหลังผสมเทียมเสร็จ#ผสมเทียมหมู #artficial #หมูนิ่ง #หมูเป็..._7586631063464725780_d87e9608	2026-02-19 12:55:56.822723
1079	1022079796	lendspele	tiktok	Video	https://vt.tiktok.com/ZSmf3jUYY/	HEART-STOPPING MOMENTS： Terrifying security footage shows a man alleg..._7607821078844509470_1d743cea	2026-02-19 12:55:57.87014
1080	8232490379	reyiise	tiktok	Video	https://vt.tiktok.com/ZSmPAxrw1	#fyp #viral #fyppppppppppppppppppppppp #fup _7605222155965451540_25471f85	2026-02-19 17:45:32.388029
1081	8232490379	reyiise	tiktok	Video	https://vt.tiktok.com/ZSmPAG3bw	#fyp #viral #fup #fyppppppppppppppppppppppp _7604108956889402644_51fea9e7	2026-02-19 17:46:02.632821
1082	8232490379	reyiise	tiktok	Video	https://vt.tiktok.com/ZSmPAqCby	#fyp #viral #fyppppppppppppppppppppppp #fup _7607817605994253589_d34305d2	2026-02-19 17:46:14.440748
1083	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRPx7uWH/	I ❤️ the big Yahu #epstein #diddyparty #icespice #isreal #bdays _7608411933229763854_c9d0f3f1	2026-02-20 00:57:16.510138
1084	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRPx7Ega/	🫣🫣_7608657431580642582_ef8b3ba6	2026-02-20 01:32:11.839776
1085	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRP4JW1H/	totaly normal things for the ceo of a billion dollar tech surveillanc..._7594833184169200929_b43a6a63	2026-02-20 10:02:12.68679
1086	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRP4cogy/	#ceo #inspiring #realstory #⚪️ _7584480186935037191_5fe8ca7f	2026-02-20 11:13:49.899377
1179	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNR5g6D9E/	🚘Car😍Premium🚗Edit❤️‍🔥 #animation #minecraft #edit _7610563372152573215_82e3a745	2026-02-25 15:24:52.335508
1087	7809554925	arsema630	youtube	Music	https://youtu.be/exUiLldO4Gc?si=jKfb3d3n64vMftbA	ልብን በሐዘን የሚመስጠው መልክአ ሕማማት ክፍል ፩  (የሕማማት ሰላምታ)             በመምህር መንክር ሐዲስ_exUiLldO4Gc_e0d632ce	2026-02-20 11:19:43.445927
1088	7809554925	arsema630	youtube	Video	https://youtu.be/CerZG3SbieA?si=BylHI7lNrqG_SKPy	🛑 መልክዐ ሕማማት ዘነግህ ｜｜ ሊቀ ጠበብት መንክር ሐዲስ_CerZG3SbieA_678d52a5	2026-02-20 11:24:05.172708
1089	7809554925	arsema630	youtube	Music	https://youtu.be/CerZG3SbieA?si=BylHI7lNrqG_SKPy	🛑 መልክዐ ሕማማት ዘነግህ ｜｜ ሊቀ ጠበብት መንክር ሐዲስ_CerZG3SbieA_52a909bc	2026-02-20 11:24:21.098511
1090	7809554925	arsema630	youtube	Music	https://youtu.be/T9qXDHeyHHM?si=8NQjVIpbz_4Jumow	🛑 እጅግ የሚመስጠው የሦስት ሰዓት መልክዐ ሕማማት ዜማ በሊቀ ጠበብት መንክር ሐዲስ_T9qXDHeyHHM_79c42f8d	2026-02-20 11:26:38.766885
1091	7809554925	arsema630	youtube	Video	https://youtu.be/T9qXDHeyHHM?si=8NQjVIpbz_4Jumow	🛑 እጅግ የሚመስጠው የሦስት ሰዓት መልክዐ ሕማማት ዜማ በሊቀ ጠበብት መንክር ሐዲስ_T9qXDHeyHHM_3079b5ff	2026-02-20 11:26:47.559023
1092	1022079796	lendspele	tiktok	Video	https://vt.tiktok.com/ZSmarkV6j/	##Крутая  Габба! 💃👍_7596231743741480200_8e5dafae	2026-02-20 14:25:44.666768
1093	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRPbvas9/	Strongest Border Security #stopracism #europe #poland #czhechrepublic..._7589361437911305528_6d52d3df	2026-02-20 14:57:35.558936
1094	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRPbTyXg/	TikTok video #7607553375936187656_7607553375936187656_2bf65945	2026-02-20 16:06:36.216099
1095	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRPbEsjR/	Open ur eyes  #alexkarp #palantir #israel #gaza #freegaza _7592311513579343117_c9129fad	2026-02-20 16:13:17.399466
1097	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRPpSnmG/	Telecomanda 2026 - Dados_7606951693145754902_7151ce06	2026-02-20 18:20:47.210188
1098	6299330933	datapeice	tiktok	Video	https://www.tiktok.com/@cooper_anovick/video/7551516868511616269?_r=1&u_code=e93ci44g0c3e23&preview_pb=0&sharer_language=en&_d=el3f40k4mb6l28&share_item_id=7551516868511616269&source=h5_m&timestamp=1771629508&user_id=7257128984390157338&sec_user_id=MS4wLjABAAAAPrSC4RfpYnxvNqljY4Zyg9yIj5IA0HjlyJoWUChHtEYtG11590IcFOJToPwVASgL&item_author_type=2&social_share_type=0&utm_source=copy&utm_campaign=client_share&utm_medium=android&share_iid=7606937006011565846&share_link_id=c1d3327a-3724-4494-9b78-aaac434906af&share_app_id=1233&ugbiz_name=MAIN&ug_btm=b9081%2Cb2878&link_reflow_popup_iteration_sharer=%7B%22click_empty_to_play%22%3A1%2C%22dynamic_cover%22%3A1%2C%22follow_to_play_duration%22%3A-1.0%2C%22profile_clickable%22%3A1%7D&enable_checksum=1	Bubba da goat @Bubba Wallace #bubbawallace #viral #nascar #edit #fyp _7551516868511616269_94457ae4	2026-02-20 23:51:47.134664
1099	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRPGvhbh/	muyehotdog #muye #muyefunny #muyefunnymoments #fyp #_7608629320109575446_2539b6c2	2026-02-20 23:51:51.383534
1123	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRP3s4JX/	TikTok video #7601144925278784789_7601144925278784789_c39a9724	2026-02-21 14:30:12.931805
1124	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRP33Kyh/	от этой песни веет нереальным летним вайбом ：D #foryou #fyp #summer #..._7608564463339572500_d727eadb	2026-02-21 15:31:32.379243
1125	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRPTSF7J/	TikTok video #7604002379805101320_7604002379805101320_9b3358ac	2026-02-21 15:53:32.348489
1126	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRPTJATB/	safe place. #supernatural #foryoupage #fyp #bpwkpp #bpwkpp _7596308991127342343_49918d15	2026-02-21 15:55:49.323782
1127	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRPTVWUk/	#isla #parati #loro #aura #fyp	2026-02-21 16:23:10.881437
1128	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRPT5p5M/	totaly normal things for the ceo of a billion dollar tech surveillanc..._7594833184169200929_5277fdde	2026-02-21 16:36:05.972796
1129	6299330933	datapeice	instagram	Video	https://www.instagram.com/p/DU05IjGDNDS/?img_index=4&igsh=MTI0ZHQ0NHphMjVvag==	Carousel Media	2026-02-21 19:16:51.43542
1130	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRPKMseR/	twitch： lagoda1337 #lagoda1337 #новости #одноклассники #зумеры_7608568264473595158_39a7d6e9	2026-02-21 20:22:21.234665
1131	6299330933	datapeice	instagram	Video	https://www.instagram.com/reel/DT8hA58AaT0/?igsh=azZ5MTdsbHVmdWpl	instagram_DT8hA58AaT0	2026-02-21 21:58:49.002999
1132	6299330933	datapeice	instagram	Video	https://www.instagram.com/reel/DTiaH2tjKHe/?igsh=c2o5MGpvcGF2Y2N4	instagram_DTiaH2tjKHe	2026-02-21 22:02:31.158693
1133	6299330933	datapeice	instagram	Video	https://www.instagram.com/reel/DT-WYXKDQgd/?igsh=dzVjN2RwOTl4dHVk	instagram_DT-WYXKDQgd	2026-02-21 22:10:12.506658
1134	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRPEFvSF/	“That’s a long hesitation” #fyp #politics #psyop #palantir _7593872934045748494_d014a1e2	2026-02-21 23:33:32.434172
1135	6453575758	gwaloneboy1158	youtube	Video	https://youtu.be/u2Amyd2L5X8?si=b9MqxGnljsFOrvT6	Alice -「2 PHUT HON」【Genshin Impact MMD】 #genshin_u2Amyd2L5X8_997365f0	2026-02-22 07:04:48.086588
1136	6453575758	gwaloneboy1158	youtube	Video	https://youtu.be/GmU6yFacZyM?si=KowGCqXuY4M0L38y	Caesar⭒Burnice -「LIKE IN THE MOVIES」【Zenless Zone Zero MMD】 #zzzero_GmU6yFacZyM_426fca43	2026-02-22 07:05:08.919399
1137	6453575758	gwaloneboy1158	youtube	Video	https://youtu.be/YG0Md7CZ8eU?si=MobOFGKTfsY0-Sor	Laevatain -「IGLOO」【Arknights： Endfield MMD】 #EndfieldCreators_YG0Md7CZ8eU_f1d053d3	2026-02-22 07:06:10.297135
1138	6453575758	gwaloneboy1158	youtube	Video	https://youtu.be/4Au2Q9E5ksw?si=rL6VX_IXmBbETKPd	Alice -「CLUTCH DANCE」【Genshin Impact MMD】 #genshin_4Au2Q9E5ksw_6432014e	2026-02-22 07:07:42.325928
1139	6453575758	gwaloneboy1158	youtube	Video	https://youtu.be/3opP7OGKfJw?si=5semXErnVmA4kgV4	「THE EDGE」- Evelyn⭒Jane doe⭒Yixuan⭒Grace⭒Zhuyuan 【Zenless Zone Zero MMD】#zzzero_3opP7OGKfJw_99f90caf	2026-02-22 07:08:04.884546
1140	6453575758	gwaloneboy1158	youtube	Video	https://youtu.be/5OGe0azt6yA?si=n-XZ-84D5zLdfC_f	Zhuyuan -「NO BATIDÃO」【Zenless Zone Zero MMD】 #zzzero_5OGe0azt6yA_15bdb028	2026-02-22 07:08:16.491732
1141	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNR5dy7rD/	By d1psick. Оплатил товар картой кента. Новая км, всем начинающим пом..._7604434088912506134_aaef327e	2026-02-22 17:51:42.94789
1142	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNR5RkqtV/	Meet the @exteraGram ｜ тгк： kstaaqs ＜3 #graphicdesign #telegram #диза..._7590871156530433336_4f263267	2026-02-22 19:36:34.113331
1143	1022079796	lendspele	youtube	Music	https://youtube.com/watch?v=RZrrL63Jo60&si=4re__45d3NBe6j2G	Дави на газ_RZrrL63Jo60_bf6e9e2e	2026-02-22 19:38:49.575146
1145	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNR58boaq/	Будущее ИИ #чедрик #twitch #ии #ai #minecraft _7609606624902171925_8fc88623	2026-02-22 23:42:50.375776
1146	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNR58cRdG/	#всёидётпоплану #егорлетов #кавернаукулеле #femboytiktok _7391548897111411973_6c34fb1c	2026-02-22 23:49:52.528967
1147	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNR5879hG/	big bad john machine #bigjohn #soundsystem #колонки #satsuma_rtn _7608961052440546568_d8b34bcd	2026-02-22 23:49:59.248177
1148	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNR584CK3/	TikTok video #7609304363403709717_7609304363403709717_5cd62a84	2026-02-22 23:50:25.048647
1149	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNR58cKrW/	twitch 5opka #bo55ik #пятерка #5opka #42братуха _7597805847774760200_5b80aacd	2026-02-22 23:54:46.298772
1150	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNR5LBPWq/	Phaeton 5.0 V10 TDI front start and sound #phaeton #tdi #v10 #start _7609337404494826774_9f1cb5bb	2026-02-23 00:24:28.473332
1096	5331446232	True_Jentelmen	youtube	Video	https://porn.storylegends.xyz/HeGy7rjG7	Bo cię weźmie zły pan” – ten żart o mało nie stał się prawdą !#shorts_woHgkWpR0VQ_a5ac6dca	2026-02-20 16:16:44.092414
1151	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNR52JABb/	‼️ВСЕ ГИФКИ В @pinkmangif‼️ #toystory #woody #buzzlightyear _7609605864739130632_17efc878	2026-02-23 10:27:00.403999
1152	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNR52CkkG/	Lo siento Wilson lo siento #desrt #adesrt #desert #thelongdrive #wilson _7609674652985740566_3f0b6a13	2026-02-23 11:35:07.363889
1153	6453575758	gwaloneboy1158	youtube	Video	https://youtu.be/JnX7Oc8LqD8?si=uDtNGmozs2PBaq6B	সূরা আর রহমান (الرحمن)  - মন জুড়ানো তেলাওয়াত ｜ Zain Abu Kautsar_JnX7Oc8LqD8_c7613d7a	2026-02-23 11:37:59.087702
1154	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNR5j1dbW/	Jakoś tak wyszło cn 🔥ᅠᅠᅠᅠᅠᅠᅠᅠᅠᅠᅠᅠᅠᅠᅠᅠᅠᅠᅠᅠᅠᅠᅠᅠᅠᅠᅠᅠᅠᅠᅠᅠᅠᅠᅠᅠᅠᅠᅠᅠᅠᅠᅠᅠᅠᅠᅠᅠ..._7609806892726095126_6e6d3121	2026-02-23 11:54:15.242472
1155	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNR5j6HmF/	Ящерицы  #pihta #пихта #recomendation #vtuberclips #vtuber #витубер #..._7609466138287983893_1a5c3b1e	2026-02-23 11:55:02.029605
1156	7957396621	lafreak2	youtube	Video	https://youtu.be/eSIHKrvu8rI?si=x-wXUevGHo_v-QJg	Messi vs Ajax UCL (AWAY) 2015 ● 4K60FPS Scenepack ⧸ ● ( ADDED TOPAZ NO AE CC) FOR EDITING_eSIHKrvu8rI_a27037d2	2026-02-23 12:17:39.220977
1157	7957396621	lafreak2	youtube	Video	https://youtu.be/eSIHKrvu8rI?si=x-wXUevGHo_v-QJg	Messi vs Ajax UCL (AWAY) 2015 ● 4K60FPS Scenepack ⧸ ● ( ADDED TOPAZ NO AE CC) FOR EDITING_eSIHKrvu8rI_e834bd4d	2026-02-23 12:18:25.975062
1158	7579210619	Judeataranam	youtube	Video	https://youtu.be/eSIHKrvu8rI?si=x-wXUevGHo_v-QJg	Messi vs Ajax UCL (AWAY) 2015 ● 4K60FPS Scenepack ⧸ ● ( ADDED TOPAZ NO AE CC) FOR EDITING_eSIHKrvu8rI_8e5ca85e	2026-02-23 12:23:12.41718
1159	6299330933	datapeice	instagram	Video	https://www.instagram.com/reel/DS1bnNjgrhP/?igsh=MTlxY3Q2ZmIwN3psMQ==	instagram_DS1bnNjgrhP	2026-02-23 13:13:23.12223
1160	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNR56vqX6/	I can handle it🥀🥀 #supernatural #dastiel #castiel #deanwinchester 	2026-02-23 14:33:23.899547
1161	8232490379	reyiise	tiktok	Video	https://vt.tiktok.com/ZSmCkWgyR	spinning flying cat #spiningcat #viral #spiningcatedit #catmeme _7608647116595973396_049f61ee	2026-02-23 17:14:55.67223
1162	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNR5hGMJm/	Губка Боб #сфера #рек #рекомендации #губкабоб #анимации #спанчбоб_7609221239676194061_e1e9c463	2026-02-23 18:32:11.041793
1163	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNR5DRwwc/	we laughing to the bank💲 #BigYahu #telaviv #explorepage✨ _7607963219218533646_92ef63f9	2026-02-24 07:38:13.097837
1164	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNR5fJx3j/	Crying so much rn 😭💔 (story time soon)_7601033808455961889_867f2bf3	2026-02-24 11:07:27.697397
1165	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNR5fkm2f/	#israel #netanyahu #fyp #tattoo @Benjamin Netanyahu - נתניהו 	2026-02-24 11:08:28.943038
1166	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNR5f2QyQ/	#fyp #xybca #netanyahu #History #educated 	2026-02-24 11:10:37.617897
1167	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNR5mPVqw/	Герои «Сверхьестественного» попали в Беларусь. #сэмвинчестер #динвинч..._7187499019965369606_f5c121f3	2026-02-24 16:54:33.110674
1168	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNR5mVEJV/	This duo is COOKED 😭🙏 #breakingbad #epstein #diddy #edit #fyp #brainrot_7610157458086006038_a65804e7	2026-02-24 17:09:07.08536
1169	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNR5mbwVv/	@Тгк：дарк триад сквад @костянчик покойо @RomaBurger1195 @Колянчик_про..._7609299247372012818_505557c4	2026-02-24 17:12:29.687596
1170	1022079796	lendspele	youtube	Music	https://youtube.com/watch?v=PwEj4Iq1Kzg&si=P0VCI-2f7X-bupRO	speed_PwEj4Iq1Kzg_3a948d1d	2026-02-24 18:48:01.596978
1171	8351348456	.. !!	youtube	Music	https://youtu.be/_yLAOG6kG6M?si=PGvqwY_qYg6W3G73	অর্ধেকদ্বীন ডটকমের মাধ্যমে ২৪৮০তম বিবাহের মুহুর্ত ｜ দ্বীনদার পাত্রপাত্রী ｜ OrdhekDeen.com__yLAOG6kG6M_6f77507e	2026-02-24 21:21:59.148639
1172	6453575758	gwaloneboy1158	youtube	Music	https://youtu.be/8Qx8tjVaj8o?si=Tq0IbLPplMjM92ht	SOL VIBRA (Slowed)_8Qx8tjVaj8o_e994a072	2026-02-25 10:00:48.907355
1173	6453575758	gwaloneboy1158	youtube	Music	https://youtu.be/lwZUb3OCGHw?si=Zi-pObBWRP5je7mL	KPHK - SOUL! (PHONK)_lwZUb3OCGHw_87607242	2026-02-25 10:02:53.312177
1174	6453575758	gwaloneboy1158	youtube	Music	https://youtu.be/p78uta1tpTc?si=n69dN5pvb3V1ow_A	MOTIVATION FUNK (feat. ROIK) [Slowed]_p78uta1tpTc_c7ea82af	2026-02-25 14:46:05.772963
1175	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNR5gSorK/	why did bro ask for that plate 🥀 #fyp #viral #efn #epstein #goviral	2026-02-25 15:05:16.037781
1176	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNR5gRV9S/	Эминем требует косарь     #музыка #эминем #eminemrap #рэп #караоке _7610794598813715732_1d9c8947	2026-02-25 15:17:03.28917
1177	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNR5gN8Fy/	🤍⚽️TikTok😍Premium😈💜 #animation #meme #Minecraft #edit _7592044672265014550_58d783bd	2026-02-25 15:19:07.959323
1178	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNR5gJPYC/	😈💜TikTok🌌Mango🥭Premium 🌕✨️#animation #meme #minecraft #edit #car _7594553950217473311_2f1c03bf	2026-02-25 15:24:41.226894
1180	6299330933	datapeice	tiktok	Video	https://www.tiktok.com/@dimensi_lirik/photo/7507714361671159096?_r=1&u_code=e93ci44g0c3e23&preview_pb=0&sharer_language=en&_d=el3f40k4mb6l28&share_item_id=7507714361671159096&source=h5_m&timestamp=1772038659&user_id=7257128984390157338&sec_user_id=MS4wLjABAAAAPrSC4RfpYnxvNqljY4Zyg9yIj5IA0HjlyJoWUChHtEYtG11590IcFOJToPwVASgL&aweme_type=150&pic_cnt=2&item_author_type=2&social_share_type=14&ug_photo_idx=0&utm_source=copy&utm_campaign=client_share&utm_medium=android&share_iid=7606937006011565846&share_link_id=53733c44-01e8-4523-9fb6-f9e9e9382a3a&share_app_id=1233&ugbiz_name=UNKNOWN&ug_btm=b6880%2Cb2878&link_reflow_popup_iteration_sharer=%7B%22click_empty_to_play%22%3A1%2C%22dynamic_cover%22%3A1%2C%22follow_to_play_duration%22%3A-1.0%2C%22profile_clickable%22%3A1%7D&enable_checksum=1	#Lyrics #Song #Apaciapacu 	2026-02-25 16:57:50.717923
1181	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNR5pvtuP/	#гламурныймейк #мукбанг #еда #вкусно #рецепт _7609769910385921300_f552cc18	2026-02-25 18:27:43.460518
1182	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNR5sfB8F/	Jeffrey Gorri 🏝️ #fyp	2026-02-25 18:48:28.614024
1183	8232490379	/	tiktok	Video	https://www.tiktok.com/@nyneex_bs/video/7610797302428519688?_r=1	67#67 #gazan #russia #fyp #реки _7610797302428519688_4b88a2d0	2026-02-26 06:14:09.469371
1184	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNR5WCfo1/	Lego Impala67 and Lego Dean Winchester. ｜｜ {4K} Supernatural #superna..._7611080348700560661_08a3439e	2026-02-26 08:05:35.217865
1185	8351348456	.. !!	youtube	Music	https://youtu.be/JIcDEPdmaug?si=09g3fLzhGYidQ04t	Khoon Phir Khoon Hai ｜ Sahir Ludhianvi ｜ Dr. Haider Saif ｜ Shahzan Mujeeb_JIcDEPdmaug_620d87c3	2026-02-26 08:44:45.529894
1186	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNR5vaQUN/	🇮🇱🇮🇱🇮🇱 #israel #music #музыка #rushmanoff #поезд _7610935220690324757_1758c420	2026-02-26 10:13:56.736343
1189	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRaJ6gGH/	#гламурныймейк #мукбанг #еда #вкусно #рецепт _7594538971024100629_a2c164dd	2026-02-26 20:34:05.433476
1190	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRaJkM5e/	ביבי מלך ישראל 👑#ביביהמלך🇮🇱🇮🇱🇮🇱 _7610812503295118600_9565ee36	2026-02-26 20:34:38.700905
1191	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRaJhF1m/	Gotta keep an eye on him😟😂😭 #meme #isreal #westernwall #bird #fy _7609770173930687775_3128f739	2026-02-26 20:53:00.686443
1192	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRaJcuQE/	test	2026-02-26 22:21:07.416062
1193	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRaJtyQD/	עם ישראל חי בכיכר הגדולה בעולם#cteen #עםישראלחי #יהדות _7609503636372213013_717f051c	2026-02-26 22:25:30.718721
1194	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRajsfsh/	#netanyahu #grzegorzbraun #izrael #polska #uk _7606955015923600662_6b96a8a3	2026-02-27 18:14:45.24254
1195	5782116557	egor_smileeey	youtube	Music	https://youtu.be/zA1c7NYVQqw?si=dGdwgv5Rs3rxj3t7	Moon Rider - Fan Made Minecraft Music Disc_zA1c7NYVQqw_967786db	2026-02-27 19:15:44.836531
1196	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRaMMmG9/	idk( #supernatural #castiel #deanwinchester #samwinchester #destiel #..._7536236939754605832_d6eb9206	2026-02-27 20:39:18.609474
1197	6299330933	datapeice	instagram	Video	https://www.instagram.com/reel/DSmoBfhADuh/?igsh=N3RuZmNmZHVkam94	instagram_DSmoBfhADuh	2026-02-27 20:55:38.348922
1198	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRarkmGY/	Ну типо #negevchan #negev #negevcosplay #jewish #jewishtiktok #israel..._7050062805210369281_8ff2345f	2026-02-27 22:40:29.820597
1199	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRarUKa8/	Six-day War 🇮🇱⚔️🇪🇬🇸🇾🇯🇴🇮🇶 #sixdaywar #israel #1967 #negev #war  Israel..._7604548519382256904_0f305c88	2026-02-27 22:43:32.618946
1200	6453575758	gwaloneboy1158	instagram	Video	https://www.instagram.com/reel/DVP7NhODu4K/?igsh=MTZ0MDMxNWlnMjBobg==	instagram_DVP7NhODu4K	2026-02-28 02:38:22.589658
1201	8351348456	.. !!	youtube	Music	https://youtu.be/O3wojwwSoHw?si=LXy_gLOb9sq10Ssw	Ya Nabi Salam Alaika ｜ ইয়া নাবী সালাম আলাইকা ｜ Abu Ubayda_O3wojwwSoHw_b3d770fd	2026-02-28 04:58:38.570903
1202	6453575758	gwaloneboy1158	youtube	Music	https://youtu.be/gonYsb22xZs?si=aeL1OUUFT6ZWeCJV	ATC - Around The World (La La La La La) (Slowed & Reverb)_gonYsb22xZs_82a8b984	2026-02-28 09:43:11.480101
1203	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRaDNmFF/	⚠️Hey guys this is just meme,joke I am don't mossad agent. I don't sp..._7515882937363991826_63c25290	2026-02-28 12:37:40.491214
1204	6299330933	datapeice	youtube	Video	https://youtu.be/k2ZEsfteJ5g	＂Hava Nagila＂ - Israeli Folk Song_k2ZEsfteJ5g_947b6789	2026-02-28 12:58:45.970418
1205	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRaDgXe1/	#israel #freeisrael #✡️ ✡️ Song about thw yom kippur war only for top..._7570057847724051745_a519e485	2026-02-28 13:39:29.807974
1206	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRaUEkQk/	#benjaminnetanyahu#3000years#fyp _7609859188495306014_35850458	2026-02-28 15:25:56.252042
1207	1602649791	chelikO	tiktok	Video	https://vt.tiktok.com/ZSmWDwdU5/	tiktok_1244f920	2026-02-28 16:55:16.450194
1208	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRayvvp5/	#israel #freeisrael #✡️ ✡️ Song about thw yom kippur war only for top..._7570057847724051745_b194a6ee	2026-02-28 17:56:46.962611
1209	5331446232	True_Jentelmen	youtube	Video	https://youtu.be/mMRK44Ey15E	💔😭 the scream is sending me_mMRK44Ey15E_e589eebb	2026-02-28 18:51:14.343092
1210	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRaPMkCD/	Mimi on pmr 😆 #pmr #Mimi #baofeng _7610679607586606358_92e5af0e	2026-02-28 19:02:19.142278
1211	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRaPP4MX/	That one Family Guy edit 🥵🔥 (Song： BEETHOVEN HARDTEKK VIRUS) #familyg..._7611087805036498197_cdc1df6c	2026-02-28 19:20:52.449744
1212	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRaPXdp4/	אחיי ואחיותיי אזרחי ישראל, לפני שעה קלה יצאנו ישראל וארה״ב למבצע להסר..._7611830624399150354_1be78762	2026-02-28 19:26:44.097603
1213	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRaPVQL4/	TikTok video #7611829637794106631_7611829637794106631_2a54fb57	2026-02-28 19:57:20.175693
1214	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRaPBVno/	“That’s a long hesitation” #fyp #politics #psyop #palantir _7593872934045748494_3e134f64	2026-02-28 20:01:28.734426
1215	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRaPfMR4/	#palantir #stocks #giftok #funny _7550910221334482207_c441bcf7	2026-02-28 20:03:39.647075
1216	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRaPDPEL/	Palantir ｜ #edit #palantir #company #protection #tech _7603651757910052117_b81096ad	2026-02-28 20:07:03.70289
1217	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRaPtMfg/	трактор_7611577855746542879_d4457503	2026-02-28 20:19:25.300405
1218	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRaPgXHT/	Feb. 28, 2026 ｜ U.S. and Israeli forces launched strikes against Iran..._7611821528283499806_4878cdeb	2026-02-28 20:23:34.697912
1219	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRa5LVwd/	BUBBA WALLACE LETS EFFING GOOOOOOOOOO CANT BLAME HIM FOR THAT! @Bubba..._7607208289230671134_fd01e760	2026-02-28 20:42:37.804301
1220	5331446232	True_Jentelmen	youtube	Music	https://youtu.be/fg07w8N70q8	Matt Dusk - Five Nights At Freddy's (60's Version) - Lyric Video_fg07w8N70q8_2aba8042	2026-02-28 21:51:58.879325
1221	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRa5gqY9/	למה שהם יעשו מלחמה יומיים לפני פורים🫩#repost #🔥 #foryou #viral #fypシ゚ _7611853945622908168_e0165e1a	2026-02-28 23:06:38.501228
1222	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRa5vnde/	Insane timing _7611943462744640781_e8242c8d	2026-03-01 00:12:22.800266
1223	8232490379	/	tiktok	Video	https://vt.tiktok.com/ZSm7nsopD	#дуров #павел #телеграм #телеграм #face_7606806061466553630_a87d5a38	2026-03-01 07:43:31.938957
1224	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRauVTRj/	MARCH FIRSTT #firstofthemonth #wakeupitsthefirstofthemonth #brainrot ..._7612097675852270868_f61cc295	2026-03-01 10:43:38.781424
1225	8232490379	/	tiktok	Video	https://vt.tiktok.com/ZSmvPQHs4	#deaddynasty♻️🖤 #DD #песня #rek #fyp #PHARAOH #актив #pharaoh _7612002283655531797_0cd9f2dd	2026-03-01 13:48:02.226729
1226	5331446232	True_Jentelmen	youtube	Music	https://youtu.be/21Q35PlDbWs	Matt Dusk - Love In A Bottle (60's Version) - Lyric Video_21Q35PlDbWs_68ed66bb	2026-03-01 17:28:22.624867
1227	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRaC15n4/	hell yeah ｜｜ #missconstruction #industrial #edit #fyp #transitionedit..._7492078838852226310_5dc2b1b9	2026-03-01 19:30:36.254586
1228	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRa4NEKT/	#khamenei #iran #israel #usa #war _7612207872033770774_79ad8564	2026-03-01 21:58:30.699815
1229	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRa4dSQC/	סלאמת 👋 #בובספוג #spongebob #שאגתהארי _7612242139375865108_c599c05c	2026-03-01 22:02:22.747232
1230	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRaqXYQj/	(they'd be celebrating if biden killed him)_7612474038061092110_1ecbfd13	2026-03-02 06:20:30.129731
1231	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRabNDuE/	#engineering #aviation #usa #lockheedmartin #palantir #shieldai #boei..._7563991490909818120_f61fa138	2026-03-02 07:28:04.139916
1232	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRabBVAM/	#technology #defense #aviation #america #engineering #boeing #lockhee..._7576280448360303890_0404e444	2026-03-02 07:43:48.165974
1233	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRab3mSu/	#jeffreyepstein #meme #bird #epsteinfiles #epstein 	2026-03-02 08:13:44.916903
1234	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRabWQTd/	оригинальная озвучка Тачек core #cars #тачки #макуин #макуинтачки #мэ..._7611913773531647253_7f119eda	2026-03-02 08:14:09.349375
1235	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRagBLxQ/	בהפגנות הסוערות שהתקיימו בבני ברק ובמוקדים נוספים, תועדו מקרי אלימות ..._7597452947949194503_8705b7cb	2026-03-02 09:16:44.361086
1236	6453575758	gwaloneboy1158	youtube	Music	https://youtu.be/kyLuzKbgXAs?si=Etp2VyK2TvTG1YFA	Alok & Alan Walker - Headlights (feat. KIDDO) [Official Lyric Video]_kyLuzKbgXAs_f8e6767d	2026-03-02 09:56:24.120085
1237	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRaGRB1F/	#иран #миньоны #израиль #актуальное _7612286205274672402_be70d176	2026-03-02 11:57:27.807862
1238	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRassAMY/		2026-03-02 11:58:56.672793
1239	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRas3fDP/	my little soldier. 😭Supernatural #supernatural #supernaturaledit #sam..._7611270375791480080_17c62abe	2026-03-02 11:59:40.359508
1240	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRa7YtMH/	эхххх 😣#Amaric #vaib #вайб #novorossiysk #Омск _7612042032906833182_d6b5834b	2026-03-02 16:51:46.624227
1241	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRhDheQ8/	#agartha #fyp #animes 	2026-03-02 17:15:30.711858
1242	5331446232	True_Jentelmen	youtube	Music	https://youtu.be/LlgWqcHXD8w	Succession (Main Title Theme) - Nicholas Britell ｜ Succession (HBO Original Series Soundtrack)_LlgWqcHXD8w_0915c020	2026-03-02 19:44:43.420398
1249	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRac35A1/	Say hello #mimi #mimithedog #typh #mimityph #fyp _7612186959254916374_b1c51054	2026-03-02 21:20:50.200882
1250	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRa3FpuY/	#мем #meme #fyp #mem _7611468394964978957_797ab561	2026-03-02 21:26:59.792633
1251	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRa31Y11/	israel #israel #fyp #negevchan #girlsfrontline #negev _7611807014309809438_601df7ff	2026-03-02 21:28:34.693816
1252	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRa3YMWS/	пр8в8й дв8ж #negevchan #FYP #m8l8tx  #кошерно #warthunder _7586527600672066829_57ebd0ea	2026-03-02 21:29:15.823203
1253	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRa3N1qE/	Negev chan take on middle east conflict #anime #gachagames #labubu #t..._7573933375296245047_14098886	2026-03-02 21:29:23.051545
1254	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRa3M8AD/	#israel #war #negev #fyp #fypage #palestine _7397755884518116616_c188d77e	2026-03-02 21:29:39.215012
1255	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRa3Y3nX/	🩷🩷 #fyp #negevchan #viral #girlsfrontline #joke @★Mari3☥🦇 @𓏲𝄢 	2026-03-02 21:51:42.853674
1256	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRaT8wyp/	OPERATION EPIC FURY_7612801539761130765_b3dadc74	2026-03-03 00:06:28.979747
1257	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRaTM4jm/	Supernatural😎 Это их трек😄 #supernatural #Aikonovalov #рекомендации #..._7611869096262520072_1ec73309	2026-03-03 00:24:18.100363
1258	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRaTNT1m/	#technology #defense #aviation #america #engineering #boeing #lockhee..._7576280448360303890_c53d99c8	2026-03-03 00:29:10.578359
1259	1022079796	lendspele	tiktok	Video	https://vt.tiktok.com/ZSmwnfhXR/	Тг： ГОСПОЖА СМИРНОВА_7612759287651257603_84cd66ca	2026-03-03 07:38:50.756594
1260	6299330933	datapeice	instagram	Video	https://www.instagram.com/reel/DVICkdnkeOS/?igsh=MW12d3U0eDVmc29xMg==	instagram_DVICkdnkeOS	2026-03-03 08:35:32.48433
1261	1022079796	lendspele	tiktok	Video	https://vt.tiktok.com/ZSmwKfwJx/	кухня прости, и вы за маты простите _7607105423304707349_8565d67d	2026-03-03 08:35:46.562998
1262	1022079796	lendspele	tiktok	Video	https://vt.tiktok.com/ZSmwKfwJx/	кухня прости, и вы за маты простите _7607105423304707349_f37a7f76	2026-03-03 08:36:10.599398
1263	6299330933	datapeice	instagram	Video	https://www.instagram.com/reel/DU37nBIjUnF/?igsh=MWhhMWx1dzdmNDZldQ==	instagram_DU37nBIjUnF	2026-03-03 09:35:41.670926
1264	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRaTNT1m/	#technology #defense #aviation #america #engineering #boeing #lockhee..._7576280448360303890_677173f2	2026-03-03 11:05:30.505342
1265	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRyPNgKp/	TikTok video #7600437245706997012_7600437245706997012_ae9ed1e4	2026-03-03 11:10:10.374402
1266	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRaTNT1m/	#technology #defense #aviation #america #engineering #boeing #lockhee..._7576280448360303890_f11900c7	2026-03-03 11:13:56.654855
1267	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRaTNT1m/	#technology #defense #aviation #america #engineering #boeing #lockhee..._7576280448360303890_17ebb251	2026-03-03 12:20:50.992238
1268	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRm8RpcC/	מבסיס חיל האוויר בפלמחים： אנחנו שואגים ואנחנו פועלים. צפו ＞＞_7613067954908892434_03d471ba	2026-03-03 18:07:41.273411
1269	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRmLM5Bg/	Negev chan take on middle east conflict #anime #gachagames #labubu #t..._7573933375296245047_cfd28365	2026-03-03 18:53:31.453134
1270	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRmLhVH6/	#fyp #netanyahu #israel🇮🇱  #happy #sad _7612673147988364547_c4fdb5b7	2026-03-03 18:59:39.925733
1271	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRmNPCdd/	#fyp #madagascar #yourmonthyour #foryou 	2026-03-03 21:20:29.423649
1272	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRmNVJyr/	Need this confidence. 🎥： #MadagascarEscape2Africa_7607601604744776974_3e720594	2026-03-03 21:23:48.173189
1273	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRmNpB1a/	Тильт Кипелова      #музыкадлядуши #ария #кипелов #русскийрок #караоке _7613118953719631125_251327c9	2026-03-03 21:30:18.142174
1274	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRmNVnCV/	Israel,[a] officially the State of Israel,[b] is a country in the Southern Levant region of West Asia. It is bordered by Lebanon to the north, Syria to the northeast, Jordan to the east, and Egypt to the southwest. Israel occupies the Palestinian territories of the West Bank in the east and the Gaza Strip in the southwest, as well as the Syrian Golan Heights in the northeast. Israel's western coast lies on the Mediterranean Sea, its southern tip reaching the Red Sea, and the east includes the Earth's lowest point near the Dead Sea. Jerusalem is the government seat and proclaimed capital,[23] while Tel Aviv is Israel's largest urban area and economic centre. The Land of Israel, also called Palestine or the Holy Land, was home to the ancient Canaanites and later the kingdoms of Israel and Judah. Located near continental crossroads, its demographics shifted under various empires. 19th-century European antisemitism fuelled the Zionist movement for a Jewish homeland, supported by Britain in the 1917 Balfour Declaration. British rule and Jewish immigration intensified Arab-Jewish tensions,[24][25] and the 1947 United Nations (UN) Partition Plan led to a civil war. Israel declared independence as the British Mandate ended on 14 May 1948, followed by an invasion by Arab states. The 1949 armistice expanded Israel beyond the UN plan;[26] no Arab state was created, leaving Gaza under Egypt and the West Bank under Jordan.[26][27][28] Most Palestinian Arabs fled or were expelled during the Nakba,[29][30][31] while Israeli independence increased antisemitism in the Arab world, prompting the Jewish exodus, mainly to Israel.[32][33] After the 1967 Six-Day War, Israel occupied the West Bank, Gaza, and the Egyptian Sinai, and annexed East Jerusalem and the Syrian Golan Heights. Peace was signed with Egypt (1979; Sinai returned in 1982) and Jordan (1994). The 1993 Oslo Accords introduced limited Palestinian self-rule, and the 2020 Abraham Accords normalised ties with more Arab states, but the Israeli–Palestinian conflict persists. Israeli occupation has drawn international criticism, with experts calling its actions war crimes and crimes against humanity. After the Hamas-led October 7 attacks, Israel began committing genocide against Palestinians in Gaza.[c] Israel and several other countries, including the United States, reject that Israel's actions constitute genocide.[43][44][45] The Basic Laws of Israel establish the Knesset as a proportionally elected parliament. It shapes the government, led by the prime minister, and elects the largely ceremonial president.[46] Israel has one of the Middle East's largest economies,[47] one of Asia's highest living standards, and globally ranks 26th in nominal GDP and 14th in nominal GDP per capita.[20][48] One of the world's most technologically advanced countries,[49][50] Israel allocates a larger share of its economy to research and development than any other state[51][52] and is believed to possess nuclear weapons. The culture of Israel combines Jewish traditions with Arab influences. #fyp #fypシ #israel #viral 	2026-03-03 21:32:31.92444
1275	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRmNtxvm/	TikTok video #7604549379097103637_7604549379097103637_f68d2bbe	2026-03-03 21:46:53.495799
1276	1022079796	lendspele	tiktok	Video	https://vt.tiktok.com/ZSmoyEa9b/	TikTok video #7610501684552338710_7610501684552338710_83444d1d	2026-03-04 07:56:04.236378
1277	1022079796	lendspele	tiktok	Video	https://vt.tiktok.com/ZSmoaeEWw/	#fup #viral #unfreezemyacount #foryou #foryoupage _7602985588547013918_7f0d536a	2026-03-04 08:21:52.409846
1278	6299330933	datapeice	instagram	Video	https://www.instagram.com/reel/DVZ2DaKifuK/?igsh=NHY0MGNpZDFnd2M2	instagram_DVZ2DaKifuK	2026-03-04 10:41:22.44285
1279	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRmM63M9/	@Benjamin Netanyahu - נתניהו time to work #fyp #xyz #makemefamous #or..._7613091650520239390_80c59084	2026-03-04 10:47:58.931284
1280	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRm6cuJo/	🥶Fight❤️‍🩹Edit😇 #animation #meme #Minecraft #edit _7613233519078149406_3938e179	2026-03-04 10:52:53.338827
1281	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRmMN7E7/	#Maciak #polityka #MaciejMaciak #Hołownia #RDiP _7612759803563232534_79fdf129	2026-03-04 10:53:29.086477
1282	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRmMeSCY/	The Russians have TURNED on Iran! #iran #news #trump #asmongold #mili..._7612773639796100383_c3f4339a	2026-03-04 10:54:51.007642
1283	1022079796	lendspele	tiktok	Video	https://vt.tiktok.com/ZSu1r7b3f/	#architect #architecture #engineering #university #foru _7612625766261706004_2b5757c4	2026-03-04 15:04:14.074897
1284	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRaTNT1m/	#technology #defense #aviation #america #engineering #boeing #lockhee..._7576280448360303890_97746ae8	2026-03-04 17:31:01.834593
1285	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRmAb1HA/	#twogoats  #epstein  #summervibes☀️   #netanyahu  #friends 	2026-03-04 19:09:03.161906
1286	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRmAGbCA/	עם ישראל חי  #israel #telaviv #brasil #portugal 	2026-03-04 19:15:59.077527
1287	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRmDr8oR/	ахпхах,ода #fyp #шрек #мадагаскар #мультик #пингвинымадагаскара _7613428100608593170_bdb04414	2026-03-04 20:07:31.519753
1288	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRmDB1qe/	Porsche swapped MK6 Jetta #vw #bagged #vr6 _7612338485780843783_58f3c0cc	2026-03-04 20:17:39.506599
1289	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRmDmtac/	The United States didn't make the decision to go into Iran._7613169481052998942_8abf2fd6	2026-03-04 20:29:39.744571
1290	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRmU1F4c/	TikTok video #7613345956326804767_7613345956326804767_40eb15b5	2026-03-04 21:28:10.379117
1291	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRm55UEb/	#🇯🇵Japan is turning footsteps into electricity! Using piezoelectric t..._7612284600135568660_ce129d4f	2026-03-05 09:43:21.81729
1292	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRmmVVbJ/	#warsaw #vhs _7613398115802025236_979ecf6e	2026-03-05 11:41:52.111507
1293	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRmurh9u/	#netanyahu #donaldtrump #trump #israel#usa _7613533005751012638_b5527488	2026-03-05 11:50:58.019378
1294	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRmu9yE4/	Биньямин Нетаньяху (род. 1949) — израильский государственный и полити..._7613484433999432967_a1322175	2026-03-05 12:38:17.934895
1295	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRmHhaU1/	теперь кчау❤️‍🔥😬 #macqueen #lightingmcqueen #edit #cars2 #cars #editcar _7603409161942011157_aa7e60d9	2026-03-05 12:47:49.099727
1296	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRmH8W5n/	#engineering #aviation #usa #lockheedmartin #palantir #shieldai #boei..._7563991490909818120_8fbc834c	2026-03-05 13:00:58.28013
1297	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRm92eWT/	Success is 99% failure..💬 #succession #success #successful #future #r..._7507104267874995478_8cc0c17a	2026-03-05 13:42:58.601712
1298	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRmQ8ssj/	neko #Neko #nekopara #cutecore🎀🦴🍮🐾 _7613453132227448082_76a22aeb	2026-03-05 17:46:19.899002
1299	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRmC2rYA/	TikTok video #7613803692277370143_7613803692277370143_8d7a4861	2026-03-05 18:15:28.753243
1300	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRm4eDcw/	Sleep ｜ Model by Quco #mimi #typh #typhmimi #typhfandom #hazel  @Quco..._7613801772552965396_b1553a2d	2026-03-05 21:05:49.639065
1301	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRm4LPo8/	Israel core： #израиль #israel #пхтт #трек #сегодня _7612023884149296404_ce86ce88	2026-03-05 21:09:19.447697
1302	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRm4eNq3/	TikTok video #7613780369946496288_7613780369946496288_083dac23	2026-03-05 21:13:03.494119
1303	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRmqryQo/	The one and only Jewish state 🇮🇱 #Israel #Telaviv #Jerusalem #Jewish ..._7613808406180138270_ac24a4d1	2026-03-06 06:02:53.80192
1304	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRmqmnCo/	#мем #fyp #memes #рек #мемы _7614018396950252813_9d1e172d	2026-03-06 06:08:00.522997
1305	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRmqPkV3/	#fyp #viral 	2026-03-06 06:52:05.045446
1306	1022079796	lendspele	tiktok	Video	https://vt.tiktok.com/ZSuRfrFdb/	работа на отзывах tg： plohishiotz( ссылка в шапке профиля) #отношения..._7613737241470373127_3dd23130	2026-03-06 07:25:18.663259
1307	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRmb8tA7/	TikTok video #7613786466035993878_7613786466035993878_eb5d3df1	2026-03-06 08:08:58.682796
1308	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRmbhyjB/	#fyp #isreal #isreal🇮🇱 #xybca #gotolunchinajewishcommunity _7609508009403763999_b7c0f969	2026-03-06 08:09:28.861234
1309	1022079796	lendspele	youtube	Music	https://youtube.com/watch?v=vJcSND3mfFo&si=eC5n1r6JUMmmBwso	FUNCTION_vJcSND3mfFo_9d9e3e53	2026-03-06 10:54:54.828146
1310	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRmsFpVE/	#Meme #MemeCut #CapCut #врекомендации _7602635284894715156_81964b78	2026-03-06 11:32:38.649411
1311	6299330933	datapeice	facebook	Video	https://www.facebook.com/share/r/1AsREWoeNu/	16K views · 183 reactions ｜ NAGRANIE NEWSROOMU BBC STAJE SIĘ VIRALEM ｜ Super Express_1239208655066668_d014d630	2026-03-06 11:59:11.31434
1321	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRmtsC4k/	#israel🇮🇱 #nationalistedit #edit #sixdayswar #pyfツ _7611449977558240533_01e31e01	2026-03-06 14:35:57.589017
1322	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRmtnfQS/	he wouldn't hurt a fly 🥺 #netanyahu #israel #palastine🇵🇸 #donaldtrump..._7560764343055437057_adf20e8a	2026-03-06 14:38:28.693665
1323	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRmnWhUX/	#CapCut my wife😮‍💨🔥 #victoriadeangelis #maneskin #edit #fyp _7607894048434670870_bdd04685	2026-03-06 15:40:52.101788
1324	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRmnPUrr/	Use my template 🤩#cinematic #gru #capcutpioneer #pioneertemplate #Cap..._7611593943414836500_bdc480a5	2026-03-06 15:47:26.875028
1325	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRmn91E5/	zajczyk dzudihops vs артемкотенко #артемкотенко _7608268890094750998_ae98665e	2026-03-06 16:12:30.473776
1326	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRmWfbrj/	Quick response edit  #ancientisrael #isreal🇮🇱  #history #holyland #is..._7604330176926780679_d3ab941a	2026-03-06 17:08:12.980322
1327	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRm7FDDP/	Femboy new skill  #femboy #femboyfriday #femboytiktok #baddie #morgan..._7613430144035769631_31871642	2026-03-06 18:22:09.300628
1328	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRm79KXG/	#succession #successionedit _7474290820322004241_26df36ba	2026-03-06 18:43:31.40301
1329	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRmvmfBF/	Living life #pontiac #indian #american #LLL #firebird _7608241699378285855_227f45ef	2026-03-06 20:09:05.553893
1330	6299330933	datapeice	youtube	Music	https://www.youtube.com/watch?v=6b4SQGfb8RM&list=RD6b4SQGfb8RM&start_radio=1	＂Hatikvah＂ - Israel National Anthem [RARE VERSION]_6b4SQGfb8RM_c90f1236	2026-03-06 20:36:13.172986
1331	5246431453	n0yneim00	tiktok	Video	https://vt.tiktok.com/ZSu8nHoeC	a silent voice edit ｜｜ babydoll ｜｜#fyppppppppppppppppppppppp #edit #A..._7610830560298159368_8a51325c	2026-03-06 20:58:42.292244
1332	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRmcbnTx/	#war #stupid #meme #aimbot #relatable _7613809997482298632_230fd6af	2026-03-06 23:06:09.995118
1333	6453575758	gwaloneboy1158	youtube	Music	https://youtu.be/AnMhdn0wJ4I?si=a3OOkA4k_aYYyUqZ	Vicetone - Nevada (ft. Cozi Zuehlsdorff)_AnMhdn0wJ4I_8bb76a40	2026-03-07 06:07:29.27376
1334	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRmKQupX/	What is Palantir？ - - - - #palantir #cia #goverment #fyp #viral _7613972018219797791_979c09e5	2026-03-07 10:16:50.495863
1335	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRmEe2GB/	Goodbye college #rezero #felixargyle #palantir #peterthiel #conspirac..._7611350232445603102_ecdb43fe	2026-03-07 10:38:33.274218
1336	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRmEhAy8/	#ישראל #ויראלי #פוריו #פוריוישראל #whatisdiddybluddoing_7566998147528936725_47a10604	2026-03-07 11:06:55.780438
1337	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRuehakL/	Gru Edit Again ｜ Gru Prime ｜ Despicable Me #edit #caput #hardstyle #f..._7606403496883080468_64d39be8	2026-03-07 17:25:35.793901
1338	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRuegvYq/		2026-03-07 18:08:24.982976
1339	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRud4L56/	#fyp #звёзды 	2026-03-07 19:29:18.171625
1340	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRu8Drhs/	международный женский день — праздник, который отмечается ежегодно 8 ..._7614075843937062152_948ea732	2026-03-07 23:35:39.440738
1341	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRu8yGJW/	Israel is lowkey a beautiful place #israel #palestine #nation #niche ..._7613557274925075742_c94aa826	2026-03-07 23:50:43.444686
1342	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRu8AsYd/		2026-03-07 23:59:08.87801
1343	6299330933	datapeice	tiktok	Video	https://vm.tiktok.com/ZNRuYsqv1/	успех_7614810034383441183_933756b3	2026-03-08 14:25:15.018537
\.


--
-- Data for Name: download_stats; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.download_stats (content_type, count) FROM stdin;
Video	1142
Music	115
\.


--
-- Data for Name: whitelisted_users; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.whitelisted_users (username, added_at) FROM stdin;
\.


--
-- Name: active_users_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.active_users_id_seq', 565, true);


--
-- Name: cookies_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.cookies_id_seq', 132, true);


--
-- Name: download_history_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.download_history_id_seq', 1343, true);


--
-- Name: active_users active_users_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.active_users
    ADD CONSTRAINT active_users_pkey PRIMARY KEY (id);


--
-- Name: cookies cookies_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.cookies
    ADD CONSTRAINT cookies_pkey PRIMARY KEY (id);


--
-- Name: download_history download_history_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.download_history
    ADD CONSTRAINT download_history_pkey PRIMARY KEY (id);


--
-- Name: download_stats download_stats_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.download_stats
    ADD CONSTRAINT download_stats_pkey PRIMARY KEY (content_type);


--
-- Name: whitelisted_users whitelisted_users_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.whitelisted_users
    ADD CONSTRAINT whitelisted_users_pkey PRIMARY KEY (username);


--
-- Name: extension_before_drop; Type: EVENT TRIGGER; Schema: -; Owner: -
--

CREATE EVENT TRIGGER extension_before_drop ON ddl_command_start
   EXECUTE FUNCTION _heroku.extension_before_drop();


--
-- Name: log_create_ext; Type: EVENT TRIGGER; Schema: -; Owner: -
--

CREATE EVENT TRIGGER log_create_ext ON ddl_command_end
   EXECUTE FUNCTION _heroku.create_ext();


--
-- Name: log_drop_ext; Type: EVENT TRIGGER; Schema: -; Owner: -
--

CREATE EVENT TRIGGER log_drop_ext ON sql_drop
   EXECUTE FUNCTION _heroku.drop_ext();


--
-- Name: validate_extension; Type: EVENT TRIGGER; Schema: -; Owner: -
--

CREATE EVENT TRIGGER validate_extension ON ddl_command_end
   EXECUTE FUNCTION _heroku.validate_extension();


--
-- PostgreSQL database dump complete
--

\unrestrict 95hhZnmHybgwqvRPugLYVDmNrzxek2jkdp0LdyfjeKmX23ZHVKWca716GIK36y8

