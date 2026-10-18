-- Explicit synthetic pilot only. See docs/MVP_JOURNEY_CONTRACT.md.
ALTER TABLE public.c03_bundles ADD CONSTRAINT c03_bundles_tenant_subject_id_key UNIQUE (tenant_id,subject_id,id);
CREATE TABLE public.cw_objectives (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES public.tenants(id),
  subject_id uuid NOT NULL,
  profile_id uuid NOT NULL,
  policy_version text NOT NULL CHECK (policy_version = 'flowreports-demo-v1'),
  deadline timestamptz NOT NULL,
  measurement_source text NOT NULL CHECK (length(btrim(measurement_source)) BETWEEN 1 AND 200),
  capacity_ref text NOT NULL CHECK (length(btrim(capacity_ref)) BETWEEN 1 AND 1000),
  commitment_ref text NOT NULL CHECK (length(btrim(commitment_ref)) BETWEEN 1 AND 1000),
  customer_confirmation_ref text NOT NULL CHECK (length(btrim(customer_confirmation_ref)) BETWEEN 1 AND 1000),
  created_by uuid NOT NULL,
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  UNIQUE (tenant_id, id), UNIQUE (tenant_id, subject_id, id),
  FOREIGN KEY (tenant_id, subject_id) REFERENCES public.subjects(tenant_id,id),
  FOREIGN KEY (tenant_id, profile_id) REFERENCES public.tenant_value_profiles(tenant_id,id)
);

CREATE TABLE public.cw_assessments (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES public.tenants(id),
  subject_id uuid NOT NULL,
  objective_id uuid NOT NULL,
  bundle_id uuid NOT NULL,
  policy_version text NOT NULL CHECK (policy_version = 'flowreports-demo-v1'),
  result text NOT NULL CHECK (result IN ('achieved','not_achieved','pending_deadline','inconclusive')),
  evidence text NOT NULL CHECK (evidence IN ('sufficient','insufficient')),
  details jsonb NOT NULL,
  created_by uuid NOT NULL,
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  UNIQUE (tenant_id,id), UNIQUE (tenant_id,subject_id,id), UNIQUE (objective_id,bundle_id),
  FOREIGN KEY (tenant_id,subject_id,objective_id) REFERENCES public.cw_objectives(tenant_id,subject_id,id),
  FOREIGN KEY (tenant_id,subject_id,bundle_id) REFERENCES public.c03_bundles(tenant_id,subject_id,id)
);

CREATE TABLE public.cw_cases (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES public.tenants(id),
  subject_id uuid NOT NULL,
  assessment_id uuid NOT NULL UNIQUE,
  policy_version text NOT NULL CHECK (policy_version = 'flowreports-demo-v1'),
  state text NOT NULL CHECK (state IN ('investigation','needs_information','impediment_found','awaiting_approval','approved','waiting_observation','observed','remain_open','closed_resolved')),
  version integer NOT NULL DEFAULT 0,
  created_by uuid NOT NULL,
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  UNIQUE (tenant_id,id), UNIQUE (tenant_id,subject_id,id),
  FOREIGN KEY (tenant_id,subject_id,assessment_id) REFERENCES public.cw_assessments(tenant_id,subject_id,id)
);

CREATE TABLE public.cw_case_events (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES public.tenants(id),
  subject_id uuid NOT NULL,
  case_id uuid NOT NULL,
  sequence integer NOT NULL,
  operation_id uuid NOT NULL,
  command text NOT NULL,
  request_hash text NOT NULL,
  from_state text,
  to_state text NOT NULL,
  details jsonb NOT NULL,
  policy_version text NOT NULL CHECK (policy_version = 'flowreports-demo-v1'),
  created_by uuid NOT NULL,
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  UNIQUE (tenant_id,id), UNIQUE (case_id,sequence), UNIQUE (case_id,operation_id),
  FOREIGN KEY (tenant_id,subject_id,case_id) REFERENCES public.cw_cases(tenant_id,subject_id,id)
);

