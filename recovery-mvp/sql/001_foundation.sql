-- F01: install once in a dedicated PostgreSQL 17 database as its administrator.
BEGIN;
CREATE ROLE centerway_api NOLOGIN NOSUPERUSER NOBYPASSRLS;
CREATE SCHEMA centerway;
REVOKE ALL ON SCHEMA centerway FROM PUBLIC;
GRANT USAGE ON SCHEMA centerway TO centerway_api;

CREATE DOMAIN centerway.label AS text CHECK (length(VALUE) BETWEEN 1 AND 2000 AND VALUE ~ '[^[:space:]]');
CREATE DOMAIN centerway.amount AS numeric CHECK (VALUE NOT IN ('NaN'::numeric, 'Infinity'::numeric, '-Infinity'::numeric));
CREATE TYPE centerway.direction AS ENUM ('higher', 'lower');
CREATE TYPE centerway.value_state AS ENUM (
  'valor_demonstrado', 'deterioracao_demonstrada', 'valor_insuficiente', 'resultado_inconclusivo'
);

-- Provisioned only by the database administrator, never by payload/session settings.
CREATE TABLE centerway.companies (tenant_id uuid PRIMARY KEY, name centerway.label NOT NULL);
CREATE TABLE centerway.clients (
  tenant_id uuid NOT NULL REFERENCES centerway.companies,
  client_id uuid NOT NULL, name centerway.label NOT NULL,
  PRIMARY KEY (tenant_id, client_id)
);
CREATE TABLE centerway.memberships (
  principal name NOT NULL, tenant_id uuid NOT NULL REFERENCES centerway.companies,
  PRIMARY KEY (principal, tenant_id)
);
CREATE FUNCTION centerway.allowed(p_tenant uuid) RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, centerway, pg_temp AS $$
  SELECT EXISTS (SELECT 1 FROM centerway.memberships WHERE principal = session_user AND tenant_id = p_tenant)
$$;

