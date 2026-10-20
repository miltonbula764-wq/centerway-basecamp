-- All probes run in one transaction, rolled back. Synthetic facts remain labelled.
CREATE FUNCTION pg_temp.as_user(uid uuid,statement text) RETURNS jsonb LANGUAGE plpgsql AS $$
DECLARE r jsonb;BEGIN
 PERFORM set_config('request.jwt.claims',jsonb_build_object('role','authenticated','sub',uid)::text,true);
 SET LOCAL ROLE authenticated;EXECUTE statement INTO r;RESET ROLE;RETURN r;
EXCEPTION WHEN OTHERS THEN RESET ROLE;RAISE;END $$;
CREATE FUNCTION pg_temp.cmd(uid uuid,cid uuid,command text,payload jsonb) RETURNS uuid LANGUAGE plpgsql AS $$
DECLARE c public.cw_operational_cases;r jsonb;BEGIN SELECT * INTO c FROM public.cw_operational_cases WHERE id=cid;
 r:=pg_temp.as_user(uid,format('SELECT to_jsonb(public.command_operational_case(%L,%L,%s,%L,%L,%L))',c.tenant_id,c.id,c.version,gen_random_uuid(),command,payload));RETURN (r#>>'{}')::uuid;END $$;
DO $$
DECLARE f jsonb:=current_setting('cw.responsibility_fixture')::jsonb;t uuid:=(f->>'tenant')::uuid;c uuid:=(f->>'case')::uuid;a uuid:=(f->>'admin')::uuid;o uuid:=(f->>'operator')::uuid;
 q jsonb;facts jsonb;plan uuid;plan2 uuid;n integer;v integer;rev integer;notice public.cw_notifications;before jsonb;after jsonb;page jsonb;cursor public.cw_notifications;count1 integer;key uuid;
BEGIN
 -- A real plan requires the existing C05 proof and produces one administrator-only notice.
 PERFORM pg_temp.cmd(o,c,'investigate',jsonb_build_object('status','confirmed','finding','[SINTÉTICO] Facto revisto','reference','urn:notifications:investigation','observation_ids',jsonb_build_array(f->>'proof')));
 plan:=pg_temp.cmd(o,c,'plan','{"action":"[SINTÉTICO] Ação humana","rationale":"[SINTÉTICO] Fundamento","success_conditions":"Objetivo histórico com prova posterior","limitations":"Sem causalidade","reversal":"Revisão antes da reversão","reference":"urn:notifications:plan","observation_seconds":1}');
 SELECT to_jsonb(k) INTO before FROM cw_operational_cases k WHERE id=c;
 PERFORM pg_temp.as_user(a,format('SELECT public.prepare_operational_notifications(%L)',t));
 IF (SELECT count(*) FROM cw_notifications WHERE source_id=plan AND kind='authorization_needed')<>1 THEN RAISE EXCEPTION 'missing/duplicate authorization notice';END IF;
 SELECT * INTO notice FROM cw_notifications WHERE source_id=plan;
 IF notice.recipient_id<>a OR notice.required_role<>'admin' THEN RAISE EXCEPTION 'authorization privacy';END IF;
 -- Monitor snapshots of the same plan must not create a second notice.
 SELECT value INTO q FROM jsonb_array_elements(public._core_followup_engine(t,'','','','',100,(f->>'subject')::uuid,c)->'items') WHERE value->>'case_id'=c::text;
 -- The private classifier requires a member claim, including owner-only test fixtures.
 PERFORM public._review_store(t,q,public._review_facts(t,q),gen_random_uuid());PERFORM public._notification_process(t,25);
 IF (SELECT count(*) FROM cw_notifications WHERE source_id=plan)<>1 THEN RAISE EXCEPTION 'monitor duplicated Core plan';END IF;
 SELECT to_jsonb(k) INTO after FROM cw_operational_cases k WHERE id=c;IF before<>after THEN RAISE EXCEPTION 'notification mutated Core';END IF;
 -- Existing permission contracts still reject an assigned operator's approval.
 BEGIN PERFORM pg_temp.cmd(o,c,'approve',jsonb_build_object('valid_until',clock_timestamp()+interval '1 hour','reason','[SINTÉTICO] Negado','reference','urn:notifications:denied'));RAISE EXCEPTION 'assigned operator approved';EXCEPTION WHEN insufficient_privilege THEN NULL;END;
 PERFORM pg_temp.cmd(a,c,'approve',jsonb_build_object('valid_until',clock_timestamp()+interval '1 hour','reason','[SINTÉTICO] Aprovação humana','reference','urn:notifications:approve'));
 PERFORM pg_temp.cmd(o,c,'record_execution','{"receipt":"[SINTÉTICO] Registo humano","reference":"urn:notifications:receipt"}');
 SELECT value INTO q FROM jsonb_array_elements(public._core_followup_engine(t,'','','','',100,(f->>'subject')::uuid,c)->'items') WHERE value->>'case_id'=c::text;
 facts:=public._review_facts(t,q);IF facts->>'status'<>'waiting' THEN RAISE EXCEPTION 'C08 not waiting';END IF;
 PERFORM public._review_store(t,q,facts,gen_random_uuid());PERFORM public._notification_process(t,25);
 IF EXISTS(SELECT FROM cw_notifications WHERE case_id=c AND kind='observation_ended') THEN RAISE EXCEPTION 'early C08 notification';END IF;
 PERFORM pg_sleep(1.1); -- Actual one-second configured test window, not an artificial clock.
 SELECT value INTO q FROM jsonb_array_elements(public._core_followup_engine(t,'','','','',100,(f->>'subject')::uuid,c)->'items') WHERE value->>'case_id'=c::text;
 facts:=public._review_facts(t,q);PERFORM public._review_store(t,q,facts,gen_random_uuid());PERFORM public._notification_process(t,25);
 IF NOT EXISTS(SELECT FROM cw_notifications WHERE case_id=c AND kind='observation_ended' AND recipient_id=o) THEN RAISE EXCEPTION 'elapsed window not routed to owner: % / %',q,facts;END IF;
 PERFORM pg_temp.cmd(o,c,'observe',jsonb_build_object('bundle_id',f->>'after_bundle'));
 PERFORM pg_temp.cmd(a,c,'decide','{"close_requested":true,"criteria_met":true,"material_contradiction":false,"reason":"[SINTÉTICO] Sem prova suficiente","reference":"urn:notifications:decision"}');
 IF (SELECT state FROM cw_operational_cases WHERE id=c)<>'remain_open' THEN RAISE EXCEPTION 'notification treated window/receipt as value';END IF;
 PERFORM pg_temp.cmd(a,c,'start_cycle','{"reason":"[SINTÉTICO] Nova decisão humana","reference":"urn:notifications:cycle"}');
 PERFORM pg_temp.cmd(o,c,'investigate',jsonb_build_object('status','confirmed','finding','[SINTÉTICO] Outro ciclo','reference','urn:notifications:investigation2','observation_ids',jsonb_build_array(f->>'proof')));
 plan2:=pg_temp.cmd(o,c,'plan','{"action":"[SINTÉTICO] Outra ação","rationale":"[SINTÉTICO] Novo fundamento","success_conditions":"Prova deste ciclo","limitations":"Sem causalidade","reversal":"Revisão humana","reference":"urn:notifications:plan2","observation_seconds":1}');
 PERFORM pg_temp.as_user(a,format('SELECT public.prepare_operational_notifications(%L)',t));
 IF (SELECT count(*) FROM cw_notifications WHERE source_id IN(plan,plan2) AND kind='authorization_needed')<>2 THEN RAISE EXCEPTION 'independent cycles collapsed';END IF;
 -- Inbox and assignment history use stable keyset pagination, with no writes on reading.
 FOR n IN 1..28 LOOP
  SELECT revision INTO rev FROM cw_case_assignments WHERE case_id=c ORDER BY revision DESC LIMIT 1;
  PERFORM pg_temp.as_user(a,format('SELECT to_jsonb(public.assign_operational_case(%L,%L,%L,%L,%L,%s,%L))',t,c,CASE WHEN n%2=0 THEN o ELSE a END,'[SINTÉTICO] Substituição documentada','urn:notifications:pagination',rev,gen_random_uuid()));
 END LOOP;
 page:=pg_temp.as_user(o,format('SELECT public.notification_inbox(%L,_limit=>2)',t));IF NOT (page->>'has_more')::boolean THEN RAISE EXCEPTION 'inbox pagination';END IF;
 SELECT * INTO cursor FROM cw_notifications WHERE id=(page#>>'{items,1,id}')::uuid;
 page:=pg_temp.as_user(o,format('SELECT public.notification_inbox(%L,_before=>%L,_before_id=>%L,_limit=>2)',t,cursor.created_at,cursor.id));
 IF EXISTS(SELECT FROM jsonb_array_elements(page->'items') x WHERE (x->>'id')::uuid=cursor.id) THEN RAISE EXCEPTION 'cursor repeated';END IF;
 page:=pg_temp.as_user(a,format('SELECT public.case_responsibility(%L,%L,_limit=>2)',t,c));IF NOT (page->>'has_more')::boolean THEN RAISE EXCEPTION 'history pagination';END IF;
 RAISE NOTICE 'PASS notification SQL: actual Core C05-C10 events, admin-only plan, monitor dedup, configured C08 waiting/elapsed, no receipt/value confusion, remain_open and independent new cycle, inbox/history pagination. All writes rolled back.';
END $$;
