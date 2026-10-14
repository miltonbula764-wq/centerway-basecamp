-- C02 Deterioration Detector (deterministic, server-side) + C01 correction compatibility hardening.

-- 1) Explicit, typed analysis contract on indicators (NULL = not configured; never defaulted).
CREATE TYPE public.c02_aggregation AS ENUM ('mean', 'sum', 'last');
CREATE TYPE public.c02_denominator_mode AS ENUM ('observation_count', 'paired_indicator');
CREATE TYPE public.c02_status AS ENUM ('deterioration_candidate', 'no_deterioration', 'persistent_condition',
  'insufficient_data', 'insufficient_config', 'unsupported', 'not_evaluated');

ALTER TABLE public.profile_indicators
  ADD COLUMN aggregation public.c02_aggregation,
  ADD COLUMN expected_cadence_days integer CHECK (expected_cadence_days IS NULL OR expected_cadence_days BETWEEN 1 AND 366),
  ADD COLUMN denominator_mode public.c02_denominator_mode,
  ADD COLUMN denominator_indicator_key text CHECK (denominator_indicator_key IS NULL OR denominator_indicator_key ~ '^[a-z][a-z0-9_]{0,63}$');
ALTER TABLE public.profile_indicators ADD CONSTRAINT pi_denominator_pairing CHECK (
  (denominator_mode IS DISTINCT FROM 'paired_indicator' OR denominator_indicator_key IS NOT NULL)
  AND (denominator_indicator_key IS NULL OR (denominator_mode = 'paired_indicator' AND denominator_indicator_key <> key)));

-- 2) Measurement-semantics fingerprint: observations from another profile version are comparable only if equal.
CREATE FUNCTION public._c02_fingerprint(i public.profile_indicators) RETURNS text
LANGUAGE sql IMMUTABLE SET search_path = public AS $$
  SELECT md5(jsonb_build_object('unit', i.unit, 'value_type', i.value_type, 'classification', i.classification,
    'direction', i.direction, 'definition', coalesce(i.definition, ''))::text)
$$;

-- 3) C01 hardening: a correction must target a compatible observation (same subject/key/unit/source/observed_at,
--    same measurement semantics) that is not already corrected (no forks).
CREATE FUNCTION public._cw_correction_issues(_tenant uuid, _subject uuid, _ind uuid, _unit text, _src text,
  _obs timestamptz, _corr uuid, _dup_in_batch boolean) RETURNS text[]
LANGUAGE plpgsql STABLE SET search_path = public AS $$
DECLARE t record; cur public.profile_indicators; old public.profile_indicators;
BEGIN
  SELECT * INTO cur FROM public.profile_indicators WHERE id = _ind;
  SELECT o.id, o.observed_at, o.source, b.profile_id INTO t
    FROM public.observations o JOIN public.ingestion_batches b ON b.tenant_id = o.tenant_id AND b.id = o.batch_id
   WHERE o.tenant_id = _tenant AND o.id = _corr AND o.subject_id = _subject AND o.indicator_key = cur.key AND o.unit = _unit;
  IF NOT FOUND THEN RETURN ARRAY['correction_target_not_found']; END IF;
  SELECT * INTO old FROM public.profile_indicators WHERE profile_id = t.profile_id AND key = cur.key;
  IF old.id IS NULL OR public._c02_fingerprint(old) <> public._c02_fingerprint(cur) THEN
    RETURN ARRAY['correction_version_mismatch'];
  END IF;
  IF _obs IS DISTINCT FROM t.observed_at OR _src IS DISTINCT FROM t.source THEN RETURN ARRAY['correction_incompatible']; END IF;
  IF _dup_in_batch OR EXISTS (SELECT 1 FROM public.observations x WHERE x.tenant_id = _tenant AND x.corrects_observation_id = _corr) THEN
    RETURN ARRAY['correction_already_corrected'];
  END IF;
  RETURN '{}'::text[];
END $$;
REVOKE ALL ON FUNCTION public._cw_correction_issues(uuid, uuid, uuid, text, text, timestamptz, uuid, boolean) FROM PUBLIC, anon, authenticated;

CREATE UNIQUE INDEX observations_single_correction_idx ON public.observations(tenant_id, corrects_observation_id)
  WHERE corrects_observation_id IS NOT NULL;

