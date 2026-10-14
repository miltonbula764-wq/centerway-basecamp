-- c02-v1: denominator observations are evidence too; record their ids per window and in the result refs.
CREATE OR REPLACE FUNCTION public._c02_window(_tenant uuid, _subject uuid, _key text, _unit text, _compat uuid[],
  _agg public.c02_aggregation, _cad integer, _den_mode public.c02_denominator_mode, _den_key text, _den_unit text,
  _den_compat uuid[], _min_cov numeric, _min_den integer, _cutoff timestamptz, _s timestamptz, _e timestamptz)
RETURNS jsonb LANGUAGE plpgsql STABLE SET search_path = public SET timezone = 'UTC' AS $$
DECLARE
  v_n int; v_sources int; v_slots int; v_expected int; v_cov numeric; v_val numeric; v_den numeric;
  v_ids uuid[]; v_dids uuid[] := '{}'; v_excl jsonb; v_late int; v_ties int; v_dn int; v_dsrc int; v_dneg int; reasons text[] := '{}';
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
    SELECT count(*), count(DISTINCT e.source), count(*) FILTER (WHERE e.value < 0), sum(e.value),
           coalesce(array_agg(e.obs_id ORDER BY e.observed_at, e.obs_id), '{}')
      INTO v_dn, v_dsrc, v_dneg, v_den, v_dids
      FROM public._c02_effective(_tenant, _subject, _den_key, _den_unit, _den_compat, _cutoff) e
     WHERE e.issue IS NULL AND e.observed_at >= _s AND e.observed_at < _e;
    IF v_dn = 0 THEN reasons := array_append(reasons, 'denominator_missing');
    ELSIF v_dsrc > 1 THEN reasons := array_append(reasons, 'denominator_multiple_sources');
    ELSIF v_dneg > 0 THEN reasons := array_append(reasons, 'invalid_denominator'); END IF;
  END IF;
  IF v_den IS NULL OR v_den < _min_den THEN reasons := array_append(reasons, 'denominator_below_minimum'); END IF;

  RETURN jsonb_build_object('start', _s, 'end', _e, 'interval', '[start,end)', 'n', v_n,
    'expected_slots', v_expected, 'covered_slots', v_slots, 'coverage_pct', v_cov, 'sources', v_sources,
    'value', v_val, 'denominator', v_den, 'observation_ids', to_jsonb(v_ids), 'denominator_observation_ids', to_jsonb(v_dids),
    'excluded', v_excl, 'late_observations', v_late, 'sufficient', cardinality(reasons) = 0, 'reasons', to_jsonb(reasons));
END $$;
REVOKE ALL ON FUNCTION public._c02_window(uuid, uuid, text, text, uuid[], public.c02_aggregation, integer, public.c02_denominator_mode, text, text, uuid[], numeric, integer, timestamptz, timestamptz, timestamptz) FROM PUBLIC, anon, authenticated;

DO $mig$
DECLARE src text; old_block text; new_block text;
BEGIN
  SELECT pg_get_functiondef('public.run_deterioration_analysis(uuid, uuid, uuid, timestamptz)'::regprocedure) INTO src;
  old_block := $o$SELECT jsonb_array_elements_text(w -> 'observation_ids') x$o$;
  new_block := $n$SELECT jsonb_array_elements_text(coalesce(w -> 'observation_ids', '[]'::jsonb) || coalesce(w -> 'denominator_observation_ids', '[]'::jsonb)) x$n$;
  IF position(old_block IN src) = 0 THEN RAISE EXCEPTION 'run_deterioration_analysis refs block not found; aborting'; END IF;
  EXECUTE replace(src, old_block, new_block);
END $mig$;