-- F03: additive investigation over immutable F02 detections; no intervention execution.
BEGIN;
CREATE TABLE centerway.investigations (
  tenant_id uuid NOT NULL, client_id uuid NOT NULL, id uuid NOT NULL,
  detection_id uuid NOT NULL, contract_id uuid NOT NULL, contract_revision integer NOT NULL,
  question centerway.label NOT NULL, actor name NOT NULL, recorded_at timestamptz NOT NULL,
  PRIMARY KEY (tenant_id,client_id,id),
  FOREIGN KEY (tenant_id,client_id,detection_id) REFERENCES centerway.detection_runs(tenant_id,client_id,id),
  FOREIGN KEY (tenant_id,client_id,contract_id,contract_revision)
    REFERENCES centerway.contract_versions(tenant_id,client_id,id,revision)
);
CREATE TABLE centerway.investigation_factor_versions (
  tenant_id uuid NOT NULL, client_id uuid NOT NULL, investigation_id uuid NOT NULL,
  id uuid NOT NULL, revision integer NOT NULL CHECK (revision > 0),
  scope text NOT NULL CHECK (scope IN ('internal','external','mixed')),
  category centerway.label NOT NULL, hypothesis centerway.label NOT NULL,
  requirement centerway.label NOT NULL, condition centerway.label NOT NULL,
  test_protocol centerway.label NOT NULL, assessment_at timestamptz NOT NULL CHECK (isfinite(assessment_at)),
  control text NOT NULL CHECK (control IN ('saas','client','third_party','unknown','none')),
  responsible_party centerway.label,
  actor name NOT NULL, recorded_at timestamptz NOT NULL, reason centerway.label NOT NULL,
  PRIMARY KEY (tenant_id,client_id,investigation_id,id,revision),
  FOREIGN KEY (tenant_id,client_id,investigation_id) REFERENCES centerway.investigations(tenant_id,client_id,id),
  CHECK ((control IN ('saas','client','third_party')) = (responsible_party IS NOT NULL))
);
CREATE TABLE centerway.investigation_evidence_versions (
  tenant_id uuid NOT NULL, client_id uuid NOT NULL, investigation_id uuid NOT NULL,
  id uuid NOT NULL, revision integer NOT NULL CHECK (revision > 0),
  factor_id uuid NOT NULL, factor_revision integer NOT NULL,
  purpose text NOT NULL CHECK (purpose IN ('requirement_applies','condition_met')),
  kind text NOT NULL CHECK (kind IN ('direct_observation','document','reproduction','usage_context')),
  assertion boolean NOT NULL, source_id uuid NOT NULL, source_revision integer NOT NULL,
  reference centerway.label NOT NULL, content_sha256 text NOT NULL CHECK (content_sha256 ~ '^[0-9a-f]{64}$'),
  collected_at timestamptz NOT NULL CHECK (isfinite(collected_at)),
  actor name NOT NULL, recorded_at timestamptz NOT NULL, reason centerway.label NOT NULL,
  PRIMARY KEY (tenant_id,client_id,investigation_id,id,revision),
  FOREIGN KEY (tenant_id,client_id,investigation_id,factor_id,factor_revision)
    REFERENCES centerway.investigation_factor_versions(tenant_id,client_id,investigation_id,id,revision),
  FOREIGN KEY (tenant_id,client_id,source_id,source_revision)
    REFERENCES centerway.source_versions(tenant_id,client_id,id,revision)
);
CREATE TABLE centerway.investigation_verification_versions (
  tenant_id uuid NOT NULL, client_id uuid NOT NULL, investigation_id uuid NOT NULL,
  id uuid NOT NULL, revision integer NOT NULL CHECK (revision > 0),
  evidence_id uuid NOT NULL, evidence_revision integer NOT NULL,
  verdict text NOT NULL CHECK (verdict IN ('confirmed','rejected','unverifiable')),
  checked_assertion boolean, method centerway.label NOT NULL, explanation centerway.label NOT NULL,
  source_id uuid NOT NULL, source_revision integer NOT NULL,
  reference centerway.label NOT NULL, content_sha256 text NOT NULL CHECK (content_sha256 ~ '^[0-9a-f]{64}$'),
  checked_at timestamptz NOT NULL CHECK (isfinite(checked_at)),
  actor name NOT NULL, recorded_at timestamptz NOT NULL, reason centerway.label NOT NULL,
  PRIMARY KEY (tenant_id,client_id,investigation_id,id,revision),
  UNIQUE (tenant_id,client_id,investigation_id,evidence_id,evidence_revision,actor,revision),
  FOREIGN KEY (tenant_id,client_id,investigation_id,evidence_id,evidence_revision)
    REFERENCES centerway.investigation_evidence_versions(tenant_id,client_id,investigation_id,id,revision),
  FOREIGN KEY (tenant_id,client_id,source_id,source_revision)
    REFERENCES centerway.source_versions(tenant_id,client_id,id,revision),
  CHECK ((verdict = 'unverifiable') = (checked_assertion IS NULL))
);
CREATE TABLE centerway.investigation_runs (
  tenant_id uuid NOT NULL, client_id uuid NOT NULL, investigation_id uuid NOT NULL, id uuid NOT NULL,
  algorithm text NOT NULL CHECK (algorithm = 'f03-v1'),
  as_of timestamptz NOT NULL CHECK (isfinite(as_of)),
  revision integer NOT NULL CHECK (revision > 0), revision_of uuid,
  input_hash text NOT NULL CHECK (input_hash ~ '^[0-9a-f]{64}$'),
  input_snapshot jsonb NOT NULL, result jsonb NOT NULL,
  actor name NOT NULL, recorded_at timestamptz NOT NULL,
  PRIMARY KEY (tenant_id,client_id,investigation_id,id),
  UNIQUE (tenant_id,client_id,investigation_id,as_of,input_hash),
  UNIQUE (tenant_id,client_id,investigation_id,as_of,revision),
  FOREIGN KEY (tenant_id,client_id,investigation_id) REFERENCES centerway.investigations(tenant_id,client_id,id),
  FOREIGN KEY (tenant_id,client_id,investigation_id,revision_of)
    REFERENCES centerway.investigation_runs(tenant_id,client_id,investigation_id,id),
  CHECK ((revision = 1) = (revision_of IS NULL))
);
CREATE INDEX ON centerway.investigations(tenant_id,client_id,detection_id);
CREATE INDEX ON centerway.investigations(tenant_id,client_id,contract_id,contract_revision);
CREATE INDEX ON centerway.investigation_evidence_versions(tenant_id,client_id,investigation_id,factor_id,factor_revision);
CREATE INDEX ON centerway.investigation_evidence_versions(tenant_id,client_id,source_id,source_revision);
CREATE INDEX ON centerway.investigation_verification_versions(tenant_id,client_id,source_id,source_revision);
CREATE INDEX ON centerway.investigation_runs(tenant_id,client_id,investigation_id,revision_of);
DO $$
DECLARE t text;
BEGIN
  FOREACH t IN ARRAY ARRAY['investigations','investigation_factor_versions','investigation_evidence_versions',
                          'investigation_verification_versions','investigation_runs'] LOOP
    EXECUTE format('ALTER TABLE centerway.%I ENABLE ROW LEVEL SECURITY',t);
    EXECUTE format('ALTER TABLE centerway.%I FORCE ROW LEVEL SECURITY',t);
    EXECUTE format('CREATE POLICY tenant_access ON centerway.%I USING (centerway.allowed(tenant_id)) WITH CHECK (centerway.allowed(tenant_id))',t);
    EXECUTE format('CREATE TRIGGER immutable BEFORE UPDATE OR DELETE OR TRUNCATE ON centerway.%I FOR EACH STATEMENT EXECUTE FUNCTION centerway.immutable()',t);
    EXECUTE format('CREATE TRIGGER audit AFTER INSERT ON centerway.%I FOR EACH ROW EXECUTE FUNCTION centerway.audit_insert()',t);
    EXECUTE format('GRANT SELECT ON centerway.%I TO centerway_api',t);
  END LOOP;
