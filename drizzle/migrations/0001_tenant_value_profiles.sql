-- Value Profile becomes tenant-scoped (plan v1). Old per-subject tables retired (empty; kept, deprecated).
CREATE TYPE public.indicator_class AS ENUM ('outcome','usage','context');
CREATE TYPE public.baseline_method AS ENUM ('fixed_value','trailing_window','reference_period');
CREATE TYPE public.rule_kind AS ENUM ('absolute','relative_pct');
CREATE TYPE public.rule_operator AS ENUM ('lt','lte','gt','gte');

CREATE TABLE public.tenant_value_profiles (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES public.tenants(id) ON DELETE CASCADE,
  version integer NOT NULL CHECK (version > 0),
  status public.profile_status NOT NULL DEFAULT 'draft',
  promise text NOT NULL CHECK (char_length(btrim(promise)) BETWEEN 1 AND 4000),
  expected_outcome text CHECK (expected_outcome IS NULL OR char_length(expected_outcome) <= 4000),
  notes text CHECK (notes IS NULL OR char_length(notes) <= 4000),
  created_by uuid,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  approved_by uuid,
  approved_at timestamptz,
  UNIQUE (tenant_id, version),
  UNIQUE (tenant_id, id),
  CONSTRAINT tvp_approval_fields CHECK ((status = 'draft' AND approved_by IS NULL AND approved_at IS NULL)
      OR (status <> 'draft' AND approved_by IS NOT NULL AND approved_at IS NOT NULL))
);
CREATE UNIQUE INDEX tvp_one_approved_per_tenant ON public.tenant_value_profiles(tenant_id) WHERE status = 'approved';

CREATE TABLE public.profile_indicators (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES public.tenants(id) ON DELETE CASCADE,
  profile_id uuid NOT NULL,
  key text NOT NULL CHECK (key ~ '^[a-z][a-z0-9_]{0,63}$'),
  name text NOT NULL CHECK (char_length(btrim(name)) BETWEEN 1 AND 200),
  definition text CHECK (definition IS NULL OR char_length(definition) <= 4000),
  classification public.indicator_class NOT NULL,
  unit text NOT NULL CHECK (char_length(btrim(unit)) BETWEEN 1 AND 50),
  direction public.indicator_direction NOT NULL,
  -- baseline contract
  baseline_method public.baseline_method,
  baseline_value numeric,
  baseline_min_period_days integer CHECK (baseline_min_period_days IS NULL OR baseline_min_period_days > 0),
  -- windows
  observation_window_days integer CHECK (observation_window_days IS NULL OR observation_window_days > 0),
  comparison_window_days integer CHECK (comparison_window_days IS NULL OR comparison_window_days > 0),
  -- sufficiency
  min_coverage_pct numeric CHECK (min_coverage_pct IS NULL OR (min_coverage_pct > 0 AND min_coverage_pct <= 100)),
  min_denominator integer CHECK (min_denominator IS NULL OR min_denominator > 0),
  -- target / deterioration / recovery (kind + operator + value, unit = indicator unit when absolute, % of baseline when relative_pct)
  target_value numeric,
  deterioration_kind public.rule_kind,
  deterioration_operator public.rule_operator,
  deterioration_value numeric,
  deterioration_consecutive_windows integer CHECK (deterioration_consecutive_windows IS NULL OR deterioration_consecutive_windows > 0),
  recovery_kind public.rule_kind,
  recovery_operator public.rule_operator,
  recovery_value numeric,
  recovery_consecutive_windows integer CHECK (recovery_consecutive_windows IS NULL OR recovery_consecutive_windows > 0),
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (profile_id, key),
  UNIQUE (tenant_id, id),
  FOREIGN KEY (tenant_id, profile_id) REFERENCES public.tenant_value_profiles(tenant_id, id) ON DELETE CASCADE,
  CONSTRAINT pi_deterioration_rule_complete CHECK (
    (deterioration_kind IS NULL AND deterioration_operator IS NULL AND deterioration_value IS NULL)
    OR (deterioration_kind IS NOT NULL AND deterioration_operator IS NOT NULL AND deterioration_value IS NOT NULL)),
  CONSTRAINT pi_recovery_rule_complete CHECK (
    (recovery_kind IS NULL AND recovery_operator IS NULL AND recovery_value IS NULL)
    OR (recovery_kind IS NOT NULL AND recovery_operator IS NOT NULL AND recovery_value IS NOT NULL)),
  CONSTRAINT pi_fixed_baseline_value CHECK (baseline_method IS DISTINCT FROM 'fixed_value' OR baseline_value IS NOT NULL)
);

