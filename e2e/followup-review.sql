-- Read-only projection exercised under actual database roles/JWT claims. Runner rolls back all probes.
CREATE FUNCTION pg_temp.as_user(uid uuid,sql text) RETURNS text LANGUAGE plpgsql AS $$
DECLARE r text;
BEGIN
 PERFORM set_config('request.jwt.claims',CASE WHEN uid IS NULL THEN '{"role":"anon"}' ELSE jsonb_build_object('role','authenticated','sub',uid)::text END,true);
 PERFORM set_config('role',CASE WHEN uid IS NULL THEN 'anon' ELSE 'authenticated' END,true);
 EXECUTE sql INTO r; RESET ROLE; RETURN r;
EXCEPTION WHEN OTHERS THEN RESET ROLE; RAISE;
END $$;
CREATE FUNCTION pg_temp.denied(uid uuid,sql text,code text DEFAULT '42501') RETURNS void LANGUAGE plpgsql AS $$
BEGIN
 BEGIN PERFORM pg_temp.as_user(uid,sql);
 EXCEPTION WHEN OTHERS THEN IF SQLSTATE=code THEN RETURN; END IF; RAISE; END;
 RAISE EXCEPTION 'unexpected authorization success: %',sql;
END $$;
CREATE FUNCTION pg_temp.fingerprint() RETURNS text LANGUAGE sql AS $$
 SELECT jsonb_build_array((SELECT jsonb_agg(to_jsonb(c) ORDER BY id) FROM public.cw_operational_cases c),
 (SELECT jsonb_agg(to_jsonb(e) ORDER BY id) FROM public.cw_operational_events e),
 (SELECT jsonb_agg(to_jsonb(a) ORDER BY id) FROM public.audit_log a),
 (SELECT jsonb_agg(to_jsonb(a) ORDER BY id) FROM public.c04_evaluations a),
 (SELECT jsonb_agg(to_jsonb(c) ORDER BY id) FROM public.cw_cases c))::text
$$;
CREATE FUNCTION pg_temp.queue(uid uuid,t uuid,client text DEFAULT '',indicator text DEFAULT '',category text DEFAULT '',cursor text DEFAULT '',size int DEFAULT 100) RETURNS jsonb LANGUAGE plpgsql AS $$
DECLARE before text:=pg_temp.fingerprint(); r jsonb;
BEGIN
 r:=pg_temp.as_user(uid,format('SELECT public.core_followup_queue(%L,%L,%L,%L,%L,%s)',t,client,indicator,category,cursor,size))::jsonb;
 IF before IS DISTINCT FROM pg_temp.fingerprint() THEN RAISE EXCEPTION 'READ MODIFIED CASES, EVALUATIONS OR AUDIT'; END IF;
 IF r->>'tenant_id'<>t::text OR EXISTS(SELECT FROM jsonb_array_elements(r->'items') x WHERE x->>'tenant_id'<>t::text) THEN RAISE EXCEPTION 'tenant mismatch'; END IF;
 RETURN r;
END $$;
CREATE FUNCTION pg_temp.expect_case(uid uuid,t uuid,c uuid,category text,action text) RETURNS jsonb LANGUAGE plpgsql AS $$
DECLARE r jsonb; x jsonb;
BEGIN
 r:=pg_temp.queue(uid,t);
 SELECT value INTO x FROM jsonb_array_elements(r->'items') WHERE value->>'case_id'=c::text;
 IF x IS NULL OR x->>'category'<>category OR x->>'next_action'<>action THEN RAISE EXCEPTION 'case projection expected % / %, got %',category,action,x; END IF;
 RETURN x;
END $$;
CREATE FUNCTION pg_temp.command(uid uuid,c uuid,command text,payload jsonb) RETURNS void LANGUAGE plpgsql AS $$
DECLARE k public.cw_operational_cases;
BEGIN
 SELECT * INTO k FROM public.cw_operational_cases WHERE id=c;
 PERFORM pg_temp.as_user(uid,format('SELECT public.command_operational_case(%L,%L,%s,%L,%L,%L)',k.tenant_id,k.id,k.version,gen_random_uuid(),command,payload));