DO $mig$
DECLARE src text; old_block text; new_block text;
BEGIN
  SELECT pg_get_functiondef('public.import_observations(uuid, uuid, text, timestamptz, timestamptz, boolean, text, jsonb)'::regprocedure) INTO src;
  old_block := $o$          IF v_subject IS NOT NULL AND v_ind.id IS NOT NULL AND NOT EXISTS (
            SELECT 1 FROM public.observations o WHERE o.tenant_id = _tenant_id AND o.id = v_corr
              AND o.subject_id = v_subject AND o.indicator_key = v_key AND o.unit = v_unit) THEN
            v_errs := array_append(v_errs, 'correction_target_not_found');
          END IF;$o$;
  new_block := $n$          IF v_subject IS NOT NULL AND v_ind.id IS NOT NULL THEN
            v_errs := v_errs || public._cw_correction_issues(_tenant_id, v_subject, v_ind.id, v_unit, v_src, v_obs, v_corr,
              v_valid @> jsonb_build_array(jsonb_build_object('corr', v_corr)));
          END IF;$n$;
  IF position(old_block IN src) = 0 THEN RAISE EXCEPTION 'import_observations correction block not found; aborting'; END IF;
  EXECUTE replace(src, old_block, new_block);
END $mig$;

-- 4) Version copy carries the new analysis fields.
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
    recovery_kind, recovery_operator, recovery_value, recovery_consecutive_windows,
    aggregation, expected_cadence_days, denominator_mode, denominator_indicator_key)
  SELECT tenant_id, v_new, key, name, definition, classification, value_type, unit, direction,
    baseline_method, baseline_value, baseline_min_period_days, observation_window_days, comparison_window_days,
    min_coverage_pct, min_denominator, target_value,
    deterioration_kind, deterioration_operator, deterioration_value, deterioration_consecutive_windows,
    recovery_kind, recovery_operator, recovery_value, recovery_consecutive_windows,
    aggregation, expected_cadence_days, denominator_mode, denominator_indicator_key
  FROM public.profile_indicators WHERE profile_id = src.id;
  RETURN v_new;
END $$;

-- 5) Approval rejects self-contradictory outcome rules (no thresholds are invented).
CREATE OR REPLACE FUNCTION public.value_profile_approval_issues(_profile_id uuid)
RETURNS text[] LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = public AS $$
DECLARE p public.tenant_value_profiles; i public.profile_indicators; issues text[] := '{}';
BEGIN
  SELECT * INTO p FROM public.tenant_value_profiles WHERE id = _profile_id;
  IF NOT FOUND OR NOT public.is_tenant_member(p.tenant_id) THEN
    RAISE EXCEPTION 'not authorized' USING ERRCODE = '42501';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM public.profile_indicators x WHERE x.profile_id = p.id AND x.classification = 'outcome') THEN
    issues := array_append(issues, 'profile needs at least one outcome indicator'::text);
  END IF;
  FOR i IN SELECT * FROM public.profile_indicators x WHERE x.profile_id = p.id AND x.classification = 'outcome' ORDER BY x.key LOOP
    IF i.baseline_method IS NULL THEN issues := array_append(issues, i.key || ': baseline_method missing'); END IF;
    IF i.baseline_min_period_days IS NULL THEN issues := array_append(issues, i.key || ': baseline_min_period_days missing'); END IF;
    IF i.observation_window_days IS NULL THEN issues := array_append(issues, i.key || ': observation_window_days missing'); END IF;
    IF i.comparison_window_days IS NULL THEN issues := array_append(issues, i.key || ': comparison_window_days missing'); END IF;
    IF i.min_coverage_pct IS NULL THEN issues := array_append(issues, i.key || ': min_coverage_pct missing'); END IF;
    IF i.min_denominator IS NULL THEN issues := array_append(issues, i.key || ': min_denominator missing'); END IF;
    IF i.deterioration_kind IS NULL OR i.deterioration_consecutive_windows IS NULL THEN issues := array_append(issues, i.key || ': deterioration rule incomplete'); END IF;
    IF i.recovery_kind IS NULL OR i.recovery_consecutive_windows IS NULL THEN issues := array_append(issues, i.key || ': recovery rule incomplete'); END IF;
    IF (i.direction = 'higher_is_better' AND i.deterioration_operator IN ('gt','gte'))
       OR (i.direction = 'lower_is_better' AND i.deterioration_operator IN ('lt','lte')) THEN
      issues := array_append(issues, i.key || ': deterioration operator contradicts direction');
    END IF;
  END LOOP;
  FOR i IN SELECT * FROM public.profile_indicators x WHERE x.profile_id = p.id AND x.denominator_mode = 'paired_indicator' ORDER BY x.key LOOP
    IF NOT EXISTS (SELECT 1 FROM public.profile_indicators d WHERE d.profile_id = p.id AND d.key = i.denominator_indicator_key AND d.value_type = 'numeric') THEN
      issues := array_append(issues, i.key || ': denominator indicator not found');
    END IF;
  END LOOP;
  RETURN issues;
END $$;