CREATE TABLE centerway.source_versions (
  tenant_id uuid NOT NULL, client_id uuid NOT NULL, id uuid NOT NULL,
  revision integer NOT NULL CHECK (revision > 0),
  name centerway.label NOT NULL, locator centerway.label NOT NULL,
  method centerway.label NOT NULL,
  actor name NOT NULL, recorded_at timestamptz NOT NULL, reason centerway.label NOT NULL,
  PRIMARY KEY (tenant_id, client_id, id, revision),
  FOREIGN KEY (tenant_id, client_id) REFERENCES centerway.clients
);
CREATE TABLE centerway.contract_versions (
  tenant_id uuid NOT NULL, client_id uuid NOT NULL, id uuid NOT NULL,
  revision integer NOT NULL CHECK (revision > 0),
  objective centerway.label NOT NULL, expected_outcome centerway.label NOT NULL,
  indicator centerway.label NOT NULL, unit centerway.label NOT NULL,
  measurement_method centerway.label NOT NULL, direction centerway.direction NOT NULL,
  baseline centerway.amount NOT NULL, minimum_acceptable centerway.amount NOT NULL,
  target centerway.amount NOT NULL,
  baseline_start timestamptz NOT NULL, baseline_end timestamptz NOT NULL,
  period_start timestamptz NOT NULL, period_end timestamptz NOT NULL,
  source_id uuid NOT NULL, source_revision integer NOT NULL,
  baseline_reference centerway.label NOT NULL,
  actor name NOT NULL, recorded_at timestamptz NOT NULL, reason centerway.label NOT NULL,
  PRIMARY KEY (tenant_id, client_id, id, revision),
  FOREIGN KEY (tenant_id, client_id) REFERENCES centerway.clients,
  FOREIGN KEY (tenant_id, client_id, source_id, source_revision)
    REFERENCES centerway.source_versions (tenant_id, client_id, id, revision),
  CHECK (isfinite(baseline_start) AND isfinite(baseline_end) AND isfinite(period_start) AND isfinite(period_end)),
  CHECK (baseline_start < baseline_end AND baseline_end <= period_start AND period_start < period_end),
  CHECK ((direction = 'higher' AND baseline <= minimum_acceptable AND minimum_acceptable <= target)
      OR (direction = 'lower' AND baseline >= minimum_acceptable AND minimum_acceptable >= target))
);
CREATE TABLE centerway.evidence_versions (
  tenant_id uuid NOT NULL, client_id uuid NOT NULL, id uuid NOT NULL,
  revision integer NOT NULL CHECK (revision > 0),
  contract_id uuid NOT NULL, contract_revision integer NOT NULL,
  source_id uuid NOT NULL, source_revision integer NOT NULL,
  evidence_type text NOT NULL CHECK (evidence_type IN ('outcome', 'usage')),
  quality text NOT NULL CHECK (quality IN ('verified', 'partial', 'disputed')),
  observed_value centerway.amount NOT NULL,
  unit centerway.label NOT NULL, measurement_method centerway.label NOT NULL,
  period_start timestamptz NOT NULL, period_end timestamptz NOT NULL,
  reference centerway.label NOT NULL, content_sha256 text NOT NULL CHECK (content_sha256 ~ '^[0-9a-f]{64}$'),
  actor name NOT NULL, recorded_at timestamptz NOT NULL, reason centerway.label NOT NULL,
  PRIMARY KEY (tenant_id, client_id, id, revision),
  FOREIGN KEY (tenant_id, client_id) REFERENCES centerway.clients,
  FOREIGN KEY (tenant_id, client_id, contract_id, contract_revision)
    REFERENCES centerway.contract_versions (tenant_id, client_id, id, revision),
  FOREIGN KEY (tenant_id, client_id, source_id, source_revision)
    REFERENCES centerway.source_versions (tenant_id, client_id, id, revision),
  CHECK (isfinite(period_start) AND isfinite(period_end) AND period_start < period_end)
);
CREATE TABLE centerway.assessment_versions (
  tenant_id uuid NOT NULL, client_id uuid NOT NULL, id uuid NOT NULL,
  revision integer NOT NULL CHECK (revision > 0),
  contract_id uuid NOT NULL, contract_revision integer NOT NULL,
  evidence_id uuid, evidence_revision integer,
  state centerway.value_state NOT NULL, rationale centerway.label NOT NULL,
  validation_policy text NOT NULL CHECK (validation_policy = 'f01-v1'),
  actor name NOT NULL, recorded_at timestamptz NOT NULL, reason centerway.label NOT NULL,
  PRIMARY KEY (tenant_id, client_id, id, revision),
  FOREIGN KEY (tenant_id, client_id) REFERENCES centerway.clients,
  FOREIGN KEY (tenant_id, client_id, contract_id, contract_revision)
    REFERENCES centerway.contract_versions (tenant_id, client_id, id, revision),
  FOREIGN KEY (tenant_id, client_id, evidence_id, evidence_revision)
    REFERENCES centerway.evidence_versions (tenant_id, client_id, id, revision),
  CHECK ((evidence_id IS NULL) = (evidence_revision IS NULL))
);
CREATE INDEX ON centerway.contract_versions (tenant_id, client_id, source_id, source_revision);
CREATE INDEX ON centerway.evidence_versions (tenant_id, client_id, contract_id, contract_revision);
CREATE INDEX ON centerway.evidence_versions (tenant_id, client_id, source_id, source_revision);
CREATE INDEX ON centerway.assessment_versions (tenant_id, client_id, contract_id, contract_revision);
CREATE INDEX ON centerway.assessment_versions (tenant_id, client_id, evidence_id, evidence_revision);

