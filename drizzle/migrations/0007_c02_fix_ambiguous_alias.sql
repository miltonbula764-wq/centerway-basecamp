-- The alias "w" collided with the PL/pgSQL interval variable W (identifiers are case-insensitive).
DO $mig$
DECLARE src text; old_block text; new_block text;
BEGIN
  SELECT pg_get_functiondef('public.run_deterioration_analysis(uuid, uuid, uuid, timestamptz)'::regprocedure) INTO src;
  old_block := $o$            SELECT jsonb_array_elements_text(coalesce(w -> 'observation_ids', '[]'::jsonb) || coalesce(w -> 'denominator_observation_ids', '[]'::jsonb)) x
              FROM jsonb_array_elements(v_windows || jsonb_build_array(v_ref) || coalesce(jsonb_build_array(v_base), '[]'::jsonb)) w
             WHERE w IS NOT NULL AND w <> 'null'::jsonb) q ORDER BY 1);$o$;
  new_block := $n$            SELECT jsonb_array_elements_text(coalesce(wj.value -> 'observation_ids', '[]'::jsonb) || coalesce(wj.value -> 'denominator_observation_ids', '[]'::jsonb)) x
              FROM jsonb_array_elements(v_windows || jsonb_build_array(v_ref) || jsonb_build_array(v_base)) wj
             WHERE jsonb_typeof(wj.value) = 'object') q ORDER BY 1);$n$;
  IF position(old_block IN src) = 0 THEN RAISE EXCEPTION 'run_deterioration_analysis refs block not found; aborting'; END IF;
  EXECUTE replace(src, old_block, new_block);
END $mig$;