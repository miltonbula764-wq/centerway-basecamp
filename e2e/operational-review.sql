-- Actual authenticated/anon roles, no service-role authorization proofs. Runner always rolls back.
DO $review$
DECLARE f jsonb:=current_setting('cw.review_fixture')::jsonb; sample jsonb; resolved jsonb; unmet jsonb;
 t uuid:=(f->>'tenant')::uuid; actor uuid:=(f->>'actor')::uuid; operator_id uuid:=(f->>'operator')::uuid; viewer uuid:=(f->>'viewer')::uuid;
 outsider uuid:=gen_random_uuid(); foreign_tenant uuid; c uuid; hc uuid; uc uuid; event_id uuid; replay uuid; operation uuid:=gen_random_uuid();
 expected int; payload jsonb; opening jsonb; plan jsonb; ev public.cw_operational_events; def jsonb; table_name text; u uuid; result jsonb; run_result jsonb; bundle_result jsonb;
 before_demo text; after_demo text;
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
  EXCEPTION WHEN OTHERS THEN IF SQLSTATE=_state THEN RETURN; END IF; RAISE EXCEPTION '% expected %, got %: %',_name,_state,SQLSTATE,SQLERRM; END;
  RAISE EXCEPTION '% unexpectedly succeeded',_name;
 END $fn$;
 CREATE FUNCTION pg_temp.cmd(_actor uuid,_case uuid,_command text,_payload jsonb) RETURNS uuid LANGUAGE plpgsql AS $fn$
 DECLARE c public.cw_operational_cases;
 BEGIN
  SELECT * INTO c FROM public.cw_operational_cases WHERE id=_case;
  RETURN pg_temp.run_as(_actor,format('SELECT public.command_operational_case(%L,%L,%s,%L,%L,%L)',c.tenant_id,c.id,c.version,gen_random_uuid(),_command,_payload))::uuid;
 END $fn$;
 -- Optional additive monitoring assertions: same real Core transitions, never a parallel state engine.
 CREATE FUNCTION pg_temp.review_state(_tenant uuid,_case uuid,_expected text) RETURNS void LANGUAGE plpgsql AS $fn$
 DECLARE q jsonb; f jsonb; before_row jsonb; BEGIN
  IF to_regprocedure('public.prepare_scheduled_reviews(uuid,uuid)') IS NULL THEN RETURN; END IF;
  SELECT to_jsonb(c) INTO before_row FROM public.cw_operational_cases c WHERE id=_case;
  SELECT value INTO q FROM jsonb_array_elements(public._core_followup_projection(_tenant,'','','','',100)->'items') WHERE value->>'case_id'=_case::text;
  f:=public._review_facts(_tenant,q);
  IF q IS NULL OR f->>'status' IS DISTINCT FROM _expected THEN RAISE EXCEPTION 'monitor state expected %, got % / %',_expected,q,f; END IF;
  IF before_row IS DISTINCT FROM (SELECT to_jsonb(c) FROM public.cw_operational_cases c WHERE id=_case) THEN RAISE EXCEPTION 'monitor changed case'; END IF;
 END $fn$;
 SELECT value INTO sample FROM jsonb_array_elements(f->'customers') WHERE value->>'stage'='prospective';
 SELECT value INTO resolved FROM jsonb_array_elements(f->'customers') WHERE value->>'stage'='historical_resolved';
 SELECT value INTO unmet FROM jsonb_array_elements(f->'customers') WHERE value->>'stage'='historical_unmet';
 SELECT id INTO hc FROM public.cw_operational_cases WHERE evaluation_id=(resolved->>'evaluation_id')::uuid;
 SELECT id INTO uc FROM public.cw_operational_cases WHERE evaluation_id=(unmet->>'evaluation_id')::uuid;
 SELECT jsonb_agg(to_jsonb(x) ORDER BY id)::text INTO before_demo FROM public.cw_cases x;
 opening:='{"eligible":true,"configuration_pinned":true,"eligibility_reason":"[SYNTHETIC] Authorized individual review","eligibility_ref":"urn:atlas:test:opening","opening_criteria":"[SYNTHETIC] Measured goal gap despite no deterioration signal","closure_criteria":"[SYNTHETIC] Historical goal, valid post-execution measurements and human review","closure_ref":"urn:atlas:test:closure"}';
 c:=pg_temp.run_as(actor,format('SELECT public.open_operational_case(%L,%L,%L,%L)',t,sample->>'evaluation_id',operation,opening))::uuid;
 IF c<>pg_temp.run_as(actor,format('SELECT public.open_operational_case(%L,%L,%L,%L)',t,sample->>'evaluation_id',operation,opening))::uuid THEN RAISE EXCEPTION 'open replay duplicated'; END IF;
 PERFORM pg_temp.expect_error('open idempotency conflict',actor,format('SELECT public.open_operational_case(%L,%L,%L,%L)',t,sample->>'evaluation_id',operation,opening||'{"eligibility_reason":"changed"}'::jsonb),'22023');
 PERFORM pg_temp.expect_error('duplicate case',actor,format('SELECT public.open_operational_case(%L,%L,%L,%L)',t,sample->>'evaluation_id',gen_random_uuid(),opening),'22023');
 PERFORM pg_temp.expect_error('inconclusive entry',actor,format('SELECT public.open_operational_case(%L,%L,%L,%L)',t,f->>'incompleteEvaluation',gen_random_uuid(),opening),'22023');
 FOREACH u IN ARRAY ARRAY[operator_id,viewer] LOOP
  PERFORM pg_temp.expect_error('non-admin opening',u,format('SELECT public.open_operational_case(%L,%L,%L,%L)',t,sample->>'evaluation_id',gen_random_uuid(),opening),'42501');
 END LOOP;
 payload:='{"status":"hypothesis","finding":"[SYNTHETIC] Possible blocker, no confirmation","reference":"urn:atlas:test:hypothesis","observation_ids":[]}';
 event_id:=pg_temp.cmd(operator_id,c,'investigate',payload);
 IF (SELECT state FROM public.cw_operational_cases WHERE id=c)<>'hypothesis' THEN RAISE EXCEPTION 'hypothesis promoted'; END IF;
 plan:='{"action":"[SYNTHETIC] Human adjustment of documented configuration","rationale":"Explicit bounded intervention","success_conditions":"Historical C04 goal and human review","limitations":"No causality inferred","reversal":"Human review before restoration","reference":"urn:atlas:test:plan","observation_seconds":2}';
 PERFORM pg_temp.expect_error('hypothesis plan',operator_id,format('SELECT public.command_operational_case(%L,%L,1,%L,''plan'',%L)',t,c,gen_random_uuid(),plan),'22023');
 event_id:=pg_temp.cmd(operator_id,c,'investigate',payload||'{"status":"insufficient"}'::jsonb);
 IF (SELECT state FROM public.cw_operational_cases WHERE id=c)<>'needs_information' THEN RAISE EXCEPTION 'insufficient promoted'; END IF;
 PERFORM pg_temp.expect_error('unreferenced confirmation',operator_id,format('SELECT public.command_operational_case(%L,%L,2,%L,''investigate'',%L)',t,c,gen_random_uuid(),payload||'{"status":"confirmed"}'::jsonb),'22023');
 PERFORM pg_temp.expect_error('wrong client evidence',operator_id,format('SELECT public.command_operational_case(%L,%L,2,%L,''investigate'',%L)',t,c,gen_random_uuid(),payload||jsonb_build_object('status','confirmed','observation_ids',jsonb_build_array(resolved->>'proof_id'))),'22023');
 payload:=payload||jsonb_build_object('status','confirmed','observation_ids',jsonb_build_array(sample->>'proof_id'));
 event_id:=pg_temp.cmd(operator_id,c,'investigate',payload);
 event_id:=pg_temp.cmd(operator_id,c,'plan',plan);
 PERFORM pg_temp.expect_error('operator approval',operator_id,format('SELECT public.command_operational_case(%L,%L,4,%L,''approve'',''{}'')',t,c,gen_random_uuid()),'42501');
 PERFORM pg_temp.expect_error('invalid window',operator_id,format('SELECT public.command_operational_case(%L,%L,4,%L,''plan'',%L)',t,c,gen_random_uuid(),plan||'{"observation_seconds":0}'::jsonb),'22023');
 payload:=jsonb_build_object('reason','[SYNTHETIC] explicit approval','reference','urn:atlas:test:approval','valid_until',to_char(clock_timestamp()-interval '1 hour','YYYY-MM-DD"T"HH24:MI:SS"Z"'));
 PERFORM pg_temp.expect_error('expired authorization',actor,format('SELECT public.command_operational_case(%L,%L,4,%L,''approve'',%L)',t,c,gen_random_uuid(),payload),'22023');
 payload:=payload||jsonb_build_object('valid_until',to_char(clock_timestamp()+interval '1 hour','YYYY-MM-DD"T"HH24:MI:SS"Z"'));
 event_id:=pg_temp.cmd(actor,c,'approve',payload);
 event_id:=pg_temp.cmd(operator_id,c,'plan',plan); -- revision invalidates approval
 PERFORM pg_temp.expect_error('old plan authorization',operator_id,format('SELECT public.command_operational_case(%L,%L,6,%L,''record_execution'',''{"receipt":"x","reference":"urn:test:x"}'')',t,c,gen_random_uuid()),'22023');
 event_id:=pg_temp.cmd(actor,c,'approve',payload);
 -- A once-valid approver must still hold the role at execution time.
 PERFORM pg_temp.run_as(actor,format('SELECT public.set_member_role(%L,%L,''admin'')',t,viewer));
 PERFORM pg_temp.run_as(viewer,format('SELECT public.set_member_role(%L,%L,''operator'')',t,actor));
 PERFORM pg_temp.expect_error('revoked approver',operator_id,format('SELECT public.command_operational_case(%L,%L,7,%L,''record_execution'',''{"receipt":"x","reference":"urn:test:x"}'')',t,c,gen_random_uuid()),'42501');
 PERFORM pg_temp.run_as(viewer,format('SELECT public.set_member_role(%L,%L,''admin'')',t,actor));
 PERFORM pg_temp.run_as(actor,format('SELECT public.set_member_role(%L,%L,''viewer'')',t,viewer));
 operation:=gen_random_uuid(); payload:='{"receipt":"[SYNTHETIC] actual human execution record","reference":"urn:atlas:test:receipt"}';
 event_id:=pg_temp.run_as(operator_id,format('SELECT public.command_operational_case(%L,%L,7,%L,''record_execution'',%L)',t,c,operation,payload))::uuid;
 replay:=pg_temp.run_as(operator_id,format('SELECT public.command_operational_case(%L,%L,7,%L,''record_execution'',%L)',t,c,operation,payload))::uuid;
 IF replay<>event_id OR (SELECT count(*) FROM public.cw_operational_events WHERE case_id=c AND command='record_execution')<>1 THEN RAISE EXCEPTION 'execution duplicated'; END IF;
 SELECT * INTO ev FROM public.cw_operational_events WHERE id=event_id;
 IF ev.details->>'value_recovery'<>'not_proven' OR (ev.details->>'wait_until')::timestamptz-(ev.details->>'executed_at')::timestamptz<>interval '2 seconds' THEN RAISE EXCEPTION 'execution conflated with value / wrong window'; END IF;
 PERFORM pg_temp.expect_error('premature observation',operator_id,format('SELECT public.command_operational_case(%L,%L,8,%L,''observe'',%L)',t,c,gen_random_uuid(),jsonb_build_object('bundle_id',sample->>'after_bundle_id')),'22023');
 PERFORM pg_temp.expect_error('stale version',operator_id,format('SELECT public.command_operational_case(%L,%L,0,%L,''plan'',%L)',t,c,gen_random_uuid(),plan),'40001');
 PERFORM pg_temp.expect_error('second execution',operator_id,format('SELECT public.command_operational_case(%L,%L,8,%L,''record_execution'',%L)',t,c,gen_random_uuid(),payload),'22023');
 PERFORM pg_temp.review_state(t,c,'waiting');
 PERFORM pg_sleep(2.1); -- Actual elapsed small synthetic window, not a mocked clock or bypass.
 PERFORM pg_temp.review_state(t,c,'available');
 event_id:=pg_temp.cmd(operator_id,c,'observe',jsonb_build_object('bundle_id',sample->>'after_bundle_id'));
 SELECT * INTO ev FROM public.cw_operational_events WHERE id=event_id;
 IF ev.details->>'result'<>'inconclusive' OR (ev.details->>'sufficient')::boolean THEN RAISE EXCEPTION 'pre-execution measurements treated as recovery'; END IF;
 payload:='{"close_requested":true,"criteria_met":true,"material_contradiction":false,"reason":"[SYNTHETIC] explicit closure review","reference":"urn:atlas:test:decision"}';
 event_id:=pg_temp.cmd(actor,c,'decide',payload);
 IF (SELECT state FROM public.cw_operational_cases WHERE id=c)<>'remain_open' THEN RAISE EXCEPTION 'insufficient case closed'; END IF;
 IF to_regprocedure('public.prepare_scheduled_reviews(uuid,uuid)') IS NOT NULL THEN
  IF NOT (public._review_facts(t,(SELECT value FROM jsonb_array_elements(public._core_followup_projection(t,'','','','',100)->'items') WHERE value->>'case_id'=c::text))->'reasons' ? 'new_evidence_required') THEN RAISE EXCEPTION 'open case lost evidence pending'; END IF;
 END IF;
 -- Retrospective history is ONLY fixture setup. These comparisons and decisions run under actual roles.
 event_id:=pg_temp.cmd(operator_id,hc,'observe',jsonb_build_object('bundle_id',resolved->>'after_bundle_id'));
 SELECT * INTO ev FROM public.cw_operational_events WHERE id=event_id;
 IF ev.details->>'result'<>'achieved' OR (ev.details->>'sufficient')::boolean IS NOT TRUE THEN RAISE EXCEPTION 'valid historical goal not recognized'; END IF;
 event_id:=pg_temp.cmd(actor,hc,'decide',payload||'{"material_contradiction":true}'::jsonb);
 IF (SELECT state FROM public.cw_operational_cases WHERE id=hc)<>'remain_open' THEN RAISE EXCEPTION 'contradiction closed'; END IF;
 event_id:=pg_temp.cmd(operator_id,hc,'observe',jsonb_build_object('bundle_id',resolved->>'after_bundle_id'));
 event_id:=pg_temp.cmd(actor,hc,'decide',payload||'{"criteria_met":false}'::jsonb);
 IF (SELECT state FROM public.cw_operational_cases WHERE id=hc)<>'remain_open' THEN RAISE EXCEPTION 'pending criteria closed'; END IF;
 event_id:=pg_temp.cmd(operator_id,hc,'observe',jsonb_build_object('bundle_id',resolved->>'after_bundle_id'));
 BEGIN
  result:=pg_temp.run_as(actor,format('SELECT public.import_observations(%L,%L,''synthetic-atlas'',%L,%L,true,''new-facts.csv'',%L)',t,f->>'profile',date_trunc('day',now())-interval '1 day',clock_timestamp(),jsonb_build_array(jsonb_build_object('line',1,'subject_external_ref','atlas-historical_resolved','indicator_key','cycle_minutes','unit','min','value_numeric','200','observed_at',clock_timestamp()-interval '1 hour','idempotency_key',gen_random_uuid()))))::jsonb;
  IF result->>'status'<>'completed' THEN RAISE EXCEPTION 'new fact import failed: %',result; END IF;
  event_id:=pg_temp.cmd(actor,hc,'decide',payload);
  IF (SELECT state FROM public.cw_operational_cases WHERE id=hc)<>'remain_open' THEN RAISE EXCEPTION 'new measurement ignored'; END IF;
  run_result:=pg_temp.run_as(actor,format('SELECT public.run_deterioration_analysis(%L,%L,%L,%L)',t,resolved->>'subject_id',f->>'profile',date_trunc('day',now())-interval '1 day'))::jsonb;
  bundle_result:=pg_temp.run_as(actor,format('SELECT public.build_evidence_bundle(%L,%L)',t,run_result->>'run_id'))::jsonb;
  event_id:=pg_temp.cmd(operator_id,hc,'observe',jsonb_build_object('bundle_id',bundle_result->>'bundle_id'));
  event_id:=pg_temp.cmd(actor,hc,'decide',payload);
  IF (SELECT state FROM public.cw_operational_cases WHERE id=hc)<>'remain_open' THEN RAISE EXCEPTION 'fresh cutoff concealed measurements beyond observed period'; END IF;
  RAISE EXCEPTION 'rollback isolated new-fact probe' USING ERRCODE='CWOP1';
 EXCEPTION WHEN SQLSTATE 'CWOP1' THEN NULL; END;
 event_id:=pg_temp.cmd(actor,hc,'decide',payload);
 IF (SELECT state FROM public.cw_operational_cases WHERE id=hc)<>'closed_resolved' THEN RAISE EXCEPTION 'satisfied specific criteria did not close'; END IF;
 PERFORM pg_temp.review_state(t,hc,'closed');
 event_id:=pg_temp.cmd(operator_id,uc,'observe',jsonb_build_object('bundle_id',unmet->>'after_bundle_id'));
 event_id:=pg_temp.cmd(actor,uc,'decide',payload);
 IF (SELECT state FROM public.cw_operational_cases WHERE id=uc)<>'remain_open' THEN RAISE EXCEPTION 'unmet goal closed'; END IF;
 INSERT INTO auth.users(id,instance_id,aud,role,email) VALUES(outsider,'00000000-0000-0000-0000-000000000000','authenticated','authenticated','operational-outsider@example.invalid');
 foreign_tenant:=pg_temp.run_as(outsider,$$SELECT public.create_tenant('Synthetic other SaaS','organization')$$)::uuid;
 FOREACH table_name IN ARRAY ARRAY['cw_operational_cases','cw_operational_events'] LOOP
  IF NOT (SELECT relrowsecurity FROM pg_class WHERE oid=('public.'||table_name)::regclass) THEN RAISE EXCEPTION 'RLS disabled'; END IF;
  FOREACH u IN ARRAY ARRAY[actor,operator_id,viewer] LOOP
   IF pg_temp.run_as(u,format('SELECT count(*) FROM public.%I WHERE tenant_id=%L',table_name,t))::int<1 THEN RAISE EXCEPTION 'member read blocked'; END IF;
   PERFORM pg_temp.expect_error('direct insert',u,format('INSERT INTO public.%I DEFAULT VALUES',table_name),'42501');
   PERFORM pg_temp.expect_error('direct update',u,format('UPDATE public.%I SET tenant_id=tenant_id',table_name),'42501');
   PERFORM pg_temp.expect_error('direct delete',u,format('DELETE FROM public.%I',table_name),'42501');
  END LOOP;
  IF pg_temp.run_as(outsider,format('SELECT count(*) FROM public.%I WHERE tenant_id=%L',table_name,t))::int<>0 THEN RAISE EXCEPTION 'cross-tenant read'; END IF;
  PERFORM pg_temp.expect_error('anon read',NULL,format('SELECT count(*) FROM public.%I',table_name),'42501');
 END LOOP;
 PERFORM pg_temp.expect_error('viewer command',viewer,format('SELECT public.command_operational_case(%L,%L,0,%L,''plan'',''{}'')',t,c,gen_random_uuid()),'42501');
 PERFORM pg_temp.expect_error('anon command',NULL,format('SELECT public.command_operational_case(%L,%L,0,%L,''plan'',''{}'')',t,c,gen_random_uuid()),'42501');
 PERFORM pg_temp.expect_error('foreign case reference',outsider,format('SELECT public.command_operational_case(%L,%L,0,%L,''plan'',''{}'')',foreign_tenant,c,gen_random_uuid()),'22023');
 PERFORM pg_temp.expect_error('private helper',actor,$$SELECT public._cwop_text('{}','x')$$,'42501');
 IF NOT EXISTS(SELECT FROM public.audit_log WHERE entity_type='cw_operational_events' AND entity_id=event_id AND actor_id=actor) THEN RAISE EXCEPTION 'authentic audit absent'; END IF;
 SELECT jsonb_agg(to_jsonb(x) ORDER BY id)::text INTO after_demo FROM public.cw_cases x;
 IF before_demo IS DISTINCT FROM after_demo THEN RAISE EXCEPTION 'demo historical cases changed'; END IF;
 RAISE NOTICE 'Operational review passed: independent C04 entry without C02 signal, C05-C10 guards, authorization revocation, idempotency, actual observation clock, historical goal closure, pending/new facts, roles/RLS/audit and unchanged demo cases.';
END $review$;