END $$;

CREATE FUNCTION centerway.open_investigation(p_tenant uuid,p_client uuid,p_id uuid,
  p_detection uuid,p_contract_revision integer,p_question text) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog,centerway,pg_temp AS $$
DECLARE d centerway.detection_runs; created centerway.investigations;
BEGIN
  IF p_tenant IS NULL OR NOT centerway.allowed(p_tenant) THEN
    RAISE EXCEPTION 'not_authorized' USING ERRCODE='42501';
  END IF;
  SELECT * INTO STRICT d FROM centerway.detection_runs
    WHERE (tenant_id,client_id,id)=(p_tenant,p_client,p_detection);
  IF p_contract_revision IS NULL OR NOT EXISTS (
    SELECT 1 FROM jsonb_array_elements(d.result->'periods') t(x)
    WHERE (x->>'contract_revision')::integer=p_contract_revision) THEN
    RAISE EXCEPTION 'period_not_in_detection' USING ERRCODE='22023';
  END IF;
  INSERT INTO centerway.investigations VALUES
    (p_tenant,p_client,p_id,p_detection,d.contract_id,p_contract_revision,p_question,session_user,clock_timestamp())
    RETURNING * INTO created;
  RETURN to_jsonb(created);
END $$;

CREATE FUNCTION centerway._validate_investigation_record() RETURNS trigger
LANGUAGE plpgsql SET search_path=pg_catalog,centerway,pg_temp AS $$
DECLARE c centerway.contract_versions; e centerway.investigation_evidence_versions; previous jsonb; assessment_time timestamptz;
BEGIN
  IF TG_TABLE_NAME='investigation_factor_versions' THEN
    SELECT c0.* INTO STRICT c FROM centerway.contract_versions c0
      JOIN centerway.investigations i ON (i.tenant_id,i.client_id,i.contract_id,i.contract_revision)=
        (c0.tenant_id,c0.client_id,c0.id,c0.revision)
      WHERE (i.tenant_id,i.client_id,i.id)=(NEW.tenant_id,NEW.client_id,NEW.investigation_id);
    IF NEW.assessment_at < c.period_start OR NEW.assessment_at >= c.period_end OR NEW.assessment_at > clock_timestamp() THEN
      RAISE EXCEPTION 'assessment_outside_detection_period' USING ERRCODE='23514';
    END IF;
  ELSIF TG_TABLE_NAME='investigation_evidence_versions' THEN
    IF NEW.collected_at > clock_timestamp() THEN
      RAISE EXCEPTION 'future_collection' USING ERRCODE='23514';
    END IF;
  ELSE
    SELECT * INTO STRICT e FROM centerway.investigation_evidence_versions
      WHERE (tenant_id,client_id,investigation_id,id,revision)=
        (NEW.tenant_id,NEW.client_id,NEW.investigation_id,NEW.evidence_id,NEW.evidence_revision);
    IF NEW.actor=e.actor THEN RAISE EXCEPTION 'self_verification_forbidden' USING ERRCODE='42501'; END IF;
    SELECT assessment_at INTO STRICT assessment_time FROM centerway.investigation_factor_versions
      WHERE (tenant_id,client_id,investigation_id,id,revision)=
        (e.tenant_id,e.client_id,e.investigation_id,e.factor_id,e.factor_revision);
    IF NEW.checked_at > clock_timestamp() OR NEW.checked_at < e.collected_at OR NEW.checked_at < assessment_time THEN
      RAISE EXCEPTION 'invalid_verification_time' USING ERRCODE='23514';
    END IF;
    IF (NEW.verdict='confirmed' AND NEW.checked_assertion IS DISTINCT FROM e.assertion)
       OR (NEW.verdict='rejected' AND NEW.checked_assertion IS NOT DISTINCT FROM e.assertion) THEN
      RAISE EXCEPTION 'verdict_assertion_mismatch' USING ERRCODE='23514';
    END IF;
  END IF;
  IF NEW.revision > 1 AND TG_TABLE_NAME<>'investigation_factor_versions' THEN
    EXECUTE format('SELECT to_jsonb(t) FROM centerway.%I t WHERE tenant_id=$1 AND client_id=$2 AND investigation_id=$3 AND id=$4 AND revision=$5',TG_TABLE_NAME)
      INTO previous USING NEW.tenant_id,NEW.client_id,NEW.investigation_id,NEW.id,NEW.revision-1;
    IF TG_TABLE_NAME='investigation_evidence_versions' THEN
      IF (previous - ARRAY['assertion','source_id','source_revision','reference','content_sha256','collected_at','actor','recorded_at','reason','revision']) <>
         (to_jsonb(NEW) - ARRAY['assertion','source_id','source_revision','reference','content_sha256','collected_at','actor','recorded_at','reason','revision']) THEN
        RAISE EXCEPTION 'correction_changes_proposition' USING ERRCODE='23514';
      END IF;
    ELSIF previous->>'evidence_id'<>NEW.evidence_id::text OR previous->>'evidence_revision'<>NEW.evidence_revision::text
       OR previous->>'actor'<>NEW.actor::text THEN
      RAISE EXCEPTION 'correction_changes_review_subject' USING ERRCODE='23514';
    END IF;
  END IF;
  RETURN NEW;
