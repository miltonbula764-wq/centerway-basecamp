-- Configured, human-directed, single-indicator operational journey. No demo mutation.
ALTER TABLE public.c04_evaluations ADD CONSTRAINT c04_evaluations_tenant_subject_id_key UNIQUE(tenant_id,subject_id,id);
CREATE TABLE public.cw_operational_cases (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(), tenant_id uuid NOT NULL REFERENCES public.tenants(id), subject_id uuid NOT NULL,
  evaluation_id uuid NOT NULL UNIQUE, configuration_id uuid NOT NULL,
  contract_version text NOT NULL CHECK(contract_version='individual-review-v1'),
  opening_definition jsonb NOT NULL, operation_id uuid NOT NULL, request_hash text NOT NULL,
  state text NOT NULL CHECK(state IN ('investigation','needs_information','hypothesis','impediment_confirmed','awaiting_approval','approved','waiting_observation','observed','remain_open','closed_resolved')),
  version integer NOT NULL DEFAULT 0, created_by uuid NOT NULL, created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  UNIQUE(tenant_id,id), UNIQUE(tenant_id,subject_id,id), UNIQUE(tenant_id,operation_id),
  FOREIGN KEY(tenant_id,subject_id,evaluation_id) REFERENCES public.c04_evaluations(tenant_id,subject_id,id),
  FOREIGN KEY(tenant_id,subject_id,configuration_id) REFERENCES public.c04_configurations(tenant_id,subject_id,id)
);
CREATE TABLE public.cw_operational_events (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(), tenant_id uuid NOT NULL REFERENCES public.tenants(id), subject_id uuid NOT NULL, case_id uuid NOT NULL,
  sequence integer NOT NULL, operation_id uuid NOT NULL, request_hash text NOT NULL,
  command text NOT NULL, from_state text, to_state text NOT NULL, details jsonb NOT NULL,
  created_by uuid NOT NULL, created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  UNIQUE(tenant_id,id), UNIQUE(case_id,sequence), UNIQUE(case_id,operation_id),
  FOREIGN KEY(tenant_id,subject_id,case_id) REFERENCES public.cw_operational_cases(tenant_id,subject_id,id)
);
CREATE INDEX cw_operational_cases_subject_idx ON public.cw_operational_cases(tenant_id,subject_id,created_at DESC);
CREATE INDEX cw_operational_events_case_idx ON public.cw_operational_events(tenant_id,case_id,sequence);
CREATE FUNCTION public._cwop_projection_guard() RETURNS trigger LANGUAGE plpgsql SET search_path=public AS $$
BEGIN
  IF TG_OP='DELETE' OR (to_jsonb(NEW)-ARRAY['state','version']) IS DISTINCT FROM (to_jsonb(OLD)-ARRAY['state','version']) THEN
    RAISE EXCEPTION 'operational_case_identity_immutable' USING ERRCODE='42501'; END IF;
  RETURN NEW;
END $$;
DO $$ DECLARE t text; BEGIN
  FOREACH t IN ARRAY ARRAY['cw_operational_cases','cw_operational_events'] LOOP
    EXECUTE format('REVOKE ALL ON public.%I FROM PUBLIC,anon,authenticated',t);
    EXECUTE format('GRANT SELECT ON public.%I TO authenticated',t);
    EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY',t);
    EXECUTE format('CREATE POLICY tenant_read ON public.%I FOR SELECT TO authenticated USING (public.is_tenant_member(tenant_id))',t);
    EXECUTE format('CREATE TRIGGER audit AFTER INSERT OR UPDATE ON public.%I FOR EACH ROW EXECUTE FUNCTION public._cw_audit()',t);
  END LOOP;
END $$;
CREATE TRIGGER immutable BEFORE UPDATE OR DELETE ON public.cw_operational_events FOR EACH ROW EXECUTE FUNCTION public._c02_immutable();
CREATE TRIGGER identity_guard BEFORE UPDATE OR DELETE ON public.cw_operational_cases FOR EACH ROW EXECUTE FUNCTION public._cwop_projection_guard();

CREATE FUNCTION public._cwop_text(_d jsonb,_key text) RETURNS text LANGUAGE plpgsql IMMUTABLE SET search_path=public AS $$
DECLARE v text:=btrim(_d->>_key);
BEGIN
  IF jsonb_typeof(_d->_key) IS DISTINCT FROM 'string' OR length(v) NOT BETWEEN 1 AND 4000 THEN
    RAISE EXCEPTION 'required_text: %',_key USING ERRCODE='22023'; END IF;
  RETURN v;
