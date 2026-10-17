-- ONLY disposable fixture loader; not a product RPC or proof of elapsed live time.
-- Passed by scripts/mvp/load-history.py after localhost/GitHub-hosted checks.
DO $fixture$
DECLARE f jsonb := current_setting('cw.mvp_fixture')::jsonb; x jsonb; c uuid; t uuid := (f->>'tenant')::uuid;
  s uuid; actor uuid := (f->>'actor')::uuid; exec_at timestamptz := (f->>'executed_at')::timestamptz;
  cmd text; seq int; result jsonb; d jsonb; st text;
BEGIN
  FOR x IN SELECT value FROM jsonb_array_elements(f->'cases') WHERE value->>'stage' LIKE 'historical_%' LOOP
    s := (x->>'subject_id')::uuid;
    INSERT INTO public.cw_cases(tenant_id,subject_id,assessment_id,policy_version,state,version,created_by)
      VALUES(t,s,(x->>'assessment_id')::uuid,'flowreports-demo-v1','waiting_observation',4,actor) RETURNING id INTO c;
    FOR seq IN 0..4 LOOP
      cmd := (ARRAY['open','investigate','plan','approve','record_execution'])[seq+1];
      st := (ARRAY['investigation','impediment_found','awaiting_approval','approved','waiting_observation'])[seq+1];
      d := jsonb_build_object('fixture','synthetic_retrospective_history','notice','Carga de histórico fictício, não execução observada nem prova de espera real.');
      IF seq=0 THEN d:=d||jsonb_build_object('assessment_id',x->>'assessment_id','objective_id',x->>'objective_id'); END IF;
      IF seq=1 THEN d:=d||jsonb_build_object('component','C05','status','confirmed_blocker','observation_id',x->>'proof_id','finding','[SINTÉTICO] Integração necessária desativada.'); END IF;
      IF seq=2 THEN d:=d||jsonb_build_object('component','C06','action','manual_enable_integration','instructions','[SINTÉTICO] Verificar, reativar manualmente e guardar recibo.','observation_days',14); END IF;
      IF seq=3 THEN d:=d||jsonb_build_object('component','C07','expires_at',exec_at+interval '24 hours'); END IF;
      IF seq=4 THEN d:=d||jsonb_build_object('component','C07/C08','execution_kind','synthetic_retrospective_human_report','receipt','[SINTÉTICO] Recibo histórico DEMO-002','executed_at',exec_at,'wait_until',exec_at+interval '14 days','value_realized',false); END IF;
      INSERT INTO public.cw_case_events(tenant_id,subject_id,case_id,sequence,operation_id,command,request_hash,from_state,to_state,details,policy_version,created_by)
        VALUES(t,s,c,seq,gen_random_uuid(),cmd,'synthetic-fixture',CASE WHEN seq>0 THEN (ARRAY['investigation','impediment_found','awaiting_approval','approved'])[seq] END,st,d,'flowreports-demo-v1',actor);
    END LOOP;
    -- These two transitions ARE evaluated by real Core RPCs under authenticated claims.
    PERFORM set_config('request.jwt.claims',jsonb_build_object('sub',actor,'role','authenticated')::text,true);
    SET LOCAL ROLE authenticated;
    result := public.command_demo_case(t,c,4,gen_random_uuid(),'observe',jsonb_build_object('bundle_id',x->>'after_bundle_id'));
    result := public.command_demo_case(t,c,5,gen_random_uuid(),'decide','{}');
    RESET ROLE;
    IF x->>'stage'='historical_resolved' AND result->>'to_state'<>'closed_resolved' THEN RAISE EXCEPTION 'resolved fixture did not meet criteria: %',result; END IF;
    IF x->>'stage'='historical_open' AND result->>'to_state'<>'remain_open' THEN RAISE EXCEPTION 'unmet objective closed unexpectedly: %',result; END IF;
  END LOOP;
END $fixture$;