CREATE TABLE centerway.audit_log (
  sequence bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  tenant_id uuid NOT NULL, entity text NOT NULL, operation text NOT NULL,
  actor name NOT NULL, recorded_at timestamptz NOT NULL, snapshot jsonb NOT NULL
);
CREATE FUNCTION centerway.immutable() RETURNS trigger
LANGUAGE plpgsql SET search_path = pg_catalog AS $$
BEGIN RAISE EXCEPTION 'append_only' USING ERRCODE = '55000'; END $$;
CREATE FUNCTION centerway.audit_insert() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, centerway, pg_temp AS $$
BEGIN
  INSERT INTO centerway.audit_log(tenant_id, entity, operation, actor, recorded_at, snapshot)
  VALUES (NEW.tenant_id, TG_TABLE_NAME, TG_OP, session_user, clock_timestamp(), to_jsonb(NEW));
  RETURN NEW;
END $$;

-- Only validates explicitly submitted conclusions; no detection or investigation engine.
CREATE FUNCTION centerway.validate_record() RETURNS trigger
LANGUAGE plpgsql SET search_path = pg_catalog, centerway, pg_temp AS $$
DECLARE c centerway.contract_versions; e centerway.evidence_versions;
        expected centerway.value_state; previous jsonb;
BEGIN
  IF TG_TABLE_NAME = 'contract_versions' THEN
    IF NEW.baseline_end > clock_timestamp() THEN
      RAISE EXCEPTION 'future_baseline' USING ERRCODE = '23514';
    END IF;
  ELSIF TG_TABLE_NAME = 'evidence_versions' THEN
    SELECT * INTO STRICT c FROM centerway.contract_versions
      WHERE (tenant_id, client_id, id, revision) = (NEW.tenant_id, NEW.client_id, NEW.contract_id, NEW.contract_revision);
    IF NEW.unit <> c.unit OR NEW.measurement_method <> c.measurement_method
       OR NEW.source_id <> c.source_id OR NEW.source_revision <> c.source_revision
       OR NEW.period_start < c.period_start OR NEW.period_end > c.period_end
       OR NEW.period_end > clock_timestamp() THEN
      RAISE EXCEPTION 'incompatible_evidence' USING ERRCODE = '23514';
    END IF;
  ELSIF TG_TABLE_NAME = 'assessment_versions' THEN
    SELECT * INTO STRICT c FROM centerway.contract_versions
      WHERE (tenant_id, client_id, id, revision) = (NEW.tenant_id, NEW.client_id, NEW.contract_id, NEW.contract_revision);
    expected := 'resultado_inconclusivo';
    IF NEW.evidence_id IS NOT NULL THEN
      SELECT * INTO STRICT e FROM centerway.evidence_versions
        WHERE (tenant_id, client_id, id, revision) = (NEW.tenant_id, NEW.client_id, NEW.evidence_id, NEW.evidence_revision);
      IF (e.contract_id, e.contract_revision) <> (NEW.contract_id, NEW.contract_revision) THEN
        RAISE EXCEPTION 'incompatible_contract' USING ERRCODE = '23514';
      END IF;
      IF e.evidence_type = 'outcome' AND e.quality = 'verified'
         AND e.period_start = c.period_start AND e.period_end = c.period_end
         AND c.period_end <= clock_timestamp() THEN
        IF (c.direction = 'higher' AND e.observed_value < c.baseline)
           OR (c.direction = 'lower' AND e.observed_value > c.baseline) THEN
          expected := 'deterioracao_demonstrada';
        ELSIF (c.direction = 'higher' AND e.observed_value >= c.minimum_acceptable)
           OR (c.direction = 'lower' AND e.observed_value <= c.minimum_acceptable) THEN
          expected := 'valor_demonstrado';
        ELSE expected := 'valor_insuficiente'; END IF;
      END IF;
    END IF;
    IF NEW.state <> expected THEN
      RAISE EXCEPTION 'unsupported_conclusion: expected %', expected USING ERRCODE = '23514';
    END IF;
  END IF;
  -- Corrections retain their subject and measurement window; new meanings need new IDs.
  IF NEW.revision > 1 AND TG_TABLE_NAME IN ('evidence_versions', 'assessment_versions') THEN
    EXECUTE format('SELECT to_jsonb(t) FROM centerway.%I t WHERE tenant_id=$1 AND client_id=$2 AND id=$3 AND revision=$4', TG_TABLE_NAME)
      INTO previous USING NEW.tenant_id, NEW.client_id, NEW.id, NEW.revision - 1;
    IF previous->>'contract_id' <> to_jsonb(NEW)->>'contract_id'
       OR previous->>'contract_revision' <> to_jsonb(NEW)->>'contract_revision' THEN
      RAISE EXCEPTION 'correction_changes_contract' USING ERRCODE = '23514';
    END IF;
    IF TG_TABLE_NAME = 'evidence_versions' AND
       (previous->>'period_start' <> to_jsonb(NEW)->>'period_start'
        OR previous->>'period_end' <> to_jsonb(NEW)->>'period_end'
        OR previous->>'evidence_type' <> to_jsonb(NEW)->>'evidence_type') THEN
      RAISE EXCEPTION 'correction_changes_measurement' USING ERRCODE = '23514';
    END IF;
  END IF;
  RETURN NEW;