END $$;
DO $$
DECLARE t text;
BEGIN
  FOREACH t IN ARRAY ARRAY['investigation_factor_versions','investigation_evidence_versions','investigation_verification_versions'] LOOP
    EXECUTE format('CREATE TRIGGER validate BEFORE INSERT ON centerway.%I FOR EACH ROW EXECUTE FUNCTION centerway._validate_investigation_record()',t);
  END LOOP;
END $$;

CREATE FUNCTION centerway.append_investigation_record(p_tenant uuid,p_client uuid,p_investigation uuid,
  p_kind text,p_id uuid,p_expected_revision integer,p_reason text,p_data jsonb) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,centerway,pg_temp AS $$
DECLARE tbl text; latest integer; allowed_keys text[]; k text; typ oid; result jsonb;
BEGIN
  IF p_tenant IS NULL OR NOT centerway.allowed(p_tenant) THEN
    RAISE EXCEPTION 'not_authorized' USING ERRCODE='42501';
  END IF;
  IF p_kind IS NULL OR p_kind NOT IN ('factor','evidence','verification') OR p_id IS NULL
     OR p_expected_revision IS NULL OR p_expected_revision<0 OR p_data IS NULL OR jsonb_typeof(p_data)<>'object' THEN
    RAISE EXCEPTION 'invalid_investigation_request' USING ERRCODE='22023';
  END IF;
  PERFORM 1 FROM centerway.investigations WHERE (tenant_id,client_id,id)=(p_tenant,p_client,p_investigation);
  IF NOT FOUND THEN RAISE EXCEPTION 'investigation_not_found' USING ERRCODE='22023'; END IF;
  tbl:='investigation_'||p_kind||'_versions';
  SELECT array_agg(attname::text) INTO allowed_keys FROM pg_attribute
    WHERE attrelid=('centerway.'||tbl)::regclass AND attnum>0 AND NOT attisdropped
      AND attname NOT IN ('tenant_id','client_id','investigation_id','id','revision','actor','recorded_at','reason');
  FOR k IN SELECT jsonb_object_keys(p_data) LOOP
    IF NOT k=ANY(allowed_keys) THEN RAISE EXCEPTION 'unknown_or_reserved_field: %',k USING ERRCODE='22023'; END IF;
    SELECT atttypid INTO typ FROM pg_attribute WHERE attrelid=('centerway.'||tbl)::regclass AND attname=k;
    IF p_data->k<>'null'::jsonb THEN
      IF (typ='integer'::regtype AND jsonb_typeof(p_data->k)<>'number')
         OR (typ='boolean'::regtype AND jsonb_typeof(p_data->k)<>'boolean')
         OR (typ NOT IN ('integer'::regtype,'boolean'::regtype) AND jsonb_typeof(p_data->k)<>'string') THEN
        RAISE EXCEPTION 'invalid_field_type: %',k USING ERRCODE='22023';
      END IF;
      IF typ='timestamptz'::regtype AND (p_data->>k)!~'(Z|[+-][0-9]{2}:[0-9]{2})$' THEN
        RAISE EXCEPTION 'timezone_required: %',k USING ERRCODE='22023';
      END IF;
    END IF;
  END LOOP;
  PERFORM pg_advisory_xact_lock(hashtextextended(p_tenant::text||p_client::text||p_investigation::text||tbl||p_id::text,0));
  EXECUTE format('SELECT coalesce(max(revision),0) FROM centerway.%I WHERE tenant_id=$1 AND client_id=$2 AND investigation_id=$3 AND id=$4',tbl)
    INTO latest USING p_tenant,p_client,p_investigation,p_id;
  IF latest<>p_expected_revision THEN RAISE EXCEPTION 'revision_conflict' USING ERRCODE='40001'; END IF;
  p_data:=p_data||jsonb_build_object('tenant_id',p_tenant,'client_id',p_client,'investigation_id',p_investigation,
    'id',p_id,'revision',latest+1,'actor',session_user,'recorded_at',clock_timestamp(),'reason',p_reason);
  EXECUTE format('INSERT INTO centerway.%I SELECT * FROM jsonb_populate_record(NULL::centerway.%I,$1) RETURNING to_jsonb(%I.*)',tbl,tbl,tbl)
    INTO result USING p_data;
  RETURN result;