DO $$ DECLARE t text; BEGIN
  FOREACH t IN ARRAY ARRAY['cw_objectives','cw_assessments','cw_cases','cw_case_events'] LOOP
    EXECUTE format('REVOKE ALL ON public.%I FROM PUBLIC, anon, authenticated',t);
    EXECUTE format('GRANT SELECT ON public.%I TO authenticated',t);
    EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY',t);
    EXECUTE format('CREATE POLICY tenant_read ON public.%I FOR SELECT TO authenticated USING (public.is_tenant_member(tenant_id))',t);
    EXECUTE format('CREATE TRIGGER identity_guard BEFORE UPDATE ON public.%I FOR EACH ROW EXECUTE FUNCTION public._cw_lock_columns()',t);
    EXECUTE format('CREATE TRIGGER audit AFTER INSERT OR UPDATE ON public.%I FOR EACH ROW EXECUTE FUNCTION public._cw_audit()',t);
    IF t <> 'cw_cases' THEN
      EXECUTE format('CREATE TRIGGER immutable BEFORE UPDATE OR DELETE ON public.%I FOR EACH ROW EXECUTE FUNCTION public._c02_immutable()',t);
    END IF;
  END LOOP;
END $$;

-- A single, documented evaluator for this pilot; never a universal value classifier.
CREATE FUNCTION public._cw_demo_evaluate(_objective public.cw_objectives, _bundle uuid, _after timestamptz DEFAULT NULL)
RETURNS jsonb LANGUAGE plpgsql SET search_path = public AS $$
DECLARE b public.c03_bundles; r public.c02_runs; i public.c03_indicators;
  p jsonb; w jsonb; wins jsonb := '[]'; n int := 0; good boolean := true;
  all_met boolean := true; avg_value numeric := 0; start_at timestamptz; end_at timestamptz;