REVOKE ALL ON public.tenant_value_profiles, public.profile_indicators FROM anon, authenticated;
GRANT SELECT, UPDATE, DELETE ON public.tenant_value_profiles TO authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.profile_indicators TO authenticated;
GRANT ALL ON public.tenant_value_profiles, public.profile_indicators TO service_role;

-- retire old per-subject tables
REVOKE ALL ON public.value_profiles, public.indicators FROM authenticated;
COMMENT ON TABLE public.value_profiles IS 'DEPRECATED: replaced by tenant_value_profiles (profile is per tenant, not per subject)';
COMMENT ON TABLE public.indicators IS 'DEPRECATED: replaced by profile_indicators';
DROP FUNCTION public.approve_value_profile(uuid);
DROP FUNCTION public.create_value_profile_version(uuid);

-- guards
CREATE FUNCTION public._cw_tvp_guard() RETURNS trigger LANGUAGE plpgsql SET search_path = public AS $$
DECLARE v_priv boolean := public._cw_is_privileged();
BEGIN
  IF TG_OP = 'INSERT' THEN
    IF NOT v_priv THEN RAISE EXCEPTION 'use create_value_profile_draft()' USING ERRCODE = '42501'; END IF;
    IF NEW.status <> 'draft' THEN RAISE EXCEPTION 'new value profiles must be drafts' USING ERRCODE = '42501'; END IF;
    RETURN NEW;
  END IF;
  IF TG_OP = 'DELETE' THEN
    IF NOT EXISTS (SELECT 1 FROM public.tenants t WHERE t.id = OLD.tenant_id) THEN RETURN OLD; END IF;
    IF OLD.status <> 'draft' THEN RAISE EXCEPTION 'approved or superseded value profiles cannot be deleted' USING ERRCODE = '42501'; END IF;
    RETURN OLD;
  END IF;
  IF NEW.version IS DISTINCT FROM OLD.version THEN
    RAISE EXCEPTION 'version is immutable' USING ERRCODE = '42501';
  END IF;
  IF OLD.status = 'draft' THEN
    IF NOT v_priv AND (NEW.status <> 'draft' OR NEW.approved_by IS DISTINCT FROM OLD.approved_by OR NEW.approved_at IS DISTINCT FROM OLD.approved_at) THEN
      RAISE EXCEPTION 'only approve_value_profile() can approve a value profile' USING ERRCODE = '42501';
    END IF;
    RETURN NEW;
  ELSIF OLD.status = 'approved' THEN
    IF v_priv AND NEW.status = 'superseded'
       AND NEW.promise IS NOT DISTINCT FROM OLD.promise AND NEW.expected_outcome IS NOT DISTINCT FROM OLD.expected_outcome
       AND NEW.notes IS NOT DISTINCT FROM OLD.notes
       AND NEW.approved_by IS NOT DISTINCT FROM OLD.approved_by AND NEW.approved_at IS NOT DISTINCT FROM OLD.approved_at THEN
      RETURN NEW;
    END IF;
    RAISE EXCEPTION 'approved value profile is immutable; create a new version' USING ERRCODE = '42501';
  END IF;
  RAISE EXCEPTION 'superseded value profile is immutable' USING ERRCODE = '42501';
END $$;

-- SECURITY DEFINER so it can row-lock the parent profile regardless of caller privileges.
-- FOR SHARE: concurrent draft edits allowed; conflicts with approval's FOR UPDATE, so an edit
-- either completes before approval reads indicators or waits and then sees status <> draft.
CREATE FUNCTION public._cw_profile_indicator_guard() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $$
DECLARE v_pid uuid; v_status public.profile_status;
BEGIN
  IF TG_OP = 'DELETE' THEN v_pid := OLD.profile_id; ELSE v_pid := NEW.profile_id; END IF;
  IF TG_OP = 'UPDATE' AND NEW.profile_id IS DISTINCT FROM OLD.profile_id THEN
    RAISE EXCEPTION 'indicator cannot move between value profiles' USING ERRCODE = '42501';
  END IF;
  SELECT p.status INTO v_status FROM public.tenant_value_profiles p WHERE p.id = v_pid FOR SHARE;
  IF NOT FOUND THEN
    IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
    RAISE EXCEPTION 'value profile not found' USING ERRCODE = '23503';
  END IF;
  IF v_status <> 'draft' THEN
    RAISE EXCEPTION 'indicators of an approved or superseded value profile are immutable; create a new version' USING ERRCODE = '42501';
  END IF;
  IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
  RETURN NEW;