END $$;

DO $$
DECLARE t text;
BEGIN
  FOREACH t IN ARRAY ARRAY['source_versions','contract_versions','evidence_versions','assessment_versions'] LOOP
    EXECUTE format('ALTER TABLE centerway.%I ENABLE ROW LEVEL SECURITY', t);
    EXECUTE format('ALTER TABLE centerway.%I FORCE ROW LEVEL SECURITY', t);
    EXECUTE format('CREATE POLICY tenant_access ON centerway.%I USING (centerway.allowed(tenant_id)) WITH CHECK (centerway.allowed(tenant_id))', t);
    EXECUTE format('CREATE TRIGGER immutable BEFORE UPDATE OR DELETE OR TRUNCATE ON centerway.%I FOR EACH STATEMENT EXECUTE FUNCTION centerway.immutable()', t);
    EXECUTE format('CREATE TRIGGER audit AFTER INSERT ON centerway.%I FOR EACH ROW EXECUTE FUNCTION centerway.audit_insert()', t);
    EXECUTE format('CREATE TRIGGER validate BEFORE INSERT ON centerway.%I FOR EACH ROW EXECUTE FUNCTION centerway.validate_record()', t);
    EXECUTE format('GRANT SELECT ON centerway.%I TO centerway_api', t);
  END LOOP;
  FOREACH t IN ARRAY ARRAY['companies','clients','memberships'] LOOP
    EXECUTE format('CREATE TRIGGER audit AFTER INSERT ON centerway.%I FOR EACH ROW EXECUTE FUNCTION centerway.audit_insert()', t);
    EXECUTE format('CREATE TRIGGER immutable BEFORE UPDATE OR DELETE OR TRUNCATE ON centerway.%I FOR EACH STATEMENT EXECUTE FUNCTION centerway.immutable()', t);
  END LOOP;
END $$;
ALTER TABLE centerway.audit_log ENABLE ROW LEVEL SECURITY;
ALTER TABLE centerway.audit_log FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_access ON centerway.audit_log USING (centerway.allowed(tenant_id));
CREATE TRIGGER immutable BEFORE UPDATE OR DELETE OR TRUNCATE ON centerway.audit_log
  FOR EACH STATEMENT EXECUTE FUNCTION centerway.immutable();
GRANT SELECT ON centerway.audit_log TO centerway_api;