END $$;

-- Private evaluator: structured propositions are never inferred from hypothesis prose.
CREATE FUNCTION centerway._evaluate_investigation(s jsonb) RETURNS jsonb
LANGUAGE plpgsql IMMUTABLE SET search_path=pg_catalog,centerway,pg_temp AS $$
DECLARE
  item jsonb; f jsonb; bundle jsonb; e jsonb; v jsonb; p text; period jsonb;
  facts jsonb:='[]'; hypotheses jsonb:='[]'; contradictions jsonb:='[]'; missing jsonb:='[]';
  conclusions jsonb:='[]'; candidates jsonb:='[]'; excluded jsonb:='[]';
  refs jsonb; review_refs jsonb; proposition_facts jsonb; factor_reasons jsonb; fact_ref jsonb;
  n integer; yes_count integer; no_count integer; checked boolean; bad boolean; conflict boolean;
  factor_bad boolean; requirement_value boolean; condition_value boolean; detection_supported boolean;
  status text; overall text; conclusion jsonb; any_unknown boolean:=false; any_demonstrated boolean:=false;
BEGIN
  SELECT x INTO period FROM jsonb_array_elements(s->'detection'->'result'->'periods') t(x)
    WHERE x->'contract_revision'=s->'investigation'->'contract_revision';
  detection_supported:=coalesce(period->>'state'='deterioracao_demonstrada'
    OR period->'comparison'->>'status'='worsening',false);
  IF NOT detection_supported THEN
    missing:=missing||jsonb_build_array(jsonb_build_object('reason','no_supported_deterioration_in_selected_period'));
  END IF;
  IF jsonb_array_length(s->'factors')=0 THEN
    missing:=missing||jsonb_build_array(jsonb_build_object('reason','no_factors_submitted')); any_unknown:=true;
  END IF;
  FOR item IN SELECT x FROM jsonb_array_elements(s->'factors') t(x) LOOP
    f:=item->'factor'; factor_bad:=NOT detection_supported; factor_reasons:='[]';
    requirement_value:=NULL; condition_value:=NULL;
    fact_ref:=jsonb_build_object('factor_id',f->'id','factor_revision',f->'revision');
    hypotheses:=hypotheses||jsonb_build_array(fact_ref||jsonb_build_object('statement',f->'hypothesis',
      'scope',f->'scope','category',f->'category','causal_status','not_established'));
    FOREACH p IN ARRAY ARRAY['requirement_applies','condition_met'] LOOP
      refs:='[]'; review_refs:='[]'; n:=0; yes_count:=0; no_count:=0; bad:=false; conflict:=false;
      FOR bundle IN SELECT x FROM jsonb_array_elements(item->'evidence') t(x) WHERE x->'evidence'->>'purpose'=p LOOP
        e:=bundle->'evidence';
        IF e->>'kind'='usage_context' THEN
          excluded:=excluded||jsonb_build_array(fact_ref||jsonb_build_object('evidence_id',e->'id',
            'evidence_revision',e->'revision','reason','usage_does_not_establish_impediment')); CONTINUE;
        END IF;
        n:=n+1;
        IF (e->>'assertion')::boolean THEN yes_count:=yes_count+1; ELSE no_count:=no_count+1; END IF;
        refs:=refs||jsonb_build_array(jsonb_build_object('id',e->'id','revision',e->'revision'));
        checked:=false;
        IF jsonb_array_length(bundle->'verifications')=0 THEN
          missing:=missing||jsonb_build_array(fact_ref||jsonb_build_object('purpose',p,'evidence_id',e->'id',
            'evidence_revision',e->'revision','reason','verification_missing')); bad:=true;
        END IF;
        FOR v IN SELECT x->'verification' FROM jsonb_array_elements(bundle->'verifications') t(x) LOOP
          review_refs:=review_refs||jsonb_build_array(jsonb_build_object('id',v->'id','revision',v->'revision'));
          IF v->>'verdict'='confirmed' THEN checked:=true;
          ELSIF v->>'verdict'='rejected' THEN
            conflict:=true;
            contradictions:=contradictions||jsonb_build_array(fact_ref||jsonb_build_object('purpose',p,
              'evidence_id',e->'id','evidence_revision',e->'revision','verification_id',v->'id',
              'verification_revision',v->'revision','reason','verification_rejected'));
          ELSE
            bad:=true;
            missing:=missing||jsonb_build_array(fact_ref||jsonb_build_object('purpose',p,'evidence_id',e->'id',
              'evidence_revision',e->'revision','verification_id',v->'id','verification_revision',v->'revision','reason','verification_unverifiable'));
          END IF;
        END LOOP;
        IF NOT checked THEN bad:=true; END IF;
      END LOOP;
      IF n=0 THEN
        bad:=true; missing:=missing||jsonb_build_array(fact_ref||jsonb_build_object('purpose',p,'reason','evidence_missing'));
      END IF;
      IF yes_count>0 AND no_count>0 THEN
        conflict:=true;
        contradictions:=contradictions||jsonb_build_array(fact_ref||jsonb_build_object('purpose',p,
          'evidence_refs',refs,'reason','conflicting_assertions'));
      END IF;
      IF bad OR conflict THEN
        factor_bad:=true; factor_reasons:=factor_reasons||jsonb_build_array(p||'_unresolved');
      ELSE
        IF p='requirement_applies' THEN requirement_value:=yes_count>0; ELSE condition_value:=yes_count>0; END IF;
        proposition_facts:=fact_ref||jsonb_build_object('predicate',p,'value',yes_count>0,
          'requirement',f->'requirement','condition',f->'condition','assessment_at',f->'assessment_at',
          'evidence_refs',refs,'verification_refs',review_refs,'basis','recorded_verification');
        facts:=facts||jsonb_build_array(proposition_facts);
      END IF;
    END LOOP;
    IF factor_bad THEN status:='inconclusivo'; any_unknown:=true;
    ELSIF requirement_value AND NOT condition_value THEN
      status:='impedimento_demonstrado'; any_demonstrated:=true;
      factor_reasons:=factor_reasons||'"documented_requirement_unmet"'::jsonb;
    ELSE
      status:='impedimento_nao_demonstrado';
      factor_reasons:=factor_reasons||to_jsonb(CASE WHEN NOT requirement_value THEN 'requirement_not_applicable' ELSE 'condition_satisfied' END::text);
    END IF;
    conclusion:=fact_ref||jsonb_build_object('status',status,'scope',f->'scope','category',f->'category',
      'reason_codes',factor_reasons,'control',f->'control','responsible_party',f->'responsible_party',
      'potentially_actionable',status='impedimento_demonstrado' AND f->>'control' IN ('saas','client','third_party'),
      'causal_status','not_established',
      'supporting_facts',coalesce((SELECT jsonb_agg(x) FROM jsonb_array_elements(facts) t(x)
        WHERE x->'factor_id'=f->'id' AND x->'factor_revision'=f->'revision'),'[]'::jsonb));
    conclusions:=conclusions||jsonb_build_array(conclusion);
  END LOOP;
  overall:=CASE WHEN any_unknown OR NOT detection_supported THEN 'inconclusivo'
    WHEN any_demonstrated THEN 'impedimento_demonstrado' ELSE 'nenhum_impedimento_demonstrado' END;
  IF overall='impedimento_demonstrado' THEN
    SELECT coalesce(jsonb_agg(x),'[]'::jsonb) INTO candidates FROM jsonb_array_elements(conclusions) t(x)
      WHERE (x->>'potentially_actionable')::boolean;
  END IF;
  RETURN jsonb_build_object('status',overall,'observed_facts',facts,'hypotheses',hypotheses,
    'contradictions',contradictions,'missing_information',missing,'excluded_evidence',excluded,
    'factor_conclusions',conclusions,'intervention_candidates',candidates,
    'execution_authorized',false,'independent_verification','not_established','causal_inference','not_performed',
    'demonstration_scope','documented_requirement_unmet_at_assessment_time');
