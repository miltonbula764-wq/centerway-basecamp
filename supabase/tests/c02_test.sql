-- CENTERWAY C02 Deterioration Detector tests (re-runnable) for public.run_deterioration_analysis (+ C01 correction hardening).
-- Calls run as real `anon` / `authenticated` roles with JWT claims (never service_role for assertions).
-- The whole block is ALWAYS rolled back (it ends with RAISE EXCEPTION carrying the results).
-- Synthetic timeline (fixture only, not real data): as_of = 2026-09-01T00:00Z, window W = 7 days, N = 2 consecutive windows:
--   current_1 = [08-25, 09-01), current_2 = [08-18, 08-25), reference = [08-11, 08-18), trailing baseline (28d) = [07-21, 08-18).
DO $test$
DECLARE
  ua uuid := gen_random_uuid(); uop uuid := gen_random_uuid(); uv uuid := gen_random_uuid(); ub uuid := gen_random_uuid();
  ta uuid; tb uuid; pa uuid; pa2 uuid; pb uuid; sb uuid;
  s1 uuid; s2 uuid; s3 uuid; s4 uuid; s5 uuid; s6 uuid; s7 uuid; s8 uuid;
  s9 uuid; s10 uuid; s11 uuid; s12 uuid; s13 uuid; s14 uuid; s15 uuid; p4 uuid; p5 uuid;
  v1run uuid; v1md5 text; runA jsonb; runB jsonb; mdA text; oc uuid; compat uuid[]; nnot int;
  r text := ''; npass int; nfail int; res jsonb; run1 jsonb; run2 jsonb; o26 uuid; o19 uuid;
  asof text := '2026-09-01T00:00:00Z';
  cols text := 'tenant_id,profile_id,key,name,classification,unit,direction,baseline_method,baseline_value,baseline_min_period_days,
    observation_window_days,comparison_window_days,min_coverage_pct,min_denominator,target_value,deterioration_kind,deterioration_operator,
    deterioration_value,deterioration_consecutive_windows,recovery_kind,recovery_operator,recovery_value,recovery_consecutive_windows,
    aggregation,expected_cadence_days,denominator_mode,denominator_indicator_key';
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
  CREATE FUNCTION pg_temp.row(_ref text, _key text, _num text, _unit text, _at text, _corr text DEFAULT '', _tag text DEFAULT '')
  RETURNS jsonb LANGUAGE sql AS $f$
    SELECT jsonb_build_object('subject_external_ref', _ref, 'indicator_key', _key, 'value_numeric', _num, 'value_text', '',
      'unit', _unit, 'observed_at', _at, 'idempotency_key', _ref||'|'||_key||'|'||_at||'|'||_num||_tag, 'corrects_observation_id', _corr) $f$;
  CREATE FUNCTION pg_temp.imp(_uid uuid, _t uuid, _p uuid, _rows jsonb, _src text DEFAULT 'fixture-c02') RETURNS jsonb LANGUAGE plpgsql AS $f$
  BEGIN
    RETURN pg_temp.val(_uid, format($$select public.import_observations(%L,%L,%L,'2026-07-01T00:00:00Z','2026-09-02T00:00:00Z',true,'c02.csv',%L::jsonb)::text$$,
      _t, _p, _src, _rows))::jsonb;
  END $f$;
  CREATE FUNCTION pg_temp.codes(_res jsonb) RETURNS text LANGUAGE sql AS $f$
    SELECT coalesce(string_agg((SELECT string_agg(c, ',' ORDER BY c) FROM jsonb_array_elements_text(e->'errors') c), ' '), '')
    FROM jsonb_array_elements(_res->'errors') e $f$;
  -- weekly series helper: values at 07-22, 07-29, 08-05, 08-12, 08-19, 08-26 (NULL = no row: absence, never zero)
  CREATE FUNCTION pg_temp.series(_ref text, _key text, _unit text, _v numeric[]) RETURNS jsonb LANGUAGE sql AS $f$
    SELECT coalesce(jsonb_agg(pg_temp.row(_ref, _key, (_v[i])::text, _unit, d[i])), '[]'::jsonb)
    FROM (SELECT ARRAY['2026-07-22T10:00:00Z','2026-07-29T10:00:00Z','2026-08-05T10:00:00Z','2026-08-12T10:00:00Z',
                       '2026-08-19T10:00:00Z','2026-08-26T10:00:00Z'] AS d) z, generate_series(1, 6) i WHERE _v[i] IS NOT NULL $f$;
  CREATE FUNCTION pg_temp.run(_uid uuid, _t uuid, _s uuid, _p uuid, _asof text) RETURNS jsonb LANGUAGE plpgsql AS $f$
  BEGIN RETURN pg_temp.val(_uid, format($$select public.run_deterioration_analysis(%L,%L,%L,%L)::text$$, _t, _s, _p, _asof))::jsonb; END $f$;
  -- status[/below_target] of one indicator in one run, read back as the tenant admin (through RLS)
  CREATE FUNCTION pg_temp.st(_uid uuid, _run jsonb, _key text) RETURNS text LANGUAGE plpgsql AS $f$
  BEGIN RETURN pg_temp.val(_uid, format($$select status::text||coalesce('/below='||below_target,'') from public.c02_results where run_id=%L and indicator_key=%L$$, _run->>'run_id', _key)); END $f$;
  CREATE FUNCTION pg_temp.rs(_uid uuid, _run jsonb, _key text) RETURNS text LANGUAGE plpgsql AS $f$
  BEGIN RETURN pg_temp.val(_uid, format($$select array_to_string(reasons, ',') from public.c02_results where run_id=%L and indicator_key=%L$$, _run->>'run_id', _key)); END $f$;

  INSERT INTO auth.users(id, instance_id, aud, role, email) VALUES
   (ua,  '00000000-0000-0000-0000-000000000000','authenticated','authenticated','cw-c02-a@example.invalid'),
   (uop, '00000000-0000-0000-0000-000000000000','authenticated','authenticated','cw-c02-op@example.invalid'),
   (uv,  '00000000-0000-0000-0000-000000000000','authenticated','authenticated','cw-c02-v@example.invalid'),
   (ub,  '00000000-0000-0000-0000-000000000000','authenticated','authenticated','cw-c02-b@example.invalid');

  ta := pg_temp.val(ua, $$select public.create_tenant('C02 A','organization')$$)::uuid;
  PERFORM pg_temp.val(ua, format($$select public.add_tenant_member(%L,%L,'operator')$$, ta, uop));
  PERFORM pg_temp.val(ua, format($$select public.add_tenant_member(%L,%L,'viewer')$$, ta, uv));
  s1 := pg_temp.val(ua, format($$insert into public.subjects(tenant_id, external_ref) values (%L,'drop') returning id$$, ta))::uuid;
  s2 := pg_temp.val(ua, format($$insert into public.subjects(tenant_id, external_ref) values (%L,'usage') returning id$$, ta))::uuid;
  s3 := pg_temp.val(ua, format($$insert into public.subjects(tenant_id, external_ref) values (%L,'below') returning id$$, ta))::uuid;
  s4 := pg_temp.val(ua, format($$insert into public.subjects(tenant_id, external_ref) values (%L,'gaps') returning id$$, ta))::uuid;
  s5 := pg_temp.val(ua, format($$insert into public.subjects(tenant_id, external_ref) values (%L,'latency') returning id$$, ta))::uuid;
  s6 := pg_temp.val(ua, format($$insert into public.subjects(tenant_id, external_ref) values (%L,'edges') returning id$$, ta))::uuid;
  s7 := pg_temp.val(ua, format($$insert into public.subjects(tenant_id, external_ref) values (%L,'corr') returning id$$, ta))::uuid;
  s8 := pg_temp.val(ua, format($$insert into public.subjects(tenant_id, external_ref) values (%L,'multi') returning id$$, ta))::uuid;

  pa := pg_temp.val(uop, format($$select public.create_value_profile_draft(%L,'Synthetic C02 promise')$$, ta))::uuid;
  PERFORM pg_temp.val(uop, format('insert into public.profile_indicators(%s) values (%L,%L,%s) returning id', cols, ta, pa,
    $$'paid_pct','Pagas no prazo','outcome','%','higher_is_better','fixed_value',80,28,7,7,100,30,80,'absolute','lt',56,2,'absolute','gte',72,2,'mean',7,'paired_indicator','eligible_invoices'$$));
  -- c02-v2: a paired denominator needs its own explicit cadence and coverage (weekly, 100% here).
  PERFORM pg_temp.val(uop, format('insert into public.profile_indicators(tenant_id,profile_id,key,name,classification,unit,direction,expected_cadence_days,min_coverage_pct) values (%L,%L,%s) returning id', ta, pa,
    $$'eligible_invoices','Faturas elegíveis','context','faturas','higher_is_better',7,100$$));
  PERFORM pg_temp.val(uop, format('insert into public.profile_indicators(%s) values (%L,%L,%s) returning id', cols, ta, pa,
    $$'logins','Sessões','usage','sessões','higher_is_better','trailing_window',null,28,7,28,100,1,null,'relative_pct','lte',-30,2,null,null,null,null,'mean',7,'observation_count',null$$));
  PERFORM pg_temp.val(uop, format('insert into public.profile_indicators(%s) values (%L,%L,%s) returning id', cols, ta, pa,
    $$'latency','Latência','outcome','ms','lower_is_better','fixed_value',200,28,7,7,100,1,null,'absolute','gt',300,2,'absolute','lte',250,2,'mean',7,'observation_count',null$$));
  PERFORM pg_temp.val(uop, format('insert into public.profile_indicators(%s) values (%L,%L,%s) returning id', cols, ta, pa,
    $$'churn','Churn','outcome','%','lower_is_better','fixed_value',5,28,7,7,100,1,null,'absolute','gt',10,2,'absolute','lte',6,2,null,7,'observation_count',null$$));
  PERFORM pg_temp.val(uop, format('insert into public.profile_indicators(%s) values (%L,%L,%s) returning id', cols, ta, pa,
    $$'errors','Erros','usage','erros','lower_is_better','trailing_window',null,28,7,28,100,1,null,'relative_pct','gte',50,2,null,null,null,null,'mean',7,'observation_count',null$$));
  PERFORM pg_temp.val(ua, format($$select (public.approve_value_profile(%L)).id::text$$, pa));

  tb := pg_temp.val(ub, $$select public.create_tenant('C02 B','person')$$)::uuid;
  sb := pg_temp.val(ub, format($$insert into public.subjects(tenant_id, external_ref) values (%L,'b-1') returning id$$, tb))::uuid;

  -- ---------- synthetic history (through the real C01 RPC) ----------
  res := pg_temp.imp(uop, ta, pa,
       pg_temp.series('drop','paid_pct','%',    ARRAY[null,null,null,80,52,48])
    || pg_temp.series('drop','eligible_invoices','faturas', ARRAY[null,null,null,100,100,100])
    || pg_temp.series('drop','logins','sessões', ARRAY[100,100,100,100,100,100])
    || pg_temp.series('drop','latency','ms',    ARRAY[null,null,null,180,190,185])
    || pg_temp.series('drop','errors','erros',  ARRAY[0,0,0,0,3,4])
    || pg_temp.series('usage','paid_pct','%',   ARRAY[null,null,null,80,80,80])
    || pg_temp.series('usage','eligible_invoices','faturas', ARRAY[null,null,null,100,100,100])
    || pg_temp.series('usage','logins','sessões', ARRAY[100,100,100,100,50,40])
    || pg_temp.series('below','paid_pct','%',   ARRAY[null,null,null,50,50,50])
    || pg_temp.series('below','eligible_invoices','faturas', ARRAY[null,null,null,100,100,100])
    || pg_temp.series('gaps','paid_pct','%',    ARRAY[null,null,null,80,null,48])
    || pg_temp.series('gaps','eligible_invoices','faturas', ARRAY[null,null,null,100,null,10])
    || pg_temp.series('latency','latency','ms', ARRAY[null,null,null,200,350,400])
    || pg_temp.series('corr','paid_pct','%',    ARRAY[null,null,null,80,52,48])
    || pg_temp.series('corr','eligible_invoices','faturas', ARRAY[null,null,null,100,100,100])
    || pg_temp.series('multi','paid_pct','%',   ARRAY[null,null,null,80,52,48])
    || pg_temp.series('multi','eligible_invoices','faturas', ARRAY[null,null,null,100,100,100])
    || jsonb_build_array(  -- UTC boundaries: window starts are inclusive, as_of itself is excluded
         pg_temp.row('edges','paid_pct','80','%','2026-08-11T00:00:00Z'), pg_temp.row('edges','eligible_invoices','100','faturas','2026-08-11T00:00:00Z'),
         pg_temp.row('edges','paid_pct','52','%','2026-08-18T00:00:00Z'), pg_temp.row('edges','eligible_invoices','100','faturas','2026-08-18T00:00:00Z'),
         pg_temp.row('edges','paid_pct','48','%','2026-08-25T00:00:00Z'), pg_temp.row('edges','eligible_invoices','100','faturas','2026-08-25T00:00:00Z'),
         pg_temp.row('edges','paid_pct','10','%','2026-09-01T00:00:00Z'), pg_temp.row('edges','eligible_invoices','100','faturas','2026-09-01T00:00:00Z')));
  r := r || pg_temp.check('C00 synthetic history imported', res->>'status', 'completed');
  res := pg_temp.imp(uop, ta, pa, jsonb_build_array(pg_temp.row('multi','paid_pct','47','%','2026-08-27T10:00:00Z')), 'other-source');
  r := r || pg_temp.check('C00b second source imported', res->>'status', 'completed');

  -- ---------- permissions ----------
  r := r || pg_temp.expect_err('C01 anon cannot run analysis', NULL, format($$select public.run_deterioration_analysis(%L,%L,%L,%L)$$, ta, s1, pa, asof), '42501');
  r := r || pg_temp.expect_err('C02 viewer cannot run analysis', uv, format($$select public.run_deterioration_analysis(%L,%L,%L,%L)$$, ta, s1, pa, asof), '42501', 'not authorized');
  r := r || pg_temp.expect_err('C03 tenant B admin cannot run on tenant A', ub, format($$select public.run_deterioration_analysis(%L,%L,%L,%L)$$, ta, s1, pa, asof), '42501', 'not authorized');
  r := r || pg_temp.expect_err('C04 tenant B cannot use A ids through its own tenant', ub, format($$select public.run_deterioration_analysis(%L,%L,%L,%L)$$, tb, s1, pa, asof), '22023', 'analysis: no approved value profile');
  r := r || pg_temp.expect_err('C05 stale profile id refused', uop, format($$select public.run_deterioration_analysis(%L,%L,%L,%L)$$, ta, s1, gen_random_uuid(), asof), '22023', 'analysis: approved value profile changed');
  r := r || pg_temp.expect_err('C06 future as_of refused', uop, format($$select public.run_deterioration_analysis(%L,%L,%L,%L)$$, ta, s1, pa, '2999-01-01T00:00:00Z'), '22023', 'analysis: as_of in the future');

  -- ---------- semantics ----------
  run1 := pg_temp.run(uop, ta, s1, pa, asof);
  r := r || pg_temp.check('C10 outcome drop 80 -> 52,48 (rule <56 x2, reference 80) = candidate, gap vs target', pg_temp.st(ua, run1, 'paid_pct'), 'deterioration_candidate/below=true');
  r := r || pg_temp.check('C11 current_1 value / denominator / coverage computed server-side',
    pg_temp.val(ua, format($$select trim_scale((details->'windows'->0->>'value')::numeric)::text||'|'||(details->'windows'->0->>'denominator')||'|'||(details->'windows'->0->>'coverage_pct') from public.c02_results where run_id=%L and indicator_key='paid_pct'$$, run1->>'run_id')),
    '48|100|100.00');
  r := r || pg_temp.check('C12 evidence refs = the 3 values + 3 denominators used, all of tenant A',
    pg_temp.val(ua, format($$select cardinality(observation_ids)||'/'||(select count(*) from public.observations o where o.id = any(observation_ids) and o.tenant_id=%L) from public.c02_results where run_id=%L and indicator_key='paid_pct'$$, ta, run1->>'run_id')), '6/6');
  r := r || pg_temp.check('C13 stable usage = no deterioration', pg_temp.st(ua, run1, 'logins'), 'no_deterioration');
  r := r || pg_temp.check('C14 lower-is-better stable latency = no deterioration', pg_temp.st(ua, run1, 'latency'), 'no_deterioration');
  r := r || pg_temp.check('C15 trailing baseline of zeros + relative rule = insufficient (baseline_zero)', pg_temp.st(ua, run1, 'errors')||' '||pg_temp.rs(ua, run1, 'errors'), 'insufficient_data baseline_zero');
  r := r || pg_temp.check('C16 approved outcome without aggregation = insufficient_config', pg_temp.st(ua, run1, 'churn')||' '||pg_temp.rs(ua, run1, 'churn'), 'insufficient_config aggregation_missing');
  r := r || pg_temp.check('C17 context indicator not evaluated', pg_temp.st(ua, run1, 'eligible_invoices'), 'not_evaluated');
  r := r || pg_temp.check('C18 run summary: 1 outcome candidate, never an actionable case',
    pg_temp.val(ua, format($$select (summary->>'outcome_candidates')||'/'||(summary->>'actionable_case') from public.c02_runs where id=%L$$, run1->>'run_id')), '1/false');

  res := pg_temp.run(uop, ta, s2, pa, asof);
  r := r || pg_temp.check('C20 only usage drops: usage candidate, outcome stable', pg_temp.st(ua, res, 'logins')||' '||pg_temp.st(ua, res, 'paid_pct'), 'deterioration_candidate no_deterioration/below=false');
  r := r || pg_temp.check('C21 usage-only run has 0 outcome candidates',
    pg_temp.val(ua, format($$select (summary->>'outcome_candidates')||'/'||(summary->>'usage_candidates') from public.c02_runs where id=%L$$, res->>'run_id')), '0/1');

  res := pg_temp.run(uop, ta, s3, pa, asof);
  r := r || pg_temp.check('C22 stable below target = persistent condition (gap), not new deterioration', pg_temp.st(ua, res, 'paid_pct'), 'persistent_condition/below=true');

  res := pg_temp.run(uop, ta, s4, pa, asof);
  r := r || pg_temp.check('C23 missing week is absence (insufficient), small denominator flagged', pg_temp.st(ua, res, 'paid_pct')||' '||pg_temp.rs(ua, res, 'paid_pct'),
    'insufficient_data current_1:denominator_below_minimum,current_2:no_observations,current_2:coverage_below_minimum,current_2:denominator_missing,current_2:denominator_below_minimum');
  r := r || pg_temp.check('C24 subject with no data at all = insufficient, not zero', pg_temp.st(ua, res, 'latency')||' '||split_part(pg_temp.rs(ua, res, 'latency'), ',', 1), 'insufficient_data current_1:no_observations');

  res := pg_temp.run(uop, ta, s5, pa, asof);
  r := r || pg_temp.check('C25 lower-is-better rise 200 -> 350,400 (rule >300) = candidate', pg_temp.st(ua, res, 'latency'), 'deterioration_candidate');

  res := pg_temp.run(uop, ta, s6, pa, asof);
  r := r || pg_temp.check('C26 UTC boundaries [start,end): 08-25T00 in current_1, 09-01T00 excluded',
    pg_temp.st(ua, res, 'paid_pct')||' '||pg_temp.val(ua, format($$select trim_scale((details->'windows'->0->>'value')::numeric)::text||'/'||(details->'windows'->0->>'n')||'/'||trim_scale((details->'windows'->1->>'value')::numeric)::text from public.c02_results where run_id=%L and indicator_key='paid_pct'$$, res->>'run_id')),
    'deterioration_candidate/below=true 48/1/52');

  res := pg_temp.run(uop, ta, s8, pa, asof);
  r := r || pg_temp.check('C27 two sources in one window are not merged', pg_temp.rs(ua, res, 'paid_pct'), 'current_1:multiple_sources');

  -- ---------- idempotency and revisions ----------
  run2 := pg_temp.run(uop, ta, s1, pa, asof);
  r := r || pg_temp.check('C30 rerun with same inputs reuses run, no duplicate', (run2->>'reused')||' '||((run2->>'run_id') = (run1->>'run_id'))::text||' '||
    pg_temp.val(ua, format($$select count(*)::text from public.c02_runs where subject_id=%L$$, s1)), 'true true 1');

  -- ---------- corrections (C01 hardening + C02 effective values) ----------
  SELECT id INTO o26 FROM public.observations WHERE subject_id = s7 AND indicator_key = 'paid_pct' AND observed_at = '2026-08-26T10:00:00Z';
  SELECT id INTO o19 FROM public.observations WHERE subject_id = s7 AND indicator_key = 'paid_pct' AND observed_at = '2026-08-19T10:00:00Z';
  res := pg_temp.imp(uop, ta, pa, jsonb_build_array(pg_temp.row('corr','paid_pct','70','%','2026-08-27T10:00:00Z', o26::text)));
  r := r || pg_temp.check('C40 correction with different observed_at refused', pg_temp.codes(res), 'correction_incompatible');
  res := pg_temp.imp(uop, ta, pa, jsonb_build_array(pg_temp.row('corr','paid_pct','70','%','2026-08-26T10:00:00Z', o26::text)), 'other-source');
  r := r || pg_temp.check('C41 correction from another source refused', pg_temp.codes(res), 'correction_incompatible');
  res := pg_temp.imp(uop, ta, pa, jsonb_build_array(pg_temp.row('corr','paid_pct','70','%','2026-08-26T10:00:00Z', o26::text),
                                                    pg_temp.row('corr','paid_pct','71','%','2026-08-26T10:00:00Z', o26::text)));
  r := r || pg_temp.check('C42 two corrections of one target in a batch refused', pg_temp.codes(res), 'correction_already_corrected');
  res := pg_temp.imp(uop, ta, pa, jsonb_build_array(pg_temp.row('corr','paid_pct','70','%','2026-08-26T10:00:00Z', o26::text)));
  r := r || pg_temp.check('C43 compatible correction accepted', res->>'status', 'completed');
  res := pg_temp.imp(uop, ta, pa, jsonb_build_array(pg_temp.row('corr','paid_pct','72','%','2026-08-26T10:00:00Z', o26::text, 'b')));
  r := r || pg_temp.check('C44 second correction of the same target refused (no forks)', pg_temp.codes(res), 'correction_already_corrected');
  res := pg_temp.run(uop, ta, s7, pa, asof);
  r := r || pg_temp.check('C45 correction replaces value without double count (70, n=1) -> no deterioration',
    pg_temp.st(ua, res, 'paid_pct')||' '||pg_temp.val(ua, format($$select trim_scale((details->'windows'->0->>'value')::numeric)::text||'/'||(details->'windows'->0->>'n') from public.c02_results where run_id=%L and indicator_key='paid_pct'$$, res->>'run_id')),
    'no_deterioration/below=true 70/1');

  -- new late data for s1 -> traceable revision, previous run untouched
  res := pg_temp.imp(uop, ta, pa, jsonb_build_array(pg_temp.row('drop','logins','90','sessões','2026-08-27T10:00:00Z')));
  run2 := pg_temp.run(uop, ta, s1, pa, asof);
  r := r || pg_temp.check('C31 new data -> new run with revision_of = previous', (run2->>'reused')||' '||((run2->>'revision_of') = (run1->>'run_id'))::text, 'false true');
  r := r || pg_temp.check('C32 previous run results still present', pg_temp.val(ua, format($$select count(*)::text from public.c02_results where run_id=%L$$, run1->>'run_id')), '6');

  -- ---------- immutability / forgery ----------
  r := r || pg_temp.expect_err('C50 client cannot insert a run', ua, format($$insert into public.c02_runs(tenant_id,subject_id,profile_id,profile_version,algorithm_version,as_of,data_cutoff,input_hash,observation_count,summary) values (%L,%L,%L,1,'x',now(),now(),'h',0,'{}')$$, ta, s1, pa), '42501');
  r := r || pg_temp.expect_err('C51 client cannot insert a result', ua, format($$insert into public.c02_results(tenant_id,run_id,subject_id,indicator_key,classification,status,details) values (%L,%L,%L,'k','outcome','deterioration_candidate','{}')$$, ta, run1->>'run_id', s1), '42501');
  r := r || pg_temp.expect_err('C52 client cannot update a result', ua, format($$update public.c02_results set status='no_deterioration' where run_id=%L$$, run1->>'run_id'), '42501');
  r := r || pg_temp.expect_err('C53 anon cannot read runs', NULL, 'select count(*) from public.c02_runs', '42501');
  BEGIN
    UPDATE public.c02_runs SET summary = '{}' WHERE id = (run1->>'run_id')::uuid;
    r := r || E'\nFAIL C54 owner update of run not blocked';
  EXCEPTION WHEN SQLSTATE '42501' THEN r := r || E'\nPASS C54 owner update of run blocked by trigger [42501]'; END;
  r := r || pg_temp.check('C55 viewer reads results; tenant B reads none',
    pg_temp.val(uv, format($$select count(*)::text from public.c02_runs where tenant_id=%L$$, ta))||'/'||pg_temp.val(ub, format($$select (select count(*) from public.c02_runs where tenant_id=%1$L)+(select count(*) from public.c02_results where tenant_id=%1$L) from (select 1) z$$, ta)),
    '9/0');
  r := r || pg_temp.check('C56 run audited with real actor', pg_temp.val(ua, format($$select count(*)::text from public.audit_log where entity_type='c02_runs' and entity_id=%L and actor_id=%L$$, run1->>'run_id', uop)), '1');

  -- ---------- version mismatch ----------
  pa2 := pg_temp.val(uop, format($$select public.create_value_profile_version(%L)$$, pa))::uuid;
  r := r || pg_temp.check('C60 new C02 fields copied to new version', pg_temp.val(ua, format($$select aggregation||'/'||expected_cadence_days||'/'||denominator_mode||'/'||denominator_indicator_key from public.profile_indicators where profile_id=%L and key='paid_pct'$$, pa2)), 'mean/7/paired_indicator/eligible_invoices');
  PERFORM pg_temp.val(uop, format($$update public.profile_indicators set definition='Changed meaning' where profile_id=%L and key='paid_pct' returning id$$, pa2));
  PERFORM pg_temp.val(ua, format($$select (public.approve_value_profile(%L)).id::text$$, pa2));
  res := pg_temp.imp(uop, ta, pa2, jsonb_build_array(pg_temp.row('corr','paid_pct','60','%','2026-08-19T10:00:00Z', o19::text)));
  r := r || pg_temp.check('C61 correction across incompatible versions refused', pg_temp.codes(res), 'correction_version_mismatch');
  res := pg_temp.run(uop, ta, s1, pa2, asof);
  r := r || pg_temp.check('C62 v1 observations of a changed indicator are not mixed into v2',
    pg_temp.st(ua, res, 'paid_pct')||' '||pg_temp.val(ua, format($$select details->'windows'->0->'excluded'->>'version_mismatch' from public.c02_results where run_id=%L and indicator_key='paid_pct'$$, res->>'run_id')),
    'insufficient_data 1');
  r := r || pg_temp.check('C63 unchanged indicator stays comparable across versions', pg_temp.st(ua, res, 'logins'), 'no_deterioration');
  pa := pg_temp.val(uop, format($$select public.create_value_profile_version(%L)$$, pa2))::uuid;
  PERFORM pg_temp.val(uop, format($$update public.profile_indicators set deterioration_operator='lt' where profile_id=%L and key='latency' returning id$$, pa));
  r := r || pg_temp.check('C64 approval issues flag operator contradicting direction (lower_is_better with <)',
    pg_temp.val(uop, format($$select array_to_string(public.value_profile_approval_issues(%L), ';')$$, pa)), 'latency: deterioration operator contradicts direction');
  r := r || pg_temp.expect_err('C65 approval refused while contradiction remains', ua, format($$select public.approve_value_profile(%L)$$, pa), '22023');

  -- ================= c02-v2: source comparability, paired denominator contract, cut-off/correction proof =================
  r := r || pg_temp.check('V00 new runs are stamped c02-v2', pg_temp.val(ua, format($$select algorithm_version||'/'||(select details->>'algorithm' from public.c02_results where run_id=%1$L limit 1) from public.c02_runs where id=%1$L$$, run1->>'run_id')), 'c02-v2/c02-v2');
  s9  := pg_temp.val(ua, format($$insert into public.subjects(tenant_id, external_ref) values (%L,'srcx') returning id$$, ta))::uuid;
  s10 := pg_temp.val(ua, format($$insert into public.subjects(tenant_id, external_ref) values (%L,'okv2') returning id$$, ta))::uuid;
  s11 := pg_temp.val(ua, format($$insert into public.subjects(tenant_id, external_ref) values (%L,'densrc') returning id$$, ta))::uuid;
  s12 := pg_temp.val(ua, format($$insert into public.subjects(tenant_id, external_ref) values (%L,'dencfg') returning id$$, ta))::uuid;
  s13 := pg_temp.val(ua, format($$insert into public.subjects(tenant_id, external_ref) values (%L,'denlow') returning id$$, ta))::uuid;
  s14 := pg_temp.val(ua, format($$insert into public.subjects(tenant_id, external_ref) values (%L,'dendaily') returning id$$, ta))::uuid;
  s15 := pg_temp.val(ua, format($$insert into public.subjects(tenant_id, external_ref) values (%L,'cutoff') returning id$$, ta))::uuid;

  -- each window has ONE source (individually valid), but reference = src-a and current windows = src-b
  res := pg_temp.imp(uop, ta, pa2, pg_temp.series('srcx','paid_pct','%', ARRAY[null,null,null,80,null,null])
                                || pg_temp.series('srcx','eligible_invoices','faturas', ARRAY[null,null,null,100,null,null]), 'src-a');
  res := pg_temp.imp(uop, ta, pa2, pg_temp.series('srcx','paid_pct','%', ARRAY[null,null,null,null,52,48])
                                || pg_temp.series('srcx','eligible_invoices','faturas', ARRAY[null,null,null,null,100,100]), 'src-b');
  res := pg_temp.run(uop, ta, s9, pa2, asof);
  r := r || pg_temp.check('V01 different sources between windows (each valid alone) = insufficient, never candidate',
    pg_temp.st(ua, res, 'paid_pct')||' '||pg_temp.rs(ua, res, 'paid_pct'), 'insufficient_data source_mismatch_across_windows,denominator_source_mismatch_across_windows');

  res := pg_temp.imp(uop, ta, pa2, pg_temp.series('okv2','paid_pct','%', ARRAY[null,null,null,80,52,48])
                                || pg_temp.series('okv2','eligible_invoices','faturas', ARRAY[null,null,null,100,100,100]), 'src-a');
  -- synthetic historical c02-v1 run (fixture) for the same subject: must never be reused, recomputed or rewritten
  INSERT INTO public.c02_runs(tenant_id, subject_id, profile_id, profile_version, algorithm_version, as_of, data_cutoff, input_hash, observation_count, summary)
  VALUES (ta, s10, pa2, (SELECT version FROM public.tenant_value_profiles WHERE id = pa2), 'c02-v1', asof::timestamptz, now(), 'fixture-v1-hash', 6, '{"fixture":"c02-v1"}')
  RETURNING id INTO v1run;
  SELECT md5(x::text) INTO v1md5 FROM public.c02_runs x WHERE x.id = v1run;
  res := pg_temp.run(uop, ta, s10, pa2, asof);
  r := r || pg_temp.check('V02 same source everywhere = candidate (positive control)', pg_temp.st(ua, res, 'paid_pct'), 'deterioration_candidate/below=true');
  r := r || pg_temp.check('V03 window records numerator/denominator source and denominator coverage',
    pg_temp.val(ua, format($$select (details->'windows'->0->>'source')||'|'||(details->'windows'->0->>'denominator_source')||'|'||(details->'windows'->0->>'denominator_coverage_pct')||'|'||(details->'denominator_parameters'->>'key') from public.c02_results where run_id=%L and indicator_key='paid_pct'$$, res->>'run_id')),
    'src-a|src-a|100.00|eligible_invoices');
  r := r || pg_temp.check('V04 v2 run is a traceable revision of the v1 run, not a reuse',
    (res->>'reused')||' '||((res->>'revision_of') = v1run::text)::text, 'false true');
  r := r || pg_temp.check('V05 v1 run byte-identical after v2', ((SELECT md5(x::text) FROM public.c02_runs x WHERE x.id = v1run) = v1md5)::text, 'true');
  run2 := pg_temp.run(uop, ta, s10, pa2, asof);
  r := r || pg_temp.check('V06 replay with same inputs reuses the v2 run', (run2->>'reused')||' '||((run2->>'run_id') = (res->>'run_id'))::text, 'true true');
  run2 := pg_temp.run(uop, ta, s10, pa2, '2026-08-31T00:00:00Z');
  r := r || pg_temp.check('V07 different as_of = new run (no revision link)', (run2->>'reused')||'/'||coalesce(run2->>'revision_of', 'null'), 'false/null');

  res := pg_temp.imp(uop, ta, pa2, pg_temp.series('densrc','paid_pct','%', ARRAY[null,null,null,80,52,48]), 'src-a');
  res := pg_temp.imp(uop, ta, pa2, pg_temp.series('densrc','eligible_invoices','faturas', ARRAY[null,null,null,100,100,100]), 'src-b');
  res := pg_temp.run(uop, ta, s11, pa2, asof);
  r := r || pg_temp.check('V08 denominator from another source than numerator = insufficient per window',
    pg_temp.st(ua, res, 'paid_pct')||' '||pg_temp.rs(ua, res, 'paid_pct'),
    'insufficient_data current_1:denominator_source_mismatch,current_2:denominator_source_mismatch,reference:denominator_source_mismatch');

  -- cut-off + correction chain
  res := pg_temp.imp(uop, ta, pa2, pg_temp.series('cutoff','paid_pct','%', ARRAY[null,null,null,80,52,48])
                                || pg_temp.series('cutoff','eligible_invoices','faturas', ARRAY[null,null,null,100,100,100]));
  runA := pg_temp.run(uop, ta, s15, pa2, asof);
  SELECT md5(string_agg(x::text, '|' ORDER BY x.indicator_key)) INTO mdA FROM public.c02_results x WHERE x.run_id = (runA->>'run_id')::uuid;
  r := r || pg_temp.check('V10 before correction: candidate', pg_temp.st(ua, runA, 'paid_pct'), 'deterioration_candidate/below=true');
  SELECT id INTO oc FROM public.observations WHERE subject_id = s15 AND indicator_key = 'paid_pct' AND observed_at = '2026-08-26T10:00:00Z';
  res := pg_temp.imp(uop, ta, pa2, jsonb_build_array(pg_temp.row('cutoff','paid_pct','70','%','2026-08-26T10:00:00Z', oc::text)));
  runB := pg_temp.run(uop, ta, s15, pa2, asof);
  r := r || pg_temp.check('V11 late correction (same as_of) -> new run, revision_of = previous', (runB->>'reused')||' '||((runB->>'revision_of') = (runA->>'run_id'))::text, 'false true');
  r := r || pg_temp.check('V12 revision uses corrected value, no double count',
    pg_temp.st(ua, runB, 'paid_pct')||' '||pg_temp.val(ua, format($$select trim_scale((details->'windows'->0->>'value')::numeric)::text||'/'||(details->'windows'->0->>'n') from public.c02_results where run_id=%L and indicator_key='paid_pct'$$, runB->>'run_id')),
    'no_deterioration/below=true 70/1');
  r := r || pg_temp.check('V13 revision stores correction-chain proof (used id supersedes original)',
    pg_temp.val(ua, format($$select details->'windows'->0->'corrections'->0->'supersedes'->>0 from public.c02_results where run_id=%L and indicator_key='paid_pct'$$, runB->>'run_id')), oc::text);
  r := r || pg_temp.check('V14 earlier run unchanged and has no correction in its snapshot',
    ((SELECT md5(string_agg(x::text, '|' ORDER BY x.indicator_key)) FROM public.c02_results x WHERE x.run_id = (runA->>'run_id')::uuid) = mdA)::text||' '||
    pg_temp.val(ua, format($$select details->'windows'->0->>'corrections' from public.c02_results where run_id=%L and indicator_key='paid_pct'$$, runA->>'run_id')),
    'true []');
  -- Chain resolution honours the cut-off. All rows of one transaction share now(), so the ORIGINAL rows of this fixture subject
  -- are back-dated by one day (session-local replica mode, fixture rows only, rolled back with everything else).
  BEGIN
    PERFORM set_config('session_replication_role', 'replica', true);
    UPDATE public.observations SET ingested_at = ingested_at - interval '1 day' WHERE subject_id = s15 AND corrects_observation_id IS NULL;
    PERFORM set_config('session_replication_role', 'origin', true);
    SELECT ARRAY(SELECT jsonb_array_elements_text(details->'compatible_profile_ids')::uuid) INTO compat FROM public.c02_results WHERE run_id = (runB->>'run_id')::uuid AND indicator_key = 'paid_pct';
    r := r || pg_temp.check('V15 chain resolution with cut-off before / after the correction',
      (SELECT trim_scale(e.value)::text||'/'||e.supersedes::text FROM public._c02v2_effective(ta, s15, 'paid_pct', '%', compat, now() - interval '1 hour') e WHERE e.observed_at = '2026-08-26T10:00:00Z')
      ||'|'||(SELECT trim_scale(e.value)::text||'/'||e.supersedes::text FROM public._c02v2_effective(ta, s15, 'paid_pct', '%', compat, now()) e WHERE e.observed_at = '2026-08-26T10:00:00Z'),
      '48/{}|70/{'||oc::text||'}');
  EXCEPTION WHEN insufficient_privilege THEN
    r := r || E'\nNOT_RUN V15 cut-off back-dating not permitted for this runner: ' || SQLERRM;
  END;

  -- paired denominator contract across profile versions (draft pa = copy of pa2 with a contradiction)
  PERFORM pg_temp.val(uop, format($$update public.profile_indicators set deterioration_operator='gt' where profile_id=%L and key='latency' returning id$$, pa));
  PERFORM pg_temp.val(uop, format($$update public.profile_indicators set expected_cadence_days=1, min_coverage_pct=null where profile_id=%L and key='eligible_invoices' returning id$$, pa));
  PERFORM pg_temp.val(ua, format($$select (public.approve_value_profile(%L)).id::text$$, pa));
  res := pg_temp.run(uop, ta, s12, pa, asof);
  r := r || pg_temp.check('V20 denominator without its own coverage = insufficient_config (nothing copied from numerator)',
    pg_temp.st(ua, res, 'paid_pct')||' '||pg_temp.rs(ua, res, 'paid_pct'), 'insufficient_config denominator_min_coverage_missing');
  p4 := pg_temp.val(uop, format($$select public.create_value_profile_version(%L)$$, pa))::uuid;
  PERFORM pg_temp.val(uop, format($$update public.profile_indicators set min_coverage_pct=50 where profile_id=%L and key='eligible_invoices' returning id$$, p4));
  PERFORM pg_temp.val(ua, format($$select (public.approve_value_profile(%L)).id::text$$, p4));
  res := pg_temp.imp(uop, ta, p4, pg_temp.series('denlow','paid_pct','%', ARRAY[null,null,null,80,52,48])
                               || pg_temp.series('denlow','eligible_invoices','faturas', ARRAY[null,null,null,100,100,100]));
  res := pg_temp.run(uop, ta, s13, p4, asof);
  r := r || pg_temp.check('V21 denominator sum >= minimum but own coverage 1/7 < 50% = insufficient',
    pg_temp.rs(ua, res, 'paid_pct')||' '||pg_temp.val(ua, format($$select (details->'windows'->0->>'denominator')||'/'||(details->'windows'->0->>'denominator_coverage_pct') from public.c02_results where run_id=%L and indicator_key='paid_pct'$$, res->>'run_id')),
    'current_1:denominator_coverage_below_minimum,current_2:denominator_coverage_below_minimum,reference:denominator_coverage_below_minimum 100/14.29');
  res := pg_temp.imp(uop, ta, p4, pg_temp.series('dendaily','paid_pct','%', ARRAY[null,null,null,80,52,48])
    || (SELECT jsonb_agg(pg_temp.row('dendaily','eligible_invoices','20','faturas', to_char(d, 'YYYY-MM-DD"T"10:00:00"Z"')))
          FROM generate_series('2026-08-11'::date, '2026-08-31'::date, interval '1 day') d));
  res := pg_temp.run(uop, ta, s14, p4, asof);
  r := r || pg_temp.check('V22 daily denominator with full own coverage = candidate (positive control)',
    pg_temp.st(ua, res, 'paid_pct')||' '||pg_temp.val(ua, format($$select (details->'windows'->0->>'denominator')||'/'||(details->'windows'->0->>'denominator_coverage_pct') from public.c02_results where run_id=%L and indicator_key='paid_pct'$$, res->>'run_id')),
    'deterioration_candidate/below=true 140/100.00');
  p5 := pg_temp.val(uop, format($$select public.create_value_profile_version(%L)$$, p4))::uuid;
  PERFORM pg_temp.val(uop, format($$update public.profile_indicators set definition='Changed denominator meaning' where profile_id=%L and key='eligible_invoices' returning id$$, p5));
  PERFORM pg_temp.val(ua, format($$select (public.approve_value_profile(%L)).id::text$$, p5));
  res := pg_temp.run(uop, ta, s14, p5, asof);
  r := r || pg_temp.check('V23 denominator observations of an incompatible version = explicit reason, not used',
    pg_temp.st(ua, res, 'paid_pct')||' '||(position('current_1:denominator_incompatible_observations' in pg_temp.rs(ua, res, 'paid_pct')) > 0)::text||' '||
    pg_temp.val(ua, format($$select details->'windows'->0->'denominator_excluded'->>'version_mismatch' from public.c02_results where run_id=%L and indicator_key='paid_pct'$$, res->>'run_id')),
    'insufficient_data true 7');

  r := r || pg_temp.expect_err('V30 authenticated cannot call v2 internals', ua, format($$select count(*) from public._c02v2_effective(%L,%L,'paid_pct','%%','{}'::uuid[],now())$$, ta, s1), '42501');
  r := r || pg_temp.expect_err('V31 anon cannot run analysis', NULL, format($$select public.run_deterioration_analysis(%L,%L,%L,%L)$$, ta, s14, p5, asof), '42501');
  r := r || pg_temp.expect_err('V32 viewer cannot run analysis (v2)', uv, format($$select public.run_deterioration_analysis(%L,%L,%L,%L)$$, ta, s14, p5, asof), '42501', 'not authorized');
  r := r || pg_temp.check('V33 tenant B reads no v2 results', pg_temp.val(ub, format($$select count(*)::text from public.c02_results where tenant_id=%L$$, ta)), '0');

  npass := (length(r) - length(replace(r, E'\nPASS', ''))) / 5;
  nfail := (length(r) - length(replace(r, E'\nFAIL', ''))) / 5;
  nnot := (length(r) - length(replace(r, E'\nNOT_RUN', ''))) / 8;
  RAISE EXCEPTION 'CW_C02_RESULTS pass=% fail=% not_run=% (transaction rolled back)%', npass, nfail, nnot, r;
END
$test$;
