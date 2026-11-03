-- M01: raw daily outcome-event counts, not customer value assertions.
-- Additive to F01-F06. No customer records, contracts or interventions created.
CREATE TABLE centerway.outcome_imports (
    tenant_id uuid NOT NULL REFERENCES centerway.companies(tenant_id),
    import_id uuid NOT NULL,
    provider text NOT NULL DEFAULT 'posthog' CHECK (provider = 'posthog'),
    project_id integer NOT NULL CHECK (project_id > 0),
    event_name text NOT NULL CHECK (event_name ~ '^[A-Za-z_][A-Za-z0-9_.:-]{0,79}$'),
    group_index smallint NOT NULL CHECK (group_index BETWEEN 0 AND 4),
    period_start timestamptz NOT NULL,
    period_end timestamptz NOT NULL,
    counts jsonb NOT NULL CHECK (jsonb_typeof(counts) = 'array'),
    data_sha256 text NOT NULL CHECK (data_sha256 ~ '^[0-9a-f]{64}$'),
    actor name NOT NULL DEFAULT session_user,
    recorded_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY (tenant_id, import_id),
    CONSTRAINT intake_utc_day CHECK (
        period_start = date_trunc('day', period_start, 'UTC')
        AND period_end = period_start + interval '1 day'
    )
);
CREATE INDEX outcome_imports_history ON centerway.outcome_imports
    (tenant_id, project_id, event_name, group_index, period_start, recorded_at DESC);
ALTER TABLE centerway.outcome_imports ENABLE ROW LEVEL SECURITY;
CREATE POLICY outcome_imports_tenant ON centerway.outcome_imports
    USING (centerway.allowed(tenant_id)) WITH CHECK (centerway.allowed(tenant_id));
GRANT SELECT ON centerway.outcome_imports TO centerway_api;

CREATE FUNCTION centerway.append_posthog_outcome_import(
    p_tenant uuid,
    p_import uuid,
    p_project integer,
    p_event text,
    p_group_index integer,
    p_start timestamptz,
    p_end timestamptz,
    p_counts jsonb
) RETURNS uuid
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, centerway
AS $$
DECLARE
    item jsonb;
    customer_key text;
    count_text text;
    observed_customers text[] := ARRAY[]::text[];
    previous centerway.outcome_imports%ROWTYPE;
    current_hash text;
BEGIN
    IF NOT centerway.allowed(p_tenant) THEN
        RAISE EXCEPTION 'intake_not_authorized' USING ERRCODE = '42501';
    END IF;
    IF p_import IS NULL OR p_project IS NULL OR p_project <= 0
        OR p_event !~ '^[A-Za-z_][A-Za-z0-9_.:-]{0,79}$'
        OR p_group_index NOT BETWEEN 0 AND 4
        OR p_start IS NULL OR p_end IS NULL
        OR p_start <> date_trunc('day', p_start, 'UTC')
        OR p_end <> p_start + interval '1 day'
        OR p_end > clock_timestamp()
        OR p_counts IS NULL OR jsonb_typeof(p_counts) <> 'array'
        OR jsonb_array_length(p_counts) > 200
    THEN
        RAISE EXCEPTION 'invalid_intake_batch' USING ERRCODE = '22023';
    END IF;

    FOR item IN SELECT value FROM jsonb_array_elements(p_counts)
    LOOP
        IF jsonb_typeof(item) <> 'object'
            OR NOT (item ? 'customer' AND item ? 'count')
            OR (SELECT count(*) FROM jsonb_object_keys(item)) <> 2
            OR jsonb_typeof(item->'customer') <> 'string'
            OR jsonb_typeof(item->'count') <> 'number'
        THEN
            RAISE EXCEPTION 'invalid_intake_row' USING ERRCODE = '22023';
        END IF;
        customer_key := item->>'customer';
        count_text := item->>'count';
        IF length(customer_key) < 1 OR length(customer_key) > 256
            OR customer_key <> btrim(customer_key)
            OR count_text !~ '^(0|[1-9][0-9]{0,9})$'
            OR count_text::numeric > 2147483647
            OR customer_key = ANY(observed_customers)
        THEN
            RAISE EXCEPTION 'invalid_intake_row' USING ERRCODE = '22023';
        END IF;
        observed_customers := array_append(observed_customers, customer_key);
    END LOOP;
    current_hash := encode(sha256(convert_to(p_counts::text, 'UTF8')), 'hex');

    INSERT INTO centerway.outcome_imports (
      tenant_id, import_id, project_id, event_name, group_index,
      period_start, period_end, counts, data_sha256
    ) VALUES (
      p_tenant, p_import, p_project, p_event, p_group_index,
      p_start, p_end, p_counts, current_hash
    ) ON CONFLICT (tenant_id, import_id) DO NOTHING;

    SELECT * INTO previous
    FROM centerway.outcome_imports
    WHERE tenant_id = p_tenant AND import_id = p_import;
    IF NOT FOUND OR previous.project_id <> p_project
        OR previous.event_name <> p_event
        OR previous.group_index <> p_group_index
        OR previous.period_start <> p_start
        OR previous.period_end <> p_end
        OR previous.counts <> p_counts
        OR previous.data_sha256 <> current_hash
    THEN
        RAISE EXCEPTION 'intake_replay_conflict' USING ERRCODE = '23505';
    END IF;
    RETURN p_import;
END;
$$;
REVOKE ALL ON FUNCTION centerway.append_posthog_outcome_import(
    uuid,uuid,integer,text,integer,timestamptz,timestamptz,jsonb
) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION centerway.append_posthog_outcome_import(
    uuid,uuid,integer,text,integer,timestamptz,timestamptz,jsonb
) TO centerway_api;