END $$;
CREATE FUNCTION public._cwop_reference(_d jsonb,_key text) RETURNS text LANGUAGE plpgsql IMMUTABLE SET search_path=public AS $$
DECLARE v text:=public._cwop_text(_d,_key);
BEGIN
  -- Validate reference syntax only; never pretend to fetch or certify external documents.
  IF v !~ '^(https://[a-zA-Z0-9][a-zA-Z0-9.-]*(:[0-9]+)?([/?#][^[:space:]]*)?|urn:[a-zA-Z0-9][a-zA-Z0-9-]{0,31}:[^[:space:]]+)$' THEN
    RAISE EXCEPTION 'reference_uri_required: %',_key USING ERRCODE='22023'; END IF;
  RETURN v;
END $$;
CREATE FUNCTION public._cwop_keys(_d jsonb,_keys text[]) RETURNS void LANGUAGE plpgsql IMMUTABLE SET search_path=public AS $$
BEGIN
  IF _d IS NULL OR jsonb_typeof(_d)<>'object' OR length(_d::text)>30000
    OR EXISTS(SELECT FROM jsonb_object_keys(_d) k WHERE NOT k=ANY(_keys)) THEN
    RAISE EXCEPTION 'invalid_command_payload' USING ERRCODE='22023'; END IF;
END $$;

-- C04 numeric semantics and stored results are unchanged. Acquire tenant before configuration
-- to avoid a lock inversion with Core/C01 and the tenant FK checks during standalone C04 evaluation.
CREATE OR REPLACE FUNCTION public.evaluate_c04_configuration(_tenant_id uuid,_configuration_id uuid,_bundle_id uuid)
RETURNS uuid LANGUAGE plpgsql SECURITY DEFINER SET search_path=public AS $$
DECLARE c public.c04_configurations; b public.c03_bundles; r public.c02_runs; i public.c03_indicators;
  d jsonb; p jsonb; w jsonb; wins jsonb:='[]'; missing text[]:='{}'; reasons text[]:='{}'; k text;
  cs text; outcome text; disposition text; enough boolean:=true; met boolean:=true; n int:=0; required_n int;
  v_id uuid; measurement_met boolean; compatible_measurement boolean;
