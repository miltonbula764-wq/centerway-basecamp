-- EXPLICIT OWNER-ONLY SYNTHETIC RETROSPECTIVE FIXTURE. Disposable DB only.
-- Does not prove historical authorization/execution or an elapsed prospective window.
-- Real HTTP opening and C01-C04 remain intact. Only four synthetic historical events
-- and their case projection are mounted for current authenticated C09/C10 checks.
DO $fixture$
DECLARE f jsonb:=current_setting('cw.core_fixture')::jsonb; x jsonb; c public.cw_operational_cases;
 proof public.observations; actor uuid:=(f->>'actor')::uuid; exec_at timestamptz:=(f->>'executed_at')::timestamptz;
 seq int; cmd text; prior text; st text; d jsonb; finding_id uuid; plan_id uuid; approval_id uuid; eid uuid;
BEGIN
 FOR x IN SELECT value FROM jsonb_array_elements(f->'cases') LOOP
  SELECT * INTO c FROM public.cw_operational_cases WHERE id=(x->>'case')::uuid AND tenant_id=(f->>'tenant')::uuid;
  IF c.id IS NULL OR c.state<>'investigation' OR c.version<>0 THEN RAISE EXCEPTION 'Retrospective fixture requires a freshly HTTP-opened case'; END IF;
  SELECT * INTO proof FROM public.observations WHERE id=(x->>'proof')::uuid AND tenant_id=c.tenant_id AND subject_id=c.subject_id;
  IF proof.id IS NULL THEN RAISE EXCEPTION 'Fixture proof must be an actual same-client C01 observation'; END IF;
  FOR seq IN 1..4 LOOP
   cmd:=(ARRAY['investigate','plan','approve','record_execution'])[seq];
   prior:=(ARRAY['investigation','impediment_confirmed','awaiting_approval','approved'])[seq];
   st:=(ARRAY['impediment_confirmed','awaiting_approval','approved','waiting_observation'])[seq];
   d:=jsonb_build_object('fixture','synthetic_retrospective_history','notice','Owner-loaded synthetic history; not evidence of past authorization or execution.','cycle_id',c.id,'cycle_number',1);
   IF seq=1 THEN d:=d||jsonb_build_object('status','confirmed','finding','[SYNTHETIC RETROSPECTIVE] Human interpretation fixture','reference','urn:sentinel:fixture:investigation','confirmation','human_interpretation','causality','not_established','reference_validation','syntax_and_internal_ownership_only','evidence',jsonb_build_array(jsonb_build_object('id',proof.id,'indicator_key',proof.indicator_key,'payload_hash',proof.payload_hash,'value_numeric',proof.value_numeric,'unit',proof.unit,'source',proof.source,'observed_at',proof.observed_at))); END IF;
   IF seq=2 THEN d:=d||jsonb_build_object('action','[SYNTHETIC RETROSPECTIVE] Human checklist fixture','rationale','Bounded fixture','success_conditions','Historical individual goal and human review','limitations','No causal claim','reversal','Human review','reference','urn:sentinel:fixture:plan','observation_seconds',259200,'investigation_event_id',finding_id,'historical_configuration_id',c.configuration_id); END IF;
   IF seq=3 THEN d:=d||jsonb_build_object('valid_until',exec_at+interval '1 day','reference','urn:sentinel:fixture:approval','reason','Synthetic historical approval, never validated retrospectively by a production RPC','authorized_by',actor,'plan_event_id',plan_id); END IF;
   IF seq=4 THEN d:=d||jsonb_build_object('executed_at',exec_at,'wait_until',exec_at+interval '3 days','execution_type','synthetic_retrospective_human_report','value_recovery','not_proven','receipt','[SYNTHETIC RETROSPECTIVE] No external action certified','reference','urn:sentinel:fixture:receipt','approval_event_id',approval_id,'plan_event_id',plan_id); END IF;
   INSERT INTO public.cw_operational_events(tenant_id,subject_id,case_id,sequence,operation_id,request_hash,command,from_state,to_state,details,created_by)
     VALUES(c.tenant_id,c.subject_id,c.id,seq,gen_random_uuid(),'synthetic-retrospective-fixture',cmd,prior,st,d,actor) RETURNING id INTO eid;
   IF seq=1 THEN finding_id:=eid; ELSIF seq=2 THEN plan_id:=eid; ELSIF seq=3 THEN approval_id:=eid; END IF;
  END LOOP;
  UPDATE public.cw_operational_cases SET state='waiting_observation',version=4 WHERE id=c.id;
 END LOOP;
END $fixture$;
