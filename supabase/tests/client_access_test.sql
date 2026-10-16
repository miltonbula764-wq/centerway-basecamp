-- LOCAL ISOLATED DATABASE ONLY. Synthetic fixtures; no real application data.
-- psql -X -v ON_ERROR_STOP=1 -f supabase/tests/client_access_test.sql
-- On any error ON_ERROR_STOP closes the connection and rolls back the transaction.
BEGIN;
CREATE FUNCTION pg_temp.act(uid uuid, statement text) RETURNS text LANGUAGE plpgsql AS $$
DECLARE result text;
BEGIN
  PERFORM set_config('request.jwt.claims', json_build_object('sub', uid,
    'role', CASE WHEN uid IS NULL THEN 'anon' ELSE 'authenticated' END)::text, true);
  PERFORM set_config('role', CASE WHEN uid IS NULL THEN 'anon' ELSE 'authenticated' END, true);
  EXECUTE statement INTO result;
  RESET ROLE;
  RETURN result;
EXCEPTION WHEN OTHERS THEN RESET ROLE; RAISE;
END $$;
CREATE FUNCTION pg_temp.check(label text, actual text, expected text) RETURNS void LANGUAGE plpgsql AS $$
BEGIN
  IF actual IS DISTINCT FROM expected THEN
    RAISE EXCEPTION '%: expected %, got %', label, expected, actual;
  END IF;
END $$;
CREATE FUNCTION pg_temp.denied(uid uuid, statement text) RETURNS void LANGUAGE plpgsql AS $$
BEGIN
  BEGIN
    PERFORM pg_temp.act(uid, statement);
  EXCEPTION WHEN insufficient_privilege THEN RETURN;
  END;
  RAISE EXCEPTION 'Expected SQLSTATE 42501 for %', statement;
END $$;

DO $test$
DECLARE
  admin_a uuid := gen_random_uuid(); operator_a uuid := gen_random_uuid(); viewer_a uuid := gen_random_uuid();
  admin_b uuid := gen_random_uuid(); tenant_a uuid; tenant_b uuid; profile_a uuid; subject_a uuid;
  run_a uuid; bundle_a uuid; result jsonb; draft uuid; subject_b uuid; table_name text; uid uuid;
  run_before jsonb; bundles_before bigint; draft_indicator_ids jsonb;
