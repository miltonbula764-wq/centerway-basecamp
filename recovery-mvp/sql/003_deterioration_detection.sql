-- F02 is additive: no F01 table, function, assessment or historical row is changed.
BEGIN;
CREATE TABLE centerway.detection_runs (
  tenant_id uuid NOT NULL, client_id uuid NOT NULL, id uuid NOT NULL,
  contract_id uuid NOT NULL, contract_revision integer NOT NULL,
  algorithm text NOT NULL CHECK (algorithm = 'f02-v1'),
  as_of timestamptz NOT NULL CHECK (isfinite(as_of)),
  required_periods integer NOT NULL CHECK (required_periods BETWEEN 2 AND 120),
  request_key text NOT NULL CHECK (request_key ~ '^[0-9a-f]{64}$'),
  input_hash text NOT NULL CHECK (input_hash ~ '^[0-9a-f]{64}$'),
  revision integer NOT NULL CHECK (revision > 0), revision_of uuid,
  input_snapshot jsonb NOT NULL, result jsonb NOT NULL,
  state centerway.value_state NOT NULL,
  actor name NOT NULL, recorded_at timestamptz NOT NULL,
  PRIMARY KEY (tenant_id, client_id, id),
  UNIQUE (tenant_id, client_id, request_key, input_hash),
  UNIQUE (tenant_id, client_id, request_key, revision),
  FOREIGN KEY (tenant_id, client_id, contract_id, contract_revision)
    REFERENCES centerway.contract_versions (tenant_id, client_id, id, revision),
  FOREIGN KEY (tenant_id, client_id, revision_of)
    REFERENCES centerway.detection_runs (tenant_id, client_id, id),
  CHECK (jsonb_typeof(input_snapshot) = 'array' AND jsonb_typeof(result) = 'object'),
  CHECK (result->>'state' = state::text),
  CHECK ((revision = 1) = (revision_of IS NULL))
);
CREATE INDEX ON centerway.detection_runs (tenant_id, client_id, contract_id, contract_revision);
CREATE INDEX ON centerway.detection_runs (tenant_id, client_id, revision_of);
ALTER TABLE centerway.detection_runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE centerway.detection_runs FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_access ON centerway.detection_runs
  USING (centerway.allowed(tenant_id)) WITH CHECK (centerway.allowed(tenant_id));
CREATE TRIGGER immutable BEFORE UPDATE OR DELETE OR TRUNCATE ON centerway.detection_runs
  FOR EACH STATEMENT EXECUTE FUNCTION centerway.immutable();
CREATE TRIGGER audit AFTER INSERT ON centerway.detection_runs
  FOR EACH ROW EXECUTE FUNCTION centerway.audit_insert();
GRANT SELECT ON centerway.detection_runs TO centerway_api;

-- Private deterministic evaluator. It can neither read tables nor persist caller-supplied results.
-- Input is produced exclusively by run_detection, in one database snapshot.
CREATE FUNCTION centerway._evaluate_detection(p_snapshot jsonb, p_as_of timestamptz, p_required integer)
RETURNS jsonb LANGUAGE plpgsql IMMUTABLE
SET search_path = pg_catalog, centerway, pg_temp SET timezone = 'UTC' AS $$
DECLARE
  item jsonb; c jsonb; previous_c jsonb; e jsonb; current_result jsonb;
  results jsonb := '[]'; reasons jsonb; used_refs jsonb; ignored_refs jsonb;
  value numeric; candidate_value numeric; previous_value numeric; delta numeric;
  state centerway.value_state; previous_state centerway.value_state;
  full_count integer; outcome_count integer; conflict boolean; uncertain boolean;
  comparison text; comparison_reason text; fingerprint jsonb; previous_fingerprint jsonb;
  tail jsonb; sustained boolean; sustained_reason text; n integer;