END $$;

CREATE TRIGGER tvp_guard BEFORE INSERT OR UPDATE OR DELETE ON public.tenant_value_profiles FOR EACH ROW EXECUTE FUNCTION public._cw_tvp_guard();
CREATE TRIGGER tvp_lock BEFORE UPDATE ON public.tenant_value_profiles FOR EACH ROW EXECUTE FUNCTION public._cw_lock_columns();
CREATE TRIGGER tvp_touch BEFORE UPDATE ON public.tenant_value_profiles FOR EACH ROW EXECUTE FUNCTION public._cw_touch();
CREATE TRIGGER tvp_audit AFTER INSERT OR UPDATE OR DELETE ON public.tenant_value_profiles FOR EACH ROW EXECUTE FUNCTION public._cw_audit();
CREATE TRIGGER pi_guard BEFORE INSERT OR UPDATE OR DELETE ON public.profile_indicators FOR EACH ROW EXECUTE FUNCTION public._cw_profile_indicator_guard();
CREATE TRIGGER pi_lock BEFORE UPDATE ON public.profile_indicators FOR EACH ROW EXECUTE FUNCTION public._cw_lock_columns();
CREATE TRIGGER pi_touch BEFORE UPDATE ON public.profile_indicators FOR EACH ROW EXECUTE FUNCTION public._cw_touch();
CREATE TRIGGER pi_audit AFTER INSERT OR UPDATE OR DELETE ON public.profile_indicators FOR EACH ROW EXECUTE FUNCTION public._cw_audit();

-- audit whitelist gains classification / profile_id
CREATE OR REPLACE FUNCTION public._cw_audit() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $$
DECLARE r jsonb; o jsonb; v_tenant uuid; d jsonb := '{}'::jsonb; k text;
BEGIN
  IF TG_OP = 'DELETE' THEN r := to_jsonb(OLD); ELSE r := to_jsonb(NEW); END IF;
  IF TG_OP = 'UPDATE' THEN o := to_jsonb(OLD); END IF;
  IF TG_TABLE_NAME = 'tenants' THEN v_tenant := (r->>'id')::uuid; ELSE v_tenant := (r->>'tenant_id')::uuid; END IF;
  FOREACH k IN ARRAY ARRAY['user_id','role','status','version','key','classification','external_ref','idempotency_key','source',
                           'subject_id','profile_id','value_profile_id','batch_id','corrects_observation_id','subject_unit_type'] LOOP
    IF r ? k THEN
      d := d || jsonb_build_object(k, r->k);
      IF o IS NOT NULL AND (o->k) IS DISTINCT FROM (r->k) THEN
        d := d || jsonb_build_object('previous_' || k, o->k);
      END IF;
    END IF;
  END LOOP;
  INSERT INTO public.audit_log(tenant_id, actor_id, action, entity_type, entity_id, details)
  VALUES (v_tenant, auth.uid(), lower(TG_OP), TG_TABLE_NAME, (r->>'id')::uuid, d);
  RETURN NULL;
END $$;

-- RPCs. Lock order everywhere: tenants row (FOR UPDATE) -> profile row -> indicators.
CREATE FUNCTION public.create_value_profile_draft(_tenant_id uuid, _promise text, _expected_outcome text DEFAULT NULL)
RETURNS uuid LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $$
DECLARE v_id uuid; v_version int;
BEGIN
  IF auth.uid() IS NULL THEN RAISE EXCEPTION 'authentication required' USING ERRCODE = '28000'; END IF;
  IF NOT public.has_tenant_role(_tenant_id, ARRAY['admin','operator']::public.member_role[]) THEN
    RAISE EXCEPTION 'not authorized' USING ERRCODE = '42501';
  END IF;
  PERFORM 1 FROM public.tenants t WHERE t.id = _tenant_id FOR UPDATE;
  SELECT coalesce(max(version), 0) + 1 INTO v_version FROM public.tenant_value_profiles WHERE tenant_id = _tenant_id;
  INSERT INTO public.tenant_value_profiles(tenant_id, version, promise, expected_outcome, created_by)
  VALUES (_tenant_id, v_version, _promise, _expected_outcome, auth.uid()) RETURNING id INTO v_id;
  RETURN v_id;
END $$;