END $$;

CREATE FUNCTION centerway.run_investigation(p_tenant uuid,p_client uuid,p_investigation uuid,p_as_of timestamptz)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER
SET search_path=pg_catalog,centerway,pg_temp SET timezone='UTC' SET datestyle='ISO, YMD' AS $$
DECLARE snapshot jsonb; fingerprint text; existing centerway.investigation_runs;
        previous centerway.investigation_runs; created centerway.investigation_runs;
BEGIN
  IF p_tenant IS NULL OR NOT centerway.allowed(p_tenant) THEN
    RAISE EXCEPTION 'not_authorized' USING ERRCODE='42501';
  END IF;
  IF p_as_of IS NULL OR NOT isfinite(p_as_of) OR p_as_of>clock_timestamp() THEN
    RAISE EXCEPTION 'invalid_cutoff' USING ERRCODE='22023';
  END IF;
  PERFORM pg_advisory_xact_lock(hashtextextended(p_tenant::text||p_client::text||p_investigation::text||p_as_of::text||'f03-v1',0));
  -- One snapshot across the frozen detection, all factor heads and their exact evidence/reviews.
  WITH root AS (
    SELECT i.*,to_jsonb(d) AS detection FROM centerway.investigations i
    JOIN centerway.detection_runs d ON (d.tenant_id,d.client_id,d.id)=(i.tenant_id,i.client_id,i.detection_id)
    WHERE (i.tenant_id,i.client_id,i.id)=(p_tenant,p_client,p_investigation) AND i.recorded_at<=p_as_of
  ), factors AS (
    SELECT DISTINCT ON (id) f.* FROM centerway.investigation_factor_versions f
    WHERE (tenant_id,client_id,investigation_id)=(p_tenant,p_client,p_investigation) AND recorded_at<=p_as_of
    ORDER BY id,revision DESC
  ), evidence AS (
    SELECT DISTINCT ON (e.id) e.* FROM centerway.investigation_evidence_versions e
    JOIN factors f ON (e.tenant_id,e.client_id,e.investigation_id,e.factor_id,e.factor_revision)=
      (f.tenant_id,f.client_id,f.investigation_id,f.id,f.revision)
    WHERE e.recorded_at<=p_as_of ORDER BY e.id,e.revision DESC
  ), reviews AS (
    SELECT DISTINCT ON (v.id) v.* FROM centerway.investigation_verification_versions v
    JOIN evidence e ON (v.tenant_id,v.client_id,v.investigation_id,v.evidence_id,v.evidence_revision)=
      (e.tenant_id,e.client_id,e.investigation_id,e.id,e.revision)
    WHERE v.recorded_at<=p_as_of ORDER BY v.id,v.revision DESC
  )
  SELECT jsonb_build_object('investigation',to_jsonb(root)-'detection','detection',root.detection,
    'factors',coalesce((SELECT jsonb_agg(jsonb_build_object('factor',to_jsonb(f),
      'evidence',coalesce((SELECT jsonb_agg(jsonb_build_object('evidence',to_jsonb(e),'source',to_jsonb(es),
        'verifications',coalesce((SELECT jsonb_agg(jsonb_build_object('verification',to_jsonb(v),'source',to_jsonb(vs)) ORDER BY v.id)
          FROM reviews v JOIN centerway.source_versions vs ON
            (vs.tenant_id,vs.client_id,vs.id,vs.revision)=(v.tenant_id,v.client_id,v.source_id,v.source_revision)
          WHERE (v.evidence_id,v.evidence_revision)=(e.id,e.revision)),'[]'::jsonb)) ORDER BY e.id)
        FROM evidence e JOIN centerway.source_versions es ON
          (es.tenant_id,es.client_id,es.id,es.revision)=(e.tenant_id,e.client_id,e.source_id,e.source_revision)
        WHERE (e.factor_id,e.factor_revision)=(f.id,f.revision)),'[]'::jsonb)) ORDER BY f.id) FROM factors f),'[]'::jsonb))
    INTO snapshot FROM root;
  IF snapshot IS NULL THEN RAISE EXCEPTION 'investigation_not_available_at_cutoff' USING ERRCODE='22023'; END IF;
  fingerprint:=encode(sha256(convert_to(snapshot::text,'UTF8')),'hex');
  SELECT * INTO existing FROM centerway.investigation_runs
    WHERE (tenant_id,client_id,investigation_id,as_of,input_hash)=(p_tenant,p_client,p_investigation,p_as_of,fingerprint);
  IF FOUND THEN RETURN to_jsonb(existing); END IF;
  SELECT * INTO previous FROM centerway.investigation_runs
    WHERE (tenant_id,client_id,investigation_id,as_of)=(p_tenant,p_client,p_investigation,p_as_of)
    ORDER BY revision DESC LIMIT 1;
  INSERT INTO centerway.investigation_runs VALUES
    (p_tenant,p_client,p_investigation,gen_random_uuid(),'f03-v1',p_as_of,coalesce(previous.revision,0)+1,previous.id,
     fingerprint,snapshot,centerway._evaluate_investigation(snapshot),session_user,clock_timestamp()) RETURNING * INTO created;
  RETURN to_jsonb(created);