-- 6) Persistence: immutable runs and per-indicator results.
CREATE TABLE public.c02_runs (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES public.tenants(id),
  subject_id uuid NOT NULL,
  profile_id uuid NOT NULL,
  profile_version integer NOT NULL,
  algorithm_version text NOT NULL,
  as_of timestamptz NOT NULL,
  data_cutoff timestamptz NOT NULL,
  input_hash text NOT NULL,
  observation_count integer NOT NULL,
  revision_of uuid,
  summary jsonb NOT NULL,
  created_by uuid,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, id),
  UNIQUE (tenant_id, subject_id, input_hash),
  FOREIGN KEY (tenant_id, subject_id) REFERENCES public.subjects(tenant_id, id),
  FOREIGN KEY (tenant_id, profile_id) REFERENCES public.tenant_value_profiles(tenant_id, id),
  FOREIGN KEY (tenant_id, revision_of) REFERENCES public.c02_runs(tenant_id, id)
);
CREATE INDEX c02_runs_subject_idx ON public.c02_runs(tenant_id, subject_id, created_at DESC);

CREATE TABLE public.c02_results (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES public.tenants(id),
  run_id uuid NOT NULL,
  subject_id uuid NOT NULL,
  indicator_key text NOT NULL,
  classification public.indicator_class NOT NULL,
  status public.c02_status NOT NULL,
  below_target boolean,
  baseline_value numeric,
  reasons text[] NOT NULL DEFAULT '{}',
  observation_ids uuid[] NOT NULL DEFAULT '{}',
  details jsonb NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (run_id, indicator_key),
  FOREIGN KEY (tenant_id, run_id) REFERENCES public.c02_runs(tenant_id, id),
  FOREIGN KEY (tenant_id, subject_id) REFERENCES public.subjects(tenant_id, id)
);
CREATE INDEX c02_results_tenant_status_idx ON public.c02_results(tenant_id, status, classification);

GRANT SELECT ON public.c02_runs, public.c02_results TO authenticated;
GRANT ALL ON public.c02_runs, public.c02_results TO service_role;
ALTER TABLE public.c02_runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.c02_results ENABLE ROW LEVEL SECURITY;
CREATE POLICY c02_runs_select ON public.c02_runs FOR SELECT TO authenticated USING (public.is_tenant_member(tenant_id));
CREATE POLICY c02_results_select ON public.c02_results FOR SELECT TO authenticated USING (public.is_tenant_member(tenant_id));

CREATE FUNCTION public._c02_immutable() RETURNS trigger LANGUAGE plpgsql SET search_path = public AS $$
BEGIN
  IF TG_OP = 'DELETE' AND NOT EXISTS (SELECT 1 FROM public.tenants t WHERE t.id = OLD.tenant_id) THEN RETURN OLD; END IF;
  RAISE EXCEPTION '% is immutable', TG_TABLE_NAME USING ERRCODE = '42501';
END $$;
CREATE TRIGGER c02_runs_immutable BEFORE UPDATE OR DELETE ON public.c02_runs FOR EACH ROW EXECUTE FUNCTION public._c02_immutable();
CREATE TRIGGER c02_results_immutable BEFORE UPDATE OR DELETE ON public.c02_results FOR EACH ROW EXECUTE FUNCTION public._c02_immutable();
CREATE TRIGGER c02_runs_audit AFTER INSERT ON public.c02_runs FOR EACH ROW EXECUTE FUNCTION public._cw_audit();

-- 7) Helpers.
CREATE FUNCTION public._c02_cmp(_a numeric, _op public.rule_operator, _b numeric) RETURNS boolean
LANGUAGE sql IMMUTABLE AS $$
  SELECT CASE _op WHEN 'lt' THEN _a < _b WHEN 'lte' THEN _a <= _b WHEN 'gt' THEN _a > _b WHEN 'gte' THEN _a >= _b END
$$;

-- Effective observations of one series: correction chains resolved to their leaf; forks, version/unit mismatches flagged.
CREATE FUNCTION public._c02_effective(_tenant uuid, _subject uuid, _key text, _unit text, _compat uuid[], _cutoff timestamptz)
RETURNS TABLE(obs_id uuid, observed_at timestamptz, value numeric, source text, ingested_at timestamptz, issue text)
LANGUAGE sql STABLE SET search_path = public AS $$
  WITH RECURSIVE base AS (
    SELECT o.id, o.observed_at, o.value_numeric, o.source, o.ingested_at, o.unit, o.corrects_observation_id AS corr, b.profile_id
      FROM public.observations o JOIN public.ingestion_batches b ON b.tenant_id = o.tenant_id AND b.id = o.batch_id
     WHERE o.tenant_id = _tenant AND o.subject_id = _subject AND o.indicator_key = _key AND o.ingested_at <= _cutoff
  ), kids AS (
    SELECT corr, count(*) AS n FROM base WHERE corr IS NOT NULL GROUP BY corr
  ), leaves AS (
    SELECT x.* FROM base x WHERE NOT EXISTS (SELECT 1 FROM base y WHERE y.corr = x.id)
  ), chain AS (
    SELECT l.id AS leaf, l.corr AS anc, 0 AS depth FROM leaves l WHERE l.corr IS NOT NULL
    UNION ALL
    SELECT c.leaf, b.corr, c.depth + 1 FROM chain c JOIN base b ON b.id = c.anc WHERE b.corr IS NOT NULL AND c.depth < 1000
  )
  SELECT l.id, l.observed_at, l.value_numeric, l.source, l.ingested_at,
    CASE
      WHEN EXISTS (SELECT 1 FROM chain c JOIN kids k ON k.corr = c.anc WHERE c.leaf = l.id AND k.n > 1) THEN 'ambiguous_correction'
      WHEN NOT (l.profile_id = ANY (_compat)) THEN 'version_mismatch'
      WHEN l.unit <> _unit THEN 'unit_mismatch'
      WHEN l.value_numeric IS NULL THEN 'non_numeric'
    END
  FROM leaves l