BEGIN
  IF NOT public.has_tenant_role(_tenant_id,ARRAY['admin','operator']::public.member_role[]) THEN
    RAISE EXCEPTION 'write_role_required' USING ERRCODE='42501'; END IF;
  PERFORM 1 FROM public.tenants WHERE id=_tenant_id FOR UPDATE;
  SELECT * INTO c FROM public.c04_configurations WHERE tenant_id=_tenant_id AND id=_configuration_id FOR UPDATE;
  IF NOT FOUND THEN RAISE EXCEPTION 'configuration_not_found' USING ERRCODE='22023'; END IF;
  SELECT id INTO v_id FROM public.c04_evaluations WHERE configuration_id=c.id AND bundle_id=_bundle_id AND algorithm_version='c04-numeric-v1';
  IF FOUND THEN RETURN v_id; END IF;
  SELECT * INTO b FROM public.c03_bundles WHERE tenant_id=_tenant_id AND subject_id=c.subject_id AND id=_bundle_id;
  IF NOT FOUND THEN RAISE EXCEPTION 'bundle_not_found' USING ERRCODE='22023'; END IF;
  SELECT * INTO r FROM public.c02_runs WHERE tenant_id=_tenant_id AND id=b.run_id;
  d:=c.definition;
  FOREACH k IN ARRAY ARRAY['promise','promise_ref','plan_capability','plan_ref','customer_goal','customer_ref','compatibility','compatibility_ref'] LOOP
    IF d->>k IS NULL THEN missing:=array_append(missing,k); END IF;
  END LOOP;
  cs:=CASE WHEN d->>'compatibility'='contradiction' AND d->>'compatibility_ref' IS NOT NULL THEN 'contradiction'
    WHEN cardinality(missing)>0 THEN 'missing_documentation' ELSE d->>'compatibility' END;
  FOREACH k IN ARRAY ARRAY['customer_goal','customer_ref','unit','source','aggregation','comparator','target','deadline','window_count','observation_start'] LOOP
    IF d->>k IS NULL THEN enough:=false; reasons:=array_append(reasons,'missing_'||k); END IF;
  END LOOP;
  SELECT * INTO i FROM public.c03_indicators WHERE tenant_id=_tenant_id AND bundle_id=b.id AND indicator_key=c.indicator_key;
  p:=i.snapshot#>'{details,parameters}'; required_n:=(d->>'window_count')::int;
  compatible_measurement:=r.profile_id=c.profile_id AND r.algorithm_version='c02-v2' AND b.algorithm_version='c03-v1'
    AND i.snapshot->>'classification'='outcome'
    AND (d->>'unit' IS NULL OR p->>'unit' IS NULL OR p->>'unit'=d->>'unit')
    AND (d->>'aggregation' IS NULL OR p->>'aggregation' IS NULL OR p->>'aggregation'=d->>'aggregation');
  IF compatible_measurement IS DISTINCT FROM true THEN
    enough:=false; reasons:=array_append(reasons,'historical_measurement_configuration_mismatch');
    cs:=CASE WHEN i.id IS NULL THEN 'not_checkable' ELSE 'contradiction' END;
  END IF;
  IF i.id IS NOT NULL AND (p->>'unit' IS NULL OR p->>'aggregation' IS NULL) THEN
    enough:=false; reasons:=array_append(reasons,'historical_measurement_configuration_incomplete');
    IF cs<>'contradiction' THEN cs:='not_checkable'; END IF;
  END IF;
  IF i.status IS DISTINCT FROM 'complete'::public.c03_indicator_status THEN enough:=false; reasons:=array_append(reasons,'indicator_evidence_insufficient'); END IF;
  -- Per-indicator only: no dependence on the bundle-wide status or other indicators.
  FOR w IN SELECT value FROM jsonb_array_elements(coalesce(i.snapshot#>'{details,windows}','[]'))
    WHERE value->>'label' ~ '^current_[0-9]+$' AND substring(value->>'label' FROM '[0-9]+$')::int <= required_n LOOP
    n:=n+1; wins:=wins||jsonb_build_array(w);
    IF (w->>'sufficient')::boolean IS DISTINCT FROM true OR w->>'source' IS DISTINCT FROM d->>'source'
      OR w->>'value' IS NULL OR (w->>'start')::timestamptz < (d->>'observation_start')::timestamptz
      OR (w->>'end')::timestamptz > r.as_of OR (w->>'end')::timestamptz > clock_timestamp() THEN enough:=false; END IF;
    measurement_met:=CASE d->>'comparator'
      WHEN 'lt' THEN (w->>'value')::numeric < (d->>'target')::numeric
      WHEN 'lte' THEN (w->>'value')::numeric <= (d->>'target')::numeric
      WHEN 'gt' THEN (w->>'value')::numeric > (d->>'target')::numeric
      WHEN 'gte' THEN (w->>'value')::numeric >= (d->>'target')::numeric
      WHEN 'eq' THEN (w->>'value')::numeric = (d->>'target')::numeric ELSE false END;
    met:=met AND coalesce(measurement_met,false);
  END LOOP;
  IF n IS DISTINCT FROM required_n OR n=0 THEN enough:=false; reasons:=array_append(reasons,'required_windows_unavailable'); END IF;
  IF NOT enough THEN reasons:=array_append(reasons,'measurement_rules_not_satisfied'); END IF;
  outcome:=CASE WHEN NOT enough THEN 'inconclusive' WHEN r.as_of < (d->>'deadline')::timestamptz THEN 'pending_deadline'
    WHEN met THEN 'achieved' ELSE 'not_achieved' END;
  disposition:=CASE WHEN cs='contradiction' THEN 'configuration_review'
    WHEN cs<>'compatible' OR NOT enough OR outcome='pending_deadline' THEN 'needs_information' ELSE 'assessment_available' END;
  INSERT INTO public.c04_evaluations(tenant_id,subject_id,configuration_id,bundle_id,algorithm_version,configuration_state,result,evidence,core_disposition,details,created_by)
    VALUES(_tenant_id,c.subject_id,c.id,b.id,'c04-numeric-v1',cs,outcome,CASE WHEN enough THEN 'sufficient' ELSE 'insufficient' END,disposition,
      jsonb_build_object('definition',d,'configuration_version',c.version,'profile_id',r.profile_id,'run_id',r.id,'as_of',r.as_of,
        'data_cutoff',b.data_cutoff,'bundle_content_hash',b.content_hash,'indicator_key',c.indicator_key,'windows',wins,
        'missing_documentation',to_jsonb(missing),'reasons',to_jsonb(reasons),'all_windows_meet_target',enough AND met,
        'comparison_rule','each_selected_current_window','causality','not_established','promise_fulfillment','not_determined',
        'automatic_case_transition',false),auth.uid()) RETURNING id INTO v_id;
  RETURN v_id;
END $$;

CREATE FUNCTION public.open_operational_case(_tenant_id uuid,_evaluation_id uuid,_operation_id uuid,_definition jsonb)
RETURNS uuid LANGUAGE plpgsql SECURITY DEFINER SET search_path=public AS $$
DECLARE a public.c04_evaluations; c public.cw_operational_cases; cfg public.c04_configurations; h text; v_id uuid; k text;
BEGIN
  IF NOT public.has_tenant_role(_tenant_id,ARRAY['admin']::public.member_role[]) THEN RAISE EXCEPTION 'admin_required' USING ERRCODE='42501'; END IF;
  IF _operation_id IS NULL THEN RAISE EXCEPTION 'operation_id_required' USING ERRCODE='22023'; END IF;
  PERFORM 1 FROM public.tenants WHERE id=_tenant_id FOR UPDATE;
  h:=encode(sha256(convert_to(jsonb_build_array(_evaluation_id,_definition)::text,'UTF8')),'hex');
  SELECT * INTO c FROM public.cw_operational_cases WHERE tenant_id=_tenant_id AND operation_id=_operation_id;
  IF FOUND THEN
    IF c.request_hash<>h THEN RAISE EXCEPTION 'idempotency_conflict' USING ERRCODE='22023'; END IF;
    RETURN c.id;
  END IF;
  SELECT * INTO a FROM public.c04_evaluations WHERE tenant_id=_tenant_id AND id=_evaluation_id;
  IF NOT FOUND OR a.evidence<>'sufficient' OR a.configuration_state<>'compatible' OR a.result NOT IN ('achieved','not_achieved') THEN
    RAISE EXCEPTION 'evaluation_requires_information' USING ERRCODE='22023'; END IF;
  SELECT * INTO cfg FROM public.c04_configurations WHERE tenant_id=_tenant_id AND id=a.configuration_id;
  IF EXISTS(SELECT FROM public.c04_configurations WHERE tenant_id=_tenant_id AND subject_id=cfg.subject_id AND indicator_key=cfg.indicator_key AND version>cfg.version) THEN
    RAISE EXCEPTION 'configuration_revision_requires_review' USING ERRCODE='22023'; END IF;
  PERFORM public._cwop_keys(_definition,ARRAY['eligible','eligibility_reason','eligibility_ref','opening_criteria','closure_criteria','closure_ref','configuration_pinned']);
  IF (_definition->'eligible') IS DISTINCT FROM 'true'::jsonb OR (_definition->'configuration_pinned') IS DISTINCT FROM 'true'::jsonb THEN
    RAISE EXCEPTION 'explicit_eligibility_required' USING ERRCODE='22023'; END IF;
  FOREACH k IN ARRAY ARRAY['eligibility_reason','opening_criteria','closure_criteria'] LOOP PERFORM public._cwop_text(_definition,k); END LOOP;
  PERFORM public._cwop_reference(_definition,'eligibility_ref'); PERFORM public._cwop_reference(_definition,'closure_ref');
  -- One human-directed case per evaluation; different operation IDs do not silently change the decision.
  IF EXISTS(SELECT FROM public.cw_operational_cases WHERE evaluation_id=a.id) THEN RAISE EXCEPTION 'evaluation_already_has_case' USING ERRCODE='22023'; END IF;
  INSERT INTO public.cw_operational_cases(tenant_id,subject_id,evaluation_id,configuration_id,contract_version,opening_definition,operation_id,request_hash,state,created_by)
    VALUES(_tenant_id,a.subject_id,a.id,a.configuration_id,'individual-review-v1',_definition,_operation_id,h,'investigation',auth.uid()) RETURNING id INTO v_id;
  INSERT INTO public.cw_operational_events(tenant_id,subject_id,case_id,sequence,operation_id,request_hash,command,to_state,details,created_by)
    VALUES(_tenant_id,a.subject_id,v_id,0,_operation_id,h,'open','investigation',jsonb_build_object('evaluation_id',a.id,'configuration_id',cfg.id,'indicator_key',cfg.indicator_key,'definition',_definition,'baseline',a.details,'entry_result',a.result),auth.uid());
  RETURN v_id;
END $$;

CREATE FUNCTION public.command_operational_case(_tenant_id uuid,_case_id uuid,_expected_version integer,_operation_id uuid,_command text,_payload jsonb)
RETURNS uuid LANGUAGE plpgsql SECURITY DEFINER SET search_path=public AS $$
DECLARE c public.cw_operational_cases; previous public.cw_operational_events; finding public.cw_operational_events;
  plan public.cw_operational_events; approval public.cw_operational_events; execution public.cw_operational_events; comparison public.cw_operational_events;
  cfg public.c04_configurations; a public.c04_evaluations; baseline public.c04_evaluations; b public.c03_bundles;
  h text; next_state text; d jsonb; v_id uuid; k text; status text; refs jsonb:='[]'; oid uuid; o public.observations;
  seconds numeric; valid_until timestamptz; executed_at timestamptz; wait_until timestamptz; reasons text[]:='{}'; temporal boolean:=true;
BEGIN
  IF NOT public.has_tenant_role(_tenant_id,ARRAY['admin','operator']::public.member_role[]) THEN RAISE EXCEPTION 'write_role_required' USING ERRCODE='42501'; END IF;
  IF _operation_id IS NULL OR _expected_version IS NULL THEN RAISE EXCEPTION 'operation_and_version_required' USING ERRCODE='22023'; END IF;
  -- Tenant -> case -> C04 configuration: serializes ingestion/profile changes with final decisions.
  PERFORM 1 FROM public.tenants WHERE id=_tenant_id FOR UPDATE;
  SELECT * INTO c FROM public.cw_operational_cases WHERE tenant_id=_tenant_id AND id=_case_id FOR UPDATE;
  IF NOT FOUND THEN RAISE EXCEPTION 'case_not_found' USING ERRCODE='22023'; END IF;
  h:=encode(sha256(convert_to(jsonb_build_array(_command,_payload,_expected_version)::text,'UTF8')),'hex');
  SELECT * INTO previous FROM public.cw_operational_events WHERE case_id=c.id AND operation_id=_operation_id;
  IF FOUND THEN
    IF previous.request_hash<>h THEN RAISE EXCEPTION 'idempotency_conflict' USING ERRCODE='22023'; END IF;
    RETURN previous.id;
  END IF;
  IF c.version<>_expected_version THEN RAISE EXCEPTION 'case_version_conflict' USING ERRCODE='40001'; END IF;
  IF c.state='closed_resolved' THEN RAISE EXCEPTION 'case_closed' USING ERRCODE='22023'; END IF;
  SELECT * INTO cfg FROM public.c04_configurations WHERE tenant_id=_tenant_id AND id=c.configuration_id;
  SELECT * INTO baseline FROM public.c04_evaluations WHERE tenant_id=_tenant_id AND id=c.evaluation_id;
  SELECT * INTO execution FROM public.cw_operational_events WHERE case_id=c.id AND command='record_execution' ORDER BY sequence DESC LIMIT 1;
  SELECT * INTO finding FROM public.cw_operational_events WHERE case_id=c.id AND command='investigate' ORDER BY sequence DESC LIMIT 1;
  SELECT * INTO plan FROM public.cw_operational_events WHERE case_id=c.id AND command='plan' ORDER BY sequence DESC LIMIT 1;
  SELECT * INTO approval FROM public.cw_operational_events WHERE case_id=c.id AND command='approve' ORDER BY sequence DESC LIMIT 1;
  -- A changed contract never retroactively changes this case. A fresh decision/case is required in this bounded version.
  IF _command IN ('plan','approve','record_execution') AND EXISTS(SELECT FROM public.c04_configurations
    WHERE tenant_id=_tenant_id AND subject_id=c.subject_id AND indicator_key=cfg.indicator_key AND version>cfg.version) THEN
    RAISE EXCEPTION 'configuration_revision_requires_review' USING ERRCODE='22023'; END IF;
  IF _command='investigate' THEN
    IF execution.id IS NOT NULL THEN RAISE EXCEPTION 'single_intervention_cycle' USING ERRCODE='22023'; END IF;
    PERFORM public._cwop_keys(_payload,ARRAY['status','finding','reference','observation_ids']);
    status:=public._cwop_text(_payload,'status'); PERFORM public._cwop_text(_payload,'finding'); PERFORM public._cwop_reference(_payload,'reference');
    IF status NOT IN ('confirmed','hypothesis','insufficient') OR jsonb_typeof(_payload->'observation_ids') IS DISTINCT FROM 'array'
      OR jsonb_array_length(_payload->'observation_ids')>50 THEN RAISE EXCEPTION 'invalid_investigation' USING ERRCODE='22023'; END IF;
    FOR oid IN SELECT DISTINCT value::uuid FROM jsonb_array_elements_text(_payload->'observation_ids') LOOP
      SELECT * INTO o FROM public.observations WHERE tenant_id=_tenant_id AND subject_id=c.subject_id AND id=oid;
      IF NOT FOUND OR o.observed_at>clock_timestamp() OR EXISTS(SELECT FROM public.observations x WHERE x.tenant_id=_tenant_id AND x.corrects_observation_id=o.id) THEN
        RAISE EXCEPTION 'invalid_or_superseded_evidence_reference' USING ERRCODE='22023'; END IF;
      refs:=refs||jsonb_build_array(jsonb_build_object('id',o.id,'indicator_key',o.indicator_key,'value_numeric',o.value_numeric,'value_text',o.value_text,'unit',o.unit,'source',o.source,'observed_at',o.observed_at,'payload_hash',o.payload_hash));
    END LOOP;
    IF status='confirmed' AND jsonb_array_length(refs)=0 THEN RAISE EXCEPTION 'confirmed_requires_observation' USING ERRCODE='22023'; END IF;
    next_state:=CASE status WHEN 'confirmed' THEN 'impediment_confirmed' WHEN 'hypothesis' THEN 'hypothesis' ELSE 'needs_information' END;
    d:=_payload||jsonb_build_object('evidence',refs,'confirmation','human_interpretation','causality','not_established','reference_validation','syntax_and_internal_ownership_only');
  ELSIF _command='plan' THEN
    IF c.state NOT IN ('impediment_confirmed','awaiting_approval','approved') OR finding.details->>'status' IS DISTINCT FROM 'confirmed' THEN RAISE EXCEPTION 'confirmed_impediment_required' USING ERRCODE='22023'; END IF;
    PERFORM public._cwop_keys(_payload,ARRAY['action','rationale','success_conditions','limitations','reversal','reference','observation_seconds']);
    FOREACH k IN ARRAY ARRAY['action','rationale','success_conditions','limitations','reversal'] LOOP PERFORM public._cwop_text(_payload,k); END LOOP;
    PERFORM public._cwop_reference(_payload,'reference');
    IF jsonb_typeof(_payload->'observation_seconds') IS DISTINCT FROM 'number' THEN RAISE EXCEPTION 'observation_window_required' USING ERRCODE='22023'; END IF;
    seconds:=(_payload->>'observation_seconds')::numeric;
    IF seconds<1 OR seconds>31536000 OR seconds<>trunc(seconds) THEN RAISE EXCEPTION 'invalid_observation_window' USING ERRCODE='22023'; END IF;
    -- Revalidate the factual references before preparing an action.
    IF EXISTS(SELECT FROM jsonb_array_elements(finding.details->'evidence') f JOIN public.observations x ON x.tenant_id=_tenant_id AND x.corrects_observation_id=(f->>'id')::uuid) THEN
      RAISE EXCEPTION 'investigation_evidence_changed' USING ERRCODE='22023'; END IF;
    next_state:='awaiting_approval'; d:=_payload||jsonb_build_object('investigation_event_id',finding.id,'historical_configuration_id',cfg.id);
  ELSIF _command='approve' THEN
    IF NOT public.has_tenant_role(_tenant_id,ARRAY['admin']::public.member_role[]) THEN RAISE EXCEPTION 'admin_required' USING ERRCODE='42501'; END IF;
    IF c.state NOT IN ('awaiting_approval','approved') OR plan.id IS NULL THEN RAISE EXCEPTION 'plan_required' USING ERRCODE='22023'; END IF;
    PERFORM public._cwop_keys(_payload,ARRAY['valid_until','reference','reason']); PERFORM public._cwop_text(_payload,'reason'); PERFORM public._cwop_reference(_payload,'reference');
    k:=public._cwop_text(_payload,'valid_until');
    IF k !~ '(Z|[+-][0-9]{2}:[0-9]{2})$' THEN RAISE EXCEPTION 'timestamp_with_timezone_required' USING ERRCODE='22023'; END IF;
    valid_until:=k::timestamptz;
    IF NOT isfinite(valid_until) OR valid_until<=clock_timestamp() THEN RAISE EXCEPTION 'valid_authorization_required' USING ERRCODE='22023'; END IF;
    next_state:='approved'; d:=_payload||jsonb_build_object('plan_event_id',plan.id,'authorized_by',auth.uid(),'approved_at',clock_timestamp());
  ELSIF _command='record_execution' THEN
    IF c.state<>'approved' OR approval.id IS NULL OR approval.details->>'plan_event_id' IS DISTINCT FROM plan.id::text
      OR (approval.details->>'valid_until')::timestamptz<=clock_timestamp() THEN
      RAISE EXCEPTION 'valid_authorization_required' USING ERRCODE='22023'; END IF;
    IF NOT EXISTS(SELECT FROM public.memberships WHERE tenant_id=_tenant_id AND user_id=approval.created_by AND role='admin') THEN
      RAISE EXCEPTION 'approver_no_longer_authorized' USING ERRCODE='42501'; END IF;
    IF EXISTS(SELECT FROM jsonb_array_elements(finding.details->'evidence') f JOIN public.observations x ON x.tenant_id=_tenant_id AND x.corrects_observation_id=(f->>'id')::uuid) THEN
      RAISE EXCEPTION 'investigation_evidence_changed' USING ERRCODE='22023'; END IF;
    PERFORM public._cwop_keys(_payload,ARRAY['receipt','reference']); PERFORM public._cwop_text(_payload,'receipt'); PERFORM public._cwop_reference(_payload,'reference');
    executed_at:=clock_timestamp(); wait_until:=executed_at+make_interval(secs=>(plan.details->>'observation_seconds')::double precision);
    next_state:='waiting_observation'; d:=_payload||jsonb_build_object('approval_event_id',approval.id,'plan_event_id',plan.id,'executed_at',executed_at,'wait_until',wait_until,'execution_type','human_record','value_recovery','not_proven');
  ELSIF _command='observe' THEN
    IF c.state NOT IN ('waiting_observation','observed','remain_open') OR execution.id IS NULL THEN RAISE EXCEPTION 'execution_required' USING ERRCODE='22023'; END IF;
    executed_at:=(execution.details->>'executed_at')::timestamptz; wait_until:=(execution.details->>'wait_until')::timestamptz;
    IF clock_timestamp()<wait_until THEN RAISE EXCEPTION 'observation_window_not_elapsed' USING ERRCODE='22023'; END IF;
    PERFORM public._cwop_keys(_payload,ARRAY['bundle_id']);
    SELECT * INTO b FROM public.c03_bundles WHERE tenant_id=_tenant_id AND subject_id=c.subject_id AND id=(_payload->>'bundle_id')::uuid;
    IF NOT FOUND OR b.id=baseline.bundle_id THEN RAISE EXCEPTION 'new_subject_bundle_required' USING ERRCODE='22023'; END IF;
    v_id:=public.evaluate_c04_configuration(_tenant_id,cfg.id,b.id);
    SELECT * INTO a FROM public.c04_evaluations WHERE id=v_id AND tenant_id=_tenant_id;
    IF jsonb_array_length(a.details->'windows')=0 OR EXISTS(SELECT FROM jsonb_array_elements(a.details->'windows') w
      WHERE (w->>'start')::timestamptz<executed_at OR (w->>'end')::timestamptz>clock_timestamp())
      OR (SELECT max((w->>'end')::timestamptz) FROM jsonb_array_elements(a.details->'windows') w)<wait_until THEN
      temporal:=false; reasons:=array_append(reasons,'post_execution_observation_insufficient'); END IF;
    IF a.evidence<>'sufficient' OR a.configuration_state<>'compatible' THEN reasons:=array_append(reasons,'c04_evidence_or_configuration_pending'); END IF;
    next_state:='observed'; d:=jsonb_build_object('evaluation_id',a.id,'bundle_id',b.id,'configuration_id',cfg.id,'before',baseline.details,'after',a.details,
      'result',CASE WHEN temporal THEN a.result ELSE 'inconclusive' END,'sufficient',temporal AND a.evidence='sufficient' AND a.configuration_state='compatible',
      'reasons',to_jsonb(reasons),'data_cutoff',b.data_cutoff,'executed_at',executed_at,'wait_until',wait_until,'causality','not_established');
  ELSIF _command='decide' THEN
    IF NOT public.has_tenant_role(_tenant_id,ARRAY['admin']::public.member_role[]) THEN RAISE EXCEPTION 'admin_required' USING ERRCODE='42501'; END IF;
    IF c.state<>'observed' THEN RAISE EXCEPTION 'comparison_required' USING ERRCODE='22023'; END IF;
    PERFORM public._cwop_keys(_payload,ARRAY['close_requested','criteria_met','material_contradiction','reason','reference']);
    PERFORM public._cwop_text(_payload,'reason'); PERFORM public._cwop_reference(_payload,'reference');
    FOREACH k IN ARRAY ARRAY['close_requested','criteria_met','material_contradiction'] LOOP
      IF jsonb_typeof(_payload->k) IS DISTINCT FROM 'boolean' THEN RAISE EXCEPTION 'explicit_decision_required' USING ERRCODE='22023'; END IF;
    END LOOP;
    SELECT * INTO comparison FROM public.cw_operational_events WHERE case_id=c.id AND command='observe' ORDER BY sequence DESC LIMIT 1;
    IF comparison.details->>'result' IS DISTINCT FROM 'achieved' OR (comparison.details->>'sufficient')::boolean IS DISTINCT FROM true THEN reasons:=array_append(reasons,'objective_not_demonstrated'); END IF;
    IF (_payload->>'criteria_met')::boolean IS NOT TRUE THEN reasons:=array_append(reasons,'specific_closure_criteria_pending'); END IF;
    IF (_payload->>'material_contradiction')::boolean THEN reasons:=array_append(reasons,'material_contradiction'); END IF;
    IF EXISTS(SELECT FROM public.c04_configurations WHERE tenant_id=_tenant_id AND subject_id=c.subject_id AND indicator_key=cfg.indicator_key AND version>cfg.version) THEN reasons:=array_append(reasons,'configuration_revision_requires_review'); END IF;
    -- New facts for the goal, its paired denominator, or C05 evidence keys require a new C09 snapshot.
    IF EXISTS(SELECT FROM public.observations x WHERE x.tenant_id=_tenant_id AND x.subject_id=c.subject_id
      AND (x.ingested_at>(comparison.details->>'data_cutoff')::timestamptz OR x.observed_at>=(SELECT max((w->>'end')::timestamptz) FROM jsonb_array_elements(comparison.details#>'{after,windows}') w))
      AND (x.indicator_key=cfg.indicator_key OR x.indicator_key IN (SELECT i.denominator_indicator_key FROM public.profile_indicators i WHERE i.tenant_id=_tenant_id AND i.profile_id=cfg.profile_id AND i.key=cfg.indicator_key)
        OR x.indicator_key IN (SELECT f->>'indicator_key' FROM jsonb_array_elements(coalesce(finding.details->'evidence','[]')) f))) THEN reasons:=array_append(reasons,'new_relevant_evidence_requires_comparison'); END IF;
    next_state:=CASE WHEN (_payload->>'close_requested')::boolean AND cardinality(reasons)=0 THEN 'closed_resolved' ELSE 'remain_open' END;
    d:=_payload||jsonb_build_object('comparison_event_id',comparison.id,'configuration_id',cfg.id,'closure_criteria',c.opening_definition->'closure_criteria','reasons',to_jsonb(reasons),'causality','not_established');
  ELSE RAISE EXCEPTION 'unsupported_command' USING ERRCODE='22023';
  END IF;
  INSERT INTO public.cw_operational_events(tenant_id,subject_id,case_id,sequence,operation_id,request_hash,command,from_state,to_state,details,created_by)
    VALUES(_tenant_id,c.subject_id,c.id,c.version+1,_operation_id,h,_command,c.state,next_state,d,auth.uid()) RETURNING id INTO v_id;
  UPDATE public.cw_operational_cases SET state=next_state,version=version+1 WHERE id=c.id;
  RETURN v_id;
END $$;
REVOKE ALL ON FUNCTION public._cwop_projection_guard(),public._cwop_text(jsonb,text),public._cwop_reference(jsonb,text),public._cwop_keys(jsonb,text[]) FROM PUBLIC,anon,authenticated;
REVOKE ALL ON FUNCTION public.open_operational_case(uuid,uuid,uuid,jsonb),public.command_operational_case(uuid,uuid,integer,uuid,text,jsonb) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.open_operational_case(uuid,uuid,uuid,jsonb),public.command_operational_case(uuid,uuid,integer,uuid,text,jsonb) TO authenticated;
NOTIFY pgrst,'reload schema';
