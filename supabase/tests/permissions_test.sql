-- CENTERWAY permission tests (re-runnable).
-- Runs every action as real `anon` / `authenticated` roles with JWT claims (never service_role).
-- All fixtures live inside one transaction that is ALWAYS rolled back: the block ends with
-- RAISE EXCEPTION carrying the results, so nothing persists.
-- Negative tests assert the exact SQLSTATE (and constraint name where relevant).
-- Run: paste the whole file into the backend SQL runner; read the result list in the error text.
DO $test$
DECLARE
  ua uuid := gen_random_uuid(); ub uuid := gen_random_uuid(); uop uuid := gen_random_uuid(); uv uuid := gen_random_uuid();
  ta uuid; tb uuid; sa uuid; sb uuid; pa uuid; pb uuid; pa2 uuid; pa3 uuid; ia uuid; ba uuid; bb uuid; oa uuid; ob uuid;
  r text := ''; root uuid := '00000000-0000-0000-0000-0000000000ff'; npass int; nfail int;
BEGIN
  -- ---------- helpers (temp, rolled back) ----------
  CREATE FUNCTION pg_temp.as_user(_uid uuid) RETURNS void LANGUAGE plpgsql AS $f$
  BEGIN
    IF _uid = '00000000-0000-0000-0000-0000000000ff'::uuid THEN  -- privileged fixture path (no RLS), only for setup / trigger-level checks
      PERFORM set_config('request.jwt.claims', '', true); RESET ROLE; RETURN;
    END IF;
    PERFORM set_config('request.jwt.claims', CASE WHEN _uid IS NULL THEN '{"role":"anon"}'
      ELSE json_build_object('sub', _uid, 'role', 'authenticated')::text END, true);
    PERFORM set_config('role', CASE WHEN _uid IS NULL THEN 'anon' ELSE 'authenticated' END, true);
  END $f$;
  CREATE FUNCTION pg_temp.val(_uid uuid, _sql text) RETURNS text LANGUAGE plpgsql AS $f$
  DECLARE v text;
  BEGIN PERFORM pg_temp.as_user(_uid); EXECUTE _sql INTO v; RESET ROLE; RETURN v; END $f$;
  CREATE FUNCTION pg_temp.expect_err(_label text, _uid uuid, _sql text, _state text, _constraint text DEFAULT NULL)
  RETURNS text LANGUAGE plpgsql AS $f$
  DECLARE c text;
  BEGIN
    BEGIN
      PERFORM pg_temp.as_user(_uid); EXECUTE _sql; RESET ROLE;
      RETURN E'\nFAIL ' || _label || ' (no error raised)';
    EXCEPTION WHEN OTHERS THEN
      GET STACKED DIAGNOSTICS c = CONSTRAINT_NAME;
      IF SQLSTATE = _state AND (_constraint IS NULL OR c = _constraint) THEN
        RETURN E'\nPASS ' || _label || ' [' || SQLSTATE || coalesce(' ' || nullif(c, ''), '') || ']';
      END IF;
      RETURN E'\nFAIL ' || _label || ' expected ' || _state || coalesce('/' || _constraint, '') || ' got ' || SQLSTATE || ' ' || coalesce(c, '') || ' ' || SQLERRM;
    END;
  END $f$;
  CREATE FUNCTION pg_temp.expect_rows(_label text, _uid uuid, _sql text, _n int) RETURNS text LANGUAGE plpgsql AS $f$
  DECLARE n int;
  BEGIN
    BEGIN
      PERFORM pg_temp.as_user(_uid); EXECUTE _sql; GET DIAGNOSTICS n = ROW_COUNT; RESET ROLE;
    EXCEPTION WHEN OTHERS THEN RETURN E'\nFAIL ' || _label || ' unexpected error ' || SQLSTATE || ' ' || SQLERRM; END;
    IF n = _n THEN RETURN E'\nPASS ' || _label || ' [' || n || ' rows]'; END IF;
    RETURN E'\nFAIL ' || _label || ' expected ' || _n || ' rows got ' || n;
  END $f$;
  CREATE FUNCTION pg_temp.expect_val(_label text, _uid uuid, _sql text, _expected text) RETURNS text LANGUAGE plpgsql AS $f$
  DECLARE v text;
  BEGIN
    BEGIN v := pg_temp.val(_uid, _sql);
    EXCEPTION WHEN OTHERS THEN RETURN E'\nFAIL ' || _label || ' unexpected error ' || SQLSTATE || ' ' || SQLERRM; END;
    IF v IS NOT DISTINCT FROM _expected THEN RETURN E'\nPASS ' || _label || ' [' || coalesce(v, 'null') || ']'; END IF;
    RETURN E'\nFAIL ' || _label || ' expected ' || coalesce(_expected, 'null') || ' got ' || coalesce(v, 'null');
  END $f$;

  -- ---------- fixture users ----------
  INSERT INTO auth.users(id, instance_id, aud, role, email) VALUES
   (ua,  '00000000-0000-0000-0000-000000000000','authenticated','authenticated','cw-fixture-a@example.invalid'),
   (ub,  '00000000-0000-0000-0000-000000000000','authenticated','authenticated','cw-fixture-b@example.invalid'),
   (uop, '00000000-0000-0000-0000-000000000000','authenticated','authenticated','cw-fixture-op@example.invalid'),
   (uv,  '00000000-0000-0000-0000-000000000000','authenticated','authenticated','cw-fixture-v@example.invalid');

  -- ---------- anon ----------
  r := r || pg_temp.expect_err('T01 anon cannot read tenants', NULL, 'select 1 from public.tenants', '42501');
  r := r || pg_temp.expect_err('T02 anon cannot onboard', NULL, $$select public.create_tenant('x','person')$$, '42501');

  -- ---------- onboarding ----------
  ta := pg_temp.val(ua, $$select public.create_tenant('Fixture A','organization')$$)::uuid;
  r := r || pg_temp.expect_val('T03 onboarding = exactly one admin membership (creator)', ua,
        format($$select count(*) filter (where user_id=%L and role='admin')||'/'||count(*) from public.memberships where tenant_id=%L$$, ua, ta), '1/1');
  PERFORM pg_temp.val(ua, format($$select public.add_tenant_member(%L,%L,'operator')$$, ta, uop));
  PERFORM pg_temp.val(ua, format($$select public.add_tenant_member(%L,%L,'viewer')$$, ta, uv));

  tb := pg_temp.val(ub, $$select public.create_tenant('Fixture B','person')$$)::uuid;
  sb := pg_temp.val(ub, format($$insert into public.subjects(tenant_id, external_ref) values (%L,'b-1') returning id$$, tb))::uuid;
  pb := pg_temp.val(ub, format($$select public.create_value_profile_draft(%L,'B promise')$$, tb))::uuid;
  bb := pg_temp.val(root, format($$insert into public.ingestion_batches(tenant_id, source) values (%L,'fixture') returning id$$, tb))::uuid;
  ob := pg_temp.val(root, format($$insert into public.observations(tenant_id,batch_id,subject_id,indicator_key,value_numeric,unit,source,observed_at,idempotency_key)
         values (%L,%L,%L,'paid_on_time_pct',80,'%%','fixture','2026-01-31T00:00:00Z','b-k1') returning id$$, tb, bb, sb))::uuid;
  r := r || pg_temp.expect_err('T04 B cannot join A as admin', ub, format($$select public.add_tenant_member(%L,%L,'admin')$$, ta, ub), '42501');

  -- ---------- tenant isolation ----------
  r := r || pg_temp.expect_val('T05 A sees zero rows of B (8 tables)', ua, format($$select (
      (select count(*) from public.tenants where id=%1$L)+(select count(*) from public.memberships where tenant_id=%1$L)
     +(select count(*) from public.subjects where tenant_id=%1$L)+(select count(*) from public.tenant_value_profiles where tenant_id=%1$L)
     +(select count(*) from public.profile_indicators where tenant_id=%1$L)+(select count(*) from public.ingestion_batches where tenant_id=%1$L)
     +(select count(*) from public.observations where tenant_id=%1$L)+(select count(*) from public.audit_log where tenant_id=%1$L))::text$$, tb), '0');
  r := r || pg_temp.expect_val('T06 helpers reveal nothing about B', ua, format($$select (public.is_tenant_member(%1$L) or public.my_tenant_role(%1$L) is not null or public.effective_value_profile(%1$L) is not null)::text$$, tb), 'false');
  r := r || pg_temp.expect_err('T07 A cannot insert subject into B', ua, format($$insert into public.subjects(tenant_id, external_ref) values (%L,'x')$$, tb), '42501');
  r := r || pg_temp.expect_rows('T08 A cannot update B subject', ua, format($$update public.subjects set display_name='h' where id=%L$$, sb), 0);
  r := r || pg_temp.expect_err('T09 A cannot create draft in B', ua, format($$select public.create_value_profile_draft(%L,'x')$$, tb), '42501');
  r := r || pg_temp.expect_err('T10 A cannot approve B profile', ua, format($$select public.approve_value_profile(%L)$$, pb), '42501');
  r := r || pg_temp.expect_err('T11 admin A cannot change roles in B', ua, format($$select public.set_member_role(%L,%L,'viewer')$$, tb, ub), '42501');
  r := r || pg_temp.expect_err('T12 A cannot write indicator into B', ua, format($$insert into public.profile_indicators(tenant_id,profile_id,key,name,classification,unit,direction) values (%L,%L,'k','k','usage','%%','higher_is_better')$$, tb, pb), '42501');
  r := r || pg_temp.expect_err('T13 A indicator pointing to B profile rejected by FK', ua, format($$insert into public.profile_indicators(tenant_id,profile_id,key,name,classification,unit,direction) values (%L,%L,'k','k','usage','%%','higher_is_better')$$, ta, pb), '23503', 'profile_indicators_tenant_id_profile_id_fkey');

  sa := pg_temp.val(ua, format($$insert into public.subjects(tenant_id, external_ref, display_name) values (%L,'a-1','Cliente A1') returning id$$, ta))::uuid;
  ba := pg_temp.val(root, format($$insert into public.ingestion_batches(tenant_id, source) values (%L,'fixture') returning id$$, ta))::uuid;
  r := r || pg_temp.expect_err('T14 observation with B batch rejected by FK', root, format($$insert into public.observations(tenant_id,batch_id,subject_id,indicator_key,value_numeric,unit,source,observed_at,idempotency_key) values (%L,%L,%L,'k',1,'%%','f',now(),'x1')$$, ta, bb, sa), '23503', 'observations_tenant_id_batch_id_fkey');
  r := r || pg_temp.expect_err('T15 observation with B subject rejected by FK', root, format($$insert into public.observations(tenant_id,batch_id,subject_id,indicator_key,value_numeric,unit,source,observed_at,idempotency_key) values (%L,%L,%L,'k',1,'%%','f',now(),'x1')$$, ta, ba, sb), '23503', 'observations_tenant_id_subject_id_fkey');
  r := r || pg_temp.expect_err('T16 correction pointing to B observation rejected', root, format($$insert into public.observations(tenant_id,batch_id,subject_id,indicator_key,value_numeric,unit,source,observed_at,idempotency_key,corrects_observation_id) values (%L,%L,%L,'paid_on_time_pct',1,'%%','f',now(),'x2',%L)$$, ta, ba, sa, ob), '23503');
  r := r || pg_temp.expect_err('T16b authenticated cannot INSERT observations directly (RPC only)', ua, format($$insert into public.observations(tenant_id,batch_id,subject_id,indicator_key,value_numeric,unit,source,observed_at,idempotency_key) values (%L,%L,%L,'k',1,'%%','f',now(),'d1')$$, ta, ba, sa), '42501');
  r := r || pg_temp.expect_err('T16c authenticated cannot INSERT batches directly (RPC only)', ua, format($$insert into public.ingestion_batches(tenant_id, source) values (%L,'x')$$, ta), '42501');
  r := r || pg_temp.expect_err('T16d authenticated cannot UPDATE batches directly', ua, format($$update public.ingestion_batches set status='completed' where id=%L$$, ba), '42501');
  r := r || pg_temp.expect_err('T17 tenant_id is immutable', ua, format($$update public.subjects set tenant_id=%L where id=%L$$, tb, sa), '42501');
  r := r || pg_temp.expect_err('T18 created_by is immutable', ua, format($$update public.subjects set created_by=%L where id=%L$$, ub, sa), '42501');
  r := r || pg_temp.expect_err('T19 last admin cannot be demoted', ua, format($$select public.set_member_role(%L,%L,'viewer')$$, ta, ua), '42501');
  r := r || pg_temp.expect_err('T20 last admin cannot leave', ua, format($$select public.remove_tenant_member(%L,%L)$$, ta, ua), '42501');
  r := r || pg_temp.expect_err('T21 deprecated per-subject table not reachable', ua, 'select 1 from public.value_profiles', '42501');

  -- ---------- viewer ----------
  r := r || pg_temp.expect_val('T22 viewer reads own tenant', uv, format($$select count(*)::text from public.subjects where tenant_id=%L$$, ta), '1');
  r := r || pg_temp.expect_err('T23 viewer cannot create subject', uv, format($$insert into public.subjects(tenant_id, external_ref) values (%L,'v')$$, ta), '42501');
  r := r || pg_temp.expect_rows('T24 viewer cannot update subject', uv, format($$update public.subjects set display_name='v' where id=%L$$, sa), 0);
  r := r || pg_temp.expect_err('T25 viewer cannot create draft', uv, format($$select public.create_value_profile_draft(%L,'v')$$, ta), '42501');
  r := r || pg_temp.expect_err('T26 viewer cannot insert observation', uv, format($$insert into public.observations(tenant_id,batch_id,subject_id,indicator_key,value_numeric,unit,source,observed_at,idempotency_key) values (%L,%L,%L,'k',1,'%%','f',now(),'v1')$$, ta, ba, sa), '42501');

  -- ---------- operator ----------
  r := r || pg_temp.expect_err('T27 operator cannot promote self', uop, format($$select public.set_member_role(%L,%L,'admin')$$, ta, uop), '42501');
  r := r || pg_temp.expect_err('T28 operator cannot add members', uop, format($$select public.add_tenant_member(%L,%L,'admin')$$, ta, ub), '42501');
  r := r || pg_temp.expect_err('T29 direct profile insert not granted', uop, format($$insert into public.tenant_value_profiles(tenant_id,version,promise) values (%L,1,'x')$$, ta), '42501');
  pa := pg_temp.val(uop, format($$select public.create_value_profile_draft(%L,'Faturas elegiveis pagas no prazo (exemplo sintetico)')$$, ta))::uuid;
  r := r || pg_temp.expect_val('T30 operator creates tenant draft v1', uop, format($$select version||'/'||status from public.tenant_value_profiles where id=%L$$, pa), '1/draft');
  r := r || pg_temp.expect_err('T31 classification is mandatory', uop, format($$insert into public.profile_indicators(tenant_id,profile_id,key,name,unit,direction) values (%L,%L,'k','k','%%','higher_is_better')$$, ta, pa), '23502');
  r := r || pg_temp.expect_err('T32 partial deterioration rule rejected', uop, format($$insert into public.profile_indicators(tenant_id,profile_id,key,name,classification,unit,direction,deterioration_kind) values (%L,%L,'k','k','outcome','%%','higher_is_better','absolute')$$, ta, pa), '23514', 'pi_deterioration_rule_complete');
  r := r || pg_temp.expect_err('T33 fixed baseline needs value', uop, format($$insert into public.profile_indicators(tenant_id,profile_id,key,name,classification,unit,direction,baseline_method) values (%L,%L,'k','k','outcome','%%','higher_is_better','fixed_value')$$, ta, pa), '23514', 'pi_fixed_baseline_value');
  ia := pg_temp.val(uop, format($$insert into public.profile_indicators(tenant_id,profile_id,key,name,classification,unit,direction) values (%L,%L,'paid_on_time_pct','Pagas no prazo','outcome','%%','higher_is_better') returning id$$, ta, pa))::uuid;
  r := r || pg_temp.expect_val('T34 draft accepts outcome indicator with NULL params', uop, format($$select count(*)::text from public.profile_indicators where id=%L$$, ia), '1');
  r := r || pg_temp.expect_err('T35 operator cannot approve by direct UPDATE', uop, format($$update public.tenant_value_profiles set status='approved', approved_by=%L, approved_at=now() where id=%L$$, uop, pa), '42501');
  r := r || pg_temp.expect_err('T36 operator cannot approve via RPC', uop, format($$select public.approve_value_profile(%L)$$, pa), '42501');

  -- ---------- approval validation ----------
  r := r || pg_temp.expect_err('T37 incomplete outcome indicator blocks approval', ua, format($$select public.approve_value_profile(%L)$$, pa), '22023');
  r := r || pg_temp.expect_val('T38 approval issues listed', ua, format($$select cardinality(public.value_profile_approval_issues(%L))::text$$, pa), '8');
  PERFORM pg_temp.val(uop, format($$update public.profile_indicators set baseline_method='fixed_value', baseline_value=80, baseline_min_period_days=60,
      observation_window_days=30, comparison_window_days=30, min_coverage_pct=90, min_denominator=100, target_value=80,
      deterioration_kind='absolute', deterioration_operator='lt', deterioration_value=56, deterioration_consecutive_windows=2,
      recovery_kind='absolute', recovery_operator='gte', recovery_value=72, recovery_consecutive_windows=2 where id=%L returning id$$, ia));
  r := r || pg_temp.expect_val('T39 complete config has no issues', ua, format($$select cardinality(public.value_profile_approval_issues(%L))::text$$, pa), '0');
  r := r || pg_temp.expect_val('T40 admin approves', ua, format($$select (public.approve_value_profile(%L)).status::text$$, pa), 'approved');
  r := r || pg_temp.expect_val('T41 subjects inherit tenant profile (viewer)', uv, format($$select public.effective_value_profile(%L)::text$$, ta), pa::text);

  -- ---------- immutability ----------
  r := r || pg_temp.expect_rows('T42 approved profile not updatable', ua, format($$update public.tenant_value_profiles set promise='x' where id=%L$$, pa), 0);
  r := r || pg_temp.expect_rows('T43 approved profile not deletable', ua, format($$delete from public.tenant_value_profiles where id=%L$$, pa), 0);
  r := r || pg_temp.expect_err('T44 approved indicator not updatable', ua, format($$update public.profile_indicators set target_value=99 where id=%L$$, ia), '42501');
  r := r || pg_temp.expect_err('T45 approved indicator not deletable', ua, format($$delete from public.profile_indicators where id=%L$$, ia), '42501');
  r := r || pg_temp.expect_err('T46 no new indicator on approved profile', ua, format($$insert into public.profile_indicators(tenant_id,profile_id,key,name,classification,unit,direction) values (%L,%L,'extra','x','usage','%%','higher_is_better')$$, ta, pa), '42501');

  -- ---------- versioning ----------
  pa2 := pg_temp.val(uop, format($$select public.create_value_profile_version(%L)$$, pa))::uuid;
  r := r || pg_temp.expect_val('T47 new version is draft v2 with full copy', uop, format($$select p.version||'/'||p.status||'/'||(select count(*) from public.profile_indicators i where i.profile_id=p.id and i.classification='outcome' and i.recovery_value=72) from public.tenant_value_profiles p where p.id=%L$$, pa2), '2/draft/1');
  PERFORM pg_temp.val(uop, format($$insert into public.profile_indicators(tenant_id,profile_id,key,name,classification,unit,direction) values (%L,%L,'logins','Logins','usage','count','higher_is_better') returning id$$, ta, pa2));
  pa3 := pg_temp.val(uop, format($$select public.create_value_profile_version(%L)$$, pa))::uuid;
  r := r || pg_temp.expect_val('T48 v3 (copy of v1) approved', ua, format($$select (public.approve_value_profile(%L)).version::text$$, pa3), '3');
  r := r || pg_temp.expect_val('T49 previous approved becomes superseded', ua, format($$select status::text from public.tenant_value_profiles where id=%L$$, pa), 'superseded');
  r := r || pg_temp.expect_err('T50 older draft cannot override newer approved', ua, format($$select public.approve_value_profile(%L)$$, pa2), '22023');
  r := r || pg_temp.expect_val('T51 one approved profile per tenant', ua, format($$select count(*)::text from public.tenant_value_profiles where tenant_id=%L and status='approved'$$, ta), '1');

  -- ---------- observations ----------
  oa := pg_temp.val(root, format($$insert into public.observations(tenant_id,batch_id,subject_id,indicator_key,value_numeric,unit,source,observed_at,idempotency_key,payload)
        values (%L,%L,%L,'paid_on_time_pct',80,'%%','fixture','2026-01-31T00:00:00Z','a-k1','{"eligible":100,"paid_on_time":80}') returning id$$, ta, ba, sa))::uuid;
  r := r || pg_temp.expect_rows('T52 identical replay is a no-op', root, format($$insert into public.observations(tenant_id,batch_id,subject_id,indicator_key,value_numeric,unit,source,observed_at,idempotency_key,payload)
        values (%L,%L,%L,'paid_on_time_pct',80.0,'%%','fixture','2026-01-31T00:00:00Z','a-k1','{"eligible":100,"paid_on_time":80}')$$, ta, ba, sa), 0);
  r := r || pg_temp.expect_err('T53 same key, different content = conflict', root, format($$insert into public.observations(tenant_id,batch_id,subject_id,indicator_key,value_numeric,unit,source,observed_at,idempotency_key)
        values (%L,%L,%L,'paid_on_time_pct',55,'%%','fixture','2026-01-31T00:00:00Z','a-k1')$$, ta, ba, sa), '23505');
  r := r || pg_temp.expect_err('T54 observations not updatable', ua, format($$update public.observations set value_numeric=1 where id=%L$$, oa), '42501');
  r := r || pg_temp.expect_rows('T55 explicit same-tenant correction accepted', root, format($$insert into public.observations(tenant_id,batch_id,subject_id,indicator_key,value_numeric,unit,source,observed_at,idempotency_key,corrects_observation_id)
        values (%L,%L,%L,'paid_on_time_pct',78,'%%','fixture','2026-01-31T00:00:00Z','a-k1-fix',%L)$$, ta, ba, sa, oa), 1);

  -- ---------- regression 0002: zero outcome indicators must report an issue, not crash ----------
  PERFORM pg_temp.val(ub, format($$insert into public.profile_indicators(tenant_id,profile_id,key,name,classification,unit,direction) values (%L,%L,'logins','Logins','usage','count','higher_is_better') returning id$$, tb, pb));
  r := r || pg_temp.expect_val('T62 zero-outcome profile returns the explicit issue', ub, format($$select array_to_string(public.value_profile_approval_issues(%L),'|')$$, pb), 'profile needs at least one outcome indicator');
  r := r || pg_temp.expect_err('T63 zero-outcome profile cannot be approved', ub, format($$select public.approve_value_profile(%L)$$, pb), '22023');
  r := r || pg_temp.expect_err('T64 outcome indicator cannot be text-typed', ub, format($$insert into public.profile_indicators(tenant_id,profile_id,key,name,classification,value_type,unit,direction) values (%L,%L,'o_txt','x','outcome','text','x','higher_is_better')$$, tb, pb), '23514', 'pi_outcome_numeric');

  -- ---------- audit ----------
  r := r || pg_temp.expect_err('T56 client cannot insert audit', ua, format($$insert into public.audit_log(tenant_id,actor_id,action,entity_type) values (%L,%L,'fake','x')$$, ta, ub), '42501');
  r := r || pg_temp.expect_err('T57 client cannot update audit', ua, format($$update public.audit_log set actor_id=%L where tenant_id=%L$$, ub, ta), '42501');
  r := r || pg_temp.expect_err('T58 client cannot delete audit', ua, format($$delete from public.audit_log where tenant_id=%L$$, ta), '42501');
  r := r || pg_temp.expect_val('T59 approval audited with true actor', ua, format($$select count(*)::text from public.audit_log where entity_type='tenant_value_profiles' and entity_id=%L and actor_id=%L and details->>'status'='approved' and details->>'previous_status'='draft'$$, pa, ua), '1');
  r := r || pg_temp.expect_val('T60 draft creation audited with operator actor', ua, format($$select count(*)::text from public.audit_log where entity_type='tenant_value_profiles' and entity_id=%L and action='insert' and actor_id=%L$$, pa, uop), '1');
  BEGIN
    UPDATE public.audit_log SET action = 'x' WHERE tenant_id = ta;
    r := r || E'\nFAIL T61 privileged role altered audit';
  EXCEPTION WHEN OTHERS THEN
    r := r || CASE WHEN SQLSTATE = '42501' THEN E'\nPASS T61 even privileged role cannot alter audit [42501]' ELSE E'\nFAIL T61 got ' || SQLSTATE END;
  END;

  npass := (length(r) - length(replace(r, E'\nPASS', ''))) / 5;
  nfail := (length(r) - length(replace(r, E'\nFAIL', ''))) / 5;
  RAISE EXCEPTION 'CW_TEST_RESULTS pass=% fail=% (transaction rolled back)%', npass, nfail, r;
END
$test$;
