-- C01 Collector: CSV ingestion through a single validated, atomic RPC.

-- 1) Explicit value type per indicator (outcome indicators are always numeric).
CREATE TYPE public.indicator_value_type AS ENUM ('numeric', 'text');
ALTER TABLE public.profile_indicators ADD COLUMN value_type public.indicator_value_type NOT NULL DEFAULT 'numeric';
ALTER TABLE public.profile_indicators ADD CONSTRAINT pi_outcome_numeric CHECK (classification <> 'outcome' OR value_type = 'numeric');

-- 2) Observation hardening.
ALTER TABLE public.observations ADD CONSTRAINT obs_single_value CHECK (value_numeric IS NULL OR value_text IS NULL);
ALTER TABLE public.observations ADD CONSTRAINT obs_finite_numeric CHECK (value_numeric IS NULL OR value_numeric NOT IN ('NaN'::numeric, 'Infinity'::numeric, '-Infinity'::numeric));

-- 3) Batch metadata: pinned profile version, declared coverage, counts, errors, contract snapshot.
ALTER TABLE public.ingestion_batches
  ADD COLUMN profile_id uuid,
  ADD COLUMN profile_version integer,
  ADD COLUMN coverage_declared boolean NOT NULL DEFAULT false,
  ADD COLUMN coverage_timezone text NOT NULL DEFAULT 'UTC' CHECK (coverage_timezone = 'UTC'),
  ADD COLUMN file_name text CHECK (file_name IS NULL OR char_length(file_name) <= 255),
  ADD COLUMN row_count integer NOT NULL DEFAULT 0 CHECK (row_count >= 0),
  ADD COLUMN inserted_count integer NOT NULL DEFAULT 0 CHECK (inserted_count >= 0),
  ADD COLUMN duplicate_count integer NOT NULL DEFAULT 0 CHECK (duplicate_count >= 0),
  ADD COLUMN rejected_count integer NOT NULL DEFAULT 0 CHECK (rejected_count >= 0),
  ADD COLUMN errors jsonb NOT NULL DEFAULT '[]'::jsonb CHECK (jsonb_typeof(errors) = 'array'),
  ADD COLUMN contract_snapshot jsonb,
  ADD COLUMN committed_at timestamptz;
ALTER TABLE public.ingestion_batches ADD CONSTRAINT batches_profile_fkey
  FOREIGN KEY (tenant_id, profile_id) REFERENCES public.tenant_value_profiles(tenant_id, id);
ALTER TABLE public.ingestion_batches ADD CONSTRAINT batches_counts_consistent CHECK (
  (status <> 'completed' OR (rejected_count = 0 AND inserted_count + duplicate_count = row_count AND committed_at IS NOT NULL))
  AND (status <> 'failed' OR (inserted_count = 0 AND duplicate_count = 0)));
CREATE INDEX batches_tenant_created_idx ON public.ingestion_batches(tenant_id, created_at DESC);
CREATE INDEX observations_batch_idx ON public.observations(tenant_id, batch_id);

-- 4) No direct client writes: the RPC is the only path (validation cannot be bypassed).
REVOKE INSERT, UPDATE ON public.ingestion_batches FROM authenticated;
REVOKE INSERT ON public.observations FROM authenticated;
DROP POLICY IF EXISTS batches_insert ON public.ingestion_batches;
DROP POLICY IF EXISTS batches_update ON public.ingestion_batches;
DROP POLICY IF EXISTS observations_insert ON public.observations;

