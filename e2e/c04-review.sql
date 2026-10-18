-- Real SQL roles/JWT claims; outer runner always rolls back. No owner-written evaluation fixtures.
DO $review$
DECLARE f jsonb:=current_setting('cw.review_fixture')::jsonb; sample jsonb; other_sample jsonb;
  tenant uuid:=(f->>'tenant')::uuid; actor uuid:=(f->>'actor')::uuid; op uuid:=(f->>'operator')::uuid; viewer uuid:=(f->>'viewer')::uuid;
  stranger uuid:=gen_random_uuid(); foreign_tenant uuid; c uuid; prev uuid; evaluation uuid; operation uuid:=gen_random_uuid();
  definition jsonb; modified jsonb; e public.c04_evaluations; cases_before text; cases_after text; t text; u uuid; k text;
  base jsonb:=f->'foundation'; fu jsonb:=f->'foundation_users'; independent uuid; empty_config uuid; incomplete_profile uuid; incomplete_run jsonb; incomplete_bundle jsonb; q uuid; before_eval text;
BEGIN
  CREATE FUNCTION pg_temp.run_as(_uid uuid,_sql text) RETURNS text LANGUAGE plpgsql AS $fn$
  DECLARE answer text;
  BEGIN
    PERFORM set_config('request.jwt.claims',CASE WHEN _uid IS NULL THEN '{"role":"anon"}' ELSE jsonb_build_object('role','authenticated','sub',_uid)::text END,true);
    PERFORM set_config('role',CASE WHEN _uid IS NULL THEN 'anon' ELSE 'authenticated' END,true);
    EXECUTE _sql INTO answer; RESET ROLE; RETURN answer;
  EXCEPTION WHEN OTHERS THEN RESET ROLE; RAISE;
  END $fn$;
  CREATE FUNCTION pg_temp.expect_error(_name text,_uid uuid,_sql text,_state text) RETURNS void LANGUAGE plpgsql AS $fn$
  BEGIN
    BEGIN PERFORM pg_temp.run_as(_uid,_sql);
    EXCEPTION WHEN OTHERS THEN
      IF SQLSTATE=_state THEN RETURN; END IF;
      RAISE EXCEPTION '% expected %, got %: %',_name,_state,SQLSTATE,SQLERRM;
    END;
    RAISE EXCEPTION '% unexpectedly succeeded',_name;
  END $fn$;
  SELECT value INTO sample FROM jsonb_array_elements(f->'cases') WHERE value->>'stage'='investigation';
  SELECT value INTO other_sample FROM jsonb_array_elements(f->'cases') WHERE value->>'stage'='approval';
  SELECT jsonb_agg(to_jsonb(x) ORDER BY id)::text INTO cases_before FROM public.cw_cases x;
  definition:='{"promise":"Synthetic automation promise","promise_ref":"synthetic:contract-v1","plan_capability":"Synthetic reporting capability","plan_ref":"synthetic:plan-v1","customer_goal":"Synthetic measurable time goal","customer_ref":"synthetic:customer-confirmed","compatibility":"compatible","compatibility_ref":"synthetic:human-review","unit":"h/semana","source":"synthetic-flowreports","target":8,"comparator":"lte","aggregation":"mean","window_count":2,"observation_start":"2020-01-01T00:00:00Z","deadline":"2021-01-01T00:00:00Z"}';
  c:=pg_temp.run_as(actor,format('SELECT public.save_c04_configuration(%L,%L,%L,''report_hours'',NULL,%L,%L)',tenant,sample->>'subject_id',f->>'profile',operation,definition))::uuid;
  IF c<>pg_temp.run_as(actor,format('SELECT public.save_c04_configuration(%L,%L,%L,''report_hours'',NULL,%L,%L)',tenant,sample->>'subject_id',f->>'profile',operation,definition))::uuid THEN RAISE EXCEPTION 'save replay duplicated'; END IF;
  PERFORM pg_temp.expect_error('conflicting operation',actor,format('SELECT public.save_c04_configuration(%L,%L,%L,''report_hours'',NULL,%L,''{}'')',tenant,sample->>'subject_id',f->>'profile',operation),'22023');
  PERFORM pg_temp.expect_error('stale revision',actor,format('SELECT public.save_c04_configuration(%L,%L,%L,''report_hours'',NULL,%L,%L)',tenant,sample->>'subject_id',f->>'profile',gen_random_uuid(),definition),'22023');
  evaluation:=pg_temp.run_as(op,format('SELECT public.evaluate_c04_configuration(%L,%L,%L)',tenant,c,sample->>'bundle_id'))::uuid;
  SELECT * INTO e FROM public.c04_evaluations WHERE id=evaluation;
  IF e.result<>'not_achieved' OR e.configuration_state<>'compatible' OR e.evidence<>'sufficient' OR e.core_disposition<>'assessment_available' THEN RAISE EXCEPTION 'non-demo target8 evaluation failed: %',to_jsonb(e); END IF;
  IF evaluation<>pg_temp.run_as(op,format('SELECT public.evaluate_c04_configuration(%L,%L,%L)',tenant,c,sample->>'bundle_id'))::uuid THEN RAISE EXCEPTION 'evaluation replay duplicated'; END IF;
  before_eval:=to_jsonb(e)::text;
  -- Each mutation is a genuinely new revision, not an update of historical contracts.
  FOR k IN SELECT unnest(ARRAY['achieved','pending','missing_goal','contradiction','missing_plan','source','unit','windows','missing_target','future_start']) LOOP
    modified:=definition||CASE k
      WHEN 'achieved' THEN '{"target":12}'::jsonb
      WHEN 'pending' THEN jsonb_build_object('deadline',to_char(now()+interval '30 days','YYYY-MM-DD"T"HH24:MI:SS"Z"'))
      WHEN 'missing_goal' THEN '{"customer_goal":null}'::jsonb
      WHEN 'contradiction' THEN '{"compatibility":"contradiction","target":12}'::jsonb
      WHEN 'missing_plan' THEN '{"plan_ref":null,"target":12}'::jsonb
      WHEN 'source' THEN '{"source":"wrong-source"}'::jsonb
      WHEN 'unit' THEN '{"unit":"wrong-unit"}'::jsonb
      WHEN 'windows' THEN '{"window_count":3}'::jsonb
      WHEN 'missing_target' THEN '{"target":null}'::jsonb
      WHEN 'future_start' THEN jsonb_build_object('observation_start',to_char(now()-interval '1 day','YYYY-MM-DD"T"HH24:MI:SS"Z"'),'deadline',to_char(now()+interval '30 days','YYYY-MM-DD"T"HH24:MI:SS"Z"')) END;
    prev:=c;
    c:=pg_temp.run_as(actor,format('SELECT public.save_c04_configuration(%L,%L,%L,''report_hours'',%L,%L,%L)',tenant,sample->>'subject_id',f->>'profile',prev,gen_random_uuid(),modified))::uuid;
    q:=pg_temp.run_as(op,format('SELECT public.evaluate_c04_configuration(%L,%L,%L)',tenant,c,sample->>'bundle_id'))::uuid;
    SELECT * INTO e FROM public.c04_evaluations WHERE id=q;
    IF e.result IS DISTINCT FROM (CASE WHEN k IN ('achieved','contradiction','missing_plan') THEN 'achieved' WHEN k='pending' THEN 'pending_deadline' ELSE 'inconclusive' END) THEN RAISE EXCEPTION '% result incorrect: %',k,e.result; END IF;
    IF k IN ('contradiction','unit') AND e.configuration_state<>'contradiction' THEN RAISE EXCEPTION 'contradiction hidden'; END IF;
    IF k='missing_plan' AND (e.configuration_state<>'missing_documentation' OR e.core_disposition<>'needs_information') THEN RAISE EXCEPTION 'missing plan treated as fulfilled'; END IF;
    IF e.details->>'promise_fulfillment'<>'not_determined' OR e.details->>'causality'<>'not_established' THEN RAISE EXCEPTION 'invented fulfillment/causality'; END IF;
  END LOOP;
  IF (SELECT to_jsonb(x)::text FROM public.c04_evaluations x WHERE id=evaluation)<>before_eval THEN RAISE EXCEPTION 'historical evaluation changed'; END IF;
  prev:=c;
  c:=pg_temp.run_as(actor,format('SELECT public.save_c04_configuration(%L,%L,%L,''report_hours'',%L,%L,''{}'')',tenant,sample->>'subject_id',f->>'profile',prev,gen_random_uuid()))::uuid;
  IF (SELECT cardinality(pending_fields) FROM public.c04_configurations WHERE id=c)<>16 THEN RAISE EXCEPTION 'partial information must expose pending fields before C03'; END IF;
  -- Reject unsupported/malformed rules rather than silently approximating them.
  FOR k IN SELECT unnest(ARRAY['aggregation','window_count','deadline','unknown']) LOOP
    modified:=definition||CASE k WHEN 'aggregation' THEN '{"aggregation":"rate"}'::jsonb
      WHEN 'window_count' THEN '{"window_count":1.5}'::jsonb
      WHEN 'deadline' THEN '{"deadline":"2026-10-18T00:00:00"}'::jsonb
      ELSE '{"invented_criterion":true}'::jsonb END;
    PERFORM pg_temp.expect_error('invalid rule '||k,actor,format('SELECT public.save_c04_configuration(%L,%L,%L,''report_hours'',%L,%L,%L)',tenant,sample->>'subject_id',f->>'profile',c,gen_random_uuid(),modified),'22023');
  END LOOP;
  -- Independent indicators share a real C03 bundle: empty remains inconclusive; outcome is assessed.
  modified:=definition||'{"unit":"count","source":"synthetic-ci","target":40,"comparator":"gte"}'::jsonb;
  independent:=pg_temp.run_as((fu#>>'{admin,id}')::uuid,format('SELECT public.save_c04_configuration(%L,%L,%L,''outcome'',NULL,%L,%L)',base->>'tenantA',base#>>'{customerA,id}',base->>'profileA',gen_random_uuid(),modified))::uuid;
  empty_config:=pg_temp.run_as((fu#>>'{admin,id}')::uuid,format('SELECT public.save_c04_configuration(%L,%L,%L,''empty'',NULL,%L,%L)',base->>'tenantA',base#>>'{customerA,id}',base->>'profileA',gen_random_uuid(),modified||'{"compatibility":"contradiction"}'::jsonb))::uuid;
  q:=pg_temp.run_as((fu#>>'{operator,id}')::uuid,format('SELECT public.evaluate_c04_configuration(%L,%L,%L)',base->>'tenantA',empty_config,base#>>'{customerA,historicalBundle}'))::uuid;
  IF (SELECT result FROM public.c04_evaluations WHERE id=q)<>'inconclusive' THEN RAISE EXCEPTION 'empty indicator not inconclusive'; END IF;
  q:=pg_temp.run_as((fu#>>'{operator,id}')::uuid,format('SELECT public.evaluate_c04_configuration(%L,%L,%L)',base->>'tenantA',independent,base#>>'{customerA,historicalBundle}'))::uuid;
  IF (SELECT result FROM public.c04_evaluations WHERE id=q)<>'achieved' THEN RAISE EXCEPTION 'independent outcome blocked'; END IF;
  -- Missing C02 configuration is not a documentary contradiction. Use genuine profile/analysis/bundle RPCs.
  incomplete_profile:=pg_temp.run_as((fu#>>'{admin,id}')::uuid,format('SELECT public.create_value_profile_version(%L)',base->>'profileV2'))::uuid;
  PERFORM pg_temp.run_as((fu#>>'{admin,id}')::uuid,format('UPDATE public.profile_indicators SET aggregation=NULL WHERE tenant_id=%L AND profile_id=%L AND key=''outcome'' RETURNING id',base->>'tenantA',incomplete_profile));
  PERFORM pg_temp.run_as((fu#>>'{admin,id}')::uuid,format('SELECT public.approve_value_profile(%L)',incomplete_profile));
  incomplete_run:=pg_temp.run_as((fu#>>'{admin,id}')::uuid,format('SELECT public.run_deterioration_analysis(%L,%L,%L,%L)',base->>'tenantA',base#>>'{customerA,id}',incomplete_profile,date_trunc('day',now())))::jsonb;
  incomplete_bundle:=pg_temp.run_as((fu#>>'{admin,id}')::uuid,format('SELECT public.build_evidence_bundle(%L,%L)',base->>'tenantA',incomplete_run->>'run_id'))::jsonb;
  IF incomplete_bundle->>'status'<>'built' THEN RAISE EXCEPTION 'incomplete fixture C03 build failed'; END IF;
  q:=pg_temp.run_as((fu#>>'{admin,id}')::uuid,format('SELECT public.save_c04_configuration(%L,%L,%L,''outcome'',%L,%L,%L)',base->>'tenantA',base#>>'{customerA,id}',incomplete_profile,independent,gen_random_uuid(),definition||'{"unit":"count","source":"synthetic-ci","target":40,"comparator":"gte"}'::jsonb))::uuid;
  q:=pg_temp.run_as((fu#>>'{operator,id}')::uuid,format('SELECT public.evaluate_c04_configuration(%L,%L,%L)',base->>'tenantA',q,incomplete_bundle->>'bundle_id'))::uuid;
  SELECT * INTO e FROM public.c04_evaluations WHERE id=q;
  IF e.result<>'inconclusive' OR e.configuration_state='contradiction' OR NOT (e.details->'reasons' ? 'historical_measurement_configuration_incomplete') THEN RAISE EXCEPTION 'missing historical configuration mislabeled: %',to_jsonb(e); END IF;
  -- Tenant isolation and roles, including authenticated users administering their own tenant.
  INSERT INTO auth.users(id,instance_id,aud,role,email) VALUES(stranger,'00000000-0000-0000-0000-000000000000','authenticated','authenticated','c04-review@example.invalid');
  foreign_tenant:=pg_temp.run_as(stranger,$$SELECT public.create_tenant('Synthetic C04 other tenant','organization')$$)::uuid;
  FOREACH t IN ARRAY ARRAY['c04_configurations','c04_evaluations'] LOOP
    IF NOT (SELECT relrowsecurity FROM pg_class WHERE oid=('public.'||t)::regclass) THEN RAISE EXCEPTION 'RLS disabled'; END IF;
    FOREACH u IN ARRAY ARRAY[actor,op,viewer] LOOP
      IF pg_temp.run_as(u,format('SELECT count(*) FROM public.%I WHERE tenant_id=%L',t,tenant))::int<1 THEN RAISE EXCEPTION 'member read blocked'; END IF;
      PERFORM pg_temp.expect_error('direct insert',u,format('INSERT INTO public.%I DEFAULT VALUES',t),'42501');
      PERFORM pg_temp.expect_error('direct update',u,format('UPDATE public.%I SET tenant_id=tenant_id',t),'42501');
      PERFORM pg_temp.expect_error('direct delete',u,format('DELETE FROM public.%I',t),'42501');
    END LOOP;
    IF pg_temp.run_as(stranger,format('SELECT count(*) FROM public.%I WHERE tenant_id=%L',t,tenant))::int<>0 THEN RAISE EXCEPTION 'cross tenant read'; END IF;
    PERFORM pg_temp.expect_error('anon read',NULL,format('SELECT count(*) FROM public.%I',t),'42501');
    BEGIN EXECUTE format('UPDATE public.%I SET created_at=now()',t); RAISE EXCEPTION 'owner update allowed'; EXCEPTION WHEN SQLSTATE '42501' THEN NULL; END;
  END LOOP;
  FOREACH u IN ARRAY ARRAY[op,viewer,stranger] LOOP
    PERFORM pg_temp.expect_error('unauthorized configuration',u,format('SELECT public.save_c04_configuration(%L,%L,%L,''report_hours'',%L,%L,%L)',tenant,sample->>'subject_id',f->>'profile',c,gen_random_uuid(),definition),'42501');
  END LOOP;
  PERFORM pg_temp.expect_error('viewer evaluate',viewer,format('SELECT public.evaluate_c04_configuration(%L,%L,%L)',tenant,c,sample->>'bundle_id'),'42501');
  PERFORM pg_temp.expect_error('anon evaluate',NULL,format('SELECT public.evaluate_c04_configuration(%L,%L,%L)',tenant,c,sample->>'bundle_id'),'42501');
  PERFORM pg_temp.expect_error('foreign config reference',stranger,format('SELECT public.evaluate_c04_configuration(%L,%L,%L)',foreign_tenant,c,sample->>'bundle_id'),'22023');
  PERFORM pg_temp.expect_error('different subject bundle',op,format('SELECT public.evaluate_c04_configuration(%L,%L,%L)',tenant,c,other_sample->>'bundle_id'),'22023');
  IF NOT EXISTS(SELECT FROM public.audit_log WHERE entity_type='c04_configurations' AND entity_id=c AND actor_id=actor) OR NOT EXISTS(SELECT FROM public.audit_log WHERE entity_type='c04_evaluations' AND entity_id=evaluation AND actor_id=op) THEN RAISE EXCEPTION 'missing authentic audit'; END IF;
  SELECT jsonb_agg(to_jsonb(x) ORDER BY id)::text INTO cases_after FROM public.cw_cases x;
  IF cases_before IS DISTINCT FROM cases_after THEN RAISE EXCEPTION 'historical cases changed'; END IF;
  RAISE NOTICE 'C04 focused review passed: configurable targets, versions/replay/conflict, deadline, partial documentation, independent indicators, real roles/RLS, audit and unchanged cases.';
END $review$;
