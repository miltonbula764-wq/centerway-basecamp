-- Additive C04 numeric goal evaluation. No changes to installed migrations or demo cases.
CREATE TABLE public.c04_configurations (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES public.tenants(id), subject_id uuid NOT NULL,
  profile_id uuid NOT NULL, indicator_key text NOT NULL,
  version integer NOT NULL CHECK(version > 0), previous_id uuid,
  operation_id uuid NOT NULL, request_hash text NOT NULL,
  definition jsonb NOT NULL CHECK(jsonb_typeof(definition)='object'),
  pending_fields text[] NOT NULL,
  created_by uuid NOT NULL, created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  UNIQUE(tenant_id,id), UNIQUE(tenant_id,subject_id,id),
  UNIQUE(tenant_id,operation_id), UNIQUE(tenant_id,subject_id,indicator_key,version),
  FOREIGN KEY(tenant_id,subject_id) REFERENCES public.subjects(tenant_id,id),
  FOREIGN KEY(tenant_id,profile_id) REFERENCES public.tenant_value_profiles(tenant_id,id),
  FOREIGN KEY(tenant_id,subject_id,previous_id) REFERENCES public.c04_configurations(tenant_id,subject_id,id)
);
CREATE TABLE public.c04_evaluations (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES public.tenants(id), subject_id uuid NOT NULL,
  configuration_id uuid NOT NULL, bundle_id uuid NOT NULL,
  algorithm_version text NOT NULL CHECK(algorithm_version='c04-numeric-v1'),
  configuration_state text NOT NULL CHECK(configuration_state IN ('compatible','contradiction','missing_documentation','not_checkable')),
  result text NOT NULL CHECK(result IN ('achieved','not_achieved','pending_deadline','inconclusive')),
  evidence text NOT NULL CHECK(evidence IN ('sufficient','insufficient')),
  core_disposition text NOT NULL CHECK(core_disposition IN ('needs_information','configuration_review','assessment_available')),
  details jsonb NOT NULL, created_by uuid NOT NULL, created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  UNIQUE(tenant_id,id), UNIQUE(configuration_id,bundle_id,algorithm_version),
  FOREIGN KEY(tenant_id,subject_id,configuration_id) REFERENCES public.c04_configurations(tenant_id,subject_id,id),
  FOREIGN KEY(tenant_id,subject_id,bundle_id) REFERENCES public.c03_bundles(tenant_id,subject_id,id)
);
CREATE INDEX c04_configurations_subject_idx ON public.c04_configurations(tenant_id,subject_id,created_at DESC);
CREATE INDEX c04_evaluations_subject_idx ON public.c04_evaluations(tenant_id,subject_id,created_at DESC);
DO $$ DECLARE t text; BEGIN
  FOREACH t IN ARRAY ARRAY['c04_configurations','c04_evaluations'] LOOP
    EXECUTE format('REVOKE ALL ON public.%I FROM PUBLIC,anon,authenticated',t);
    EXECUTE format('GRANT SELECT ON public.%I TO authenticated',t);
    EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY',t);
    EXECUTE format('CREATE POLICY tenant_read ON public.%I FOR SELECT TO authenticated USING (public.is_tenant_member(tenant_id))',t);
    EXECUTE format('CREATE TRIGGER immutable BEFORE UPDATE OR DELETE ON public.%I FOR EACH ROW EXECUTE FUNCTION public._c02_immutable()',t);
    EXECUTE format('CREATE TRIGGER audit AFTER INSERT ON public.%I FOR EACH ROW EXECUTE FUNCTION public._cw_audit()',t);
  END LOOP;
END $$;

-- Nullable fields are deliberately persisted as pending information, never defaulted.
CREATE FUNCTION public.save_c04_configuration(_tenant_id uuid,_subject_id uuid,_profile_id uuid,
  _indicator_key text,_previous_id uuid,_operation_id uuid,_definition jsonb)
