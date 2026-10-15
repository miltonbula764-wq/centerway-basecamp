-- C03 Evidence Builder (c03-v1): immutable, append-only evidence bundles assembled server-side from one stored C02 run.
-- Inputs are only (tenant_id, run_id). Evidence comes from the immutable C02 snapshot + observations ingested up to the
-- run's data_cutoff; every ref is re-validated (ownership, cut-off, payload hash, window, correction chain, calculations).
-- c02_runs/c02_results rows are never modified.

CREATE TYPE public.c03_indicator_status AS ENUM ('complete', 'insufficient', 'context_facts');
CREATE TYPE public.c03_attempt_status AS ENUM ('built', 'reused', 'rejected', 'failed');

ALTER TABLE public.c02_runs ADD CONSTRAINT c02_runs_tenant_subject_id_key UNIQUE (tenant_id, subject_id, id);

CREATE TABLE public.c03_bundles (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES public.tenants(id),
  subject_id uuid NOT NULL,
  run_id uuid NOT NULL,
  algorithm_version text NOT NULL,
  c02_algorithm_version text NOT NULL,
  c02_input_hash text NOT NULL,
  data_cutoff timestamptz NOT NULL,
  content_hash text NOT NULL,
  revision_of uuid,
  summary jsonb NOT NULL,
  created_by uuid,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, id),
  UNIQUE (tenant_id, run_id, algorithm_version),
  FOREIGN KEY (tenant_id, subject_id) REFERENCES public.subjects(tenant_id, id),
  FOREIGN KEY (tenant_id, subject_id, run_id) REFERENCES public.c02_runs(tenant_id, subject_id, id),
  FOREIGN KEY (tenant_id, revision_of) REFERENCES public.c03_bundles(tenant_id, id)
);
CREATE INDEX c03_bundles_subject_idx ON public.c03_bundles(tenant_id, subject_id, created_at DESC);

CREATE TABLE public.c03_indicators (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES public.tenants(id),
  bundle_id uuid NOT NULL,
  indicator_key text NOT NULL,
  c02_result_id uuid NOT NULL REFERENCES public.c02_results(id),
  status public.c03_indicator_status NOT NULL,
  reasons text[] NOT NULL DEFAULT '{}',
  ref_count integer NOT NULL,
  stored_ref_count integer NOT NULL,
  ref_budget integer NOT NULL,
  snapshot jsonb NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, id),
  UNIQUE (bundle_id, indicator_key),
  FOREIGN KEY (tenant_id, bundle_id) REFERENCES public.c03_bundles(tenant_id, id)
);

CREATE TABLE public.c03_refs (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  tenant_id uuid NOT NULL REFERENCES public.tenants(id),
  bundle_id uuid NOT NULL,
  indicator_id uuid NOT NULL,
  ordinal integer NOT NULL,
  role text NOT NULL CHECK (role IN ('numerator', 'denominator', 'superseded', 'denominator_superseded', 'unclassified')),
  window_label text,
  window_start timestamptz,
  window_end timestamptz,
  observation_id uuid NOT NULL,
  superseded_by uuid,
  indicator_key text NOT NULL,
  observed_at timestamptz NOT NULL,
  ingested_at timestamptz NOT NULL,
  value_numeric numeric,
  value_text text,
  unit text NOT NULL,
  source text NOT NULL,
  payload_hash text NOT NULL,
  corrects_observation_id uuid,
  UNIQUE (indicator_id, ordinal),
  FOREIGN KEY (tenant_id, bundle_id) REFERENCES public.c03_bundles(tenant_id, id),
  FOREIGN KEY (tenant_id, indicator_id) REFERENCES public.c03_indicators(tenant_id, id),
  FOREIGN KEY (tenant_id, observation_id) REFERENCES public.observations(tenant_id, id)
);
CREATE INDEX c03_refs_bundle_idx ON public.c03_refs(tenant_id, bundle_id);