BEGIN
  SELECT * INTO b FROM public.c03_bundles WHERE tenant_id=_objective.tenant_id AND id=_bundle AND subject_id=_objective.subject_id;
  IF NOT FOUND THEN RAISE EXCEPTION 'bundle_not_found' USING ERRCODE='22023'; END IF;
  SELECT * INTO r FROM public.c02_runs WHERE tenant_id=b.tenant_id AND id=b.run_id;
  IF r.profile_id IS DISTINCT FROM _objective.profile_id OR r.algorithm_version <> 'c02-v2' THEN
    RAISE EXCEPTION 'historical_profile_mismatch' USING ERRCODE='22023'; END IF;
  SELECT * INTO i FROM public.c03_indicators WHERE tenant_id=b.tenant_id AND bundle_id=b.id AND indicator_key='report_hours';
  p := i.snapshot #> '{details,parameters}';
  IF i.id IS NULL OR i.status <> 'complete' OR i.snapshot->>'classification' <> 'outcome'
    OR p->>'unit' IS DISTINCT FROM 'h/semana' OR p->>'direction' IS DISTINCT FROM 'lower_is_better'
    OR p->>'aggregation' IS DISTINCT FROM 'mean' OR p->>'denominator_mode' IS DISTINCT FROM 'observation_count'
    OR p->>'baseline_method' IS DISTINCT FROM 'fixed_value'
    OR (p->>'expected_cadence_days')::int IS DISTINCT FROM 7
    OR (p->>'observation_window_days')::int IS DISTINCT FROM 7
    OR (p->>'min_coverage_pct')::numeric IS DISTINCT FROM 100
    OR (p->>'baseline_value')::numeric IS DISTINCT FROM 10
    OR (p->>'target_value')::numeric IS DISTINCT FROM 4 THEN good := false; END IF;
  FOR w IN SELECT value FROM jsonb_array_elements(coalesce(i.snapshot #> '{details,windows}','[]'))
      WHERE value->>'label' IN ('current_1','current_2') LOOP
    n := n+1; wins := wins || jsonb_build_array(w);
    IF (w->>'sufficient')::boolean IS DISTINCT FROM true OR w->>'source' IS DISTINCT FROM _objective.measurement_source
      OR w->>'value' IS NULL OR (_after IS NOT NULL AND (w->>'start')::timestamptz < _after)
      OR (w->>'end')::timestamptz > clock_timestamp() THEN good := false; END IF;
    all_met := all_met AND coalesce((w->>'value')::numeric <= 4,false);
    avg_value := avg_value + coalesce((w->>'value')::numeric,0);
    start_at := least(start_at,(w->>'start')::timestamptz);
    end_at := greatest(end_at,(w->>'end')::timestamptz);
  END LOOP;
  good := good AND n=2;
  RETURN jsonb_build_object('bundle_id',b.id,'run_id',r.id,'as_of',r.as_of,'profile_id',r.profile_id,
    'configuration','human_confirmed','sufficient',good,'goal_achieved',good AND all_met,
    'value',CASE WHEN good THEN avg_value/2 END,'target',4,'baseline',10,'unit','h/semana',
    'period_start',start_at,'period_end',end_at,'windows',wins,'source',_objective.measurement_source,
    'reason',CASE WHEN good THEN 'two_complete_weekly_windows' ELSE 'insufficient_or_incompatible_evidence' END,
    'causality','not_established','policy_version','flowreports-demo-v1');
END $$;

CREATE FUNCTION public.create_demo_objective(_tenant_id uuid,_subject_id uuid,_profile_id uuid,_deadline timestamptz,
  _source text,_capacity_ref text,_commitment_ref text,_customer_ref text)
RETURNS uuid LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $$
DECLARE v_id uuid;
BEGIN
  IF NOT public.has_tenant_role(_tenant_id,ARRAY['admin']::public.member_role[]) THEN
    RAISE EXCEPTION 'admin_required' USING ERRCODE='42501'; END IF;
  IF NOT EXISTS (SELECT FROM public.tenant_value_profiles WHERE tenant_id=_tenant_id AND id=_profile_id AND status='approved')
    OR _deadline IS NULL OR NOT isfinite(_deadline) THEN RAISE EXCEPTION 'approved_profile_and_deadline_required' USING ERRCODE='22023'; END IF;
  IF NOT EXISTS (SELECT FROM public.profile_indicators WHERE tenant_id=_tenant_id AND profile_id=_profile_id
    AND key='report_hours' AND classification='outcome' AND unit='h/semana' AND direction='lower_is_better'
    AND baseline_method='fixed_value' AND baseline_value=10 AND target_value=4 AND aggregation='mean' AND observation_window_days=7
    AND expected_cadence_days=7 AND min_coverage_pct=100 AND denominator_mode='observation_count') THEN
    RAISE EXCEPTION 'demo_profile_incompatible' USING ERRCODE='22023'; END IF;
  IF NOT EXISTS (SELECT FROM public.profile_indicators WHERE tenant_id=_tenant_id AND profile_id=_profile_id
    AND key='integration_status' AND classification='context' AND value_type='text' AND unit='estado') THEN
    RAISE EXCEPTION 'demo_profile_incompatible' USING ERRCODE='22023'; END IF;
  INSERT INTO public.cw_objectives(tenant_id,subject_id,profile_id,policy_version,deadline,measurement_source,
    capacity_ref,commitment_ref,customer_confirmation_ref,created_by)
  VALUES(_tenant_id,_subject_id,_profile_id,'flowreports-demo-v1',_deadline,_source,_capacity_ref,_commitment_ref,_customer_ref,auth.uid()) RETURNING id INTO v_id;
  RETURN v_id;
END $$;

CREATE FUNCTION public.assess_demo_objective(_tenant_id uuid,_objective_id uuid,_bundle_id uuid)
RETURNS uuid LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $$
DECLARE o public.cw_objectives; d jsonb; v_id uuid; result text;
BEGIN
  IF NOT public.has_tenant_role(_tenant_id,ARRAY['admin','operator']::public.member_role[]) THEN
    RAISE EXCEPTION 'write_role_required' USING ERRCODE='42501'; END IF;
  SELECT * INTO o FROM public.cw_objectives WHERE tenant_id=_tenant_id AND id=_objective_id FOR UPDATE;
  IF NOT FOUND THEN RAISE EXCEPTION 'objective_not_found' USING ERRCODE='22023'; END IF;
  SELECT id INTO v_id FROM public.cw_assessments WHERE objective_id=o.id AND bundle_id=_bundle_id;
  IF FOUND THEN RETURN v_id; END IF;
  d := public._cw_demo_evaluate(o,_bundle_id);
  result := CASE WHEN NOT (d->>'sufficient')::boolean THEN 'inconclusive'
    WHEN (d->>'as_of')::timestamptz < o.deadline THEN 'pending_deadline'
    WHEN (d->>'goal_achieved')::boolean THEN 'achieved' ELSE 'not_achieved' END;
  INSERT INTO public.cw_assessments(tenant_id,subject_id,objective_id,bundle_id,policy_version,result,evidence,details,created_by)
    VALUES(_tenant_id,o.subject_id,o.id,_bundle_id,o.policy_version,result,
      CASE WHEN (d->>'sufficient')::boolean THEN 'sufficient' ELSE 'insufficient' END,d,auth.uid()) RETURNING id INTO v_id;
  RETURN v_id;
END $$;

CREATE FUNCTION public.open_demo_case(_tenant_id uuid,_assessment_id uuid)
RETURNS uuid LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $$
DECLARE a public.cw_assessments; v_id uuid;
BEGIN
  IF NOT public.has_tenant_role(_tenant_id,ARRAY['admin','operator']::public.member_role[]) THEN
    RAISE EXCEPTION 'write_role_required' USING ERRCODE='42501'; END IF;
  SELECT * INTO a FROM public.cw_assessments WHERE tenant_id=_tenant_id AND id=_assessment_id FOR UPDATE;
  IF NOT FOUND OR a.result <> 'not_achieved' OR a.evidence <> 'sufficient' THEN
    RAISE EXCEPTION 'assessment_not_eligible' USING ERRCODE='22023'; END IF;
  SELECT id INTO v_id FROM public.cw_cases WHERE assessment_id=a.id;
  IF FOUND THEN RETURN v_id; END IF;
  INSERT INTO public.cw_cases(tenant_id,subject_id,assessment_id,policy_version,state,created_by)
    VALUES(_tenant_id,a.subject_id,a.id,a.policy_version,'investigation',auth.uid()) RETURNING id INTO v_id;
  INSERT INTO public.cw_case_events(tenant_id,subject_id,case_id,sequence,operation_id,command,request_hash,to_state,details,policy_version,created_by)
    VALUES(_tenant_id,a.subject_id,v_id,0,gen_random_uuid(),'open','open','investigation',
      jsonb_build_object('assessment_id',a.id,'objective_id',a.objective_id),a.policy_version,auth.uid());
  RETURN v_id;
END $$;

CREATE FUNCTION public.command_demo_case(_tenant_id uuid,_case_id uuid,_expected_version int,_operation_id uuid,_command text,_payload jsonb)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $$
DECLARE c public.cw_cases; a public.cw_assessments; o public.cw_objectives; e public.cw_case_events;
  proof public.observations; d jsonb; next_state text; h text; approved_at timestamptz; executed_at timestamptz;
  before_value numeric; previous_result jsonb; deadline_at timestamptz; condition_state text;
  evidence_cutoff timestamptz; has_pending_evidence boolean := false;
BEGIN
  IF NOT public.has_tenant_role(_tenant_id,ARRAY['admin','operator']::public.member_role[]) THEN
    RAISE EXCEPTION 'write_role_required' USING ERRCODE='42501'; END IF;
  IF _operation_id IS NULL OR _expected_version IS NULL OR _payload IS NULL OR jsonb_typeof(_payload)<>'object' THEN
    RAISE EXCEPTION 'invalid_command' USING ERRCODE='22023'; END IF;
  SELECT * INTO c FROM public.cw_cases WHERE tenant_id=_tenant_id AND id=_case_id FOR UPDATE;
  IF NOT FOUND THEN RAISE EXCEPTION 'case_not_found' USING ERRCODE='22023'; END IF;
  h := encode(sha256(convert_to(jsonb_build_object('command',_command,'payload',_payload)::text,'UTF8')),'hex');
  SELECT * INTO e FROM public.cw_case_events WHERE case_id=c.id AND operation_id=_operation_id;
  IF FOUND THEN
    IF e.request_hash<>h THEN RAISE EXCEPTION 'idempotency_conflict' USING ERRCODE='22023'; END IF;
    RETURN to_jsonb(e);
  END IF;
  IF c.version<>_expected_version THEN RAISE EXCEPTION 'stale_case_version' USING ERRCODE='40001'; END IF;
  SELECT * INTO a FROM public.cw_assessments WHERE id=c.assessment_id AND tenant_id=c.tenant_id;
  SELECT * INTO o FROM public.cw_objectives WHERE id=a.objective_id AND tenant_id=c.tenant_id;
  next_state := NULL;
  IF _command='investigate' AND c.state IN ('investigation','needs_information') THEN
    SELECT obs.* INTO proof FROM public.observations obs
      JOIN public.ingestion_batches batch ON batch.tenant_id=obs.tenant_id AND batch.id=obs.batch_id
      WHERE obs.tenant_id=c.tenant_id AND obs.subject_id=c.subject_id
      AND obs.id=(_payload->>'observation_id')::uuid AND obs.indicator_key='integration_status'
      AND batch.profile_id=o.profile_id AND obs.unit='estado' AND obs.value_text='disabled'
      AND obs.observed_at <= (a.details->>'period_end')::timestamptz
      AND obs.observed_at >= (a.details->>'period_start')::timestamptz
      AND NOT EXISTS(SELECT FROM public.observations cor WHERE cor.tenant_id=obs.tenant_id AND cor.corrects_observation_id=obs.id);
    next_state := CASE WHEN proof.id IS NULL THEN 'needs_information' ELSE 'impediment_found' END;
    d := jsonb_build_object('component','C05','status',CASE WHEN proof.id IS NULL THEN 'insufficient_evidence' ELSE 'confirmed_blocker' END,
      'observation_id',proof.id,'payload_hash',proof.payload_hash,'temporal_scope_start',proof.observed_at,
      'required_condition','source_integration_enabled','finding',CASE WHEN proof.id IS NOT NULL
        THEN 'Integração necessária ao fluxo sintético desativada no período documentado. Não prova causa única.'
        ELSE 'Não foi possível confirmar o impedimento com a referência fornecida.' END,
      'missing_data',CASE WHEN proof.id IS NULL THEN 'Prova disabled do mesmo cliente/perfil e período, via C01.' ELSE NULL END);
  ELSIF _command='plan' AND c.state='impediment_found' THEN
    SELECT obs.value_text INTO condition_state FROM public.observations obs
      JOIN public.ingestion_batches batch ON batch.tenant_id=obs.tenant_id AND batch.id=obs.batch_id
      WHERE obs.tenant_id=c.tenant_id AND obs.subject_id=c.subject_id AND batch.profile_id=o.profile_id
        AND obs.indicator_key='integration_status' AND obs.unit='estado'
        AND NOT EXISTS(SELECT FROM public.observations cor WHERE cor.tenant_id=obs.tenant_id AND cor.corrects_observation_id=obs.id)
      ORDER BY obs.observed_at DESC,obs.ingested_at DESC LIMIT 1;
    IF condition_state IS DISTINCT FROM 'disabled' THEN RAISE EXCEPTION 'blocker_no_longer_current' USING ERRCODE='22023'; END IF;
    next_state := 'awaiting_approval';
    d := jsonb_build_object('component','C06','action','manual_enable_integration',
      'instructions','Operador verifica a integração, reativa manualmente e confirma o estado no sistema de origem.',
      'rollback','Se ocorrer erro, revisão humana antes de voltar a desativar.',
      'technical_success','Recibo humano e observação integration_status=enabled via C01.',
      'outcome_success','Duas médias semanais <=4h, fonte e perfil históricos iguais.',
      'observation_days',14,'approval_hours',24,'external_connector',false);
  ELSIF _command='approve' AND c.state='awaiting_approval' THEN
    IF NOT public.has_tenant_role(c.tenant_id,ARRAY['admin']::public.member_role[]) THEN
      RAISE EXCEPTION 'admin_required' USING ERRCODE='42501'; END IF;
    next_state := 'approved';
    d := jsonb_build_object('component','C07','plan_event_sequence',c.version,'expires_at',clock_timestamp()+interval '24 hours');
  ELSIF _command='record_execution' AND c.state='approved' THEN
    SELECT created_at,(details->>'expires_at')::timestamptz INTO approved_at,deadline_at
      FROM public.cw_case_events WHERE case_id=c.id AND command='approve' ORDER BY sequence DESC LIMIT 1;
    IF deadline_at IS NULL OR clock_timestamp()>=deadline_at THEN RAISE EXCEPTION 'approval_expired' USING ERRCODE='22023'; END IF;
    IF NOT EXISTS (SELECT FROM public.cw_case_events ev JOIN public.memberships m
      ON m.tenant_id=ev.tenant_id AND m.user_id=ev.created_by AND m.role='admin'
      WHERE ev.case_id=c.id AND ev.command='approve') THEN
      RAISE EXCEPTION 'approval_no_longer_authorized' USING ERRCODE='42501'; END IF;
    IF length(btrim(coalesce(_payload->>'receipt',''))) NOT BETWEEN 1 AND 2000 THEN
      RAISE EXCEPTION 'human_receipt_required' USING ERRCODE='22023'; END IF;
    executed_at := clock_timestamp(); next_state := 'waiting_observation';
    d := jsonb_build_object('component','C07/C08','execution_kind','human_report','receipt',_payload->>'receipt',
      'technical_status','reported_executed','executed_at',executed_at,'wait_until',executed_at+interval '14 days',
      'required_evidence','Duas janelas semanais completas posteriores ao registo e estado enabled.',
      'value_realized',false);
  ELSIF _command='observe' AND c.state IN ('waiting_observation','observed','remain_open') THEN
    SELECT (details->>'executed_at')::timestamptz,(details->>'wait_until')::timestamptz INTO executed_at,deadline_at
      FROM public.cw_case_events WHERE case_id=c.id AND command='record_execution' ORDER BY sequence DESC LIMIT 1;
    IF deadline_at IS NULL OR clock_timestamp()<deadline_at THEN RAISE EXCEPTION 'observation_window_not_due' USING ERRCODE='22023'; END IF;
    d := public._cw_demo_evaluate(o,(_payload->>'bundle_id')::uuid,executed_at);
    SELECT data_cutoff INTO evidence_cutoff FROM public.c03_bundles
      WHERE tenant_id=c.tenant_id AND subject_id=c.subject_id AND id=(_payload->>'bundle_id')::uuid;
    IF (d->>'period_end')::timestamptz < deadline_at THEN
      d := d || jsonb_build_object('sufficient',false,'goal_achieved',false,'reason','post_execution_window_incomplete'); END IF;
    before_value := (a.details->>'value')::numeric;
    SELECT obs.* INTO proof FROM public.observations obs
      JOIN public.ingestion_batches batch ON batch.tenant_id=obs.tenant_id AND batch.id=obs.batch_id
      WHERE obs.tenant_id=c.tenant_id AND obs.subject_id=c.subject_id
      AND obs.indicator_key='integration_status' AND batch.profile_id=o.profile_id AND obs.unit='estado'
      AND obs.observed_at>=executed_at AND obs.observed_at <= (d->>'period_end')::timestamptz
      AND obs.ingested_at <= evidence_cutoff
      AND NOT EXISTS(SELECT FROM public.observations cor WHERE cor.tenant_id=obs.tenant_id
        AND cor.corrects_observation_id=obs.id AND cor.ingested_at <= evidence_cutoff)
      ORDER BY obs.observed_at DESC,obs.ingested_at DESC LIMIT 1;
    d := d || jsonb_build_object('component','C09','before_value',before_value,
      'change',CASE WHEN NOT (d->>'sufficient')::boolean THEN 'inconclusive'
        WHEN (d->>'value')::numeric<before_value THEN 'improved' WHEN (d->>'value')::numeric>before_value THEN 'worsened' ELSE 'unchanged' END,
      'integration_verified',coalesce(proof.value_text='enabled',false),'integration_observation_id',proof.id,
      'integration_payload_hash',proof.payload_hash);
    next_state := 'observed';
  ELSIF _command='decide' AND c.state='observed' THEN
    SELECT details INTO previous_result FROM public.cw_case_events WHERE case_id=c.id AND command='observe' ORDER BY sequence DESC LIMIT 1;
    SELECT b.data_cutoff INTO evidence_cutoff FROM public.c03_bundles b
      WHERE b.tenant_id=c.tenant_id AND b.subject_id=c.subject_id AND b.id=(previous_result->>'bundle_id')::uuid;
    SELECT (details->>'executed_at')::timestamptz INTO executed_at FROM public.cw_case_events
      WHERE case_id=c.id AND command='record_execution' ORDER BY sequence DESC LIMIT 1;
    -- C09 remains a reproducible historical snapshot. New relevant facts require
    -- a new comparison before closure; do not silently discard known pendencies.
    SELECT EXISTS (SELECT FROM public.observations obs
      JOIN public.ingestion_batches batch ON batch.tenant_id=obs.tenant_id AND batch.id=obs.batch_id
      WHERE obs.tenant_id=c.tenant_id AND obs.subject_id=c.subject_id AND batch.profile_id=o.profile_id
        AND obs.ingested_at>evidence_cutoff AND obs.observed_at<=clock_timestamp()
        AND ((obs.indicator_key='report_hours' AND obs.observed_at>=(previous_result->>'period_start')::timestamptz)
          OR (obs.indicator_key='integration_status' AND obs.observed_at>=executed_at))) INTO has_pending_evidence;
    next_state := CASE WHEN coalesce((previous_result->>'sufficient')::boolean,false)
      AND coalesce((previous_result->>'goal_achieved')::boolean,false)
      AND coalesce((previous_result->>'integration_verified')::boolean,false)
      AND evidence_cutoff IS NOT NULL AND NOT has_pending_evidence THEN 'closed_resolved' ELSE 'remain_open' END;
    d := jsonb_build_object('component','C10','decision',next_state,'observation',previous_result,
      'pending_evidence',has_pending_evidence,
      'reason',CASE WHEN has_pending_evidence THEN 'Há nova evidência relevante após o corte do C09. É necessária nova comparação antes do encerramento.'
      WHEN next_state='closed_resolved' THEN 'Critérios sintéticos satisfeitos; sem atribuição causal.'
      ELSE 'Objetivo, suficiência ou eliminação do impedimento ainda não demonstrados.' END);
  END IF;
  IF next_state IS NULL THEN RAISE EXCEPTION 'transition_not_allowed' USING ERRCODE='22023'; END IF;
  INSERT INTO public.cw_case_events(tenant_id,subject_id,case_id,sequence,operation_id,command,request_hash,
    from_state,to_state,details,policy_version,created_by)
    VALUES(c.tenant_id,c.subject_id,c.id,c.version+1,_operation_id,_command,h,c.state,next_state,d,c.policy_version,auth.uid()) RETURNING * INTO e;
  UPDATE public.cw_cases SET state=next_state,version=version+1 WHERE id=c.id AND tenant_id=c.tenant_id;
  RETURN to_jsonb(e);
END $$;

REVOKE ALL ON FUNCTION public._cw_demo_evaluate(public.cw_objectives,uuid,timestamptz) FROM PUBLIC,anon,authenticated;
REVOKE ALL ON FUNCTION public.create_demo_objective(uuid,uuid,uuid,timestamptz,text,text,text,text) FROM PUBLIC,anon,authenticated;
REVOKE ALL ON FUNCTION public.assess_demo_objective(uuid,uuid,uuid) FROM PUBLIC,anon,authenticated;
REVOKE ALL ON FUNCTION public.open_demo_case(uuid,uuid) FROM PUBLIC,anon,authenticated;
REVOKE ALL ON FUNCTION public.command_demo_case(uuid,uuid,int,uuid,text,jsonb) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.create_demo_objective(uuid,uuid,uuid,timestamptz,text,text,text,text) TO authenticated;
GRANT EXECUTE ON FUNCTION public.assess_demo_objective(uuid,uuid,uuid) TO authenticated;
GRANT EXECUTE ON FUNCTION public.open_demo_case(uuid,uuid) TO authenticated;
GRANT EXECUTE ON FUNCTION public.command_demo_case(uuid,uuid,int,uuid,text,jsonb) TO authenticated;

-- Delivered only after the migration transaction commits. Existing API servers
-- must reload their schema cache before exposing the newly added RPCs/tables.
NOTIFY pgrst, 'reload schema';
