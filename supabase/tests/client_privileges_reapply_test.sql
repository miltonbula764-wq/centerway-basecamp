-- LOCAL ISOLATED DATABASE ONLY, after 0000-0010. Requires psql (relative includes).
-- Simulates the OBSERVED client ACL drift, not its unproven historical cause.
-- Existing policies, bodies and synthetic data must survive. Entire test rolls back.
\set ON_ERROR_STOP on
BEGIN;
CREATE TEMP TABLE cw_before AS
SELECT 'function' AS kind, p.oid::text AS id, md5(pg_get_functiondef(p.oid)) AS hash
FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname='public'
UNION ALL
SELECT 'policy', oid::text, md5(row_to_json(p)::text) FROM pg_policy p
UNION ALL
SELECT 'trigger', oid::text, md5(row_to_json(t)::text) FROM pg_trigger t WHERE NOT t.tgisinternal;
CREATE TEMP TABLE cw_data_before(name text PRIMARY KEY, hash text);
DO $$
DECLARE n text; h text;
BEGIN
  FOREACH n IN ARRAY ARRAY['tenants','memberships','subjects','tenant_value_profiles','profile_indicators',
    'value_profiles','indicators','observations','ingestion_batches','audit_log','c02_runs','c02_results',
    'c03_bundles','c03_indicators','c03_refs','c03_attempts'] LOOP
    EXECUTE format('SELECT md5(coalesce(string_agg(row_to_json(t)::text, '''' ORDER BY row_to_json(t)::text), '''')) FROM public.%I t',n) INTO h;
    INSERT INTO cw_data_before VALUES(n,h);
  END LOOP;
END $$;
GRANT ALL ON TABLE public.tenants, public.memberships, public.subjects, public.value_profiles,
  public.indicators, public.tenant_value_profiles, public.profile_indicators,
  public.observations, public.ingestion_batches, public.audit_log, public.c02_runs, public.c02_results
TO anon, authenticated;
GRANT ALL ON SEQUENCE public.audit_log_id_seq TO anon, authenticated;
DO $$
DECLARE f record;
BEGIN
  FOR f IN SELECT p.oid::regprocedure AS signature FROM pg_proc p
    JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname='public'
    AND p.proname NOT LIKE '\_c03%' AND p.proname <> 'build_evidence_bundle' LOOP
    EXECUTE format('GRANT EXECUTE ON FUNCTION %s TO PUBLIC, anon, authenticated',f.signature);
  END LOOP;
END $$;
\ir ../../drizzle/migrations/0011_restore_client_privileges.sql
\ir client_privileges_test.sql
CREATE TEMP TABLE cw_acl_once AS
SELECT 'relation' AS kind, oid, relacl::text AS acl FROM pg_class WHERE relnamespace='public'::regnamespace
UNION ALL
SELECT 'function', oid, proacl::text FROM pg_proc WHERE pronamespace='public'::regnamespace;
\ir ../../drizzle/migrations/0011_restore_client_privileges.sql
\ir client_privileges_test.sql
DO $$
DECLARE r record; h text;
BEGIN
  IF EXISTS (
    SELECT 1 FROM cw_acl_once b JOIN (
      SELECT 'relation' AS kind, oid, relacl::text AS acl FROM pg_class
      UNION ALL SELECT 'function', oid, proacl::text FROM pg_proc
    ) a USING(kind,oid) WHERE a.acl IS DISTINCT FROM b.acl
  ) THEN RAISE EXCEPTION 'ACL changed on second application'; END IF;
  IF EXISTS (
    SELECT 1 FROM cw_before b JOIN (
      SELECT 'function' AS kind, p.oid::text AS id, md5(pg_get_functiondef(p.oid)) AS hash
      FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname='public'
      UNION ALL SELECT 'policy', oid::text, md5(row_to_json(p)::text) FROM pg_policy p
      UNION ALL SELECT 'trigger', oid::text, md5(row_to_json(t)::text) FROM pg_trigger t WHERE NOT t.tgisinternal
    ) a USING(kind,id) WHERE a.hash IS DISTINCT FROM b.hash
  ) THEN RAISE EXCEPTION 'Function body/policy/trigger changed'; END IF;
  FOR r IN SELECT * FROM cw_data_before LOOP
    EXECUTE format('SELECT md5(coalesce(string_agg(row_to_json(t)::text, '''' ORDER BY row_to_json(t)::text), '''')) FROM public.%I t',r.name) INTO h;
    IF h IS DISTINCT FROM r.hash THEN RAISE EXCEPTION 'Data changed in %', r.name; END IF;
  END LOOP;
  RAISE NOTICE 'CW_REAPPLY_PASS (drift simulation rolled back)';
END $$;
ROLLBACK;