END $$;

-- Internal handoff only: immutable report, all provenance, no action scheduling or execution.
CREATE FUNCTION centerway.read_investigation_context(p_tenant uuid,p_client uuid,p_investigation uuid,p_run uuid)
RETURNS jsonb LANGUAGE sql STABLE SECURITY INVOKER SET search_path=pg_catalog,centerway,pg_temp SET timezone='UTC' AS $$
  SELECT to_jsonb(r) FROM centerway.investigation_runs r
    WHERE (r.tenant_id,r.client_id,r.investigation_id,r.id)=(p_tenant,p_client,p_investigation,p_run)
$$;
REVOKE ALL ON FUNCTION centerway.open_investigation(uuid,uuid,uuid,uuid,integer,text) FROM PUBLIC;
REVOKE ALL ON FUNCTION centerway._validate_investigation_record() FROM PUBLIC;
REVOKE ALL ON FUNCTION centerway.append_investigation_record(uuid,uuid,uuid,text,uuid,integer,text,jsonb) FROM PUBLIC;
REVOKE ALL ON FUNCTION centerway._evaluate_investigation(jsonb) FROM PUBLIC;
REVOKE ALL ON FUNCTION centerway.run_investigation(uuid,uuid,uuid,timestamptz) FROM PUBLIC;
REVOKE ALL ON FUNCTION centerway.read_investigation_context(uuid,uuid,uuid,uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION centerway.open_investigation(uuid,uuid,uuid,uuid,integer,text) TO centerway_api;
GRANT EXECUTE ON FUNCTION centerway.append_investigation_record(uuid,uuid,uuid,text,uuid,integer,text,jsonb) TO centerway_api;
GRANT EXECUTE ON FUNCTION centerway.run_investigation(uuid,uuid,uuid,timestamptz) TO centerway_api;
GRANT EXECUTE ON FUNCTION centerway.read_investigation_context(uuid,uuid,uuid,uuid) TO centerway_api;
COMMIT;