END $$;
DO $tests$
DECLARE f jsonb:=current_setting('cw.review_fixture')::jsonb;q jsonb:=f->'queue';
 t uuid:=(f->>'tenant')::uuid; qt uuid:=(q->>'tenant')::uuid; actor uuid:=(f->>'actor')::uuid; op uuid:=(f->>'operator')::uuid; viewer uuid:=(f->>'viewer')::uuid;
 sample jsonb;resolved jsonb;unmet jsonb;c uuid;hc uuid;uc uuid;cfg public.c04_configurations;
 r jsonb;x jsonb;y jsonb;seen text[]:='{}'; cursor text:='';page_count int:=0;uid uuid;newcfg uuid;opening jsonb;plan jsonb;approval jsonb;
BEGIN
 IF (SELECT prosecdef FROM pg_proc WHERE oid='public.core_followup_queue(uuid,text,text,text,text,integer)'::regprocedure) THEN RAISE EXCEPTION 'projection must preserve caller RLS'; END IF;
 FOREACH uid IN ARRAY ARRAY[actor,op,viewer] LOOP
  r:=pg_temp.queue(uid,qt,'queue-000');
  IF jsonb_array_length(r->'items')<>3 THEN RAISE EXCEPTION 'independent indicators missing'; END IF;
  FOR x IN SELECT value FROM jsonb_array_elements(r->'items') LOOP
   IF x->>'indicator_key'='contradiction_minutes' AND x->>'category'<>'contradiction' THEN RAISE EXCEPTION 'documented contradiction lost'; END IF;
   IF x->>'indicator_key'='independent_minutes' AND x->>'category'<>'assessment_review' THEN RAISE EXCEPTION 'contradiction blocked independent indicator'; END IF;
   IF x->>'indicator_key'='partial_minutes' AND x->>'category'<>'information_pending' THEN RAISE EXCEPTION 'insufficient evaluation promoted'; END IF;
   IF uid=viewer AND (x->>'can_prepare')::boolean THEN RAISE EXCEPTION 'viewer offered write preparation'; END IF;
   IF uid=op AND x->>'next_action'='review_eligibility' AND (x->>'can_prepare')::boolean THEN RAISE EXCEPTION 'operator offered admin eligibility'; END IF;
  END LOOP;
 END LOOP;
 PERFORM pg_temp.denied(actor,format('SELECT public.core_followup_queue(%L)',q->>'foreignTenant'));
 PERFORM pg_temp.denied(NULL,format('SELECT public.core_followup_queue(%L)',qt));
 PERFORM pg_temp.denied(actor,format('SELECT public.core_followup_queue(%L,_limit=>101)',qt),'22023');
 PERFORM pg_temp.denied(actor,format('SELECT public.core_followup_queue(%L,_category=>''invented'')',qt),'22023');
 LOOP
  r:=pg_temp.queue(viewer,qt,'','','',cursor,17);page_count:=page_count+1;
  FOR x IN SELECT value FROM jsonb_array_elements(r->'items') LOOP
   IF x->>'entry_key'=ANY(seen) OR x->>'entry_key' COLLATE "C"<=cursor COLLATE "C" THEN RAISE EXCEPTION 'pagination duplicated or reversed'; END IF;
   seen:=array_append(seen,x->>'entry_key');
  END LOOP;
  EXIT WHEN NOT (r->>'has_more')::boolean;
  cursor:=r->>'next_cursor';
  IF page_count>30 THEN RAISE EXCEPTION 'pagination did not terminate'; END IF;
 END LOOP;
 IF cardinality(seen)<>306 THEN RAISE EXCEPTION 'pagination lost clients/indicators: %',cardinality(seen); END IF;
 r:=pg_temp.queue(actor,qt,'queue-101','independent','information_pending');
 IF jsonb_array_length(r->'items')<>1 OR r#>>'{items,0,next_action}'<>'document_goal' THEN RAISE EXCEPTION 'combined filters/missing configuration'; END IF;
 -- New data for only one indicator marks only that indicator stale; does not rewrite its C04 result.
 r:=pg_temp.as_user(actor,format('SELECT public.import_observations(%L,%L,''synthetic-atlas'',%L,%L,true,''queue-new-fact.csv'',%L)',qt,q->>'profile',clock_timestamp()-interval '1 day',clock_timestamp(),jsonb_build_array(jsonb_build_object('line',1,'subject_external_ref','queue-000','indicator_key','independent_minutes','unit','min','value_numeric','80','observed_at',clock_timestamp()-interval '1 hour','idempotency_key',gen_random_uuid()))))::jsonb;
 IF r->>'status'<>'completed' THEN RAISE EXCEPTION 'new fact failed'; END IF;
 r:=pg_temp.queue(actor,qt,'queue-000');
 FOR x IN SELECT value FROM jsonb_array_elements(r->'items') LOOP
  IF (x->>'stale')::boolean IS DISTINCT FROM (x->>'indicator_key'='independent_minutes') THEN RAISE EXCEPTION 'staleness crossed independent indicators'; END IF;
 END LOOP;
 SELECT value INTO sample FROM jsonb_array_elements(f->'customers') WHERE value->>'stage'='prospective';
 SELECT value INTO resolved FROM jsonb_array_elements(f->'customers') WHERE value->>'stage'='historical_resolved';
 SELECT value INTO unmet FROM jsonb_array_elements(f->'customers') WHERE value->>'stage'='historical_unmet';
 SELECT id INTO hc FROM public.cw_operational_cases WHERE evaluation_id=(resolved->>'evaluation_id')::uuid;
 SELECT id INTO uc FROM public.cw_operational_cases WHERE evaluation_id=(unmet->>'evaluation_id')::uuid;
 opening:='{"eligible":true,"configuration_pinned":true,"eligibility_reason":"[SINTÉTICO] Revisão individual","eligibility_ref":"urn:queue:test:opening","opening_criteria":"[SINTÉTICO] Objetivo não demonstrado","closure_criteria":"[SINTÉTICO] Objetivo histórico e revisão humana","closure_ref":"urn:queue:test:closure"}';
 c:=pg_temp.as_user(actor,format('SELECT public.open_operational_case(%L,%L,%L,%L)',t,sample->>'evaluation_id',gen_random_uuid(),opening))::uuid;
 PERFORM pg_temp.expect_case(actor,t,c,'investigation_planning','investigate');
 PERFORM pg_temp.command(op,c,'investigate','{"status":"insufficient","finding":"Falta referência suficiente","reference":"urn:queue:test:investigate","observation_ids":[]}');
 PERFORM pg_temp.expect_case(actor,t,c,'information_pending','investigate');
 PERFORM pg_temp.command(op,c,'investigate','{"status":"hypothesis","finding":"Hipótese explícita","reference":"urn:queue:test:investigate","observation_ids":[]}');
 PERFORM pg_temp.expect_case(actor,t,c,'investigation_planning','investigate');
 PERFORM pg_temp.command(op,c,'investigate',jsonb_build_object('status','confirmed','finding','[SINTÉTICO] confirmação humana','reference','urn:queue:test:investigate','observation_ids',jsonb_build_array(sample->>'proof_id')));
 PERFORM pg_temp.expect_case(op,t,c,'investigation_planning','plan');
 plan:='{"action":"[SINTÉTICO] Ajustar configuração manual","rationale":"Revisão humana","success_conditions":"Objetivo histórico demonstrado","limitations":"Sem causalidade automática","reversal":"Rever antes de repor","reference":"urn:queue:test:plan","observation_seconds":3}';
 PERFORM pg_temp.command(op,c,'plan',plan);
 x:=pg_temp.expect_case(op,t,c,'authorization_execution','authorize');
 IF (x->>'can_prepare')::boolean THEN RAISE EXCEPTION 'operator offered authorization'; END IF;
 approval:=jsonb_build_object('valid_until',clock_timestamp()+interval '1 hour','reference','urn:queue:test:approve','reason','[SINTÉTICO] decisão humana');
 PERFORM pg_temp.command(actor,c,'approve',approval);
 BEGIN
  SELECT * INTO cfg FROM public.c04_configurations WHERE id=(sample->>'configuration_id')::uuid;
  PERFORM pg_temp.as_user(actor,format('SELECT public.save_c04_configuration(%L,%L,%L,%L,%L,%L,%L)',t,cfg.subject_id,cfg.profile_id,cfg.indicator_key,cfg.id,gen_random_uuid(),cfg.definition||'{"target":55}'::jsonb));
  PERFORM pg_temp.expect_case(actor,t,c,'information_pending','review_historical_contract');
  RAISE EXCEPTION 'rollback revision probe' USING ERRCODE='CWQ01';
 EXCEPTION WHEN SQLSTATE 'CWQ01' THEN NULL; END;
 PERFORM pg_temp.expect_case(op,t,c,'authorization_execution','record_execution');
 PERFORM pg_temp.as_user(actor,format('SELECT public.set_member_role(%L,%L,''admin'')',t,viewer));
 PERFORM pg_temp.as_user(viewer,format('SELECT public.set_member_role(%L,%L,''operator'')',t,actor));
 PERFORM pg_temp.expect_case(op,t,c,'authorization_execution','authorize');
 PERFORM pg_temp.as_user(viewer,format('SELECT public.set_member_role(%L,%L,''admin'')',t,actor));
 PERFORM pg_temp.as_user(actor,format('SELECT public.set_member_role(%L,%L,''viewer'')',t,viewer));
 PERFORM pg_temp.command(actor,c,'approve',approval||jsonb_build_object('valid_until',clock_timestamp()+interval '1 second'));
 PERFORM pg_sleep(1.1);
 PERFORM pg_temp.expect_case(actor,t,c,'authorization_execution','authorize');
 PERFORM pg_temp.command(actor,c,'approve',approval);
 PERFORM pg_temp.command(op,c,'record_execution','{"receipt":"[SINTÉTICO] declaração humana","reference":"urn:queue:test:execution"}');
 x:=pg_temp.expect_case(op,t,c,'waiting_observation','wait');
 IF x->>'review_at' IS NULL OR (x->>'review_due')::boolean THEN RAISE EXCEPTION 'window shortened'; END IF;
 PERFORM pg_sleep(3.1); -- Real elapsed explicitly configured test window, not a changed clock.
 x:=pg_temp.expect_case(op,t,c,'results_review','compare');
 IF NOT (x->>'review_due')::boolean OR (SELECT state FROM public.cw_operational_cases WHERE id=c)<>'waiting_observation' THEN RAISE EXCEPTION 'read transitioned case'; END IF;
 PERFORM pg_temp.command(op,c,'observe',jsonb_build_object('bundle_id',sample->>'after_bundle_id'));
 PERFORM pg_temp.expect_case(actor,t,c,'result_open','decide');
 x:='{"close_requested":true,"criteria_met":true,"material_contradiction":false,"reason":"[SINTÉTICO] revisão final","reference":"urn:queue:test:decide"}';
 PERFORM pg_temp.command(actor,c,'decide',x);
 PERFORM pg_temp.expect_case(actor,t,c,'result_open','collect_evidence');
 PERFORM pg_temp.command(op,hc,'observe',jsonb_build_object('bundle_id',resolved->>'after_bundle_id'));
 PERFORM pg_temp.expect_case(actor,t,hc,'results_review','decide');
 PERFORM pg_temp.command(actor,hc,'decide',x);
 PERFORM pg_temp.expect_case(viewer,t,hc,'closed','consult_history');
 PERFORM pg_temp.command(op,uc,'observe',jsonb_build_object('bundle_id',unmet->>'after_bundle_id'));
 PERFORM pg_temp.command(actor,uc,'decide',x);
 PERFORM pg_temp.expect_case(viewer,t,uc,'result_open','collect_evidence');
 SELECT * INTO cfg FROM public.c04_configurations WHERE id=(sample->>'configuration_id')::uuid;
 newcfg:=pg_temp.as_user(actor,format('SELECT public.save_c04_configuration(%L,%L,%L,%L,%L,%L,%L)',t,cfg.subject_id,cfg.profile_id,cfg.indicator_key,cfg.id,gen_random_uuid(),cfg.definition||'{"target":55}'::jsonb))::uuid;
 y:=pg_temp.expect_case(actor,t,c,'information_pending','review_historical_contract');
 IF NOT (y->>'stale')::boolean OR y->>'configuration_id'<>cfg.id::text THEN RAISE EXCEPTION 'historical configuration overwritten'; END IF;
 RAISE NOTICE 'Follow-up review passed: 306 independent entries, pagination, filters, RLS/roles, authorization expiry/revocation, actual server clock, C09 insufficiency, remain_open/closure and historical revisions. Every projection read preserved cases/evaluations/audit.';
END $tests$;