-- Internal write port. expected_revision=0 creates; otherwise append a correction/version.
CREATE FUNCTION centerway.append_version(
  p_tenant uuid, p_client uuid, p_kind text, p_id uuid,
  p_expected_revision integer, p_reason text, p_data jsonb
) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, centerway, pg_temp AS $$
DECLARE tbl text; latest integer; result jsonb; allowed_keys text[]; k text; typ text;
BEGIN
  IF p_tenant IS NULL OR NOT centerway.allowed(p_tenant) THEN
    RAISE EXCEPTION 'not_authorized' USING ERRCODE = '42501';
  END IF;
  IF p_kind IS NULL OR p_kind NOT IN ('source','contract','evidence','assessment')
     OR p_id IS NULL OR p_client IS NULL OR p_expected_revision IS NULL OR p_expected_revision < 0
     OR p_data IS NULL OR jsonb_typeof(p_data) <> 'object' THEN
    RAISE EXCEPTION 'invalid_request' USING ERRCODE = '22023';
  END IF;
  tbl := p_kind || '_versions';
  SELECT array_agg(attname::text) INTO allowed_keys FROM pg_attribute
    WHERE attrelid = ('centerway.' || tbl)::regclass AND attnum > 0 AND NOT attisdropped
      AND attname NOT IN ('tenant_id','client_id','id','revision','actor','recorded_at','reason','validation_policy');
  FOR k IN SELECT jsonb_object_keys(p_data) LOOP
    IF NOT k = ANY(allowed_keys) THEN
      RAISE EXCEPTION 'unknown_or_reserved_field: %', k USING ERRCODE = '22023';
    END IF;
    SELECT format_type(atttypid, atttypmod) INTO typ FROM pg_attribute
      WHERE attrelid = ('centerway.' || tbl)::regclass AND attname = k;
    IF p_data->k <> 'null'::jsonb THEN
      IF typ IN ('integer','amount','centerway.amount') AND jsonb_typeof(p_data->k) <> 'number' THEN
        RAISE EXCEPTION 'expected_number: %', k USING ERRCODE = '22023';
      ELSIF typ NOT IN ('integer','amount','centerway.amount') AND jsonb_typeof(p_data->k) <> 'string' THEN
        RAISE EXCEPTION 'expected_string: %', k USING ERRCODE = '22023';
      END IF;
      IF typ = 'timestamp with time zone' AND (p_data->>k) !~ '(Z|[+-][0-9]{2}:[0-9]{2})$' THEN
        RAISE EXCEPTION 'timezone_required: %', k USING ERRCODE = '22023';
      END IF;
    END IF;
  END LOOP;
  PERFORM pg_advisory_xact_lock(hashtextextended(p_tenant::text || p_client::text || tbl || p_id::text, 0));
  EXECUTE format('SELECT coalesce(max(revision),0) FROM centerway.%I WHERE tenant_id=$1 AND client_id=$2 AND id=$3', tbl)
    INTO latest USING p_tenant, p_client, p_id;
  IF latest <> p_expected_revision THEN
    RAISE EXCEPTION 'revision_conflict' USING ERRCODE = '40001';
  END IF;
  p_data := p_data || jsonb_build_object('tenant_id',p_tenant,'client_id',p_client,'id',p_id,
    'revision',latest+1,'actor',session_user,'recorded_at',clock_timestamp(),'reason',p_reason);
  IF p_kind = 'assessment' THEN
    p_data := p_data || jsonb_build_object('validation_policy','f01-v1');
  END IF;
  EXECUTE format('INSERT INTO centerway.%I SELECT * FROM jsonb_populate_record(NULL::centerway.%I,$1) RETURNING to_jsonb(%I.*)', tbl,tbl,tbl)
    INTO result USING p_data;
  RETURN result;
END $$;
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA centerway FROM PUBLIC;
GRANT EXECUTE ON FUNCTION centerway.allowed(uuid) TO centerway_api;
GRANT EXECUTE ON FUNCTION centerway.append_version(uuid,uuid,text,uuid,integer,text,jsonb) TO centerway_api;
COMMIT;