CREATE TABLE public.c03_attempts (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES public.tenants(id),
  requested_run_id uuid NOT NULL,
  actor_id uuid,
  algorithm_version text NOT NULL,
  status public.c03_attempt_status NOT NULL,
  code text,
  bundle_id uuid,
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  FOREIGN KEY (tenant_id, bundle_id) REFERENCES public.c03_bundles(tenant_id, id)
);
CREATE INDEX c03_attempts_run_idx ON public.c03_attempts(tenant_id, requested_run_id, created_at DESC);

REVOKE ALL ON public.c03_bundles, public.c03_indicators, public.c03_refs, public.c03_attempts FROM PUBLIC, anon, authenticated;
REVOKE ALL ON SEQUENCE public.c03_refs_id_seq FROM PUBLIC, anon, authenticated;
GRANT SELECT ON public.c03_bundles, public.c03_indicators, public.c03_refs, public.c03_attempts TO authenticated;
GRANT ALL ON public.c03_bundles, public.c03_indicators, public.c03_refs, public.c03_attempts TO service_role;
ALTER TABLE public.c03_bundles ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.c03_indicators ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.c03_refs ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.c03_attempts ENABLE ROW LEVEL SECURITY;
CREATE POLICY c03_bundles_select ON public.c03_bundles FOR SELECT TO authenticated USING (public.is_tenant_member(tenant_id));
CREATE POLICY c03_indicators_select ON public.c03_indicators FOR SELECT TO authenticated USING (public.is_tenant_member(tenant_id));
CREATE POLICY c03_refs_select ON public.c03_refs FOR SELECT TO authenticated USING (public.is_tenant_member(tenant_id));
CREATE POLICY c03_attempts_select ON public.c03_attempts FOR SELECT TO authenticated USING (public.is_tenant_member(tenant_id));

CREATE TRIGGER c03_bundles_immutable BEFORE UPDATE OR DELETE ON public.c03_bundles FOR EACH ROW EXECUTE FUNCTION public._c02_immutable();
CREATE TRIGGER c03_indicators_immutable BEFORE UPDATE OR DELETE ON public.c03_indicators FOR EACH ROW EXECUTE FUNCTION public._c02_immutable();
CREATE TRIGGER c03_refs_immutable BEFORE UPDATE OR DELETE ON public.c03_refs FOR EACH ROW EXECUTE FUNCTION public._c02_immutable();
CREATE TRIGGER c03_attempts_immutable BEFORE UPDATE OR DELETE ON public.c03_attempts FOR EACH ROW EXECUTE FUNCTION public._c02_immutable();
CREATE TRIGGER c03_bundles_audit AFTER INSERT ON public.c03_bundles FOR EACH ROW EXECUTE FUNCTION public._cw_audit();
CREATE TRIGGER c03_attempts_audit AFTER INSERT ON public.c03_attempts FOR EACH ROW EXECUTE FUNCTION public._cw_audit();

CREATE FUNCTION public._c03_reject(_code text) RETURNS void LANGUAGE plpgsql SET search_path = public AS $$
BEGIN RAISE EXCEPTION '%', _code USING ERRCODE = 'CWC03'; END $$;