CREATE FUNCTION public.create_value_profile_version(_from_profile_id uuid)
RETURNS uuid LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $$
DECLARE src public.tenant_value_profiles; v_new uuid; v_version int;
BEGIN
  IF auth.uid() IS NULL THEN RAISE EXCEPTION 'authentication required' USING ERRCODE = '28000'; END IF;
  SELECT * INTO src FROM public.tenant_value_profiles WHERE id = _from_profile_id;
  IF NOT FOUND OR NOT public.has_tenant_role(src.tenant_id, ARRAY['admin','operator']::public.member_role[]) THEN
    RAISE EXCEPTION 'not authorized' USING ERRCODE = '42501';
  END IF;
  PERFORM 1 FROM public.tenants t WHERE t.id = src.tenant_id FOR UPDATE;
  SELECT * INTO src FROM public.tenant_value_profiles WHERE id = _from_profile_id FOR SHARE; -- blocks concurrent draft edits during copy
  SELECT coalesce(max(version), 0) + 1 INTO v_version FROM public.tenant_value_profiles WHERE tenant_id = src.tenant_id;
  INSERT INTO public.tenant_value_profiles(tenant_id, version, promise, expected_outcome, notes, created_by)
  VALUES (src.tenant_id, v_version, src.promise, src.expected_outcome, src.notes, auth.uid()) RETURNING id INTO v_new;
  INSERT INTO public.profile_indicators(tenant_id, profile_id, key, name, definition, classification, unit, direction,
    baseline_method, baseline_value, baseline_min_period_days, observation_window_days, comparison_window_days,
    min_coverage_pct, min_denominator, target_value,
    deterioration_kind, deterioration_operator, deterioration_value, deterioration_consecutive_windows,
    recovery_kind, recovery_operator, recovery_value, recovery_consecutive_windows)
  SELECT tenant_id, v_new, key, name, definition, classification, unit, direction,
    baseline_method, baseline_value, baseline_min_period_days, observation_window_days, comparison_window_days,
    min_coverage_pct, min_denominator, target_value,
    deterioration_kind, deterioration_operator, deterioration_value, deterioration_consecutive_windows,
    recovery_kind, recovery_operator, recovery_value, recovery_consecutive_windows
  FROM public.profile_indicators WHERE profile_id = src.id;
  RETURN v_new;
END $$;

-- Returns the list of problems that block approval (empty = approvable). Caller must be a member.
CREATE FUNCTION public.value_profile_approval_issues(_profile_id uuid)
RETURNS text[] LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = public AS $$
DECLARE p public.tenant_value_profiles; i public.profile_indicators; issues text[] := '{}';
BEGIN
  SELECT * INTO p FROM public.tenant_value_profiles WHERE id = _profile_id;
  IF NOT FOUND OR NOT public.is_tenant_member(p.tenant_id) THEN
    RAISE EXCEPTION 'not authorized' USING ERRCODE = '42501';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM public.profile_indicators x WHERE x.profile_id = p.id AND x.classification = 'outcome') THEN
    issues := issues || 'profile needs at least one outcome indicator';
  END IF;
  FOR i IN SELECT * FROM public.profile_indicators x WHERE x.profile_id = p.id AND x.classification = 'outcome' ORDER BY x.key LOOP
    IF i.baseline_method IS NULL THEN issues := issues || (i.key || ': baseline_method missing'); END IF;
    IF i.baseline_min_period_days IS NULL THEN issues := issues || (i.key || ': baseline_min_period_days missing'); END IF;
    IF i.observation_window_days IS NULL THEN issues := issues || (i.key || ': observation_window_days missing'); END IF;
    IF i.comparison_window_days IS NULL THEN issues := issues || (i.key || ': comparison_window_days missing'); END IF;
    IF i.min_coverage_pct IS NULL THEN issues := issues || (i.key || ': min_coverage_pct missing'); END IF;
    IF i.min_denominator IS NULL THEN issues := issues || (i.key || ': min_denominator missing'); END IF;
    IF i.deterioration_kind IS NULL OR i.deterioration_consecutive_windows IS NULL THEN issues := issues || (i.key || ': deterioration rule incomplete'); END IF;
    IF i.recovery_kind IS NULL OR i.recovery_consecutive_windows IS NULL THEN issues := issues || (i.key || ': recovery rule incomplete'); END IF;
  END LOOP;
  RETURN issues;
END $$;