BEGIN
  FOR item IN SELECT x FROM jsonb_array_elements(p_snapshot) AS t(x) LOOP
    c := item->'contract'; reasons := '[]'; used_refs := '[]'; ignored_refs := '[]';
    value := NULL; full_count := 0; outcome_count := 0; conflict := false; uncertain := false;
    FOR e IN SELECT x FROM jsonb_array_elements(item->'evidence') AS t(x) LOOP
      IF e->>'evidence_type' = 'usage' THEN
        ignored_refs := ignored_refs || jsonb_build_array(jsonb_build_object(
          'id',e->'id','revision',e->'revision','reason','usage_is_not_outcome'));
        CONTINUE;
      END IF;
      outcome_count := outcome_count + 1;
      IF e->>'quality' <> 'verified' THEN
        uncertain := true;
        IF NOT reasons ? (e->>'quality' || '_quality') THEN
          reasons := reasons || jsonb_build_array(e->>'quality' || '_quality');
        END IF;
      END IF;
      IF (e->>'period_start')::timestamptz <> (c->>'period_start')::timestamptz
         OR (e->>'period_end')::timestamptz <> (c->>'period_end')::timestamptz THEN
        ignored_refs := ignored_refs || jsonb_build_array(jsonb_build_object(
          'id',e->'id','revision',e->'revision','reason','incomplete_window'));
        CONTINUE;
      END IF;
      candidate_value := (e->>'observed_value')::numeric;
      IF full_count > 0 AND candidate_value <> value THEN conflict := true; END IF;
      value := candidate_value;
      full_count := full_count + 1;
      used_refs := used_refs || jsonb_build_array(jsonb_build_object('id',e->'id','revision',e->'revision'));
    END LOOP;
    state := 'resultado_inconclusivo';
    IF jsonb_array_length(item->'evidence') = 0 THEN reasons := reasons || '"missing_evidence"'::jsonb; END IF;
    IF outcome_count = 0 THEN reasons := reasons || '"no_outcome_evidence"'::jsonb; END IF;
    IF full_count = 0 THEN reasons := reasons || '"no_complete_window"'::jsonb; END IF;
    IF conflict THEN reasons := reasons || '"contradictory_results"'::jsonb; END IF;
    IF (c->>'period_end')::timestamptz > p_as_of THEN reasons := reasons || '"period_not_closed"'::jsonb; END IF;
    IF full_count > 0 AND NOT conflict AND NOT uncertain AND (c->>'period_end')::timestamptz <= p_as_of THEN
      IF (c->>'direction' = 'higher' AND value < (c->>'baseline')::numeric)
         OR (c->>'direction' = 'lower' AND value > (c->>'baseline')::numeric) THEN
        state := 'deterioracao_demonstrada'; reasons := reasons || '"worse_than_baseline"'::jsonb;
      ELSIF (c->>'direction' = 'higher' AND value >= (c->>'minimum_acceptable')::numeric)
         OR (c->>'direction' = 'lower' AND value <= (c->>'minimum_acceptable')::numeric) THEN
        state := 'valor_demonstrado'; reasons := reasons || '"minimum_met"'::jsonb;
      ELSE state := 'valor_insuficiente'; reasons := reasons || '"minimum_not_met"'::jsonb; END IF;
    ELSE
      -- Never resolve conflicting/uncertain reports by order, average, vote or choosing a winner.
      value := NULL;
    END IF;

    fingerprint := c - ARRAY['tenant_id','client_id','id','revision','actor','recorded_at','reason','period_start','period_end'];
    comparison := 'inconclusive'; delta := NULL;
    IF previous_c IS NULL THEN comparison_reason := 'no_previous_period';
    ELSIF (c->>'period_start')::timestamptz <> (previous_c->>'period_end')::timestamptz THEN
      comparison_reason := 'non_contiguous_periods';
    ELSIF (c->>'period_end')::timestamptz - (c->>'period_start')::timestamptz <>
          (previous_c->>'period_end')::timestamptz - (previous_c->>'period_start')::timestamptz THEN
      comparison_reason := 'unequal_duration';
    ELSIF fingerprint <> previous_fingerprint THEN comparison_reason := 'incompatible_contracts';
    ELSIF state = 'resultado_inconclusivo' OR previous_state = 'resultado_inconclusivo' THEN
      comparison_reason := 'inconclusive_period';
    ELSE
      delta := value - previous_value;
      IF delta = 0 THEN comparison := 'unchanged';
      ELSIF (c->>'direction' = 'higher' AND delta < 0) OR (c->>'direction' = 'lower' AND delta > 0) THEN
        comparison := 'worsening';
      ELSE comparison := 'improving'; END IF;
      comparison_reason := 'comparable_declared_results';
    END IF;
    current_result := jsonb_build_object('contract_id',c->'id','contract_revision',c->'revision',
      'period_start',c->'period_start','period_end',c->'period_end','state',state,
      'observed_value',value,'reason_codes',reasons,'considered_evidence_refs',used_refs,
      'excluded_evidence_refs',ignored_refs,'comparison',jsonb_build_object(
        'status',comparison,'reason',comparison_reason,'delta',delta,
        'previous_contract_revision',previous_c->'revision'));
    results := results || jsonb_build_array(current_result);
    previous_c := c; previous_fingerprint := fingerprint; previous_value := value; previous_state := state;
  END LOOP;

  n := jsonb_array_length(results);
  sustained := NULL;
  IF n < p_required THEN sustained_reason := 'insufficient_periods';
  ELSE
    SELECT jsonb_agg(x ORDER BY ord) INTO tail
      FROM jsonb_array_elements(results) WITH ORDINALITY AS t(x,ord) WHERE ord > n - p_required;
    IF EXISTS (SELECT 1 FROM jsonb_array_elements(tail) AS t(x) WHERE x->>'state' = 'resultado_inconclusivo') THEN
      sustained_reason := 'inconclusive_period';
    ELSIF EXISTS (SELECT 1 FROM jsonb_array_elements(tail) WITH ORDINALITY AS t(x,ord)
                  WHERE ord > 1 AND x->'comparison'->>'status' = 'inconclusive') THEN
      sustained_reason := 'incompatible_sequence';
    ELSE
      SELECT bool_and(x->>'state' = 'deterioracao_demonstrada') INTO sustained
        FROM jsonb_array_elements(tail) AS t(x);
      sustained_reason := CASE WHEN sustained THEN 'sustained_baseline_deterioration' ELSE 'criterion_not_met' END;
    END IF;
  END IF;
  RETURN jsonb_build_object('state',state,'periods',results,
    'sustained_deterioration',sustained,'sustained_reason',sustained_reason,
    'required_periods',p_required,'support_basis','producer_declared_evidence',
    'independent_verification','not_established','causal_inference','not_performed');