CREATE FUNCTION public._c03_payload_hash(o public.observations) RETURNS text LANGUAGE sql STABLE SET search_path = public AS $$
  SELECT encode(sha256(convert_to(jsonb_build_object(
    'subject_id', o.subject_id, 'indicator_key', o.indicator_key, 'value_numeric', trim_scale(o.value_numeric),
    'value_text', o.value_text, 'unit', o.unit, 'source', o.source,
    'observed_at', to_char(o.observed_at AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.US"Z"'),
    'payload', o.payload, 'corrects', o.corrects_observation_id)::text, 'UTF8')), 'hex') $$;

CREATE FUNCTION public._c03_assemble(_run public.c02_runs, _bundle uuid, _alg text, _budget integer, _uid uuid)
RETURNS jsonb LANGUAGE plpgsql SET search_path = public SET "TimeZone" = 'UTC' AS $$
DECLARE
  rr public.c02_results; d jsonb; p jsonb; v_legacy boolean := _run.algorithm_version = 'c02-v1';
  v_refs jsonb; v_bad text; v_hash text; v_cnt int; v_n int; v_status public.c03_indicator_status; v_reasons text[];
  v_acc jsonb := '[]'::jsonb; v_wins jsonb; w jsonb; v_lbl text; v_k int; v_s timestamptz; v_e timestamptz;
  Wd int; Nn int; Cd int; v_asof timestamptz := _run.as_of;
  c_n int; c_ns int; c_src text; c_avg numeric; c_sum numeric; c_last numeric; c_exp numeric;
  d_n int; d_ns int; d_src text; d_sum numeric; v_metric numeric; v_base numeric;
  v_prev uuid; v_ind_id uuid; v_rows int; x jsonb; s_c int := 0; s_i int := 0; s_x int := 0; s_refs int := 0; v_summary jsonb;
BEGIN
  IF _run.algorithm_version NOT IN ('c02-v1', 'c02-v2') THEN PERFORM public._c03_reject('unknown_c02_algorithm'); END IF;

  FOR rr IN SELECT * FROM public.c02_results r WHERE r.tenant_id = _run.tenant_id AND r.run_id = _run.id ORDER BY r.indicator_key LOOP
    d := rr.details; p := d -> 'parameters';
    IF rr.subject_id <> _run.subject_id THEN PERFORM public._c03_reject('c02_result_subject_mismatch'); END IF;
    IF NOT v_legacy AND (d ->> 'algorithm') IS DISTINCT FROM _run.algorithm_version THEN PERFORM public._c03_reject('c02_result_algorithm_mismatch'); END IF;
    IF p IS NOT NULL AND (p ->> 'key') IS DISTINCT FROM rr.indicator_key THEN PERFORM public._c03_reject('c02_result_parameters_mismatch'); END IF;
    SELECT coalesce(jsonb_agg(e.value), '[]'::jsonb) INTO v_wins
      FROM jsonb_array_elements(coalesce(d -> 'windows', '[]'::jsonb) || jsonb_build_array(d -> 'reference') || jsonb_build_array(d -> 'baseline_window')) e
     WHERE jsonb_typeof(e.value) = 'object';

    IF v_legacy THEN
      SELECT coalesce(jsonb_agg(jsonb_build_object('oid', x2, 'role', 'unclassified', 'key', rr.indicator_key) ORDER BY x2), '[]'::jsonb)
        INTO v_refs FROM unnest(rr.observation_ids) x2;
    ELSE
      SELECT coalesce(jsonb_agg(z.q ORDER BY z.q ->> 'label', z.q ->> 'role', z.q ->> 'oid'), '[]'::jsonb) INTO v_refs FROM (
        SELECT jsonb_build_object('oid', i.v, 'role', 'numerator', 'label', wj.value ->> 'label', 's', wj.value -> 'start', 'e', wj.value -> 'end',
                                  'key', rr.indicator_key, 'unit', p ->> 'unit') AS q
          FROM jsonb_array_elements(v_wins) wj, jsonb_array_elements_text(coalesce(wj.value -> 'observation_ids', '[]'::jsonb)) i(v)
        UNION ALL
        SELECT jsonb_build_object('oid', i.v, 'role', 'denominator', 'label', wj.value ->> 'label', 's', wj.value -> 'start', 'e', wj.value -> 'end',
                                  'key', d -> 'denominator_parameters' ->> 'key', 'unit', d -> 'denominator_parameters' ->> 'unit')
          FROM jsonb_array_elements(v_wins) wj, jsonb_array_elements_text(coalesce(wj.value -> 'denominator_observation_ids', '[]'::jsonb)) i(v)
        UNION ALL
        SELECT jsonb_build_object('oid', sx.value #>> '{}', 'role', CASE WHEN f.den THEN 'denominator_superseded' ELSE 'superseded' END,
                                  'label', wj.value ->> 'label', 's', wj.value -> 'start', 'e', wj.value -> 'end',
                                  'key', CASE WHEN f.den THEN d -> 'denominator_parameters' ->> 'key' ELSE rr.indicator_key END,
                                  'leaf', c.value ->> 'observation_id',
                                  'prev', CASE WHEN sx.ordinality = 1 THEN c.value ->> 'observation_id' ELSE c.value -> 'supersedes' ->> (sx.ordinality::int - 2) END)
          FROM jsonb_array_elements(v_wins) wj,
               LATERAL (VALUES (false, wj.value -> 'corrections'), (true, wj.value -> 'denominator_corrections')) f(den, arr),
               jsonb_array_elements(coalesce(f.arr, '[]'::jsonb)) c,
               jsonb_array_elements(coalesce(c.value -> 'supersedes', '[]'::jsonb)) WITH ORDINALITY sx
      ) z;
    END IF;

    SELECT z.bad INTO v_bad FROM (
      SELECT CASE
        WHEN o.id IS NULL THEN 'ref_missing'
        WHEN o.subject_id <> _run.subject_id THEN 'ref_wrong_subject'
        WHEN o.ingested_at > _run.data_cutoff THEN 'ref_after_cutoff'
        WHEN r.value ->> 'role' <> 'unclassified' AND o.indicator_key IS DISTINCT FROM r.value ->> 'key' THEN 'ref_wrong_indicator'
        WHEN o.payload_hash <> public._c03_payload_hash(o) THEN 'ref_payload_hash_mismatch'
        WHEN r.value ->> 'role' IN ('numerator', 'denominator')
             AND (o.observed_at < (r.value ->> 's')::timestamptz OR o.observed_at >= (r.value ->> 'e')::timestamptz) THEN 'ref_outside_window'
        WHEN r.value ->> 'role' IN ('numerator', 'denominator')
             AND (o.unit IS DISTINCT FROM r.value ->> 'unit' OR o.value_numeric IS NULL) THEN 'ref_value_incompatible'
        WHEN r.value ->> 'role' IN ('numerator', 'denominator', 'unclassified') AND EXISTS (
             SELECT 1 FROM public.observations k WHERE k.tenant_id = o.tenant_id AND k.corrects_observation_id = o.id
                AND k.ingested_at <= _run.data_cutoff) THEN 'ref_not_effective'
        WHEN r.value ->> 'role' LIKE '%superseded' AND NOT EXISTS (
             SELECT 1 FROM public.observations lf JOIN public.observations pv ON pv.tenant_id = lf.tenant_id AND pv.id = (r.value ->> 'prev')::uuid
              WHERE lf.tenant_id = o.tenant_id AND lf.id = (r.value ->> 'leaf')::uuid AND lf.id = ANY (rr.observation_ids)
                AND pv.corrects_observation_id = o.id AND pv.ingested_at <= _run.data_cutoff
                AND o.source = lf.source AND o.observed_at = lf.observed_at AND o.indicator_key = lf.indicator_key) THEN 'correction_chain_invalid'
      END AS bad
      FROM jsonb_array_elements(v_refs) r
      LEFT JOIN public.observations o ON o.tenant_id = _run.tenant_id AND o.id = (r.value ->> 'oid')::uuid
    ) z WHERE z.bad IS NOT NULL LIMIT 1;
    IF v_bad IS NOT NULL THEN PERFORM public._c03_reject(v_bad); END IF;

    IF NOT v_legacy THEN
      IF (SELECT array_agg(DISTINCT (r.value ->> 'oid')::uuid ORDER BY (r.value ->> 'oid')::uuid) FROM jsonb_array_elements(v_refs) r
           WHERE r.value ->> 'role' IN ('numerator', 'denominator'))
         IS DISTINCT FROM (SELECT array_agg(DISTINCT u ORDER BY u) FROM unnest(rr.observation_ids) u) THEN
        PERFORM public._c03_reject('ref_set_mismatch');
      END IF;
      Wd := (p ->> 'observation_window_days')::int; Nn := (p ->> 'deterioration_consecutive_windows')::int;
      Cd := (p ->> 'comparison_window_days')::int;
      FOR w IN SELECT e.value FROM jsonb_array_elements(v_wins) e LOOP
        v_lbl := w ->> 'label'; v_s := (w ->> 'start')::timestamptz; v_e := (w ->> 'end')::timestamptz;
        IF v_lbl LIKE 'current\_%' THEN v_k := substr(v_lbl, 9)::int;
          IF v_s <> v_asof - make_interval(days => Wd * v_k) OR v_e <> v_asof - make_interval(days => Wd * (v_k - 1)) OR v_k > Nn THEN
            PERFORM public._c03_reject('window_boundary_mismatch'); END IF;
        ELSIF v_lbl = 'reference' THEN
          IF v_s <> v_asof - make_interval(days => Wd * (Nn + 1)) OR v_e <> v_asof - make_interval(days => Wd * Nn) THEN
            PERFORM public._c03_reject('window_boundary_mismatch'); END IF;
        ELSIF v_lbl = 'baseline' THEN
          IF v_s <> v_asof - make_interval(days => Wd * Nn + Cd) OR v_e <> v_asof - make_interval(days => Wd * Nn) THEN
            PERFORM public._c03_reject('window_boundary_mismatch'); END IF;
        ELSE PERFORM public._c03_reject('window_boundary_mismatch');
        END IF;

        SELECT count(*), count(DISTINCT o.source), min(o.source), avg(o.value_numeric), sum(o.value_numeric)
          INTO c_n, c_ns, c_src, c_avg, c_sum
          FROM jsonb_array_elements_text(coalesce(w -> 'observation_ids', '[]'::jsonb)) i(v)
          JOIN public.observations o ON o.tenant_id = _run.tenant_id AND o.id = i.v::uuid;
        c_last := NULL;
        SELECT o.value_numeric INTO c_last FROM jsonb_array_elements_text(coalesce(w -> 'observation_ids', '[]'::jsonb)) i(v)
          JOIN public.observations o ON o.tenant_id = _run.tenant_id AND o.id = i.v::uuid ORDER BY o.observed_at DESC LIMIT 1;
        c_exp := CASE p ->> 'aggregation' WHEN 'mean' THEN c_avg WHEN 'sum' THEN c_sum WHEN 'last' THEN c_last END;
        IF c_n <> (w ->> 'n')::int
           OR (CASE WHEN c_ns = 1 THEN c_src END) IS DISTINCT FROM (w ->> 'source')
           OR ((w ->> 'value') IS NOT NULL AND (w ->> 'value')::numeric IS DISTINCT FROM c_exp) THEN
          PERFORM public._c03_reject('calculation_mismatch'); END IF;

        IF p ->> 'denominator_mode' = 'paired_indicator' THEN
          SELECT count(*), count(DISTINCT o.source), min(o.source), sum(o.value_numeric) INTO d_n, d_ns, d_src, d_sum
            FROM jsonb_array_elements_text(coalesce(w -> 'denominator_observation_ids', '[]'::jsonb)) i(v)
            JOIN public.observations o ON o.tenant_id = _run.tenant_id AND o.id = i.v::uuid;
          IF (w ->> 'denominator')::numeric IS DISTINCT FROM d_sum
             OR (CASE WHEN d_ns = 1 THEN d_src END) IS DISTINCT FROM (w ->> 'denominator_source') THEN
            PERFORM public._c03_reject('calculation_mismatch'); END IF;
        ELSIF p ->> 'denominator_mode' = 'observation_count' THEN
          IF (w ->> 'denominator')::numeric IS DISTINCT FROM c_n::numeric THEN PERFORM public._c03_reject('calculation_mismatch'); END IF;
        END IF;

        IF w ? 'metric' THEN
          v_metric := CASE p ->> 'deterioration_kind' WHEN 'absolute' THEN (w ->> 'value')::numeric
                      ELSE round(((w ->> 'value')::numeric - rr.baseline_value) / abs(rr.baseline_value) * 100, 4) END;
          IF v_metric IS DISTINCT FROM (w ->> 'metric')::numeric
             OR public._c02_cmp(v_metric, (p ->> 'deterioration_operator')::public.rule_operator, (p ->> 'deterioration_value')::numeric)
                IS DISTINCT FROM (w ->> 'meets_rule')::boolean THEN
            PERFORM public._c03_reject('calculation_mismatch'); END IF;
        END IF;
      END LOOP;
      IF rr.baseline_value IS NOT NULL THEN
        v_base := CASE p ->> 'baseline_method' WHEN 'fixed_value' THEN (p ->> 'baseline_value')::numeric
                  ELSE (d -> 'baseline_window' ->> 'value')::numeric END;
        IF v_base IS DISTINCT FROM rr.baseline_value THEN PERFORM public._c03_reject('baseline_mismatch'); END IF;
      END IF;
    END IF;

    v_n := jsonb_array_length(v_refs);
    IF rr.status IN ('not_evaluated', 'unsupported') THEN
      v_status := 'context_facts';
      v_reasons := rr.reasons || ARRAY['no_temporal_evaluation'] || CASE WHEN v_n = 0 THEN ARRAY['context_not_collected_by_c02'] ELSE '{}'::text[] END;
    ELSIF v_legacy THEN
      v_status := 'insufficient'; v_reasons := ARRAY['legacy_c02_v1_known_gaps'] || rr.reasons;
    ELSIF rr.status IN ('insufficient_data', 'insufficient_config') THEN
      v_status := 'insufficient'; v_reasons := ARRAY['c02_' || rr.status::text] || rr.reasons;
    ELSE
      v_status := 'complete'; v_reasons := '{}';
    END IF;
    IF v_n > _budget THEN
      v_status := 'insufficient'; v_reasons := v_reasons || ARRAY['ref_budget_exceeded'];
    END IF;

    SELECT coalesce(jsonb_agg(r.value || jsonb_build_object('ph', o.payload_hash, 'ord', r.ordinality) ORDER BY r.ordinality), '[]'::jsonb) INTO v_refs
      FROM jsonb_array_elements(v_refs) WITH ORDINALITY r JOIN public.observations o ON o.tenant_id = _run.tenant_id AND o.id = (r.value ->> 'oid')::uuid;
    v_acc := v_acc || jsonb_build_array(jsonb_build_object(
      'key', rr.indicator_key, 'c02_result_id', rr.id, 'status', v_status, 'reasons', to_jsonb(v_reasons), 'ref_count', v_n,
      'stored', CASE WHEN v_n > _budget THEN 0 ELSE v_n END,
      'snapshot', jsonb_build_object('c02_status', rr.status, 'c02_reasons', to_jsonb(rr.reasons), 'classification', rr.classification,
        'below_target', rr.below_target, 'baseline_value', rr.baseline_value, 'details', d),
      'refs', CASE WHEN v_n > _budget THEN '[]'::jsonb ELSE v_refs END));
    IF v_status = 'complete' THEN s_c := s_c + 1; ELSIF v_status = 'insufficient' THEN s_i := s_i + 1; ELSE s_x := s_x + 1; END IF;
    s_refs := s_refs + CASE WHEN v_n > _budget THEN 0 ELSE v_n END;
  END LOOP;

  SELECT count(*), encode(sha256(convert_to(jsonb_build_object('alg', _run.algorithm_version, 'profile', _run.profile_id,
           'subject', _run.subject_id, 'as_of', to_char(_run.as_of, 'YYYY-MM-DD"T"HH24:MI:SS.US"Z"'),
           'obs', coalesce(jsonb_agg(jsonb_build_array(o.id, o.payload_hash) ORDER BY o.id), '[]'::jsonb))::text, 'UTF8')), 'hex')
    INTO v_cnt, v_hash
    FROM public.observations o WHERE o.tenant_id = _run.tenant_id AND o.subject_id = _run.subject_id AND o.ingested_at <= _run.data_cutoff;
  IF v_hash IS DISTINCT FROM _run.input_hash OR v_cnt IS DISTINCT FROM _run.observation_count THEN
    PERFORM public._c03_reject('c02_input_hash_mismatch'); END IF;

  SELECT b.id INTO v_prev FROM public.c03_bundles b
   WHERE b.tenant_id = _run.tenant_id AND b.run_id = _run.revision_of AND b.algorithm_version = _alg;
  v_summary := jsonb_build_object('indicators', jsonb_array_length(v_acc), 'complete', s_c, 'insufficient', s_i, 'context_facts', s_x,
    'stored_refs', s_refs, 'ref_budget', _budget, 'actionable_case', false);

  INSERT INTO public.c03_bundles(id, tenant_id, subject_id, run_id, algorithm_version, c02_algorithm_version, c02_input_hash, data_cutoff,
    content_hash, revision_of, summary, created_by)
  VALUES (_bundle, _run.tenant_id, _run.subject_id, _run.id, _alg, _run.algorithm_version, _run.input_hash, _run.data_cutoff,
    encode(sha256(convert_to(jsonb_build_object('alg', _alg, 'run', _run.id, 'c02_alg', _run.algorithm_version, 'input_hash', _run.input_hash,
      'cutoff', to_char(_run.data_cutoff, 'YYYY-MM-DD"T"HH24:MI:SS.US"Z"'), 'budget', _budget,
      'indicators', (SELECT coalesce(jsonb_agg(a.value - 'c02_result_id'), '[]'::jsonb) FROM jsonb_array_elements(v_acc) a))::text, 'UTF8')), 'hex'),
    v_prev, v_summary, _uid);

  FOR x IN SELECT a.value FROM jsonb_array_elements(v_acc) a LOOP
    INSERT INTO public.c03_indicators(tenant_id, bundle_id, indicator_key, c02_result_id, status, reasons, ref_count, stored_ref_count, ref_budget, snapshot)
    VALUES (_run.tenant_id, _bundle, x ->> 'key', (x ->> 'c02_result_id')::uuid, (x ->> 'status')::public.c03_indicator_status,
      ARRAY(SELECT jsonb_array_elements_text(x -> 'reasons')), (x ->> 'ref_count')::int, (x ->> 'stored')::int, _budget, x -> 'snapshot')
    RETURNING id INTO v_ind_id;
    INSERT INTO public.c03_refs(tenant_id, bundle_id, indicator_id, ordinal, role, window_label, window_start, window_end, observation_id,
      superseded_by, indicator_key, observed_at, ingested_at, value_numeric, value_text, unit, source, payload_hash, corrects_observation_id)
    SELECT _run.tenant_id, _bundle, v_ind_id, (r.value ->> 'ord')::int, r.value ->> 'role', r.value ->> 'label',
      (r.value ->> 's')::timestamptz, (r.value ->> 'e')::timestamptz, o.id, (r.value ->> 'prev')::uuid, o.indicator_key, o.observed_at,
      o.ingested_at, o.value_numeric, o.value_text, o.unit, o.source, o.payload_hash, o.corrects_observation_id
    FROM jsonb_array_elements(x -> 'refs') r
    JOIN public.observations o ON o.tenant_id = _run.tenant_id AND o.id = (r.value ->> 'oid')::uuid
    WHERE o.payload_hash = r.value ->> 'ph';
    GET DIAGNOSTICS v_rows = ROW_COUNT;
    IF v_rows <> (x ->> 'stored')::int THEN PERFORM public._c03_reject('ref_changed_during_build'); END IF;
  END LOOP;
  RETURN v_summary;
END $$;

CREATE FUNCTION public._c03_build(_tenant_id uuid, _run_id uuid, _budget integer)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path = public SET "TimeZone" = 'UTC' AS $$
DECLARE
  v_alg constant text := 'c03-v1'; v_uid uuid := auth.uid(); v_run public.c02_runs; v_bundle uuid; v_new uuid := gen_random_uuid();
  v_status public.c03_attempt_status; v_code text; v_summary jsonb;
BEGIN
  IF v_uid IS NULL THEN RAISE EXCEPTION 'authentication required' USING ERRCODE = '28000'; END IF;
  IF NOT public.has_tenant_role(_tenant_id, ARRAY['admin','operator']::public.member_role[]) THEN
    RAISE EXCEPTION 'not authorized' USING ERRCODE = '42501';
  END IF;
  IF _budget IS NULL OR _budget < 0 THEN RAISE EXCEPTION 'invalid budget' USING ERRCODE = '22023'; END IF;
  PERFORM 1 FROM public.tenants t WHERE t.id = _tenant_id FOR SHARE;
  PERFORM pg_advisory_xact_lock(hashtextextended('c03:' || _tenant_id::text || ':' || coalesce(_run_id::text, ''), 0));

  SELECT * INTO v_run FROM public.c02_runs r WHERE r.tenant_id = _tenant_id AND r.id = _run_id;
  IF NOT FOUND THEN
    INSERT INTO public.c03_attempts(tenant_id, requested_run_id, actor_id, algorithm_version, status, code)
    VALUES (_tenant_id, coalesce(_run_id, '00000000-0000-0000-0000-000000000000'), v_uid, v_alg, 'rejected', 'run_not_found');
    RETURN jsonb_build_object('status', 'rejected', 'code', 'run_not_found');
  END IF;

  SELECT b.id INTO v_bundle FROM public.c03_bundles b WHERE b.tenant_id = _tenant_id AND b.run_id = _run_id AND b.algorithm_version = v_alg;
  IF FOUND THEN
    INSERT INTO public.c03_attempts(tenant_id, requested_run_id, actor_id, algorithm_version, status, bundle_id)
    VALUES (_tenant_id, _run_id, v_uid, v_alg, 'reused', v_bundle);
    RETURN jsonb_build_object('status', 'reused', 'bundle_id', v_bundle);
  END IF;

  BEGIN
    v_summary := public._c03_assemble(v_run, v_new, v_alg, _budget, v_uid);
    v_status := 'built';
  EXCEPTION WHEN OTHERS THEN
    IF SQLSTATE = 'CWC03' THEN v_status := 'rejected'; v_code := SQLERRM;
    ELSE v_status := 'failed'; v_code := 'internal_error:' || SQLSTATE; END IF;
  END;

  INSERT INTO public.c03_attempts(tenant_id, requested_run_id, actor_id, algorithm_version, status, code, bundle_id)
  VALUES (_tenant_id, _run_id, v_uid, v_alg, v_status, v_code, CASE WHEN v_status = 'built' THEN v_new END);
  IF v_status = 'built' THEN
    RETURN jsonb_build_object('status', 'built', 'bundle_id', v_new, 'summary', v_summary);
  END IF;
  RETURN jsonb_build_object('status', v_status, 'code', v_code);
END $$;

CREATE FUNCTION public.build_evidence_bundle(_tenant_id uuid, _run_id uuid)
RETURNS jsonb LANGUAGE sql SECURITY DEFINER SET search_path = public AS $$
  SELECT public._c03_build(_tenant_id, _run_id, 5000) $$;

REVOKE ALL ON FUNCTION public._c03_reject(text) FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public._c03_payload_hash(public.observations) FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public._c03_assemble(public.c02_runs, uuid, text, integer, uuid) FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public._c03_build(uuid, uuid, integer) FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.build_evidence_bundle(uuid, uuid) FROM PUBLIC, anon;
GRANT EXECUTE ON FUNCTION public.build_evidence_bundle(uuid, uuid) TO authenticated;