RETURNS uuid LANGUAGE plpgsql SECURITY DEFINER SET search_path=public AS $$
DECLARE old public.c04_configurations; latest public.c04_configurations; v_id uuid; h text; k text; v jsonb; pending text[]:='{}';
BEGIN
  IF NOT public.has_tenant_role(_tenant_id,ARRAY['admin']::public.member_role[]) THEN
    RAISE EXCEPTION 'admin_required' USING ERRCODE='42501'; END IF;
  IF _operation_id IS NULL OR _definition IS NULL OR jsonb_typeof(_definition)<>'object' OR length(_definition::text)>20000 THEN
    RAISE EXCEPTION 'invalid_configuration' USING ERRCODE='22023'; END IF;
  h:=encode(sha256(convert_to(jsonb_build_array(_subject_id,_profile_id,_indicator_key,_previous_id,_definition)::text,'UTF8')),'hex');
  -- Same lock order as profile approval; serializes revisions and operation replay.
  PERFORM 1 FROM public.tenants WHERE id=_tenant_id FOR UPDATE;
  SELECT * INTO old FROM public.c04_configurations WHERE tenant_id=_tenant_id AND operation_id=_operation_id;
  IF FOUND THEN
    IF old.request_hash<>h THEN RAISE EXCEPTION 'idempotency_conflict' USING ERRCODE='22023'; END IF;
    RETURN old.id;
  END IF;
  IF NOT EXISTS(SELECT FROM public.subjects WHERE tenant_id=_tenant_id AND id=_subject_id) THEN
    RAISE EXCEPTION 'subject_not_found' USING ERRCODE='22023'; END IF;
  IF NOT EXISTS(SELECT FROM public.tenant_value_profiles p JOIN public.profile_indicators i ON i.tenant_id=p.tenant_id AND i.profile_id=p.id
    WHERE p.tenant_id=_tenant_id AND p.id=_profile_id AND p.status IN ('approved','superseded')
      AND i.key=_indicator_key AND i.classification='outcome') THEN
    RAISE EXCEPTION 'approved_outcome_required' USING ERRCODE='22023'; END IF;
  FOR k,v IN SELECT * FROM jsonb_each(_definition) LOOP
    IF k NOT IN ('promise','promise_ref','plan_capability','plan_ref','customer_goal','customer_ref','compatibility','compatibility_ref',
      'unit','source','aggregation','comparator','target','deadline','window_count','observation_start') THEN
      RAISE EXCEPTION 'unknown_configuration_field: %',k USING ERRCODE='22023'; END IF;
    IF v<>'null'::jsonb THEN
      IF k IN ('target','window_count') THEN
        IF jsonb_typeof(v)<>'number' THEN RAISE EXCEPTION 'numeric_field_required: %',k USING ERRCODE='22023'; END IF;
      ELSIF jsonb_typeof(v)<>'string' OR length(btrim(v#>>'{}')) NOT BETWEEN 1 AND 4000 THEN
        RAISE EXCEPTION 'invalid_text_field: %',k USING ERRCODE='22023';
      END IF;
    END IF;
  END LOOP;
  IF (_definition->>'window_count')::numeric NOT BETWEEN 1 AND 100
    OR (_definition->>'window_count')::numeric<>trunc((_definition->>'window_count')::numeric)
    OR _definition->>'comparator' NOT IN ('lt','lte','gt','gte','eq')
    OR _definition->>'aggregation' NOT IN ('mean','sum','last')
    OR _definition->>'compatibility' NOT IN ('compatible','contradiction','not_checkable') THEN
    RAISE EXCEPTION 'unsupported_configuration' USING ERRCODE='22023'; END IF;
  FOREACH k IN ARRAY ARRAY['deadline','observation_start'] LOOP
    IF _definition->>k IS NOT NULL THEN
      IF (_definition->>k)!~'(Z|[+-][0-9]{2}:[0-9]{2})$' OR NOT isfinite((_definition->>k)::timestamptz) THEN
        RAISE EXCEPTION 'timestamp_with_timezone_required' USING ERRCODE='22023'; END IF;
    END IF;
  END LOOP;
  IF (_definition->>'observation_start')::timestamptz >= (_definition->>'deadline')::timestamptz THEN
    RAISE EXCEPTION 'invalid_goal_period' USING ERRCODE='22023'; END IF;
  FOREACH k IN ARRAY ARRAY['promise','promise_ref','plan_capability','plan_ref','customer_goal','customer_ref','compatibility','compatibility_ref',
    'unit','source','aggregation','comparator','target','deadline','window_count','observation_start'] LOOP
    IF _definition->>k IS NULL THEN pending:=array_append(pending,k); END IF;
  END LOOP;
  SELECT * INTO latest FROM public.c04_configurations WHERE tenant_id=_tenant_id AND subject_id=_subject_id
    AND indicator_key=_indicator_key ORDER BY version DESC LIMIT 1;
  IF latest.id IS DISTINCT FROM _previous_id THEN RAISE EXCEPTION 'configuration_version_conflict' USING ERRCODE='22023'; END IF;
  INSERT INTO public.c04_configurations(tenant_id,subject_id,profile_id,indicator_key,version,previous_id,operation_id,request_hash,definition,pending_fields,created_by)
    VALUES(_tenant_id,_subject_id,_profile_id,_indicator_key,coalesce(latest.version,0)+1,_previous_id,_operation_id,h,_definition,pending,auth.uid()) RETURNING id INTO v_id;
  RETURN v_id;
END $$;

CREATE FUNCTION public.evaluate_c04_configuration(_tenant_id uuid,_configuration_id uuid,_bundle_id uuid)
RETURNS uuid LANGUAGE plpgsql SECURITY DEFINER SET search_path=public AS $$
DECLARE c public.c04_configurations; b public.c03_bundles; r public.c02_runs; i public.c03_indicators;
  d jsonb; p jsonb; w jsonb; wins jsonb:='[]'; missing text[]:='{}'; reasons text[]:='{}'; k text;
  cs text; outcome text; disposition text; enough boolean:=true; met boolean:=true; n int:=0; required_n int;
  v_id uuid; measurement_met boolean; compatible_measurement boolean;
BEGIN
  IF NOT public.has_tenant_role(_tenant_id,ARRAY['admin','operator']::public.member_role[]) THEN
    RAISE EXCEPTION 'write_role_required' USING ERRCODE='42501'; END IF;
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
    AND (d->>'unit' IS NULL OR p->>'unit'=d->>'unit')
    AND (d->>'aggregation' IS NULL OR p->>'aggregation'=d->>'aggregation');
  IF compatible_measurement IS DISTINCT FROM true THEN
    enough:=false; reasons:=array_append(reasons,'historical_measurement_configuration_mismatch');
    cs:=CASE WHEN i.id IS NULL THEN 'not_checkable' ELSE 'contradiction' END;
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
REVOKE ALL ON FUNCTION public.save_c04_configuration(uuid,uuid,uuid,text,uuid,uuid,jsonb),public.evaluate_c04_configuration(uuid,uuid,uuid) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.save_c04_configuration(uuid,uuid,uuid,text,uuid,uuid,jsonb),public.evaluate_c04_configuration(uuid,uuid,uuid) TO authenticated;
COMMENT ON TABLE public.c04_evaluations IS 'Immutable per-indicator Core input. No promise fulfillment, overall value score or automatic case transition. Documentary and measured states are independent.';
NOTIFY pgrst,'reload schema';