BEGIN
  INSERT INTO auth.users(id, instance_id, aud, role, email) VALUES
    (admin_a, '00000000-0000-0000-0000-000000000000','authenticated','authenticated','cw-acl-admin-a@example.invalid'),
    (operator_a, '00000000-0000-0000-0000-000000000000','authenticated','authenticated','cw-acl-operator@example.invalid'),
    (viewer_a, '00000000-0000-0000-0000-000000000000','authenticated','authenticated','cw-acl-viewer@example.invalid'),
    (admin_b, '00000000-0000-0000-0000-000000000000','authenticated','authenticated','cw-acl-admin-b@example.invalid');
  PERFORM pg_temp.denied(NULL, $$SELECT public.create_tenant('denied','organization')$$);
  tenant_a := pg_temp.act(admin_a, $$SELECT public.create_tenant('ACL fixture A','organization')$$)::uuid;
  tenant_b := pg_temp.act(admin_b, $$SELECT public.create_tenant('ACL fixture B','organization')$$)::uuid;
  PERFORM pg_temp.act(admin_a, format('SELECT public.add_tenant_member(%L,%L,''operator'')',tenant_a,operator_a));
  PERFORM pg_temp.act(admin_a, format('SELECT public.add_tenant_member(%L,%L,''viewer'')',tenant_a,viewer_a));
  PERFORM pg_temp.denied(operator_a, format('SELECT public.set_member_role(%L,%L,''admin'')',tenant_a,viewer_a));
  PERFORM pg_temp.denied(admin_b, format('SELECT public.add_tenant_member(%L,%L,''admin'')',tenant_a,admin_b));

  -- Direct UI writes exercise invoker triggers and _cw_is_privileged, not just RPC grants.
  subject_a := pg_temp.act(operator_a, format($$INSERT INTO public.subjects(tenant_id,external_ref)
    VALUES (%L,'acl-a') RETURNING id$$, tenant_a))::uuid;
  subject_b := pg_temp.act(admin_b, format($$INSERT INTO public.subjects(tenant_id,external_ref)
    VALUES (%L,'acl-b') RETURNING id$$, tenant_b))::uuid;
  PERFORM pg_temp.check('operator subject edit', pg_temp.act(operator_a, format($$UPDATE public.subjects
    SET display_name='Edited' WHERE id=%L RETURNING display_name$$,subject_a)), 'Edited');
  PERFORM pg_temp.check('viewer subject update blocked by RLS', pg_temp.act(viewer_a, format($$UPDATE public.subjects
    SET display_name='Denied' WHERE id=%L RETURNING id$$,subject_a)), NULL);
  PERFORM pg_temp.denied(viewer_a, format($$INSERT INTO public.subjects(tenant_id,external_ref) VALUES (%L,'denied')$$,tenant_a));
  PERFORM pg_temp.denied(operator_a, format($$INSERT INTO public.subjects(tenant_id,external_ref) VALUES (%L,'denied')$$,tenant_b));
  PERFORM pg_temp.check('cross-tenant subject invisible', pg_temp.act(operator_a,
    format('SELECT count(*) FROM public.subjects WHERE id=%L',subject_b)), '0');

  profile_a := pg_temp.act(operator_a, format($$SELECT public.create_value_profile_draft(%L,'Synthetic promise')$$,tenant_a))::uuid;
  PERFORM pg_temp.check('draft edit invokes guard', pg_temp.act(operator_a, format($$UPDATE public.tenant_value_profiles
    SET notes='Edited' WHERE id=%L RETURNING notes$$,profile_a)), 'Edited');
  PERFORM pg_temp.act(operator_a, format($$INSERT INTO public.profile_indicators
    (tenant_id,profile_id,key,name,classification,unit,direction,baseline_method,baseline_value,baseline_min_period_days,
     observation_window_days,comparison_window_days,min_coverage_pct,min_denominator,deterioration_kind,deterioration_operator,
     deterioration_value,deterioration_consecutive_windows,recovery_kind,recovery_operator,recovery_value,recovery_consecutive_windows,
     aggregation,expected_cadence_days,denominator_mode)
    VALUES (%L,%L,'outcome','Synthetic outcome','outcome','count','higher_is_better','fixed_value',80,7,
      7,7,100,1,'absolute','lt',56,2,'absolute','gte',72,2,'mean',7,'observation_count') RETURNING id$$,tenant_a,profile_a));
  PERFORM pg_temp.denied(operator_a, format('SELECT public.approve_value_profile(%L)',profile_a));
  PERFORM pg_temp.check('admin approves',pg_temp.act(admin_a,
    format('SELECT (public.approve_value_profile(%L)).status',profile_a)), 'approved');
  PERFORM pg_temp.check('viewer effective profile',pg_temp.act(viewer_a,
    format('SELECT public.effective_value_profile(%L)',tenant_a)),profile_a::text);

  FOREACH uid IN ARRAY ARRAY[NULL::uuid,viewer_a,admin_b] LOOP
    PERFORM pg_temp.denied(uid,format($$SELECT public.import_observations(%L,%L,'fixture',
      '2026-08-01T00:00:00Z','2026-09-02T00:00:00Z',true,'fixture.csv','[]')$$,tenant_a,profile_a));
    PERFORM pg_temp.denied(uid,format($$SELECT public.run_deterioration_analysis(%L,%L,%L,'2026-09-01T00:00:00Z')$$,tenant_a,subject_a,profile_a));
    PERFORM pg_temp.denied(uid,format('SELECT public.build_evidence_bundle(%L,%L)',tenant_a,gen_random_uuid()));
  END LOOP;
  result := pg_temp.act(operator_a,format($$SELECT public.import_observations(%L,%L,'fixture',
    '2026-08-01T00:00:00Z','2026-09-02T00:00:00Z',true,'fixture.csv',
    '[{"subject_external_ref":"acl-a","indicator_key":"outcome","unit":"count","value_numeric":"80","observed_at":"2026-08-12T00:00:00Z","idempotency_key":"acl-1"},
      {"subject_external_ref":"acl-a","indicator_key":"outcome","unit":"count","value_numeric":"52","observed_at":"2026-08-19T00:00:00Z","idempotency_key":"acl-2"},
      {"subject_external_ref":"acl-a","indicator_key":"outcome","unit":"count","value_numeric":"48","observed_at":"2026-08-26T00:00:00Z","idempotency_key":"acl-3"}]')$$,tenant_a,profile_a))::jsonb;
  PERFORM pg_temp.check('operator C01',result->>'status','completed');
  result := pg_temp.act(operator_a,format($$SELECT public.run_deterioration_analysis(%L,%L,%L,'2026-09-01T00:00:00Z')$$,
    tenant_a,subject_a,profile_a))::jsonb;
  run_a := (result->>'run_id')::uuid;
  -- A real run must not be accessible through another tenant's admin or tenant id.
  SELECT to_jsonb(r) INTO STRICT run_before FROM public.c02_runs r WHERE r.id=run_a;
  SELECT count(*) INTO bundles_before FROM public.c03_bundles;
  PERFORM pg_temp.denied(admin_b,format('SELECT public.build_evidence_bundle(%L,%L)',tenant_a,run_a));
  -- Owner-side assertions avoid mistaking RLS invisibility for absence of side effects.
  PERFORM pg_temp.check('foreign admin creates no bundle',
    (SELECT count(*)::text FROM public.c03_bundles),bundles_before::text);
  PERFORM pg_temp.check('foreign admin preserves run',
    (SELECT to_jsonb(r)::text FROM public.c02_runs r WHERE r.id=run_a),run_before::text);
  result := pg_temp.act(admin_b,format('SELECT public.build_evidence_bundle(%L,%L)',tenant_b,run_a))::jsonb;
  -- Authorized in B, but run_a belongs to A: contract returns a persisted rejection, not 42501.
  PERFORM pg_temp.check('mismatched tenant/run rejected',result->>'status','rejected');
  PERFORM pg_temp.check('mismatched tenant/run code',result->>'code','run_not_found');
  PERFORM pg_temp.check('mismatched tenant/run creates no bundle',
    (SELECT count(*)::text FROM public.c03_bundles),bundles_before::text);
  PERFORM pg_temp.check('mismatched tenant/run preserves run',
    (SELECT to_jsonb(r)::text FROM public.c02_runs r WHERE r.id=run_a),run_before::text);
  PERFORM pg_temp.check('mismatched tenant/run records rejection',
    (SELECT count(*)::text FROM public.c03_attempts WHERE tenant_id=tenant_b
      AND requested_run_id=run_a AND actor_id=admin_b AND status='rejected'
      AND code='run_not_found' AND bundle_id IS NULL),'1');
  result := pg_temp.act(operator_a,format('SELECT public.build_evidence_bundle(%L,%L)',tenant_a,run_a))::jsonb;
  PERFORM pg_temp.check('operator C03',result->>'status','built');
  bundle_a := (result->>'bundle_id')::uuid;
  result := pg_temp.act(admin_a,format('SELECT public.build_evidence_bundle(%L,%L)',tenant_a,run_a))::jsonb;
  PERFORM pg_temp.check('admin C03 reuse',result->>'status','reused');
  PERFORM pg_temp.check('viewer reads outcome', pg_temp.act(viewer_a,format(
    'SELECT status FROM public.c02_results WHERE run_id=%L',run_a)), 'deterioration_candidate');
  PERFORM pg_temp.check('viewer reads complete evidence',pg_temp.act(viewer_a,format(
    'SELECT status FROM public.c03_indicators WHERE bundle_id=%L',bundle_a)), 'complete');
  PERFORM pg_temp.check('audit keeps operator actor',pg_temp.act(viewer_a,format($$SELECT count(*) FROM public.audit_log
    WHERE entity_type='subjects' AND entity_id=%L AND action='insert' AND actor_id=%L$$,subject_a,operator_a)), '1');
  FOREACH table_name IN ARRAY ARRAY['memberships','subjects','tenant_value_profiles','profile_indicators','audit_log',
    'ingestion_batches','observations','c02_runs','c02_results','c03_bundles','c03_indicators','c03_refs','c03_attempts'] LOOP
    PERFORM pg_temp.denied(NULL,format('SELECT count(*) FROM public.%I',table_name));
    PERFORM pg_temp.check('B cannot see A '||table_name,pg_temp.act(admin_b,
      format('SELECT count(*) FROM public.%I WHERE tenant_id=%L',table_name,tenant_a)), '0');
  END LOOP;
  FOREACH uid IN ARRAY ARRAY[admin_a,operator_a,viewer_a] LOOP
    PERFORM pg_temp.denied(uid,'SELECT public._c03_reject(''denied'')');
    PERFORM pg_temp.denied(uid,format('SELECT public._c03_build(%L,%L,5000)',tenant_a,run_a));
    PERFORM pg_temp.denied(uid,'SELECT nextval(''public.audit_log_id_seq'')');
    PERFORM pg_temp.denied(uid,'SELECT nextval(''public.c03_refs_id_seq'')');
    PERFORM pg_temp.denied(uid,'TRUNCATE public.memberships');
    PERFORM pg_temp.denied(uid,format('UPDATE public.c02_runs SET summary=''{}'' WHERE id=%L',run_a));
    PERFORM pg_temp.denied(uid,format('DELETE FROM public.c03_refs WHERE bundle_id=%L',bundle_a));
  END LOOP;
  -- Copy/edit/delete draft remains available; membership administration still works.
  draft := pg_temp.act(operator_a,format('SELECT public.create_value_profile_version(%L)',profile_a))::uuid;
  SELECT jsonb_agg(id ORDER BY id) INTO draft_indicator_ids
    FROM public.profile_indicators WHERE profile_id=draft;
  PERFORM pg_temp.check('draft copy contains the expected indicator',jsonb_array_length(draft_indicator_ids)::text,'1');
  PERFORM pg_temp.check('operator deletes exactly the draft indicators',pg_temp.act(operator_a,format(
    'WITH deleted AS (DELETE FROM public.profile_indicators WHERE profile_id=%L RETURNING id) SELECT jsonb_agg(id ORDER BY id)::text FROM deleted',
    draft)),draft_indicator_ids::text);
  PERFORM pg_temp.check('deleted draft indicators are absent',
    (SELECT count(*)::text FROM public.profile_indicators WHERE profile_id=draft),'0');
  PERFORM pg_temp.check('operator deletes the expected draft',pg_temp.act(operator_a,format(
    'DELETE FROM public.tenant_value_profiles WHERE id=%L RETURNING id',draft)),draft::text);
  PERFORM pg_temp.check('deleted draft is absent',
    (SELECT count(*)::text FROM public.tenant_value_profiles WHERE id=draft),'0');
  PERFORM pg_temp.act(admin_a,format('SELECT public.set_member_role(%L,%L,''operator'')',tenant_a,viewer_a));
  PERFORM pg_temp.act(admin_a,format('SELECT public.remove_tenant_member(%L,%L)',tenant_a,viewer_a));
  RAISE NOTICE 'CW_ACCESS_PASS (fixtures rolled back)';
END
$test$;
ROLLBACK;