-- 5) Version copy must carry value_type.
CREATE OR REPLACE FUNCTION public.create_value_profile_version(_from_profile_id uuid)
RETURNS uuid LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $$
DECLARE src public.tenant_value_profiles; v_new uuid; v_version int;
BEGIN
  IF auth.uid() IS NULL THEN RAISE EXCEPTION 'authentication required' USING ERRCODE = '28000'; END IF;
  SELECT * INTO src FROM public.tenant_value_profiles WHERE id = _from_profile_id;
  IF NOT FOUND OR NOT public.has_tenant_role(src.tenant_id, ARRAY['admin','operator']::public.member_role[]) THEN
    RAISE EXCEPTION 'not authorized' USING ERRCODE = '42501';
  END IF;
  PERFORM 1 FROM public.tenants t WHERE t.id = src.tenant_id FOR UPDATE;
  SELECT * INTO src FROM public.tenant_value_profiles WHERE id = _from_profile_id FOR SHARE;
  SELECT coalesce(max(version), 0) + 1 INTO v_version FROM public.tenant_value_profiles WHERE tenant_id = src.tenant_id;
  INSERT INTO public.tenant_value_profiles(tenant_id, version, promise, expected_outcome, notes, created_by)
  VALUES (src.tenant_id, v_version, src.promise, src.expected_outcome, src.notes, auth.uid()) RETURNING id INTO v_new;
  INSERT INTO public.profile_indicators(tenant_id, profile_id, key, name, definition, classification, value_type, unit, direction,
    baseline_method, baseline_value, baseline_min_period_days, observation_window_days, comparison_window_days,
    min_coverage_pct, min_denominator, target_value,
    deterioration_kind, deterioration_operator, deterioration_value, deterioration_consecutive_windows,
    recovery_kind, recovery_operator, recovery_value, recovery_consecutive_windows)
  SELECT tenant_id, v_new, key, name, definition, classification, value_type, unit, direction,
    baseline_method, baseline_value, baseline_min_period_days, observation_window_days, comparison_window_days,
    min_coverage_pct, min_denominator, target_value,
    deterioration_kind, deterioration_operator, deterioration_value, deterioration_consecutive_windows,
    recovery_kind, recovery_operator, recovery_value, recovery_consecutive_windows
  FROM public.profile_indicators WHERE profile_id = src.id;
  RETURN v_new;
END $$;

-- 6) The ingestion RPC.
CREATE FUNCTION public.import_observations(
  _tenant_id uuid, _expected_profile_id uuid, _source text,
  _coverage_start timestamptz, _coverage_end timestamptz, _coverage_declared boolean,
  _file_name text, _rows jsonb)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $$
DECLARE
  v_uid uuid := auth.uid();
  v_prof public.tenant_value_profiles;
  v_ind public.profile_indicators;
  v_src text := btrim(coalesce(_source, ''));
  v_n int; i int; r jsonb; v_line int; v_errs text[];
  v_ref text; v_key text; v_unit text; v_num_raw text; v_txt text; v_obs_raw text; v_idem text; v_corr_raw text;
  v_subject uuid; v_num numeric; v_obs timestamptz; v_corr uuid; v_new uuid;
  v_valid jsonb := '[]'::jsonb; v_errors jsonb := '[]'::jsonb;
  v_rejected int := 0; v_ins int := 0; v_dup int := 0;
  v_batch uuid; v_snapshot jsonb; v_status public.batch_status;