$$;

-- One closed UTC window [s,e): coverage by cadence slots, denominator, aggregation, IDs used.
CREATE FUNCTION public._c02_window(_tenant uuid, _subject uuid, _key text, _unit text, _compat uuid[],
  _agg public.c02_aggregation, _cad integer, _den_mode public.c02_denominator_mode, _den_key text, _den_unit text,
  _den_compat uuid[], _min_cov numeric, _min_den integer, _cutoff timestamptz, _s timestamptz, _e timestamptz)
RETURNS jsonb LANGUAGE plpgsql STABLE SET search_path = public SET timezone = 'UTC' AS $$
DECLARE
  v_n int; v_sources int; v_slots int; v_expected int; v_cov numeric; v_val numeric; v_den numeric;
  v_ids uuid[]; v_excl jsonb; v_late int; v_ties int; v_dn int; v_dsrc int; v_dneg int; reasons text[] := '{}';
BEGIN
  v_expected := floor(extract(epoch FROM (_e - _s)) / (_cad * 86400.0))::int;
  SELECT count(*), count(DISTINCT e.source),
         count(DISTINCT floor(extract(epoch FROM (e.observed_at - _s)) / (_cad * 86400.0))),
         coalesce(array_agg(e.obs_id ORDER BY e.observed_at, e.obs_id), '{}'),
         count(*) FILTER (WHERE e.ingested_at >= _e),
         CASE _agg WHEN 'mean' THEN avg(e.value) WHEN 'sum' THEN sum(e.value) END
    INTO v_n, v_sources, v_slots, v_ids, v_late, v_val
    FROM public._c02_effective(_tenant, _subject, _key, _unit, _compat, _cutoff) e
   WHERE e.issue IS NULL AND e.observed_at >= _s AND e.observed_at < _e;
  SELECT coalesce(jsonb_object_agg(z.issue, z.n), '{}'::jsonb) INTO v_excl FROM (
    SELECT e.issue, count(*) AS n FROM public._c02_effective(_tenant, _subject, _key, _unit, _compat, _cutoff) e
     WHERE e.issue IS NOT NULL AND e.observed_at >= _s AND e.observed_at < _e GROUP BY e.issue) z;

  IF _agg = 'last' AND v_n > 0 THEN
    SELECT count(*) INTO v_ties FROM public._c02_effective(_tenant, _subject, _key, _unit, _compat, _cutoff) e
     WHERE e.issue IS NULL AND e.observed_at = (SELECT max(f.observed_at) FROM public._c02_effective(_tenant, _subject, _key, _unit, _compat, _cutoff) f
                                                WHERE f.issue IS NULL AND f.observed_at >= _s AND f.observed_at < _e);
    IF v_ties > 1 THEN reasons := array_append(reasons, 'ambiguous_last_value');
    ELSE
      SELECT e.value INTO v_val FROM public._c02_effective(_tenant, _subject, _key, _unit, _compat, _cutoff) e
       WHERE e.issue IS NULL AND e.observed_at >= _s AND e.observed_at < _e ORDER BY e.observed_at DESC LIMIT 1;
    END IF;
  END IF;

  IF v_excl ? 'ambiguous_correction' THEN reasons := array_append(reasons, 'ambiguous_correction'); END IF;
  IF v_n = 0 THEN reasons := array_append(reasons, 'no_observations'); END IF;
  IF v_sources > 1 THEN reasons := array_append(reasons, 'multiple_sources'); END IF;
  v_cov := CASE WHEN v_expected > 0 THEN round(100.0 * v_slots / v_expected, 2) END;
  IF v_cov IS NULL OR v_cov < _min_cov THEN reasons := array_append(reasons, 'coverage_below_minimum'); END IF;

  IF _den_mode = 'observation_count' THEN
    v_den := v_n;
  ELSE
    SELECT count(*), count(DISTINCT e.source), count(*) FILTER (WHERE e.value < 0), sum(e.value)
      INTO v_dn, v_dsrc, v_dneg, v_den
      FROM public._c02_effective(_tenant, _subject, _den_key, _den_unit, _den_compat, _cutoff) e
     WHERE e.issue IS NULL AND e.observed_at >= _s AND e.observed_at < _e;
    IF v_dn = 0 THEN reasons := array_append(reasons, 'denominator_missing');
    ELSIF v_dsrc > 1 THEN reasons := array_append(reasons, 'denominator_multiple_sources');
    ELSIF v_dneg > 0 THEN reasons := array_append(reasons, 'invalid_denominator'); END IF;
  END IF;
  IF v_den IS NULL OR v_den < _min_den THEN reasons := array_append(reasons, 'denominator_below_minimum'); END IF;

  RETURN jsonb_build_object('start', _s, 'end', _e, 'interval', '[start,end)', 'n', v_n,
    'expected_slots', v_expected, 'covered_slots', v_slots, 'coverage_pct', v_cov, 'sources', v_sources,
    'value', v_val, 'denominator', v_den, 'observation_ids', to_jsonb(v_ids), 'excluded', v_excl,
    'late_observations', v_late, 'sufficient', cardinality(reasons) = 0, 'reasons', to_jsonb(reasons));