CREATE FUNCTION public.approve_value_profile(_profile_id uuid)
RETURNS public.tenant_value_profiles LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $$
DECLARE v public.tenant_value_profiles; v_issues text[]; v_current int;
BEGIN
  IF auth.uid() IS NULL THEN RAISE EXCEPTION 'authentication required' USING ERRCODE = '28000'; END IF;
  SELECT * INTO v FROM public.tenant_value_profiles WHERE id = _profile_id;
  IF NOT FOUND OR NOT public.has_tenant_role(v.tenant_id, ARRAY['admin']::public.member_role[]) THEN
    RAISE EXCEPTION 'not authorized' USING ERRCODE = '42501';
  END IF;
  PERFORM 1 FROM public.tenants t WHERE t.id = v.tenant_id FOR UPDATE;
  SELECT * INTO v FROM public.tenant_value_profiles WHERE id = _profile_id FOR UPDATE; -- waits for in-flight indicator edits
  IF v.status <> 'draft' THEN RAISE EXCEPTION 'only draft value profiles can be approved' USING ERRCODE = '22023'; END IF;
  SELECT max(version) INTO v_current FROM public.tenant_value_profiles WHERE tenant_id = v.tenant_id AND status = 'approved';
  IF v_current IS NOT NULL AND v_current > v.version THEN
    RAISE EXCEPTION 'a newer version is already approved' USING ERRCODE = '22023';
  END IF;
  v_issues := public.value_profile_approval_issues(v.id);
  IF cardinality(v_issues) > 0 THEN
    RAISE EXCEPTION 'value profile is not approvable: %', array_to_string(v_issues, '; ') USING ERRCODE = '22023';
  END IF;
  UPDATE public.tenant_value_profiles SET status = 'superseded' WHERE tenant_id = v.tenant_id AND status = 'approved';
  UPDATE public.tenant_value_profiles SET status = 'approved', approved_by = auth.uid(), approved_at = now()
   WHERE id = v.id RETURNING * INTO v;
  RETURN v;
END $$;

-- Effective (approved) profile of a tenant; every subject of the tenant inherits it.
CREATE FUNCTION public.effective_value_profile(_tenant_id uuid)
RETURNS uuid LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public AS $$
  SELECT p.id FROM public.tenant_value_profiles p
   WHERE p.tenant_id = _tenant_id AND p.status = 'approved' AND public.is_tenant_member(_tenant_id)
$$;

REVOKE ALL ON FUNCTION public.create_value_profile_draft(uuid, text, text), public.create_value_profile_version(uuid),
  public.value_profile_approval_issues(uuid), public.approve_value_profile(uuid), public.effective_value_profile(uuid) FROM PUBLIC, anon;
GRANT EXECUTE ON FUNCTION public.create_value_profile_draft(uuid, text, text), public.create_value_profile_version(uuid),
  public.value_profile_approval_issues(uuid), public.approve_value_profile(uuid), public.effective_value_profile(uuid) TO authenticated, service_role;
REVOKE ALL ON FUNCTION public._cw_tvp_guard(), public._cw_profile_indicator_guard() FROM PUBLIC, anon, authenticated;

ALTER TABLE public.tenant_value_profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.profile_indicators ENABLE ROW LEVEL SECURITY;
CREATE POLICY tvp_select ON public.tenant_value_profiles FOR SELECT TO authenticated USING (public.is_tenant_member(tenant_id));
CREATE POLICY tvp_update ON public.tenant_value_profiles FOR UPDATE TO authenticated
  USING (public.has_tenant_role(tenant_id, '{admin,operator}'::public.member_role[]) AND status = 'draft')
  WITH CHECK (public.has_tenant_role(tenant_id, '{admin,operator}'::public.member_role[]) AND status = 'draft');
CREATE POLICY tvp_delete ON public.tenant_value_profiles FOR DELETE TO authenticated
  USING (public.has_tenant_role(tenant_id, '{admin,operator}'::public.member_role[]) AND status = 'draft');
CREATE POLICY pi_select ON public.profile_indicators FOR SELECT TO authenticated USING (public.is_tenant_member(tenant_id));
CREATE POLICY pi_insert ON public.profile_indicators FOR INSERT TO authenticated
  WITH CHECK (public.has_tenant_role(tenant_id, '{admin,operator}'::public.member_role[]));
CREATE POLICY pi_update ON public.profile_indicators FOR UPDATE TO authenticated
  USING (public.has_tenant_role(tenant_id, '{admin,operator}'::public.member_role[]))
  WITH CHECK (public.has_tenant_role(tenant_id, '{admin,operator}'::public.member_role[]));
CREATE POLICY pi_delete ON public.profile_indicators FOR DELETE TO authenticated
  USING (public.has_tenant_role(tenant_id, '{admin,operator}'::public.member_role[]));
