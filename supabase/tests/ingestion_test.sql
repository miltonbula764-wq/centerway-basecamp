-- CENTERWAY C01 ingestion tests (re-runnable) for public.import_observations.
-- Every call runs as real `anon` / `authenticated` roles with JWT claims (never service_role).
-- The whole block is ALWAYS rolled back (it ends with RAISE EXCEPTION carrying the results).
-- Negative tests assert the exact SQLSTATE and, where relevant, the message or per-line error codes.
DO $test$
DECLARE
  ua uuid := gen_random_uuid(); uop uuid := gen_random_uuid(); uv uuid := gen_random_uuid(); ub uuid := gen_random_uuid();
  ta uuid; tb uuid; pa uuid; pa2 uuid; pb uuid; sa1 uuid; sb1 uuid; ob1 uuid; oa1 uuid; b1 uuid;
  r text := ''; npass int; nfail int; res jsonb; rows jsonb; big jsonb;
  cs text := '2026-01-01T00:00:00Z'; ce text := '2026-03-01T00:00:00Z';
BEGIN
  CREATE FUNCTION pg_temp.as_user(_uid uuid) RETURNS void LANGUAGE plpgsql AS $f$
  BEGIN
    PERFORM set_config('request.jwt.claims', CASE WHEN _uid IS NULL THEN '{"role":"anon"}'
      ELSE json_build_object('sub', _uid, 'role', 'authenticated')::text END, true);
    PERFORM set_config('role', CASE WHEN _uid IS NULL THEN 'anon' ELSE 'authenticated' END, true);
  END $f$;
  CREATE FUNCTION pg_temp.val(_uid uuid, _sql text) RETURNS text LANGUAGE plpgsql AS $f$
  DECLARE v text;
  BEGIN PERFORM pg_temp.as_user(_uid); EXECUTE _sql INTO v; RESET ROLE; RETURN v;
  EXCEPTION WHEN OTHERS THEN RESET ROLE; RAISE; END $f$;
  CREATE FUNCTION pg_temp.expect_err(_label text, _uid uuid, _sql text, _state text, _msg text DEFAULT NULL)
  RETURNS text LANGUAGE plpgsql AS $f$
  BEGIN
    BEGIN
      PERFORM pg_temp.as_user(_uid); EXECUTE _sql; RESET ROLE;
      RETURN E'\nFAIL ' || _label || ' (no error raised)';
    EXCEPTION WHEN OTHERS THEN
      RESET ROLE;
      IF SQLSTATE = _state AND (_msg IS NULL OR SQLERRM = _msg) THEN
        RETURN E'\nPASS ' || _label || ' [' || SQLSTATE || coalesce(' ' || _msg, '') || ']';
      END IF;
      RETURN E'\nFAIL ' || _label || ' expected ' || _state || coalesce(' ' || _msg, '') || ' got ' || SQLSTATE || ' ' || SQLERRM;
    END;
  END $f$;
  CREATE FUNCTION pg_temp.check(_label text, _actual text, _expected text) RETURNS text LANGUAGE plpgsql AS $f$
  BEGIN
    IF _actual IS NOT DISTINCT FROM _expected THEN RETURN E'\nPASS ' || _label || ' [' || coalesce(_actual, 'null') || ']'; END IF;
    RETURN E'\nFAIL ' || _label || ' expected ' || coalesce(_expected, 'null') || ' got ' || coalesce(_actual, 'null');
  END $f$;
  -- import as a given user; returns the RPC result
  CREATE FUNCTION pg_temp.imp(_uid uuid, _t uuid, _p uuid, _rows jsonb, _cs text, _ce text, _declared boolean DEFAULT true)
  RETURNS jsonb LANGUAGE plpgsql AS $f$
  BEGIN
    RETURN pg_temp.val(_uid, format($$select public.import_observations(%L,%L,'fixture-csv',%L,%L,%L,'fx.csv',%L::jsonb)::text$$,
      _t, _p, _cs, _ce, _declared, _rows))::jsonb;
  END $f$;
  CREATE FUNCTION pg_temp.summary(_res jsonb) RETURNS text LANGUAGE sql AS $f$
    SELECT (_res->>'status')||' ins='||(_res->>'inserted')||' dup='||(_res->>'duplicates')||' rej='||(_res->>'rejected') $f$;
  CREATE FUNCTION pg_temp.codes(_res jsonb) RETURNS text LANGUAGE sql AS $f$
    SELECT coalesce(string_agg((e->>'line')||':'||(SELECT string_agg(c, ',' ORDER BY c) FROM jsonb_array_elements_text(e->'errors') c), ' ' ORDER BY (e->>'line')::int), '')
    FROM jsonb_array_elements(_res->'errors') e $f$;
  CREATE FUNCTION pg_temp.row(_line int, _ref text, _key text, _num text, _txt text, _unit text, _at text, _idem text, _corr text DEFAULT '')
  RETURNS jsonb LANGUAGE sql AS $f$
    SELECT jsonb_build_object('line', _line, 'subject_external_ref', _ref, 'indicator_key', _key, 'value_numeric', _num,
      'value_text', _txt, 'unit', _unit, 'observed_at', _at, 'idempotency_key', _idem, 'corrects_observation_id', _corr) $f$;

  INSERT INTO auth.users(id, instance_id, aud, role, email) VALUES
   (ua,  '00000000-0000-0000-0000-000000000000','authenticated','authenticated','cw-ing-a@example.invalid'),
   (uop, '00000000-0000-0000-0000-000000000000','authenticated','authenticated','cw-ing-op@example.invalid'),
   (uv,  '00000000-0000-0000-0000-000000000000','authenticated','authenticated','cw-ing-v@example.invalid'),
   (ub,  '00000000-0000-0000-0000-000000000000','authenticated','authenticated','cw-ing-b@example.invalid');

  -- ---------- fixtures (through the normal authenticated paths) ----------
  ta := pg_temp.val(ua, $$select public.create_tenant('Ing A','organization')$$)::uuid;
  PERFORM pg_temp.val(ua, format($$select public.add_tenant_member(%L,%L,'operator')$$, ta, uop));
  PERFORM pg_temp.val(ua, format($$select public.add_tenant_member(%L,%L,'viewer')$$, ta, uv));
  sa1 := pg_temp.val(ua, format($$insert into public.subjects(tenant_id, external_ref) values (%L,'a-1') returning id$$, ta))::uuid;
  PERFORM pg_temp.val(ua, format($$insert into public.subjects(tenant_id, external_ref) values (%L,'a-2') returning id$$, ta));
  pa := pg_temp.val(uop, format($$select public.create_value_profile_draft(%L,'Synthetic promise')$$, ta))::uuid;
  PERFORM pg_temp.val(uop, format($$insert into public.profile_indicators(tenant_id,profile_id,key,name,classification,unit,direction,
     baseline_method,baseline_value,baseline_min_period_days,observation_window_days,comparison_window_days,min_coverage_pct,min_denominator,
     deterioration_kind,deterioration_operator,deterioration_value,deterioration_consecutive_windows,
     recovery_kind,recovery_operator,recovery_value,recovery_consecutive_windows)
     values (%L,%L,'paid_on_time_pct','Pagas no prazo','outcome','%%','higher_is_better','fixed_value',80,28,7,7,90,30,
     'absolute','lt',56,2,'absolute','gte',72,2) returning id$$, ta, pa));
  PERFORM pg_temp.val(uop, format($$insert into public.profile_indicators(tenant_id,profile_id,key,name,classification,value_type,unit,direction)
     values (%L,%L,'plan_note','Nota de plano','context','text','texto','higher_is_better') returning id$$, ta, pa));

  tb := pg_temp.val(ub, $$select public.create_tenant('Ing B','person')$$)::uuid;
  sb1 := pg_temp.val(ub, format($$insert into public.subjects(tenant_id, external_ref) values (%L,'b-1') returning id$$, tb))::uuid;
  pb := pg_temp.val(ub, format($$select public.create_value_profile_draft(%L,'B promise')$$, tb))::uuid;
  PERFORM pg_temp.val(ub, format($$insert into public.profile_indicators(tenant_id,profile_id,key,name,classification,unit,direction,
     baseline_method,baseline_value,baseline_min_period_days,observation_window_days,comparison_window_days,min_coverage_pct,min_denominator,
     deterioration_kind,deterioration_operator,deterioration_value,deterioration_consecutive_windows,
     recovery_kind,recovery_operator,recovery_value,recovery_consecutive_windows)
     values (%L,%L,'paid_on_time_pct','x','outcome','%%','higher_is_better','fixed_value',80,28,7,7,90,30,'absolute','lt',56,2,'absolute','gte',72,2) returning id$$, tb, pb));

  rows := jsonb_build_array(pg_temp.row(2,'a-1','paid_on_time_pct','80','','%','2026-01-08T00:00:00Z','k1'));

  -- ---------- access ----------
  r := r || pg_temp.expect_err('I01 anon cannot import', NULL, format($$select public.import_observations(%L,%L,'s',now()-interval '1 day',now(),true,null,'[]')$$, ta, pa), '42501');
  r := r || pg_temp.expect_err('I02 approved profile required', uop, format($$select public.import_observations(%L,%L,'s',%L,%L,true,null,%L::jsonb)$$, ta, pa, cs, ce, rows), '22023', 'import: no approved value profile');
  PERFORM pg_temp.val(ua, format($$select (public.approve_value_profile(%L)).id::text$$, pa));
  PERFORM pg_temp.val(ub, format($$select (public.approve_value_profile(%L)).id::text$$, pb));
  r := r || pg_temp.expect_err('I03 viewer cannot import', uv, format($$select public.import_observations(%L,%L,'s',%L,%L,true,null,%L::jsonb)$$, ta, pa, cs, ce, rows), '42501', 'not authorized');
  r := r || pg_temp.expect_err('I04 operator of A cannot import into B', uop, format($$select public.import_observations(%L,%L,'s',%L,%L,true,null,%L::jsonb)$$, tb, pb, cs, ce, rows), '42501', 'not authorized');
  r := r || pg_temp.expect_err('I05 coverage must be declared', uop, format($$select public.import_observations(%L,%L,'s',%L,%L,false,null,%L::jsonb)$$, ta, pa, cs, ce, rows), '22023', 'import: coverage not declared');
  r := r || pg_temp.expect_err('I06 coverage end must be after start', uop, format($$select public.import_observations(%L,%L,'s',%L,%L,true,null,%L::jsonb)$$, ta, pa, ce, cs, rows), '22023', 'import: invalid coverage interval');
  SELECT jsonb_agg(pg_temp.row(g+1,'a-1','paid_on_time_pct','1','','%','2026-01-08T00:00:00Z','big'||g)) INTO big FROM generate_series(1,1001) g;
  r := r || pg_temp.expect_err('I07 more than 1000 rows rejected server-side', uop, format($$select public.import_observations(%L,%L,'s',%L,%L,true,null,%L::jsonb)$$, ta, pa, cs, ce, big), '22023', 'import: too many rows');
  r := r || pg_temp.expect_err('I08 empty batch rejected', uop, format($$select public.import_observations(%L,%L,'s',%L,%L,true,null,'[]')$$, ta, pa, cs, ce), '22023', 'import: empty batch');

  -- ---------- valid import, replay, conflict ----------
  rows := jsonb_build_array(
    pg_temp.row(2,'a-1','paid_on_time_pct','80','','%','2026-01-08T00:00:00Z','k1'),
    pg_temp.row(3,'a-2','paid_on_time_pct','78.5','','%','2026-01-08T12:00:00+01:00','k2'),
    pg_temp.row(4,'a-1','plan_note','','Plano anual','texto','2026-01-09T00:00:00Z','k3'));
  res := pg_temp.imp(uop, ta, pa, rows, cs, ce);
  b1 := (res->>'batch_id')::uuid;
  r := r || pg_temp.check('I09 valid batch committed', pg_temp.summary(res), 'completed ins=3 dup=0 rej=0');
  r := r || pg_temp.check('I10 observations persisted with server-side author and hash', pg_temp.val(ua, format(
    $$select count(*) filter (where created_by=%L and payload_hash<>'' and payload->>'profile_version'='1')::text from public.observations where batch_id=%L$$, uop, b1)), '3');
  r := r || pg_temp.check('I11 batch pins profile version and snapshot', pg_temp.val(uv, format(
    $$select profile_version||'/'||(contract_snapshot->>'contract')||'/'||coverage_declared||'/'||row_count||'/'||inserted_count from public.ingestion_batches where id=%L$$, b1)),
    '1/centerway_csv_v1/true/3/3');
  r := r || pg_temp.check('I12 "missing" stays missing (text row has NULL numeric)', pg_temp.val(ua, format(
    $$select (value_numeric is null and value_text='Plano anual')::text from public.observations where tenant_id=%L and idempotency_key='k3'$$, ta)), 'true');
  r := r || pg_temp.check('I13 offset normalized to UTC', pg_temp.val(ua, format(
    $$select (observed_at = '2026-01-08T11:00:00Z'::timestamptz)::text from public.observations where tenant_id=%L and idempotency_key='k2'$$, ta)), 'true');

  res := pg_temp.imp(uop, ta, pa, rows, cs, ce);
  r := r || pg_temp.check('I14 identical replay = no duplicates', pg_temp.summary(res), 'completed ins=0 dup=3 rej=0');
  r := r || pg_temp.check('I15 still 3 observations after replay', pg_temp.val(ua, format($$select count(*)::text from public.observations where tenant_id=%L$$, ta)), '3');

  res := pg_temp.imp(uop, ta, pa, jsonb_build_array(pg_temp.row(2,'a-1','paid_on_time_pct','55','','%','2026-01-08T00:00:00Z','k1')), cs, ce);
  r := r || pg_temp.check('I16 same key, different value = conflict', pg_temp.summary(res)||' '||pg_temp.codes(res), 'failed ins=0 dup=0 rej=1 2:idempotency_conflict');

  -- ---------- atomic rollback ----------
  res := pg_temp.imp(uop, ta, pa, jsonb_build_array(
    pg_temp.row(2,'a-1','paid_on_time_pct','70','','%','2026-01-15T00:00:00Z','k-new'),
    pg_temp.row(3,'nope','paid_on_time_pct','70','','%','2026-01-15T00:00:00Z','k-new2')), cs, ce);
  r := r || pg_temp.check('I17 one bad line fails the whole batch', pg_temp.summary(res)||' '||pg_temp.codes(res), 'failed ins=0 dup=0 rej=1 3:unknown_subject');
  r := r || pg_temp.check('I18 valid line of failed batch NOT written', pg_temp.val(ua, format($$select count(*)::text from public.observations where tenant_id=%L and idempotency_key='k-new'$$, ta)), '0');
  r := r || pg_temp.check('I19 failed batch recorded with errors', pg_temp.val(uv, format(
    $$select status||'/'||rejected_count||'/'||jsonb_array_length(errors) from public.ingestion_batches where id=%L$$, res->>'batch_id')), 'failed/1/1');

  -- conflict found only at write time (after valid pass 1) also rolls back earlier inserted rows
  res := pg_temp.imp(uop, ta, pa, jsonb_build_array(
    pg_temp.row(2,'a-1','paid_on_time_pct','71','','%','2026-01-16T00:00:00Z','k-atom'),
    pg_temp.row(3,'a-1','paid_on_time_pct','99','','%','2026-01-08T00:00:00Z','k1')), cs, ce);
  r := r || pg_temp.check('I20 write-time conflict rolls back the batch', pg_temp.summary(res)||' '||pg_temp.codes(res)||' '||
    pg_temp.val(ua, format($$select count(*) from public.observations where tenant_id=%L and idempotency_key='k-atom'$$, ta)), 'failed ins=0 dup=0 rej=1 3:idempotency_conflict 0');

  -- ---------- within one file ----------
  res := pg_temp.imp(uop, ta, pa, jsonb_build_array(
    pg_temp.row(2,'a-2','paid_on_time_pct','60','','%','2026-01-20T00:00:00Z','k-in'),
    pg_temp.row(3,'a-2','paid_on_time_pct','61','','%','2026-01-20T00:00:00Z','k-in')), cs, ce);
  r := r || pg_temp.check('I21 same key twice in a file with different values = conflict', pg_temp.summary(res)||' '||pg_temp.codes(res), 'failed ins=0 dup=0 rej=1 3:idempotency_conflict');
  res := pg_temp.imp(uop, ta, pa, jsonb_build_array(
    pg_temp.row(2,'a-2','paid_on_time_pct','60','','%','2026-01-20T00:00:00Z','k-in'),
    pg_temp.row(3,'a-2','paid_on_time_pct','60.0','','%','2026-01-20T00:00:00Z','k-in')), cs, ce);
  r := r || pg_temp.check('I22 identical repeated line in a file = 1 insert + 1 duplicate', pg_temp.summary(res), 'completed ins=1 dup=1 rej=0');

  -- ---------- per-line validation ----------
  res := pg_temp.imp(uop, ta, pa, jsonb_build_array(
    pg_temp.row(2,'a-1','unknown_k','1','','%','2026-01-08T00:00:00Z','v2'),
    pg_temp.row(3,'a-1','paid_on_time_pct','1','','pct','2026-01-08T00:00:00Z','v3'),
    pg_temp.row(4,'a-1','paid_on_time_pct','','texto','%','2026-01-08T00:00:00Z','v4'),
    pg_temp.row(5,'a-1','paid_on_time_pct','1','x','%','2026-01-08T00:00:00Z','v5'),
    pg_temp.row(6,'a-1','paid_on_time_pct','','','%','2026-01-08T00:00:00Z','v6'),
    pg_temp.row(7,'a-1','paid_on_time_pct','NaN','','%','2026-01-08T00:00:00Z','v7'),
    pg_temp.row(8,'a-1','paid_on_time_pct','Infinity','','%','2026-01-08T00:00:00Z','v8'),
    pg_temp.row(9,'a-1','paid_on_time_pct','1','','%','2026-01-08T00:00:00','v9'),
    pg_temp.row(10,'a-1','paid_on_time_pct','1','','%','2099-01-08T00:00:00Z','v10'),
    pg_temp.row(11,'a-1','paid_on_time_pct','1','','%','2026-03-01T00:00:00Z','v11'),
    pg_temp.row(12,'a-1','paid_on_time_pct','1','','%','2026-02-30T00:00:00Z','v12'),
    pg_temp.row(13,'a-1','plan_note','5','','texto','2026-01-08T00:00:00Z','v13'),
    pg_temp.row(14,'b-1','paid_on_time_pct','1','','%','2026-01-08T00:00:00Z','v14'),
    pg_temp.row(15,'a-1','paid_on_time_pct','1','','%','2026-01-08T00:00:00Z',''),
    pg_temp.row(16,'a-1','paid_on_time_pct','1,5','','%','2026-01-08T00:00:00Z','v16')), cs, ce);
  r := r || pg_temp.check('I23 per-line error codes (indicator/unit/type/values/NaN/Inf/tz/future/coverage/date/B subject/key/decimal comma)', pg_temp.codes(res),
    '2:unknown_indicator 3:unit_mismatch 4:type_mismatch 5:both_values 6:missing_value 7:invalid_number 8:invalid_number 9:invalid_timestamp 10:future_timestamp 11:outside_coverage 12:invalid_timestamp 13:type_mismatch 14:unknown_subject 15:invalid_idempotency_key 16:invalid_number');
  r := r || pg_temp.check('I24 nothing written from invalid file', pg_temp.val(ua, format($$select count(*)::text from public.observations where tenant_id=%L and idempotency_key like 'v%%'$$, ta)), '0');

  -- ---------- corrections ----------
  oa1 := pg_temp.val(ua, format($$select id::text from public.observations where tenant_id=%L and idempotency_key='k1'$$, ta))::uuid;
  ob1 := gen_random_uuid();
  res := pg_temp.imp(ub, tb, pb, jsonb_build_array(pg_temp.row(2,'b-1','paid_on_time_pct','50','','%','2026-01-08T00:00:00Z','bk1')), cs, ce);
  ob1 := pg_temp.val(ub, format($$select id::text from public.observations where tenant_id=%L and idempotency_key='bk1'$$, tb))::uuid;
  res := pg_temp.imp(uop, ta, pa, jsonb_build_array(
    pg_temp.row(2,'a-1','paid_on_time_pct','81','','%','2026-01-08T00:00:00Z','k1-fix', ob1::text)), cs, ce);
  r := r || pg_temp.check('I25 correction pointing to B observation refused (no leak)', pg_temp.codes(res), '2:correction_target_not_found');
  res := pg_temp.imp(uop, ta, pa, jsonb_build_array(
    pg_temp.row(2,'a-2','paid_on_time_pct','81','','%','2026-01-08T00:00:00Z','k1-fix', oa1::text)), cs, ce);
  r := r || pg_temp.check('I26 correction for another subject refused', pg_temp.codes(res), '2:correction_target_not_found');
  res := pg_temp.imp(uop, ta, pa, jsonb_build_array(
    pg_temp.row(2,'a-1','paid_on_time_pct','81','','%','2026-01-08T00:00:00Z','k1-fix', oa1::text)), cs, ce);
  r := r || pg_temp.check('I27 explicit same-tenant correction accepted, original untouched', pg_temp.summary(res)||' '||
    pg_temp.val(ua, format($$select (select value_numeric from public.observations where id=%L)||'/'||(select count(*) from public.observations where corrects_observation_id=%L)$$, oa1, oa1)),
    'completed ins=1 dup=0 rej=0 80/1');

  -- ---------- profile superseded between preview and commit ----------
  pa2 := pg_temp.val(uop, format($$select public.create_value_profile_version(%L)$$, pa))::uuid;
  PERFORM pg_temp.val(ua, format($$select (public.approve_value_profile(%L)).id::text$$, pa2));
  r := r || pg_temp.expect_err('I28 stale profile id blocks commit', uop, format($$select public.import_observations(%L,%L,'s',%L,%L,true,null,%L::jsonb)$$, ta, pa, cs, ce, rows), '22023', 'import: approved value profile changed');
  r := r || pg_temp.check('I29 completed batch keeps historical profile version', pg_temp.val(ua, format($$select profile_version::text from public.ingestion_batches where id=%L$$, b1)), '1');
  r := r || pg_temp.check('I30 value_type copied to new version', pg_temp.val(ua, format($$select value_type::text from public.profile_indicators where profile_id=%L and key='plan_note'$$, pa2)), 'text');
  res := pg_temp.imp(uop, ta, pa2, rows, cs, ce);
  r := r || pg_temp.check('I31 replay under a new profile version = conflict (version is part of the hash)', pg_temp.summary(res), 'failed ins=0 dup=0 rej=3');

  -- ---------- isolation, direct writes, audit ----------
  r := r || pg_temp.check('I32 B admin sees no A batches/observations', pg_temp.val(ub, format($$select ((select count(*) from public.ingestion_batches where tenant_id=%1$L)+(select count(*) from public.observations where tenant_id=%1$L))::text$$, ta)), '0');
  r := r || pg_temp.expect_err('I33 direct observation insert bypassing RPC denied', uop, format($$insert into public.observations(tenant_id,batch_id,subject_id,indicator_key,value_numeric,unit,source,observed_at,idempotency_key) values (%L,%L,%L,'paid_on_time_pct',1,'%%','x','2026-01-08T00:00:00Z','direct')$$, ta, b1, sa1), '42501');
  r := r || pg_temp.expect_err('I34 direct batch update denied', ua, format($$update public.ingestion_batches set inserted_count=99 where id=%L$$, b1), '42501');
  r := r || pg_temp.check('I35 batch creation audited with real actor', pg_temp.val(ua, format($$select count(*)::text from public.audit_log where entity_type='ingestion_batches' and entity_id=%L and action='insert' and actor_id=%L$$, b1, uop)), '1');

  npass := (length(r) - length(replace(r, E'\nPASS', ''))) / 5;
  nfail := (length(r) - length(replace(r, E'\nFAIL', ''))) / 5;
  RAISE EXCEPTION 'CW_INGEST_RESULTS pass=% fail=% (transaction rolled back)%', npass, nfail, r;
END
$test$;