END $$;
REVOKE ALL ON FUNCTION public._c02_effective(uuid, uuid, text, text, uuid[], timestamptz) FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public._c02_window(uuid, uuid, text, text, uuid[], public.c02_aggregation, integer, public.c02_denominator_mode, text, text, uuid[], numeric, integer, timestamptz, timestamptz, timestamptz) FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public._c02_fingerprint(public.profile_indicators) FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public._c02_immutable() FROM PUBLIC, anon, authenticated;

-- 8) The C02 RPC. Inputs are only ids; every result and evidence ref is computed here.
CREATE FUNCTION public.run_deterioration_analysis(_tenant_id uuid, _subject_id uuid, _expected_profile_id uuid, _as_of timestamptz DEFAULT NULL)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path = public SET timezone = 'UTC' AS $$
DECLARE
  v_uid uuid := auth.uid(); v_prof public.tenant_value_profiles; v_ind public.profile_indicators; v_den public.profile_indicators;
  v_cutoff timestamptz := now(); v_as_of timestamptz; v_hash text; v_existing uuid; v_prev uuid; v_run uuid := gen_random_uuid();
  v_obs_count int; v_results jsonb := '[]'::jsonb; v_status public.c02_status;
  cfg text[]; rsn text[]; v_compat uuid[]; v_den_compat uuid[];
  W interval; C interval; N int; k int; cur jsonb; v_windows jsonb; v_wout jsonb; v_ref jsonb; v_base jsonb; v_b numeric;
  v_all boolean; v_refmeet boolean; v_m numeric; v_meet boolean; v_below boolean; v_ids uuid[]; v_w jsonb;
  s_out int := 0; s_use int := 0; s_ins int := 0; s_pers int := 0;