BEGIN
  IF v_uid IS NULL THEN RAISE EXCEPTION 'authentication required' USING ERRCODE = '28000'; END IF;
  IF NOT public.has_tenant_role(_tenant_id, ARRAY['admin','operator']::public.member_role[]) THEN
    RAISE EXCEPTION 'not authorized' USING ERRCODE = '42501';
  END IF;
  IF _rows IS NULL OR jsonb_typeof(_rows) <> 'array' THEN RAISE EXCEPTION 'import: rows must be an array' USING ERRCODE = '22023'; END IF;
  v_n := jsonb_array_length(_rows);
  IF v_n = 0 THEN RAISE EXCEPTION 'import: empty batch' USING ERRCODE = '22023'; END IF;
  IF v_n > 1000 THEN RAISE EXCEPTION 'import: too many rows' USING ERRCODE = '22023'; END IF;
  IF octet_length(_rows::text) > 2000000 THEN RAISE EXCEPTION 'import: payload too large' USING ERRCODE = '22023'; END IF;
  IF char_length(v_src) NOT BETWEEN 1 AND 200 THEN RAISE EXCEPTION 'import: invalid source' USING ERRCODE = '22023'; END IF;
  IF _file_name IS NOT NULL AND char_length(_file_name) > 255 THEN RAISE EXCEPTION 'import: invalid file name' USING ERRCODE = '22023'; END IF;
  IF _coverage_start IS NULL OR _coverage_end IS NULL OR _coverage_end <= _coverage_start THEN
    RAISE EXCEPTION 'import: invalid coverage interval' USING ERRCODE = '22023'; END IF;
  IF _coverage_start > now() THEN RAISE EXCEPTION 'import: coverage starts in the future' USING ERRCODE = '22023'; END IF;
  IF NOT coalesce(_coverage_declared, false) THEN RAISE EXCEPTION 'import: coverage not declared' USING ERRCODE = '22023'; END IF;

  -- Serialize with approval/versioning and with other imports of this tenant (lock order: tenant -> profile).
  PERFORM 1 FROM public.tenants t WHERE t.id = _tenant_id FOR UPDATE;
  SELECT * INTO v_prof FROM public.tenant_value_profiles p WHERE p.tenant_id = _tenant_id AND p.status = 'approved' FOR SHARE;
  IF NOT FOUND THEN RAISE EXCEPTION 'import: no approved value profile' USING ERRCODE = '22023'; END IF;
  IF v_prof.id IS DISTINCT FROM _expected_profile_id THEN
    RAISE EXCEPTION 'import: approved value profile changed' USING ERRCODE = '22023'; END IF;

  v_snapshot := jsonb_build_object(
    'contract', 'centerway_csv_v1',
    'profile_id', v_prof.id, 'profile_version', v_prof.version,
    'coverage', jsonb_build_object('start', _coverage_start, 'end', _coverage_end, 'interval', '[start,end)', 'timezone', 'UTC',
                                   'semantics', 'declared by the importer; not proof of completeness'),
    'indicators', (SELECT coalesce(jsonb_agg(jsonb_build_object('key', x.key, 'unit', x.unit, 'classification', x.classification,
                   'value_type', x.value_type) ORDER BY x.key), '[]'::jsonb) FROM public.profile_indicators x WHERE x.profile_id = v_prof.id));

  -- Pass 1: validate every row (nothing written).
  FOR i IN 0 .. v_n - 1 LOOP
    r := _rows -> i; v_errs := '{}'; v_subject := NULL; v_ind := NULL; v_num := NULL; v_obs := NULL; v_corr := NULL;
    v_line := CASE WHEN jsonb_typeof(r) = 'object' AND (r ->> 'line') ~ '^[0-9]{1,7}$' THEN (r ->> 'line')::int ELSE i + 2 END;
    IF jsonb_typeof(r) <> 'object' THEN
      v_errs := array_append(v_errs, 'invalid_row');
    ELSE
      v_ref := btrim(coalesce(r ->> 'subject_external_ref', ''));
      v_key := btrim(coalesce(r ->> 'indicator_key', ''));
      v_unit := btrim(coalesce(r ->> 'unit', ''));
      v_num_raw := btrim(coalesce(r ->> 'value_numeric', ''));
      v_txt := coalesce(r ->> 'value_text', '');
      v_obs_raw := btrim(coalesce(r ->> 'observed_at', ''));
      v_idem := btrim(coalesce(r ->> 'idempotency_key', ''));
      v_corr_raw := btrim(coalesce(r ->> 'corrects_observation_id', ''));

      IF v_ref = '' THEN v_errs := array_append(v_errs, 'missing_subject');
      ELSE
        SELECT s.id INTO v_subject FROM public.subjects s WHERE s.tenant_id = _tenant_id AND s.external_ref = v_ref;
        IF v_subject IS NULL THEN v_errs := array_append(v_errs, 'unknown_subject'); END IF;
      END IF;

      IF v_key = '' THEN v_errs := array_append(v_errs, 'missing_indicator');
      ELSE
        SELECT * INTO v_ind FROM public.profile_indicators x WHERE x.profile_id = v_prof.id AND x.key = v_key;
        IF v_ind.id IS NULL THEN v_errs := array_append(v_errs, 'unknown_indicator');
        ELSIF v_unit <> v_ind.unit THEN v_errs := array_append(v_errs, 'unit_mismatch'); END IF;
      END IF;
      IF v_unit = '' THEN v_errs := array_append(v_errs, 'missing_unit'); END IF;

      IF v_num_raw <> '' AND btrim(v_txt) <> '' THEN v_errs := array_append(v_errs, 'both_values');
      ELSIF v_num_raw = '' AND btrim(v_txt) = '' THEN v_errs := array_append(v_errs, 'missing_value');
      ELSIF v_num_raw <> '' THEN
        IF v_num_raw !~ '^[+-]?([0-9]+(\.[0-9]*)?|\.[0-9]+)([eE][+-]?[0-9]{1,3})?$' THEN v_errs := array_append(v_errs, 'invalid_number');
        ELSE
          v_num := v_num_raw::numeric;
          IF v_ind.id IS NOT NULL AND v_ind.value_type <> 'numeric' THEN v_errs := array_append(v_errs, 'type_mismatch'); END IF;
        END IF;
      ELSE
        IF char_length(v_txt) > 2000 THEN v_errs := array_append(v_errs, 'text_too_long'); END IF;
        IF v_ind.id IS NOT NULL AND v_ind.value_type <> 'text' THEN v_errs := array_append(v_errs, 'type_mismatch'); END IF;
      END IF;

      IF v_obs_raw = '' THEN v_errs := array_append(v_errs, 'missing_timestamp');
      ELSIF v_obs_raw !~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}(:[0-9]{2}(\.[0-9]{1,6})?)?(Z|[+-][0-9]{2}:[0-9]{2})$' THEN
        v_errs := array_append(v_errs, 'invalid_timestamp');
      ELSE
        BEGIN v_obs := v_obs_raw::timestamptz;
        EXCEPTION WHEN OTHERS THEN v_errs := array_append(v_errs, 'invalid_timestamp'); END;
        IF v_obs IS NOT NULL THEN
          IF v_obs > now() THEN v_errs := array_append(v_errs, 'future_timestamp');
          ELSIF v_obs < _coverage_start OR v_obs >= _coverage_end THEN v_errs := array_append(v_errs, 'outside_coverage'); END IF;
        END IF;
      END IF;

      IF char_length(v_idem) NOT BETWEEN 1 AND 300 THEN v_errs := array_append(v_errs, 'invalid_idempotency_key'); END IF;

      IF v_corr_raw <> '' THEN
        IF v_corr_raw !~* '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$' THEN
          v_errs := array_append(v_errs, 'invalid_correction_ref');
        ELSE
          v_corr := v_corr_raw::uuid;
          IF v_subject IS NOT NULL AND v_ind.id IS NOT NULL AND NOT EXISTS (
            SELECT 1 FROM public.observations o WHERE o.tenant_id = _tenant_id AND o.id = v_corr
              AND o.subject_id = v_subject AND o.indicator_key = v_key AND o.unit = v_unit) THEN
            v_errs := array_append(v_errs, 'correction_target_not_found');
          END IF;
        END IF;
      END IF;
    END IF;

    IF cardinality(v_errs) > 0 THEN
      v_rejected := v_rejected + 1;
      IF jsonb_array_length(v_errors) < 500 THEN
        v_errors := v_errors || jsonb_build_array(jsonb_build_object('line', v_line, 'errors', to_jsonb(v_errs)));
      END IF;
    ELSE
      v_valid := v_valid || jsonb_build_array(jsonb_build_object('line', v_line, 'subject_id', v_subject, 'key', v_key,
        'num', v_num, 'txt', CASE WHEN v_num IS NULL THEN v_txt END, 'unit', v_unit, 'observed_at', v_obs,
        'idem', v_idem, 'corr', v_corr));
    END IF;
  END LOOP;

  -- Pass 2: atomic write (only if every row is valid). Any conflict rolls back the whole batch.
  IF v_rejected = 0 THEN
    BEGIN
      INSERT INTO public.ingestion_batches(tenant_id, source, status, coverage_start, coverage_end, coverage_declared, file_name,
        row_count, profile_id, profile_version, contract_snapshot, created_by)
      VALUES (_tenant_id, v_src, 'processing', _coverage_start, _coverage_end, true, _file_name,
        v_n, v_prof.id, v_prof.version, v_snapshot, v_uid) RETURNING id INTO v_batch;
      FOR r IN SELECT value FROM jsonb_array_elements(v_valid) LOOP
        BEGIN
          v_new := NULL;
          INSERT INTO public.observations(tenant_id, batch_id, subject_id, indicator_key, value_numeric, value_text, unit, source,
            observed_at, idempotency_key, payload, corrects_observation_id, created_by)
          VALUES (_tenant_id, v_batch, (r ->> 'subject_id')::uuid, r ->> 'key', (r ->> 'num')::numeric, r ->> 'txt', r ->> 'unit', v_src,
            (r ->> 'observed_at')::timestamptz, r ->> 'idem',
            jsonb_build_object('profile_version', v_prof.version, 'contract', 'centerway_csv_v1'),
            (r ->> 'corr')::uuid, v_uid)
          RETURNING id INTO v_new;
          IF v_new IS NULL THEN v_dup := v_dup + 1; ELSE v_ins := v_ins + 1; END IF;
        EXCEPTION
          WHEN unique_violation THEN
            v_rejected := v_rejected + 1;
            v_errors := v_errors || jsonb_build_array(jsonb_build_object('line', (r ->> 'line')::int, 'errors', jsonb_build_array('idempotency_conflict')));
          WHEN foreign_key_violation THEN
            v_rejected := v_rejected + 1;
            v_errors := v_errors || jsonb_build_array(jsonb_build_object('line', (r ->> 'line')::int, 'errors', jsonb_build_array('correction_target_not_found')));
        END;
      END LOOP;
      IF v_rejected > 0 THEN RAISE EXCEPTION 'cw_rollback' USING ERRCODE = 'P0001'; END IF;
      UPDATE public.ingestion_batches SET status = 'completed', inserted_count = v_ins, duplicate_count = v_dup, committed_at = now()
       WHERE id = v_batch;
      v_status := 'completed';
    EXCEPTION WHEN SQLSTATE 'P0001' THEN
      IF SQLERRM <> 'cw_rollback' THEN RAISE; END IF;
      v_batch := NULL; v_ins := 0; v_dup := 0;
    END;
  END IF;

  IF v_batch IS NULL THEN
    INSERT INTO public.ingestion_batches(tenant_id, source, status, coverage_start, coverage_end, coverage_declared, file_name,
      row_count, rejected_count, errors, profile_id, profile_version, contract_snapshot, created_by)
    VALUES (_tenant_id, v_src, 'failed', _coverage_start, _coverage_end, true, _file_name,
      v_n, v_rejected, v_errors, v_prof.id, v_prof.version, v_snapshot, v_uid) RETURNING id INTO v_batch;
    v_status := 'failed';
  END IF;

  RETURN jsonb_build_object('batch_id', v_batch, 'status', v_status, 'row_count', v_n,
    'inserted', v_ins, 'duplicates', v_dup, 'rejected', v_rejected, 'errors', v_errors,
    'profile_version', v_prof.version);
END $$;

REVOKE ALL ON FUNCTION public.import_observations(uuid, uuid, text, timestamptz, timestamptz, boolean, text, jsonb) FROM PUBLIC, anon;
GRANT EXECUTE ON FUNCTION public.import_observations(uuid, uuid, text, timestamptz, timestamptz, boolean, text, jsonb) TO authenticated, service_role;

COMMENT ON FUNCTION public.import_observations(uuid, uuid, text, timestamptz, timestamptz, boolean, text, jsonb) IS
  'C01 Collector. Only write path for ingestion_batches/observations. Atomic: one invalid or conflicting row => no observation written; a failed batch with per-line error codes is recorded.';