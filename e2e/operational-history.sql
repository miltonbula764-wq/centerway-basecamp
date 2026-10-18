-- OWNER-ONLY SYNTHETIC RETROSPECTIVE FIXTURE, never a production RPC or a proof of past authorization.
DO $fixture$
DECLARE f jsonb:=current_setting('cw.mvp_fixture')::jsonb; x jsonb; c uuid; t uuid:=(f->>'tenant')::uuid;
 actor uuid:=(f->>'actor')::uuid; exec_at timestamptz:=(f->>'executed_at')::timestamptz; seq int; d jsonb; cmd text; st text; prior text; proof public.observations;
BEGIN
 FOR x IN SELECT value FROM jsonb_array_elements(f->'customers') WHERE value->>'stage' LIKE 'historical_%' LOOP
  SELECT * INTO proof FROM public.observations WHERE tenant_id=t AND id=(x->>'proof_id')::uuid;
  INSERT INTO public.cw_operational_cases(tenant_id,subject_id,evaluation_id,configuration_id,contract_version,opening_definition,operation_id,request_hash,state,version,created_by)
   VALUES(t,(x->>'subject_id')::uuid,(x->>'evaluation_id')::uuid,(x->>'configuration_id')::uuid,'individual-review-v1',
    '{"eligible":true,"configuration_pinned":true,"eligibility_reason":"[SINTÉTICO] Revisão individual autorizada para demonstração retrospectiva","eligibility_ref":"urn:atlas:fixture:opening","opening_criteria":"[SINTÉTICO] Meta individual não atingida, sem exigir deterioração","closure_criteria":"[SINTÉTICO] Duas janelas diárias até 60 min, posteriores à execução, mínimo 3 dias de observação, sem pendências e com revisão humana","closure_ref":"urn:atlas:fixture:closure"}',gen_random_uuid(),'synthetic-retrospective','waiting_observation',4,actor) RETURNING id INTO c;
  FOR seq IN 0..4 LOOP
   cmd:=(ARRAY['open','investigate','plan','approve','record_execution'])[seq+1];
   st:=(ARRAY['investigation','impediment_confirmed','awaiting_approval','approved','waiting_observation'])[seq+1];
   prior:=CASE WHEN seq>0 THEN (ARRAY['investigation','impediment_confirmed','awaiting_approval','approved'])[seq] END;
   d:=jsonb_build_object('fixture','synthetic_retrospective_history','notice','Histórico fictício carregado pelo proprietário na base descartável. Não prova execução ou aprovação histórica.');
   IF seq=0 THEN d:=d||jsonb_build_object('evaluation_id',x->>'evaluation_id','configuration_id',x->>'configuration_id'); END IF;
   IF seq=1 THEN d:=d||jsonb_build_object('status','confirmed','finding','[SINTÉTICO] Condição documentada, confirmada por pessoa.','reference','urn:atlas:fixture:investigation','evidence',jsonb_build_array(jsonb_build_object('id',proof.id,'indicator_key',proof.indicator_key,'payload_hash',proof.payload_hash))); END IF;
   IF seq=2 THEN d:=d||jsonb_build_object('action','[SINTÉTICO] Ajuste humano de configuração documentado.','rationale','[SINTÉTICO] Investigar condição que impede o objetivo.','success_conditions','[SINTÉTICO] Meta histórica e revisão documental.','limitations','Sem causalidade comprovada.','reversal','Revisão humana antes de repor configuração.','observation_seconds',259200); END IF;
   IF seq=3 THEN d:=d||jsonb_build_object('valid_until',exec_at+interval '1 day','reference','urn:atlas:fixture:authorization'); END IF;
   IF seq=4 THEN d:=d||jsonb_build_object('executed_at',exec_at,'wait_until',exec_at+interval '3 days','execution_type','synthetic_retrospective_human_report','value_recovery','not_proven'); END IF;
   INSERT INTO public.cw_operational_events(tenant_id,subject_id,case_id,sequence,operation_id,request_hash,command,from_state,to_state,details,created_by)
    VALUES(t,(x->>'subject_id')::uuid,c,seq,gen_random_uuid(),'synthetic-retrospective',cmd,prior,st,d,actor);
  END LOOP;
 END LOOP;
END $fixture$;
