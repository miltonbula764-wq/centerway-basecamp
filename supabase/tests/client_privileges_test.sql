-- Effective ACL regression, PostgreSQL 17+. Read-only: safe for remote verification.
-- psql -X -v ON_ERROR_STOP=1 -f supabase/tests/client_privileges_test.sql
DO $test$
DECLARE r record; who text; priv text; expected boolean; checks int := 0;
BEGIN
  FOR r IN SELECT * FROM (VALUES
    ('tenants','SELECT'), ('memberships','SELECT'), ('audit_log','SELECT'),
    ('subjects','SELECT,INSERT,UPDATE'),
    ('tenant_value_profiles','SELECT,UPDATE,DELETE'),
    ('profile_indicators','SELECT,INSERT,UPDATE,DELETE'),
    ('value_profiles',''), ('indicators',''),
    ('observations','SELECT'), ('ingestion_batches','SELECT'),
    ('c02_runs','SELECT'), ('c02_results','SELECT'),
    ('c03_bundles','SELECT'), ('c03_indicators','SELECT'),
    ('c03_refs','SELECT'), ('c03_attempts','SELECT')
  ) v(name, allowed) LOOP
    IF NOT (SELECT relrowsecurity FROM pg_class WHERE oid = ('public.' || r.name)::regclass) THEN
      RAISE EXCEPTION 'RLS disabled on %', r.name;
    END IF;
    FOREACH who IN ARRAY ARRAY['anon','authenticated'] LOOP
      FOREACH priv IN ARRAY ARRAY['SELECT','INSERT','UPDATE','DELETE','TRUNCATE','REFERENCES','TRIGGER','MAINTAIN'] LOOP
        expected := who = 'authenticated' AND priv = ANY(string_to_array(r.allowed, ','));
        IF has_table_privilege(who, 'public.' || r.name, priv) IS DISTINCT FROM expected THEN
          RAISE EXCEPTION 'ACL %.% % expected %', who, r.name, priv, expected;
        END IF;
        IF has_table_privilege(who, 'public.' || r.name, priv || ' WITH GRANT OPTION') THEN
          RAISE EXCEPTION 'Unexpected grant option %.% %', who, r.name, priv;
        END IF;
        checks := checks + 2;
      END LOOP;
      -- Column grants are independent of table-level REVOKE.
      FOREACH priv IN ARRAY ARRAY['SELECT','INSERT','UPDATE','REFERENCES'] LOOP
        expected := who = 'authenticated' AND priv = ANY(string_to_array(r.allowed, ','));
        IF has_any_column_privilege(who, 'public.' || r.name, priv) IS DISTINCT FROM expected THEN
          RAISE EXCEPTION 'Unexpected column ACL %.% %', who, r.name, priv;
        END IF;
        checks := checks + 1;
      END LOOP;
    END LOOP;
  END LOOP;
  FOR r IN SELECT unnest(ARRAY['audit_log_id_seq','c03_refs_id_seq']) AS name LOOP
    FOREACH who IN ARRAY ARRAY['anon','authenticated'] LOOP
      FOREACH priv IN ARRAY ARRAY['SELECT','UPDATE','USAGE'] LOOP
        IF has_sequence_privilege(who, 'public.' || r.name, priv) THEN
          RAISE EXCEPTION 'Unexpected sequence ACL %.% %', who, r.name, priv;
        END IF;
        checks := checks + 1;
      END LOOP;
    END LOOP;
  END LOOP;
  FOR r IN SELECT * FROM (VALUES
    ('public._c02_cmp(numeric,public.rule_operator,numeric)', false),
    ('public._c02_effective(uuid,uuid,text,text,uuid[],timestamp with time zone)', false),
    ('public._c02_fingerprint(public.profile_indicators)', false),
    ('public._c02_immutable()', false),
    ('public._c02_window(uuid,uuid,text,text,uuid[],public.c02_aggregation,integer,public.c02_denominator_mode,text,text,uuid[],numeric,integer,timestamp with time zone,timestamp with time zone,timestamp with time zone)', false),
    ('public._c02v2_effective(uuid,uuid,text,text,uuid[],timestamp with time zone)', false),
    ('public._c02v2_window(uuid,uuid,text,text,uuid[],public.c02_aggregation,integer,public.c02_denominator_mode,text,text,uuid[],integer,numeric,numeric,integer,timestamp with time zone,timestamp with time zone,timestamp with time zone)', false),
    ('public._c03_assemble(public.c02_runs,uuid,text,integer,uuid)', false),
    ('public._c03_build(uuid,uuid,integer)', false),
    ('public._c03_payload_hash(public.observations)', false),
    ('public._c03_reject(text)', false),
    ('public._cw_append_only()', false),
    ('public._cw_audit_immutable()', false),
    ('public._cw_audit()', false),
    ('public._cw_correction_issues(uuid,uuid,uuid,text,text,timestamp with time zone,uuid,boolean)', false),
    ('public._cw_indicator_guard()', false),
    ('public._cw_is_privileged()', true),
    ('public._cw_lock_columns()', false),
    ('public._cw_membership_guard()', false),
    ('public._cw_observation_ingest()', false),
    ('public._cw_profile_indicator_guard()', false),
    ('public._cw_set_creator()', false),
    ('public._cw_touch()', false),
    ('public._cw_tvp_guard()', false),
    ('public._cw_value_profile_guard()', false),
    ('public.add_tenant_member(uuid,uuid,public.member_role)', true),
    ('public.approve_value_profile(uuid)', true),
    ('public.build_evidence_bundle(uuid,uuid)', true),
    ('public.create_tenant(text,public.subject_unit_type)', true),
    ('public.create_value_profile_draft(uuid,text,text)', true),
    ('public.create_value_profile_version(uuid)', true),
    ('public.effective_value_profile(uuid)', true),
    ('public.has_tenant_role(uuid,public.member_role[])', true),
    ('public.import_observations(uuid,uuid,text,timestamp with time zone,timestamp with time zone,boolean,text,jsonb)', true),
    ('public.is_tenant_member(uuid)', true),
    ('public.my_tenant_role(uuid)', true),
    ('public.remove_tenant_member(uuid,uuid)', true),
    ('public.run_deterioration_analysis(uuid,uuid,uuid,timestamp with time zone)', true),
    ('public.set_member_role(uuid,uuid,public.member_role)', true),
    ('public.value_profile_approval_issues(uuid)', true)
  ) v(signature, client_callable) LOOP
    FOREACH who IN ARRAY ARRAY['anon','authenticated'] LOOP
      expected := who = 'authenticated' AND r.client_callable;
      IF has_function_privilege(who, r.signature, 'EXECUTE') IS DISTINCT FROM expected THEN
        RAISE EXCEPTION 'Unexpected EXECUTE %.%', who, r.signature;
      END IF;
      IF has_function_privilege(who, r.signature, 'EXECUTE WITH GRANT OPTION') THEN
        RAISE EXCEPTION 'Unexpected function grant option %.%', who, r.signature;
      END IF;
      checks := checks + 2;
    END LOOP;
  END LOOP;
  RAISE NOTICE 'CW_ACL_PASS checks=%', checks;
END
$test$;
