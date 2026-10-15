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
  END LOOP;
  RETURN issues;
END $$;