-- c02-v1: a 'sum' over a trailing baseline window of different length is not comparable with a current window sum.
DO $mig$
DECLARE src text; old_block text; new_block text;
BEGIN
  SELECT pg_get_functiondef('public.run_deterioration_analysis(uuid, uuid, uuid, timestamptz)'::regprocedure) INTO src;
  old_block := $o$          cfg := array_append(cfg, 'comparison_not_multiple_of_cadence'); END IF;$o$;
  new_block := $n$          cfg := array_append(cfg, 'comparison_not_multiple_of_cadence'); END IF;
        IF v_ind.aggregation = 'sum' AND v_ind.comparison_window_days IS DISTINCT FROM v_ind.observation_window_days THEN
          cfg := array_append(cfg, 'sum_requires_equal_windows'); END IF;$n$;
  IF position(old_block IN src) = 0 THEN RAISE EXCEPTION 'run_deterioration_analysis block not found; aborting'; END IF;
  EXECUTE replace(src, old_block, new_block);
END $mig$;