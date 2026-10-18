-- Invoked only by scripts/mvp/review-database.py in a disposable database.
-- The caller always ROLLBACKs; JWT claims use real authenticated/anon SQL roles.
DO $review$
DECLARE f jsonb:=current_setting('cw.review_fixture')::jsonb;
  tenant uuid:=(f->>'tenant')::uuid; actor uuid:=(f->>'actor')::uuid;
  operator_id uuid:=(f->>'operator')::uuid; viewer_id uuid:=(f->>'viewer')::uuid;
  outsider uuid:=gen_random_uuid(); foreign_tenant uuid; sample jsonb; historical jsonb; second_sample jsonb;
  t text; u uuid; n int; c public.cw_cases; a public.cw_assessments; o public.cw_objectives;
  ev public.cw_case_events; original_case uuid; answer jsonb; before_hash text; after_hash text; passes int:=0;
BEGIN
  CREATE FUNCTION pg_temp.run_as(_uid uuid,_sql text) RETURNS text LANGUAGE plpgsql AS $fn$
  DECLARE answer text;
  BEGIN
    PERFORM set_config('request.jwt.claims',CASE WHEN _uid IS NULL THEN '{"role":"anon"}' ELSE jsonb_build_object('role','authenticated','sub',_uid)::text END,true);
    PERFORM set_config('role',CASE WHEN _uid IS NULL THEN 'anon' ELSE 'authenticated' END,true);
    EXECUTE _sql INTO answer;
    RESET ROLE;
    RETURN answer;
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
  SELECT value INTO second_sample FROM jsonb_array_elements(f->'cases') WHERE value->>'stage'='approval';
  SELECT value INTO historical FROM jsonb_array_elements(f->'cases') WHERE value->>'stage'='historical_resolved';
  INSERT INTO auth.users(id,instance_id,aud,role,email) VALUES(outsider,'00000000-0000-0000-0000-000000000000','authenticated','authenticated','review-outsider@example.invalid');
  foreign_tenant:=pg_temp.run_as(outsider,$$SELECT public.create_tenant('Review synthetic tenant B','organization')$$)::uuid;
  FOREACH t IN ARRAY ARRAY['cw_objectives','cw_assessments','cw_cases','cw_case_events'] LOOP
    IF NOT (SELECT relrowsecurity FROM pg_class WHERE oid=('public.'||t)::regclass) THEN RAISE EXCEPTION 'RLS disabled: %',t; END IF;
    FOREACH u IN ARRAY ARRAY[actor,operator_id,viewer_id] LOOP
      n:=pg_temp.run_as(u,format('SELECT count(*) FROM public.%I WHERE tenant_id=%L',t,tenant))::int;
      IF n<1 THEN RAISE EXCEPTION 'member cannot read %',t; END IF;
      PERFORM pg_temp.expect_error('direct insert '||t,u,format('INSERT INTO public.%I DEFAULT VALUES',t),'42501');
      PERFORM pg_temp.expect_error('direct update '||t,u,format('UPDATE public.%I SET tenant_id=tenant_id',t),'42501');
      PERFORM pg_temp.expect_error('direct delete '||t,u,format('DELETE FROM public.%I',t),'42501');
      passes:=passes+4;
    END LOOP;
    n:=pg_temp.run_as(outsider,format('SELECT count(*) FROM public.%I WHERE tenant_id=%L',t,tenant))::int;
    IF n<>0 THEN RAISE EXCEPTION 'cross-tenant read leaked: %',t; END IF;
    PERFORM pg_temp.expect_error('anon read '||t,NULL,format('SELECT count(*) FROM public.%I',t),'42501');
    passes:=passes+3;
  END LOOP;
  PERFORM pg_temp.expect_error('viewer assess',viewer_id,format('SELECT public.assess_demo_objective(%L,%L,%L)',tenant,sample->>'objective_id',sample->>'bundle_id'),'42501');
  PERFORM pg_temp.expect_error('viewer open',viewer_id,format('SELECT public.open_demo_case(%L,%L)',tenant,sample->>'assessment_id'),'42501');
  PERFORM pg_temp.expect_error('viewer command',viewer_id,format('SELECT public.command_demo_case(%L,%L,0,%L,''plan'',''{}'')',tenant,sample->>'case_id',gen_random_uuid()),'42501');
  PERFORM pg_temp.expect_error('anon RPC',NULL,format('SELECT public.open_demo_case(%L,%L)',tenant,sample->>'assessment_id'),'42501');
  PERFORM pg_temp.expect_error('private evaluator',operator_id,$$SELECT public._cw_demo_evaluate(NULL::public.cw_objectives,NULL)$$,'42501');
  PERFORM pg_temp.expect_error('operator create goal',operator_id,format('SELECT public.create_demo_objective(%L,%L,%L,now(),''x'',''a'',''b'',''c'')',tenant,sample->>'subject_id',f->>'profile'),'42501');
  PERFORM pg_temp.expect_error('operator approve',operator_id,format('SELECT public.command_demo_case(%L,%L,2,%L,''approve'',''{}'')',tenant,second_sample->>'case_id',gen_random_uuid()),'42501');
  PERFORM pg_temp.expect_error('spoof tenant',operator_id,format('SELECT public.open_demo_case(%L,%L)',foreign_tenant,sample->>'assessment_id'),'42501');
  PERFORM pg_temp.expect_error('foreign admin case reference',outsider,format('SELECT public.command_demo_case(%L,%L,0,%L,''plan'',''{}'')',foreign_tenant,sample->>'case_id',gen_random_uuid()),'22023');
  PERFORM pg_temp.expect_error('same-tenant different subject evidence',operator_id,format('SELECT public.assess_demo_objective(%L,%L,%L)',tenant,sample->>'objective_id',second_sample->>'bundle_id'),'22023');
  PERFORM pg_temp.expect_error('stale version',operator_id,format('SELECT public.command_demo_case(%L,%L,99,%L,''investigate'',''{}'')',tenant,sample->>'case_id',gen_random_uuid()),'40001');
  PERFORM pg_temp.expect_error('skip approval',operator_id,format('SELECT public.command_demo_case(%L,%L,0,%L,''record_execution'',''{"receipt":"synthetic"}'')',tenant,sample->>'case_id',gen_random_uuid()),'22023');
  -- Owner fixture probes enforce composite FKs as well as authorization above.
  BEGIN
    INSERT INTO public.cw_assessments(tenant_id,subject_id,objective_id,bundle_id,policy_version,result,evidence,details,created_by)
      VALUES(foreign_tenant,(sample->>'subject_id')::uuid,(sample->>'objective_id')::uuid,(second_sample->>'bundle_id')::uuid,'flowreports-demo-v1','inconclusive','insufficient','{}',outsider);
    RAISE EXCEPTION 'cross-tenant FK accepted';
  EXCEPTION WHEN foreign_key_violation THEN NULL; END;
  passes:=passes+13;
  -- Prepare a disposable clone immediately before the genuine C10 decision.
  -- This is fixture setup as owner, not an authorization test or elapsed live wait.
  SELECT * INTO a FROM public.cw_assessments WHERE id=(historical->>'assessment_id')::uuid;
  SELECT * INTO o FROM public.cw_objectives WHERE id=a.objective_id;
  o.id:=gen_random_uuid(); INSERT INTO public.cw_objectives SELECT (o).*;
  a.id:=gen_random_uuid();a.objective_id:=o.id;INSERT INTO public.cw_assessments SELECT (a).*;
  SELECT * INTO c FROM public.cw_cases WHERE assessment_id=(historical->>'assessment_id')::uuid;
  original_case:=c.id;c.id:=gen_random_uuid();c.assessment_id:=a.id;c.state:='observed';c.version:=5;
  INSERT INTO public.cw_cases SELECT (c).*;
  FOR ev IN SELECT * FROM public.cw_case_events WHERE case_id=original_case AND sequence<=5 LOOP
    ev.id:=gen_random_uuid();ev.case_id:=c.id;ev.operation_id:=gen_random_uuid();
    IF ev.command='open' THEN ev.details:=ev.details||jsonb_build_object('assessment_id',a.id,'objective_id',o.id); END IF;
    INSERT INTO public.cw_case_events SELECT (ev).*;
  END LOOP;
  SELECT encode(sha256(convert_to(details::text,'UTF8')),'hex') INTO before_hash
    FROM public.cw_case_events WHERE case_id=c.id AND command='observe';
  -- Genuine append-only C01 input after C09: a newly documented disabled state.
  answer:=pg_temp.run_as(actor,format($sql$SELECT public.import_observations(%L,%L,'synthetic-flowreports',%L,%L,true,'review.csv',%L::jsonb)$sql$,
    tenant,f->>'profile',date_trunc('day',now())-interval '2 days',now(),
    jsonb_build_array(jsonb_build_object('line',1,'subject_external_ref','mvp-historical_resolved','indicator_key','integration_status',
      'unit','estado','value_text','disabled','observed_at',date_trunc('day',now())-interval '1 day','idempotency_key',gen_random_uuid()::text))))::jsonb;
  IF answer->>'status'<>'completed' THEN RAISE EXCEPTION 'C01 review fixture import failed: %',answer; END IF;
  answer:=pg_temp.run_as(operator_id,format('SELECT public.command_demo_case(%L,%L,5,%L,''decide'',''{}'')',tenant,c.id,gen_random_uuid()))::jsonb;
  IF answer->>'to_state'<>'remain_open' OR (answer#>>'{details,pending_evidence}')::boolean IS DISTINCT FROM true THEN
    RAISE EXCEPTION 'C10 closed with pending evidence: %',answer->>'to_state'; END IF;
  SELECT encode(sha256(convert_to(details::text,'UTF8')),'hex') INTO after_hash
    FROM public.cw_case_events WHERE case_id=c.id AND command='observe';
  IF before_hash IS DISTINCT FROM after_hash THEN RAISE EXCEPTION 'C09 historical snapshot changed'; END IF;
  passes:=passes+3;
  RAISE NOTICE 'MVP final review: % assertions passed; RLS, grants, RPC authorization, tenant/subject links, version/approval guards and C10 pending evidence. Transaction will roll back.',passes;
END $review$;