END $$;
REVOKE ALL ON FUNCTION centerway._evaluate_detection(jsonb,timestamptz,integer) FROM PUBLIC;

CREATE FUNCTION centerway.run_detection(
  p_tenant uuid, p_client uuid, p_contract uuid, p_revisions integer[],
  p_as_of timestamptz, p_required_periods integer
) RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, centerway, pg_temp SET timezone = 'UTC' SET datestyle = 'ISO, YMD' AS $$
DECLARE
  refs integer[]; config jsonb; snapshot jsonb; evaluation jsonb;
  request_hash text; snapshot_hash text; existing centerway.detection_runs;
  previous centerway.detection_runs; created centerway.detection_runs; latest jsonb;
BEGIN
  IF p_tenant IS NULL OR NOT centerway.allowed(p_tenant) THEN
    RAISE EXCEPTION 'not_authorized' USING ERRCODE = '42501';
  END IF;
  IF p_client IS NULL OR p_contract IS NULL OR p_as_of IS NULL OR NOT isfinite(p_as_of)
     OR p_as_of > clock_timestamp() OR p_required_periods IS NULL OR p_required_periods NOT BETWEEN 2 AND 120
     OR p_revisions IS NULL OR cardinality(p_revisions) NOT BETWEEN 1 AND 120
     OR array_ndims(p_revisions) <> 1 OR array_position(p_revisions,NULL) IS NOT NULL
     OR EXISTS (SELECT 1 FROM unnest(p_revisions) AS t(r) WHERE r <= 0) THEN
    RAISE EXCEPTION 'invalid_detection_request' USING ERRCODE = '22023';
  END IF;
  SELECT array_agg(DISTINCT r ORDER BY r) INTO refs FROM unnest(p_revisions) AS t(r);
  IF cardinality(refs) <> cardinality(p_revisions) THEN
    RAISE EXCEPTION 'duplicate_revision' USING ERRCODE = '22023';
  END IF;
  config := jsonb_build_object('algorithm','f02-v1','tenant_id',p_tenant,'client_id',p_client,
    'contract_id',p_contract,'revisions',refs,'as_of',p_as_of,'required_periods',p_required_periods);
  request_hash := encode(sha256(convert_to(config::text,'UTF8')),'hex');
  -- Serializes identical requests, including retries while another run is committing.
  PERFORM pg_advisory_xact_lock(hashtextextended(request_hash,0));

  -- ONE SELECT captures contracts, sources and latest visible evidence revisions together.
  SELECT coalesce(jsonb_agg(jsonb_build_object('contract',to_jsonb(c),'source',to_jsonb(s),
    'evidence',coalesce(ev.items,'[]'::jsonb)) ORDER BY c.period_start,c.period_end,c.revision),'[]'::jsonb)
    INTO snapshot
    FROM centerway.contract_versions c
    JOIN centerway.source_versions s ON (s.tenant_id,s.client_id,s.id,s.revision) =
      (c.tenant_id,c.client_id,c.source_id,c.source_revision)
    LEFT JOIN LATERAL (
      SELECT jsonb_agg(to_jsonb(e) ORDER BY e.id) AS items FROM (
        SELECT DISTINCT ON (v.id) v.* FROM centerway.evidence_versions v
        WHERE (v.tenant_id,v.client_id,v.contract_id,v.contract_revision) =
          (c.tenant_id,c.client_id,c.id,c.revision) AND v.recorded_at <= p_as_of
        ORDER BY v.id,v.revision DESC
      ) e
    ) ev ON true
    WHERE (c.tenant_id,c.client_id,c.id) = (p_tenant,p_client,p_contract)
      AND c.revision = ANY(refs) AND c.recorded_at <= p_as_of AND s.recorded_at <= p_as_of;
  IF jsonb_array_length(snapshot) <> cardinality(refs) THEN
    RAISE EXCEPTION 'contract_not_available_at_cutoff' USING ERRCODE = '22023';
  END IF;
  IF EXISTS (SELECT 1 FROM jsonb_array_elements(snapshot) AS t(x)
      GROUP BY x->'contract'->>'period_start',x->'contract'->>'period_end' HAVING count(*) > 1) THEN
    RAISE EXCEPTION 'multiple_versions_for_same_period' USING ERRCODE = '22023';
  END IF;
  snapshot_hash := encode(sha256(convert_to(snapshot::text,'UTF8')),'hex');
  SELECT * INTO existing FROM centerway.detection_runs
    WHERE (tenant_id,client_id,request_key,input_hash) = (p_tenant,p_client,request_hash,snapshot_hash);
  IF FOUND THEN RETURN to_jsonb(existing); END IF;
  SELECT * INTO previous FROM centerway.detection_runs
    WHERE (tenant_id,client_id,request_key) = (p_tenant,p_client,request_hash)
    ORDER BY revision DESC LIMIT 1;
  evaluation := centerway._evaluate_detection(snapshot,p_as_of,p_required_periods);
  latest := snapshot->(jsonb_array_length(snapshot)-1)->'contract';
  INSERT INTO centerway.detection_runs(tenant_id,client_id,id,contract_id,contract_revision,
    algorithm,as_of,required_periods,request_key,input_hash,revision,revision_of,
    input_snapshot,result,state,actor,recorded_at)
  VALUES (p_tenant,p_client,gen_random_uuid(),p_contract,(latest->>'revision')::integer,
    'f02-v1',p_as_of,p_required_periods,request_hash,snapshot_hash,coalesce(previous.revision,0)+1,previous.id,
    snapshot,evaluation,(evaluation->>'state')::centerway.value_state,session_user,clock_timestamp())
  RETURNING * INTO created;
  RETURN to_jsonb(created);
END $$;
REVOKE ALL ON FUNCTION centerway.run_detection(uuid,uuid,uuid,integer[],timestamptz,integer) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION centerway.run_detection(uuid,uuid,uuid,integer[],timestamptz,integer) TO centerway_api;

-- Investigation consumes the stored snapshot, never a recomputation with newer evidence.
CREATE FUNCTION centerway.read_detection_context(p_tenant uuid,p_client uuid,p_run uuid)
RETURNS jsonb LANGUAGE sql STABLE SECURITY INVOKER
SET search_path = pg_catalog, centerway, pg_temp AS $$
  SELECT to_jsonb(r) FROM centerway.detection_runs r
    WHERE (r.tenant_id,r.client_id,r.id) = (p_tenant,p_client,p_run)
$$;
REVOKE ALL ON FUNCTION centerway.read_detection_context(uuid,uuid,uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION centerway.read_detection_context(uuid,uuid,uuid) TO centerway_api;
COMMIT;