BEGIN
  IF v_uid IS NULL THEN RAISE EXCEPTION 'authentication required' USING ERRCODE = '28000'; END IF;
  IF NOT public.has_tenant_role(_tenant_id, ARRAY['admin','operator']::public.member_role[]) THEN
    RAISE EXCEPTION 'not authorized' USING ERRCODE = '42501';
  END IF;
  -- Lock order: tenant -> profile (shared: blocks imports/approval while analysing).
  PERFORM 1 FROM public.tenants t WHERE t.id = _tenant_id FOR SHARE;
  SELECT * INTO v_prof FROM public.tenant_value_profiles p WHERE p.tenant_id = _tenant_id AND p.status = 'approved' FOR SHARE;
  IF NOT FOUND THEN RAISE EXCEPTION 'analysis: no approved value profile' USING ERRCODE = '22023'; END IF;
  IF v_prof.id IS DISTINCT FROM _expected_profile_id THEN RAISE EXCEPTION 'analysis: approved value profile changed' USING ERRCODE = '22023'; END IF;
  PERFORM 1 FROM public.subjects s WHERE s.tenant_id = _tenant_id AND s.id = _subject_id;
  IF NOT FOUND THEN RAISE EXCEPTION 'analysis: unknown subject' USING ERRCODE = '22023'; END IF;
  PERFORM pg_advisory_xact_lock(hashtextextended('c02:' || _subject_id::text, 0));

  v_as_of := coalesce(_as_of, date_trunc('day', v_cutoff));
  IF v_as_of > v_cutoff THEN RAISE EXCEPTION 'analysis: as_of in the future' USING ERRCODE = '22023'; END IF;

  SELECT count(*), encode(sha256(convert_to(jsonb_build_object('alg', 'c02-v1', 'profile', v_prof.id, 'subject', _subject_id,
           'as_of', to_char(v_as_of, 'YYYY-MM-DD"T"HH24:MI:SS.US"Z"'),
           'obs', coalesce(jsonb_agg(jsonb_build_array(o.id, o.payload_hash) ORDER BY o.id), '[]'::jsonb))::text, 'UTF8')), 'hex')
    INTO v_obs_count, v_hash
    FROM public.observations o WHERE o.tenant_id = _tenant_id AND o.subject_id = _subject_id AND o.ingested_at <= v_cutoff;

  SELECT r.id INTO v_existing FROM public.c02_runs r WHERE r.tenant_id = _tenant_id AND r.subject_id = _subject_id AND r.input_hash = v_hash;
  IF FOUND THEN RETURN jsonb_build_object('run_id', v_existing, 'reused', true); END IF;
  SELECT r.id INTO v_prev FROM public.c02_runs r WHERE r.tenant_id = _tenant_id AND r.subject_id = _subject_id
     AND r.profile_id = v_prof.id AND r.as_of = v_as_of ORDER BY r.created_at DESC, r.id DESC LIMIT 1;

  FOR v_ind IN SELECT * FROM public.profile_indicators x WHERE x.profile_id = v_prof.id ORDER BY x.key LOOP
    cfg := '{}'; rsn := '{}'; v_windows := '[]'::jsonb; v_ref := NULL; v_base := NULL; v_b := NULL; v_below := NULL; v_ids := '{}'; v_den := NULL;
    IF v_ind.classification = 'context' THEN
      v_status := 'not_evaluated'; rsn := ARRAY['context_indicator'];
    ELSIF v_ind.value_type <> 'numeric' THEN
      v_status := 'unsupported'; rsn := ARRAY['text_indicator'];
    ELSE
      IF v_ind.deterioration_kind IS NULL OR v_ind.deterioration_operator IS NULL OR v_ind.deterioration_value IS NULL
         OR v_ind.deterioration_consecutive_windows IS NULL THEN cfg := array_append(cfg, 'deterioration_rule_missing'); END IF;
      IF v_ind.observation_window_days IS NULL THEN cfg := array_append(cfg, 'observation_window_missing'); END IF;
      IF v_ind.aggregation IS NULL THEN cfg := array_append(cfg, 'aggregation_missing'); END IF;
      IF v_ind.expected_cadence_days IS NULL THEN cfg := array_append(cfg, 'cadence_missing');
      ELSIF v_ind.observation_window_days IS NOT NULL AND v_ind.observation_window_days % v_ind.expected_cadence_days <> 0 THEN
        cfg := array_append(cfg, 'window_not_multiple_of_cadence'); END IF;
      IF v_ind.min_coverage_pct IS NULL THEN cfg := array_append(cfg, 'min_coverage_missing'); END IF;
      IF v_ind.min_denominator IS NULL THEN cfg := array_append(cfg, 'min_denominator_missing'); END IF;
      IF v_ind.denominator_mode IS NULL THEN cfg := array_append(cfg, 'denominator_mode_missing');
      ELSIF v_ind.denominator_mode = 'paired_indicator' THEN
        SELECT * INTO v_den FROM public.profile_indicators d WHERE d.profile_id = v_prof.id AND d.key = v_ind.denominator_indicator_key;
        IF v_den.id IS NULL OR v_den.value_type <> 'numeric' THEN cfg := array_append(cfg, 'denominator_indicator_invalid'); END IF;
      END IF;
      IF v_ind.baseline_method IS NULL THEN cfg := array_append(cfg, 'baseline_method_missing');
      ELSIF v_ind.baseline_method = 'reference_period' THEN cfg := array_append(cfg, 'baseline_method_unsupported');
      ELSIF v_ind.baseline_method = 'fixed_value' THEN
        IF v_ind.baseline_value IS NULL THEN cfg := array_append(cfg, 'baseline_value_missing');
        ELSIF v_ind.deterioration_kind = 'relative_pct' AND v_ind.baseline_value = 0 THEN cfg := array_append(cfg, 'baseline_zero'); END IF;
      ELSE -- trailing_window
        IF v_ind.comparison_window_days IS NULL THEN cfg := array_append(cfg, 'comparison_window_missing'); END IF;
        IF v_ind.baseline_min_period_days IS NULL THEN cfg := array_append(cfg, 'baseline_min_period_missing'); END IF;
        IF v_ind.comparison_window_days < v_ind.baseline_min_period_days THEN cfg := array_append(cfg, 'comparison_window_shorter_than_baseline_min'); END IF;
        IF v_ind.expected_cadence_days IS NOT NULL AND v_ind.comparison_window_days % v_ind.expected_cadence_days <> 0 THEN
          cfg := array_append(cfg, 'comparison_not_multiple_of_cadence'); END IF;
      END IF;
      IF (v_ind.direction = 'higher_is_better' AND v_ind.deterioration_operator IN ('gt','gte'))
         OR (v_ind.direction = 'lower_is_better' AND v_ind.deterioration_operator IN ('lt','lte')) THEN
        cfg := array_append(cfg, 'operator_contradicts_direction'); END IF;
      IF v_ind.deterioration_kind = 'relative_pct' AND ((v_ind.direction = 'higher_is_better' AND v_ind.deterioration_value >= 0)
         OR (v_ind.direction = 'lower_is_better' AND v_ind.deterioration_value <= 0)) THEN
        cfg := array_append(cfg, 'relative_threshold_not_a_worsening'); END IF;

      IF cardinality(cfg) > 0 THEN
        v_status := 'insufficient_config'; rsn := cfg;
      ELSE
        v_compat := ARRAY(SELECT x.profile_id FROM public.profile_indicators x JOIN public.tenant_value_profiles p ON p.id = x.profile_id
                          WHERE p.tenant_id = _tenant_id AND p.status <> 'draft' AND x.key = v_ind.key
                            AND public._c02_fingerprint(x) = public._c02_fingerprint(v_ind));
        IF v_den.id IS NOT NULL THEN
          v_den_compat := ARRAY(SELECT x.profile_id FROM public.profile_indicators x JOIN public.tenant_value_profiles p ON p.id = x.profile_id
                                WHERE p.tenant_id = _tenant_id AND p.status <> 'draft' AND x.key = v_den.key
                                  AND public._c02_fingerprint(x) = public._c02_fingerprint(v_den));
        END IF;
        W := make_interval(days => v_ind.observation_window_days);
        N := v_ind.deterioration_consecutive_windows;
        FOR k IN 1 .. N LOOP
          cur := public._c02_window(_tenant_id, _subject_id, v_ind.key, v_ind.unit, v_compat, v_ind.aggregation, v_ind.expected_cadence_days,
            v_ind.denominator_mode, v_den.key, v_den.unit, v_den_compat, v_ind.min_coverage_pct, v_ind.min_denominator, v_cutoff,
            v_as_of - W * k, v_as_of - W * (k - 1)) || jsonb_build_object('label', 'current_' || k);
          v_windows := v_windows || jsonb_build_array(cur);
          rsn := rsn || ARRAY(SELECT 'current_' || k || ':' || x FROM jsonb_array_elements_text(cur -> 'reasons') x);
        END LOOP;
        v_ref := public._c02_window(_tenant_id, _subject_id, v_ind.key, v_ind.unit, v_compat, v_ind.aggregation, v_ind.expected_cadence_days,
          v_ind.denominator_mode, v_den.key, v_den.unit, v_den_compat, v_ind.min_coverage_pct, v_ind.min_denominator, v_cutoff,
          v_as_of - W * (N + 1), v_as_of - W * N) || jsonb_build_object('label', 'reference');
        rsn := rsn || ARRAY(SELECT 'reference:' || x FROM jsonb_array_elements_text(v_ref -> 'reasons') x);
        IF v_ind.baseline_method = 'fixed_value' THEN
          v_b := v_ind.baseline_value;
        ELSE
          C := make_interval(days => v_ind.comparison_window_days);
          v_base := public._c02_window(_tenant_id, _subject_id, v_ind.key, v_ind.unit, v_compat, v_ind.aggregation, v_ind.expected_cadence_days,
            v_ind.denominator_mode, v_den.key, v_den.unit, v_den_compat, v_ind.min_coverage_pct, v_ind.min_denominator, v_cutoff,
            v_as_of - W * N - C, v_as_of - W * N) || jsonb_build_object('label', 'baseline');
          rsn := rsn || ARRAY(SELECT 'baseline:' || x FROM jsonb_array_elements_text(v_base -> 'reasons') x);
          IF (v_base ->> 'sufficient')::boolean THEN v_b := (v_base ->> 'value')::numeric; END IF;
          IF v_b = 0 AND v_ind.deterioration_kind = 'relative_pct' THEN rsn := array_append(rsn, 'baseline_zero'); END IF;
        END IF;

        IF cardinality(rsn) > 0 THEN
          v_status := 'insufficient_data';
        ELSE
          v_all := true; v_wout := '[]'::jsonb;
          FOR v_w IN SELECT value FROM jsonb_array_elements(v_windows) LOOP
            v_m := CASE v_ind.deterioration_kind WHEN 'absolute' THEN (v_w ->> 'value')::numeric
                   ELSE round(((v_w ->> 'value')::numeric - v_b) / abs(v_b) * 100, 4) END;
            v_meet := public._c02_cmp(v_m, v_ind.deterioration_operator, v_ind.deterioration_value);
            v_all := v_all AND v_meet;
            v_wout := v_wout || jsonb_build_array(v_w || jsonb_build_object('metric', v_m, 'meets_rule', v_meet));
          END LOOP;
          v_windows := v_wout;
          v_m := CASE v_ind.deterioration_kind WHEN 'absolute' THEN (v_ref ->> 'value')::numeric
                 ELSE round(((v_ref ->> 'value')::numeric - v_b) / abs(v_b) * 100, 4) END;
          v_refmeet := public._c02_cmp(v_m, v_ind.deterioration_operator, v_ind.deterioration_value);
          v_ref := v_ref || jsonb_build_object('metric', v_m, 'meets_rule', v_refmeet);
          v_status := CASE WHEN v_all AND NOT v_refmeet THEN 'deterioration_candidate'
                           WHEN v_all AND v_refmeet THEN 'persistent_condition' ELSE 'no_deterioration' END;
          IF v_ind.target_value IS NOT NULL THEN
            v_below := CASE v_ind.direction WHEN 'higher_is_better' THEN (v_windows -> 0 ->> 'value')::numeric < v_ind.target_value
                            ELSE (v_windows -> 0 ->> 'value')::numeric > v_ind.target_value END;
          END IF;
        END IF;
        v_ids := ARRAY(SELECT DISTINCT x::uuid FROM (
            SELECT jsonb_array_elements_text(w -> 'observation_ids') x
              FROM jsonb_array_elements(v_windows || jsonb_build_array(v_ref) || coalesce(jsonb_build_array(v_base), '[]'::jsonb)) w
             WHERE w IS NOT NULL AND w <> 'null'::jsonb) q ORDER BY 1);
      END IF;
    END IF;

    IF v_status = 'deterioration_candidate' AND v_ind.classification = 'outcome' THEN s_out := s_out + 1; END IF;
    IF v_status = 'deterioration_candidate' AND v_ind.classification = 'usage' THEN s_use := s_use + 1; END IF;
    IF v_status IN ('insufficient_data', 'insufficient_config', 'unsupported') THEN s_ins := s_ins + 1; END IF;
    IF v_status = 'persistent_condition' THEN s_pers := s_pers + 1; END IF;

    v_results := v_results || jsonb_build_array(jsonb_build_object(
      'key', v_ind.key, 'classification', v_ind.classification, 'status', v_status, 'below_target', v_below,
      'baseline_value', v_b, 'reasons', to_jsonb(rsn), 'observation_ids', to_jsonb(v_ids),
      'details', jsonb_build_object('windows', v_windows, 'reference', v_ref, 'baseline_window', v_base,
        'parameters', to_jsonb(v_ind) - 'created_at' - 'updated_at', 'fingerprint', public._c02_fingerprint(v_ind),
        'compatible_profile_ids', to_jsonb(v_compat))));
  END LOOP;

  INSERT INTO public.c02_runs(id, tenant_id, subject_id, profile_id, profile_version, algorithm_version, as_of, data_cutoff,
    input_hash, observation_count, revision_of, summary, created_by)
  VALUES (v_run, _tenant_id, _subject_id, v_prof.id, v_prof.version, 'c02-v1', v_as_of, v_cutoff, v_hash, v_obs_count, v_prev,
    jsonb_build_object('outcome_candidates', s_out, 'usage_candidates', s_use, 'insufficient', s_ins, 'persistent', s_pers,
      'indicators', jsonb_array_length(v_results), 'actionable_case', false), v_uid);
  INSERT INTO public.c02_results(tenant_id, run_id, subject_id, indicator_key, classification, status, below_target,
    baseline_value, reasons, observation_ids, details)
  SELECT _tenant_id, v_run, _subject_id, r ->> 'key', (r ->> 'classification')::public.indicator_class, (r ->> 'status')::public.c02_status,
    (r ->> 'below_target')::boolean, (r ->> 'baseline_value')::numeric,
    ARRAY(SELECT jsonb_array_elements_text(r -> 'reasons')), ARRAY(SELECT jsonb_array_elements_text(r -> 'observation_ids')::uuid),
    r -> 'details'
  FROM jsonb_array_elements(v_results) r;
  RETURN jsonb_build_object('run_id', v_run, 'reused', false, 'revision_of', v_prev);
END $$;
REVOKE ALL ON FUNCTION public.run_deterioration_analysis(uuid, uuid, uuid, timestamptz) FROM PUBLIC, anon;
GRANT EXECUTE ON FUNCTION public.run_deterioration_analysis(uuid, uuid, uuid, timestamptz) TO authenticated, service_role;
COMMENT ON FUNCTION public.run_deterioration_analysis(uuid, uuid, uuid, timestamptz) IS
  'C02 c02-v1: deterministic deterioration candidates per subject/indicator. Signals are candidates, never actionable cases.';