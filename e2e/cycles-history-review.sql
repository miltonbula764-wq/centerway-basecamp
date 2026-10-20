-- Owner-only, rolled-back retrospective fixture. Not proof of past authorization/execution.
DO $test$
DECLARE f jsonb:=current_setting('cw.cycle_history_fixture')::jsonb;x jsonb;c public.cw_operational_cases;
 t uuid:=(f->>'tenant')::uuid;actor uuid:=(f->>'actor')::uuid;operator_id uuid:=(f->>'operator')::uuid;
 cycle uuid:=gen_random_uuid();decision uuid;finding uuid;plan uuid;approval uuid;receipt uuid;v uuid;r record;
 d jsonb;exec_at timestamptz:=(f->>'executed_at')::timestamptz+interval '1 day';s integer;h jsonb;
BEGIN
 CREATE FUNCTION pg_temp.history_cmd(_actor uuid,_case uuid,_command text,_payload jsonb) RETURNS uuid LANGUAGE plpgsql AS $fn$
 DECLARE c public.cw_operational_cases;answer uuid;BEGIN
  SELECT * INTO c FROM public.cw_operational_cases WHERE id=_case;
  PERFORM set_config('request.jwt.claims',jsonb_build_object('role','authenticated','sub',_actor)::text,true);
  SET LOCAL ROLE authenticated;
  answer:=public.command_operational_case(c.tenant_id,c.id,c.version,gen_random_uuid(),_command,_payload);
  RESET ROLE;RETURN answer;
 EXCEPTION WHEN OTHERS THEN RESET ROLE;RAISE;
 END $fn$;
 SELECT value INTO x FROM jsonb_array_elements(f->'customers') WHERE value->>'stage'='historical_resolved';
 SELECT * INTO c FROM public.cw_operational_cases WHERE tenant_id=t AND evaluation_id=(x->>'evaluation_id')::uuid;
 PERFORM pg_temp.history_cmd(operator_id,c.id,'observe',jsonb_build_object('bundle_id',x->>'after_bundle_id'));
 decision:=pg_temp.history_cmd(actor,c.id,'decide','{"close_requested":false,"criteria_met":true,"material_contradiction":false,"reason":"[SYNTHETIC] Retrospective continuity fixture","reference":"urn:cycles:history:decision"}');
 SELECT * INTO c FROM public.cw_operational_cases WHERE id=c.id;
 IF c.state<>'remain_open' THEN RAISE EXCEPTION 'fixture continuity unavailable'; END IF;
 -- Explicit retrospective second-cycle fixture; no clock manipulation or historical user session.
 INSERT INTO public.cw_operational_cycles(id,tenant_id,case_id,number,start_sequence,reason,reference,previous_decision_id,created_by,created_at)
 VALUES(cycle,t,c.id,2,c.version+1,'[SYNTHETIC RETROSPECTIVE] second intervention; not a real elapsed human journey','urn:cycles:history:fixture',decision,actor,exec_at-interval '1 hour');
 s:=c.version+1;
 INSERT INTO public.cw_operational_events(tenant_id,subject_id,case_id,sequence,operation_id,request_hash,command,from_state,to_state,details,created_by)
 VALUES(t,c.subject_id,c.id,s,gen_random_uuid(),'synthetic-retrospective','start_cycle','remain_open','investigation',jsonb_build_object('fixture','synthetic_retrospective_history','cycle_id',cycle,'cycle_number',2,'previous_decision_id',decision),actor);
 FOR r IN SELECT * FROM public.cw_operational_events WHERE case_id=c.id AND sequence BETWEEN 1 AND 4 ORDER BY sequence LOOP
  s:=s+1;v:=gen_random_uuid();d:=r.details||jsonb_build_object('cycle_id',cycle,'cycle_number',2,'fixture','synthetic_retrospective_history');
  IF r.command='investigate' THEN finding:=v;END IF;
  IF r.command='plan' THEN plan:=v;d:=d||jsonb_build_object('investigation_event_id',finding);END IF;
  IF r.command='approve' THEN approval:=v;d:=d||jsonb_build_object('plan_event_id',plan,'valid_until',exec_at+interval '1 day');END IF;
  IF r.command='record_execution' THEN receipt:=v;d:=d||jsonb_build_object('approval_event_id',approval,'plan_event_id',plan,'executed_at',exec_at,'wait_until',exec_at+interval '3 days');END IF;
  INSERT INTO public.cw_operational_events(id,tenant_id,subject_id,case_id,sequence,operation_id,request_hash,command,from_state,to_state,details,created_by)
  VALUES(v,t,c.subject_id,c.id,s,gen_random_uuid(),'synthetic-retrospective',r.command,r.from_state,r.to_state,d,actor);
 END LOOP;
 UPDATE public.cw_operational_cases SET state='waiting_observation',version=s WHERE id=c.id;
 BEGIN
  PERFORM pg_temp.history_cmd(actor,c.id,'decide','{}');RAISE EXCEPTION 'earlier comparison reused';
 EXCEPTION WHEN SQLSTATE '22023' THEN IF SQLERRM<>'comparison_required' THEN RAISE;END IF;END;
 v:=pg_temp.history_cmd(operator_id,c.id,'observe',jsonb_build_object('bundle_id',x->>'after_bundle_id'));
 SELECT details INTO d FROM public.cw_operational_events WHERE id=v;
 IF d->>'cycle_id'<>cycle::text OR d->>'result'<>'achieved' OR NOT (d->>'sufficient')::boolean OR (d->>'executed_at')::timestamptz<>exec_at THEN RAISE EXCEPTION 'second cycle valid comparison failed';END IF;
 PERFORM pg_temp.history_cmd(actor,c.id,'decide','{"close_requested":true,"criteria_met":true,"material_contradiction":false,"reason":"[SYNTHETIC] Current cycle evidence and human criteria review","reference":"urn:cycles:history:closure"}');
 IF (SELECT state FROM public.cw_operational_cases WHERE id=c.id)<>'closed_resolved' THEN RAISE EXCEPTION 'valid second cycle closure failed';END IF;
 BEGIN
  PERFORM pg_temp.history_cmd(actor,c.id,'start_cycle','{"reason":"[SYNTHETIC] denied reopening","reference":"urn:cycles:history:denied"}');RAISE EXCEPTION 'closed case reopened';
 EXCEPTION WHEN SQLSTATE '22023' THEN IF SQLERRM<>'case_closed' THEN RAISE;END IF;END;
 PERFORM set_config('request.jwt.claims',jsonb_build_object('role','authenticated','sub',operator_id)::text,true);
 SET LOCAL ROLE authenticated;
 h:=public.operational_cycle_history(t,c.id);
 RESET ROLE;
 IF h#>>'{current,id}'<>cycle::text OR h#>>'{heads,record_execution,id}'<>receipt::text OR h#>>'{heads,decide,to_state}'<>'closed_resolved' THEN RAISE EXCEPTION 'closure history selected wrong cycle';END IF;
 RAISE NOTICE 'Retrospective fixture passed: sufficient C09/authorized C10 closes cycle two, no reuse of cycle-one comparison, no reopening; owner synthetic setup and SQL role/claims are not proof of historical human execution. All fixture writes rolled back.';
END $test$;
