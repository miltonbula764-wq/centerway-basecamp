-- CENTERWAY C03 Evidence Builder tests (re-runnable) for public.build_evidence_bundle (c03-v1).
-- Assertions run as real `anon` / `authenticated` roles with JWT claims. Elevated privileges are used ONLY to prepare fixtures
-- (back-dating ingestion, forging/corrupting C02 runs, injecting a deterministic fault) and to call the private budget helper.
-- The whole block is ALWAYS rolled back (it ends with RAISE EXCEPTION carrying the results).
-- Timeline (synthetic): as_of 2026-09-01, W=7d, N=2: current_1=[08-25,09-01) current_2=[08-18,08-25) reference=[08-11,08-18).
DO $test$
DECLARE
  ua uuid := gen_random_uuid(); uop uuid := gen_random_uuid(); uv uuid := gen_random_uuid(); ub uuid := gen_random_uuid();
  ta uuid; tb uuid; pa uuid; s1 uuid; o19 uuid; c19 uuid; o26 uuid; late uuid; run1 uuid; run2 uuid; fr uuid; cut timestamptz;
  b1 jsonb; b2 jsonb; res jsonb; r text := ''; npass int; nfail int; v text; h text; n int;
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
  CREATE FUNCTION pg_temp.row(_ref text, _key text, _num text, _unit text, _at text, _corr text DEFAULT '')
  RETURNS jsonb LANGUAGE sql AS $f$
    SELECT jsonb_build_object('subject_external_ref', _ref, 'indicator_key', _key, 'value_numeric', _num, 'value_text', '',
      'unit', _unit, 'observed_at', _at, 'idempotency_key', _ref||'|'||_key||'|'||_at||'|'||_num, 'corrects_observation_id', _corr) $f$;
  CREATE FUNCTION pg_temp.imp(_uid uuid, _t uuid, _p uuid, _rows jsonb) RETURNS jsonb LANGUAGE plpgsql AS $f$
  BEGIN
    RETURN pg_temp.val(_uid, format($$select public.import_observations(%L,%L,'fixture-c03','2026-07-01T00:00:00Z','2026-09-02T00:00:00Z',true,'c03.csv',%L::jsonb)::text$$,
      _t, _p, _rows))::jsonb;
  END $f$;
  CREATE FUNCTION pg_temp.build(_uid uuid, _t uuid, _run uuid) RETURNS jsonb LANGUAGE plpgsql AS $f$
  BEGIN RETURN pg_temp.val(_uid, format($$select public.build_evidence_bundle(%L,%L)::text$$, _t, _run))::jsonb; END $f$;
  -- forged C02 run (fixture, privileged): copy of run _src with a chosen hash/algorithm, results transformed by _expr on details
  CREATE FUNCTION pg_temp.forge(_src uuid, _hash text, _alg text, _key text, _details_sql text, _ids_sql text) RETURNS uuid LANGUAGE plpgsql AS $f$
  DECLARE nid uuid := gen_random_uuid();
  BEGIN
    INSERT INTO public.c02_runs(id, tenant_id, subject_id, profile_id, profile_version, algorithm_version, as_of, data_cutoff, input_hash, observation_count, summary)
    SELECT nid, tenant_id, subject_id, profile_id, profile_version, _alg, as_of, data_cutoff, _hash, observation_count, summary FROM public.c02_runs WHERE id = _src;
    EXECUTE format($$INSERT INTO public.c02_results(tenant_id, run_id, subject_id, indicator_key, classification, status, below_target, baseline_value, reasons, observation_ids, details)
      SELECT tenant_id, %L, subject_id, indicator_key, classification, status, below_target, baseline_value, reasons,
             CASE WHEN indicator_key = %L THEN %s ELSE observation_ids END, CASE WHEN indicator_key = %L THEN %s ELSE details END
        FROM public.c02_results WHERE run_id = %L$$, nid, _key, _ids_sql, _key, _details_sql, _src);
    RETURN nid;
  END $f$;
  CREATE FUNCTION pg_temp.nb(_run uuid) RETURNS text LANGUAGE sql AS $f$
    SELECT (SELECT count(*) FROM public.c03_bundles WHERE run_id = _run)::text || '/' ||
           (SELECT string_agg(status::text || coalesce(':' || code, ''), ',' ORDER BY created_at) FROM public.c03_attempts WHERE requested_run_id = _run) $f$;

  INSERT INTO auth.users(id, instance_id, aud, role, email) VALUES
   (ua,  '00000000-0000-0000-0000-000000000000','authenticated','authenticated','cw-c03-a@example.invalid'),
   (uop, '00000000-0000-0000-0000-000000000000','authenticated','authenticated','cw-c03-op@example.invalid'),
   (uv,  '00000000-0000-0000-0000-000000000000','authenticated','authenticated','cw-c03-v@example.invalid'),
   (ub,  '00000000-0000-0000-0000-000000000000','authenticated','authenticated','cw-c03-b@example.invalid');
  ta := pg_temp.val(ua, $$select public.create_tenant('C03 fixture A','organization')$$)::uuid;
  PERFORM pg_temp.val(ua, format($$select public.add_tenant_member(%L,%L,'operator')$$, ta, uop));
  PERFORM pg_temp.val(ua, format($$select public.add_tenant_member(%L,%L,'viewer')$$, ta, uv));
  tb := pg_temp.val(ub, $$select public.create_tenant('C03 fixture B','person')$$)::uuid;
  s1 := pg_temp.val(ua, format($$insert into public.subjects(tenant_id, external_ref) values (%L,'c03-s1') returning id$$, ta))::uuid;

  pa := pg_temp.val(uop, format($$select public.create_value_profile_draft(%L,'Synthetic C03 promise')$$, ta))::uuid;
  PERFORM pg_temp.val(uop, format('insert into public.profile_indicators(%s) values (%L,%L,%s) returning id', cols, ta, pa,
    $$'paid_pct','Pagas no prazo','outcome','%','higher_is_better','fixed_value',80,28,7,7,100,30,80,'absolute','lt',56,2,'absolute','gte',72,2,'mean',7,'paired_indicator','eligible_invoices'$$));
  PERFORM pg_temp.val(uop, format('insert into public.profile_indicators(tenant_id,profile_id,key,name,classification,unit,direction,expected_cadence_days,min_coverage_pct) values (%L,%L,%s) returning id', ta, pa,
    $$'eligible_invoices','Faturas elegíveis','context','faturas','higher_is_better',7,100$$));
  PERFORM pg_temp.val(uop, format('insert into public.profile_indicators(%s) values (%L,%L,%s) returning id', cols, ta, pa,
    $$'logins','Sessões','usage','sessões','higher_is_better','trailing_window',null,28,7,28,100,1,null,'relative_pct','lte',-30,2,null,null,null,null,'mean',7,'observation_count',null$$));
  PERFORM pg_temp.val(ua, format($$select (public.approve_value_profile(%L)).id::text$$, pa));

  res := pg_temp.imp(uop, ta, pa, jsonb_build_array(
    pg_temp.row('c03-s1','paid_pct','80','%','2026-08-12T10:00:00Z'), pg_temp.row('c03-s1','eligible_invoices','100','faturas','2026-08-12T10:00:00Z'),
    pg_temp.row('c03-s1','paid_pct','52','%','2026-08-19T10:00:00Z'), pg_temp.row('c03-s1','eligible_invoices','100','faturas','2026-08-19T10:00:00Z'),
    pg_temp.row('c03-s1','paid_pct','48','%','2026-08-26T10:00:00Z'), pg_temp.row('c03-s1','eligible_invoices','100','faturas','2026-08-26T10:00:00Z')));
  r := r || pg_temp.check('F00 fixture history imported', res->>'status', 'completed');
  SELECT id INTO o19 FROM public.observations WHERE subject_id = s1 AND indicator_key = 'paid_pct' AND observed_at = '2026-08-19T10:00:00Z';
  SELECT id INTO o26 FROM public.observations WHERE subject_id = s1 AND indicator_key = 'paid_pct' AND observed_at = '2026-08-26T10:00:00Z';
  res := pg_temp.imp(uop, ta, pa, jsonb_build_array(pg_temp.row('c03-s1','paid_pct','50','%','2026-08-19T10:00:00Z', o19::text)));
  SELECT id INTO c19 FROM public.observations WHERE corrects_observation_id = o19;
  -- fixture: back-date this subject's ingestion by 1 day (only append-only guard suspended; audit untouched)
  ALTER TABLE public.observations DISABLE TRIGGER observations_append_only;
  UPDATE public.observations SET ingested_at = ingested_at - interval '1 day' WHERE subject_id = s1;
  ALTER TABLE public.observations ENABLE TRIGGER observations_append_only;
  run1 := (pg_temp.val(uop, format($$select public.run_deterioration_analysis(%L,%L,%L,%L)::text$$, ta, s1, pa, asof))::jsonb ->> 'run_id')::uuid;
  -- fixture: move run1's cut-off 12h back so data imported now is "after the cut-off" (hash stays valid: inputs are 1 day old)
  ALTER TABLE public.c02_runs DISABLE TRIGGER c02_runs_immutable;
  UPDATE public.c02_runs SET data_cutoff = data_cutoff - interval '12 hours' WHERE id = run1 RETURNING data_cutoff INTO cut;
  ALTER TABLE public.c02_runs ENABLE TRIGGER c02_runs_immutable;
  r := r || pg_temp.check('F01 C02 run1 paid_pct candidate', (SELECT status::text FROM public.c02_results WHERE run_id = run1 AND indicator_key = 'paid_pct'), 'deterioration_candidate');
  -- late data (ingested after run1's cut-off): correction of 08-26 (48 -> 45)
  res := pg_temp.imp(uop, ta, pa, jsonb_build_array(pg_temp.row('c03-s1','paid_pct','45','%','2026-08-26T10:00:00Z', o26::text)));
  SELECT id INTO late FROM public.observations WHERE corrects_observation_id = o26;

  -- ---------- permissions ----------
  r := r || pg_temp.expect_err('P01 anon cannot build', NULL, format($$select public.build_evidence_bundle(%L,%L)$$, ta, run1), '42501');
  r := r || pg_temp.expect_err('P02 viewer cannot build', uv, format($$select public.build_evidence_bundle(%L,%L)$$, ta, run1), '42501', 'not authorized');
  r := r || pg_temp.expect_err('P03 member of B cannot build in A', ub, format($$select public.build_evidence_bundle(%L,%L)$$, ta, run1), '42501', 'not authorized');
  r := r || pg_temp.expect_err('P04 client cannot call private budget helper', ua, format($$select public._c03_build(%L,%L,3)$$, ta, run1), '42501');
  r := r || pg_temp.expect_err('P05 client cannot call assembler', ua, $$select public._c03_reject('x')$$, '42501');
  r := r || pg_temp.check('P06 B admin asking for A run in B = run_not_found (no enumeration)', pg_temp.build(ub, tb, run1)->>'code', 'run_not_found');
  r := r || pg_temp.check('P07 unknown run = same answer', pg_temp.build(uop, ta, gen_random_uuid())->>'code', 'run_not_found');

  -- ---------- deterministic fault: whole bundle undone, attempt persisted ----------
  CREATE FUNCTION public._c03_test_fault() RETURNS trigger LANGUAGE plpgsql AS $f$ BEGIN RAISE EXCEPTION 'injected fault'; END $f$;
  CREATE TRIGGER c03_test_fault BEFORE INSERT ON public.c03_refs FOR EACH ROW EXECUTE FUNCTION public._c03_test_fault();
  res := pg_temp.build(uop, ta, run1);
  DROP TRIGGER c03_test_fault ON public.c03_refs; DROP FUNCTION public._c03_test_fault();
  r := r || pg_temp.check('X01 injected fault -> failed with safe code', res::text, '{"code": "internal_error:P0001", "status": "failed"}');
  r := r || pg_temp.check('X02 no bundle/indicator rows left, attempt persisted',
    pg_temp.nb(run1) || ' ind=' || (SELECT count(*) FROM public.c03_indicators i WHERE i.tenant_id = ta), '0/failed:internal_error:P0001 ind=0');

  -- ---------- budget via private helper (privileged call, claims of the operator), undone by a sub-block ----------
  BEGIN
    PERFORM set_config('request.jwt.claims', json_build_object('sub', uop, 'role', 'authenticated')::text, true);
    res := public._c03_build(ta, run1, 3);
    SELECT status || ' ' || array_to_string(reasons, ',') || ' ' || ref_count || '/' || stored_ref_count INTO v
      FROM public.c03_indicators WHERE bundle_id = (res->>'bundle_id')::uuid AND indicator_key = 'paid_pct';
    n := (SELECT count(*) FROM public.c03_refs WHERE bundle_id = (res->>'bundle_id')::uuid);
    RAISE EXCEPTION 'undo budget fixture';
  EXCEPTION WHEN raise_exception THEN NULL;
  END;
  r := r || pg_temp.check('B01 budget 3 < 7 refs -> insufficient, counted, nothing stored', v || ' refs=' || n, 'insufficient ref_budget_exceeded 7/0 refs=0');

  -- ---------- positive bundle ----------
  b1 := pg_temp.build(uop, ta, run1);
  r := r || pg_temp.check('C01 built', b1->>'status', 'built');
  r := r || pg_temp.check('C02 per-indicator status', pg_temp.val(uv, format($$select string_agg(indicator_key||'='||status, ' ' order by indicator_key) from public.c03_indicators where bundle_id=%L$$, b1->>'bundle_id')),
    'eligible_invoices=context_facts logins=insufficient paid_pct=complete');
  r := r || pg_temp.check('C03 summary counts, never a case', (b1->'summary')::text,
    '{"complete": 1, "indicators": 3, "ref_budget": 5000, "stored_refs": 7, "insufficient": 1, "context_facts": 1, "actionable_case": false}');
  r := r || pg_temp.check('C04 inherited C02 insufficiency reason', pg_temp.val(uv, format($$select reasons[1] from public.c03_indicators where bundle_id=%L and indicator_key='logins'$$, b1->>'bundle_id')), 'c02_insufficient_data');
  r := r || pg_temp.check('C05 context explicitly not collected', pg_temp.val(uv, format($$select array_to_string(reasons,',') from public.c03_indicators where bundle_id=%L and indicator_key='eligible_invoices'$$, b1->>'bundle_id')),
    'context_indicator,no_temporal_evaluation,context_not_collected_by_c02');
  r := r || pg_temp.check('C06 refs by window/role/value', pg_temp.val(uv, format($$select string_agg(window_label||':'||role||'='||trim_scale(value_numeric), ' ' order by ordinal) from public.c03_refs where bundle_id=%L$$, b1->>'bundle_id')),
    'current_1:denominator=100 current_1:numerator=48 current_2:denominator=100 current_2:numerator=50 current_2:superseded=52 reference:denominator=100 reference:numerator=80');
  r := r || pg_temp.check('C07 correction chain: superseded original points to effective correction',
    pg_temp.val(uv, format($$select (observation_id=%L and superseded_by=%L)::text from public.c03_refs where bundle_id=%L and role='superseded'$$, o19, c19, b1->>'bundle_id')), 'true');
  r := r || pg_temp.check('C08 every ref copy equals the observation (value/unit/source/hash) and is within cut-off',
    (SELECT count(*)::text FROM public.c03_refs x JOIN public.observations o ON o.id = x.observation_id WHERE x.bundle_id = (b1->>'bundle_id')::uuid
      AND (o.value_numeric IS DISTINCT FROM x.value_numeric OR o.unit <> x.unit OR o.source <> x.source OR o.payload_hash <> x.payload_hash OR x.ingested_at > cut)), '0');
  r := r || pg_temp.check('C09 late correction (after cut-off) not in old bundle', (SELECT count(*)::text FROM public.c03_refs WHERE bundle_id = (b1->>'bundle_id')::uuid AND observation_id = late), '0');
  r := r || pg_temp.check('C10 viewer reads bundle, B reads none',
    pg_temp.val(uv, format($$select count(*)::text from public.c03_bundles where tenant_id=%L$$, ta)) || '/' || pg_temp.val(ub, format($$select count(*)::text from public.c03_refs where tenant_id=%L$$, ta)), '1/0');
  r := r || pg_temp.check('C11 snapshot keeps C02 parameters (traceable without current profile)',
    pg_temp.val(uv, format($$select snapshot->'details'->'parameters'->>'deterioration_value' from public.c03_indicators where bundle_id=%L and indicator_key='paid_pct'$$, b1->>'bundle_id')), '56');

  -- ---------- replay ----------
  n := (SELECT count(*) FROM public.c03_refs WHERE tenant_id = ta);
  res := pg_temp.build(ua, ta, run1);
  r := r || pg_temp.check('R01 replay reuses same bundle, no new refs', (res->>'status') || ' ' || ((res->>'bundle_id') = (b1->>'bundle_id'))::text || ' ' || ((SELECT count(*) FROM public.c03_refs WHERE tenant_id = ta) = n)::text, 'reused true true');
  r := r || pg_temp.check('R02 attempts persisted for run1', split_part(pg_temp.nb(run1), '/', 2), 'failed:internal_error:P0001,built,reused');

  -- ---------- new C02 revision with the late correction ----------
  run2 := (pg_temp.val(uop, format($$select public.run_deterioration_analysis(%L,%L,%L,%L)::text$$, ta, s1, pa, asof))::jsonb ->> 'run_id')::uuid;
  b2 := pg_temp.build(uop, ta, run2);
  r := r || pg_temp.check('V01 new run bundle linked to previous', (b2->>'status') || ' ' || ((SELECT revision_of FROM public.c03_bundles WHERE id = (b2->>'bundle_id')::uuid) = (b1->>'bundle_id')::uuid)::text, 'built true');
  r := r || pg_temp.check('V02 new bundle uses effective late correction', pg_temp.val(uv, format($$select trim_scale(value_numeric)::text||':'||(observation_id=%L)::text from public.c03_refs where bundle_id=%L and window_label='current_1' and role='numerator'$$, late, b2->>'bundle_id')), '45:true');
  r := r || pg_temp.check('V03 old bundle intact', pg_temp.val(uv, format($$select count(*)||':'||max(trim_scale(value_numeric)) filter (where window_label='current_1' and role='numerator') from public.c03_refs where bundle_id=%L$$, b1->>'bundle_id')), '7:48');

  -- ---------- forged / corrupted C02 runs (fixtures) -> rejected, no bundle, attempt persisted ----------
  fr := pg_temp.forge(run1, 'forged-1', 'c02-v2', 'paid_pct', format($$jsonb_set(details,'{windows,0,observation_ids}',jsonb_build_array(%L))$$, gen_random_uuid()), 'observation_ids');
  r := r || pg_temp.check('G01 forged/cross-tenant ref id -> ref_missing', pg_temp.build(uop, ta, fr)->>'code' || ' ' || pg_temp.nb(fr), 'ref_missing 0/rejected:ref_missing');
  fr := pg_temp.forge(run1, 'forged-2', 'c02-v2', 'paid_pct', format($$jsonb_set(details,'{windows,0,observation_ids}',jsonb_build_array(%L))$$, late), format('array[%L::uuid]', late));
  r := r || pg_temp.check('G02 ref ingested after cut-off -> rejected', pg_temp.build(uop, ta, fr)->>'code' || ' ' || pg_temp.nb(fr), 'ref_after_cutoff 0/rejected:ref_after_cutoff');
  fr := pg_temp.forge(run1, 'forged-3', 'c02-v2', 'paid_pct', $$jsonb_set(details,'{windows,0,value}','99')$$, 'observation_ids');
  r := r || pg_temp.check('G03 value incoherent with refs -> calculation_mismatch', pg_temp.build(uop, ta, fr)->>'code' || ' ' || pg_temp.nb(fr), 'calculation_mismatch 0/rejected:calculation_mismatch');
  fr := pg_temp.forge(run1, 'forged-4', 'c02-v2', 'paid_pct', $$jsonb_set(details,'{windows,0,denominator}','90')$$, 'observation_ids');
  r := r || pg_temp.check('G04 denominator incoherent -> calculation_mismatch', pg_temp.build(uop, ta, fr)->>'code', 'calculation_mismatch');
  fr := pg_temp.forge(run1, 'forged-5', 'c02-v2', 'paid_pct', 'details', 'observation_ids');
  r := r || pg_temp.check('G05 intact refs but wrong input hash -> c02_input_hash_mismatch', pg_temp.build(uop, ta, fr)->>'code' || ' ' || pg_temp.nb(fr), 'c02_input_hash_mismatch 0/rejected:c02_input_hash_mismatch');
  fr := pg_temp.forge(run1, 'forged-6', 'c02-v2', 'paid_pct', $$jsonb_set(details,'{windows,1,corrections,0,supersedes}',jsonb_build_array(%L))$$, 'observation_ids');
  fr := pg_temp.forge(run1, 'forged-6b', 'c02-v2', 'paid_pct', format($$jsonb_set(details,'{windows,1,corrections,0,supersedes}',jsonb_build_array(%L))$$, o26), 'observation_ids');
  r := r || pg_temp.check('G06 fake correction chain -> correction_chain_invalid', pg_temp.build(uop, ta, fr)->>'code', 'correction_chain_invalid');

  -- ---------- legacy c02-v1 run (stored fixture with a real v1 hash) ----------
  SELECT encode(sha256(convert_to(jsonb_build_object('alg', 'c02-v1', 'profile', pa, 'subject', s1, 'as_of', '2026-09-01T00:00:00.000000Z',
           'obs', coalesce(jsonb_agg(jsonb_build_array(o.id, o.payload_hash) ORDER BY o.id), '[]'::jsonb))::text, 'UTF8')), 'hex')
    INTO h FROM public.observations o WHERE o.tenant_id = ta AND o.subject_id = s1 AND o.ingested_at <= cut;
  fr := pg_temp.forge(run1, h, 'c02-v1', 'paid_pct', 'details', 'observation_ids');
  res := pg_temp.build(uop, ta, fr);
  r := r || pg_temp.check('L01 legacy v1 bundle: nothing complete', (res->>'status') || ' complete=' || (res->'summary'->>'complete') || ' ' ||
    pg_temp.val(uv, format($$select reasons[1] from public.c03_indicators where bundle_id=%L and indicator_key='paid_pct'$$, res->>'bundle_id')), 'built complete=0 legacy_c02_v1_known_gaps');

  -- ---------- direct writes ----------
  r := r || pg_temp.expect_err('W01 client cannot insert bundle', ua, format($$insert into public.c03_bundles(tenant_id,subject_id,run_id,algorithm_version,c02_algorithm_version,c02_input_hash,data_cutoff,content_hash,summary) values (%L,%L,%L,'x','x','x',now(),'x','{}')$$, ta, s1, run1), '42501');
  r := r || pg_temp.expect_err('W02 client cannot update refs', ua, format($$update public.c03_refs set value_numeric=1 where bundle_id=%L$$, b1->>'bundle_id'), '42501');
  r := r || pg_temp.expect_err('W03 client cannot delete attempts', ua, format($$delete from public.c03_attempts where tenant_id=%L$$, ta), '42501');
  r := r || pg_temp.expect_err('W04 anon cannot read bundles', NULL, $$select count(*) from public.c03_bundles$$, '42501');
  BEGIN
    UPDATE public.c03_bundles SET summary = '{}' WHERE id = (b1->>'bundle_id')::uuid;
    r := r || E'\nFAIL W05 owner update not blocked';
  EXCEPTION WHEN insufficient_privilege THEN r := r || E'\nPASS W05 bundles immutable even for owner [42501]';
  END;

  npass := (length(r) - length(replace(r, E'\nPASS', ''))) / 5;
  nfail := (length(r) - length(replace(r, E'\nFAIL', ''))) / 5;
  RAISE EXCEPTION 'CW_C03_RESULTS pass=% fail=% (transaction rolled back)%', npass, nfail, r;
END
$test$;
