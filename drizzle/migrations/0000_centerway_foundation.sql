-- ===== Types =====
CREATE TYPE public.member_role AS ENUM ('admin','operator','viewer');
CREATE TYPE public.subject_unit_type AS ENUM ('organization','person');
CREATE TYPE public.profile_status AS ENUM ('draft','approved','superseded');
CREATE TYPE public.batch_status AS ENUM ('received','processing','completed','failed');
CREATE TYPE public.indicator_direction AS ENUM ('higher_is_better','lower_is_better');

-- ===== Tables =====
CREATE TABLE public.tenants (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  name text NOT NULL CHECK (char_length(btrim(name)) BETWEEN 1 AND 200),
  subject_unit_type public.subject_unit_type NOT NULL,
  created_by uuid NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE public.memberships (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES public.tenants(id) ON DELETE CASCADE,
  user_id uuid NOT NULL,
  role public.member_role NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, user_id)
);
CREATE INDEX memberships_user_idx ON public.memberships(user_id);

CREATE TABLE public.subjects (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES public.tenants(id) ON DELETE CASCADE,
  external_ref text NOT NULL CHECK (char_length(btrim(external_ref)) BETWEEN 1 AND 200),
  display_name text CHECK (display_name IS NULL OR char_length(display_name) <= 300),
  created_by uuid,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, external_ref),
  UNIQUE (tenant_id, id)
);

CREATE TABLE public.value_profiles (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES public.tenants(id) ON DELETE CASCADE,
  subject_id uuid NOT NULL,
  version integer NOT NULL DEFAULT 1 CHECK (version > 0),
  status public.profile_status NOT NULL DEFAULT 'draft',
  expected_value text NOT NULL CHECK (char_length(btrim(expected_value)) BETWEEN 1 AND 4000),
  notes text CHECK (notes IS NULL OR char_length(notes) <= 4000),
  created_by uuid,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  approved_by uuid,
  approved_at timestamptz,
  UNIQUE (tenant_id, id),
  UNIQUE (subject_id, version),
  FOREIGN KEY (tenant_id, subject_id) REFERENCES public.subjects(tenant_id, id) ON DELETE CASCADE,
  CHECK ((status = 'draft' AND approved_by IS NULL AND approved_at IS NULL)
      OR (status <> 'draft' AND approved_by IS NOT NULL AND approved_at IS NOT NULL))
);
CREATE UNIQUE INDEX value_profiles_one_approved_per_subject ON public.value_profiles(subject_id) WHERE status = 'approved';
CREATE INDEX value_profiles_tenant_subject_idx ON public.value_profiles(tenant_id, subject_id);

CREATE TABLE public.indicators (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES public.tenants(id) ON DELETE CASCADE,
  value_profile_id uuid NOT NULL,
  key text NOT NULL CHECK (key ~ '^[a-z][a-z0-9_]{0,63}$'),
  name text NOT NULL CHECK (char_length(btrim(name)) BETWEEN 1 AND 200),
  definition text CHECK (definition IS NULL OR char_length(definition) <= 4000),
  unit text NOT NULL CHECK (char_length(btrim(unit)) BETWEEN 1 AND 50),
  direction public.indicator_direction NOT NULL,
  baseline numeric,
  target numeric,
  deterioration_threshold numeric,
  evaluation_window_days integer CHECK (evaluation_window_days IS NULL OR evaluation_window_days > 0),
  min_denominator integer CHECK (min_denominator IS NULL OR min_denominator > 0),
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (value_profile_id, key),
  UNIQUE (tenant_id, id),
  FOREIGN KEY (tenant_id, value_profile_id) REFERENCES public.value_profiles(tenant_id, id) ON DELETE CASCADE
);

CREATE TABLE public.ingestion_batches (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES public.tenants(id) ON DELETE CASCADE,
  source text NOT NULL CHECK (char_length(btrim(source)) BETWEEN 1 AND 200),
  status public.batch_status NOT NULL DEFAULT 'received',
  coverage_start timestamptz,
  coverage_end timestamptz,
  notes text CHECK (notes IS NULL OR char_length(notes) <= 4000),
  created_by uuid,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, id),
  CHECK (coverage_start IS NULL OR coverage_end IS NULL OR coverage_end >= coverage_start)
);

CREATE TABLE public.observations (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES public.tenants(id) ON DELETE CASCADE,
  batch_id uuid NOT NULL,
  subject_id uuid NOT NULL,
  indicator_key text NOT NULL CHECK (indicator_key ~ '^[a-z][a-z0-9_]{0,63}$'),
  value_numeric numeric,
  value_text text CHECK (value_text IS NULL OR char_length(value_text) <= 2000),
  unit text NOT NULL CHECK (char_length(btrim(unit)) BETWEEN 1 AND 50),
  source text NOT NULL CHECK (char_length(btrim(source)) BETWEEN 1 AND 200),
  observed_at timestamptz NOT NULL,
  ingested_at timestamptz NOT NULL DEFAULT now(),
  idempotency_key text NOT NULL CHECK (char_length(idempotency_key) BETWEEN 1 AND 300),
  payload_hash text NOT NULL DEFAULT '',
  payload jsonb NOT NULL DEFAULT '{}'::jsonb,
  corrects_observation_id uuid,
  created_by uuid,
  CHECK (value_numeric IS NOT NULL OR value_text IS NOT NULL),
  CHECK (corrects_observation_id IS NULL OR corrects_observation_id <> id),
  UNIQUE (tenant_id, idempotency_key),
  UNIQUE (tenant_id, id),
  FOREIGN KEY (tenant_id, batch_id) REFERENCES public.ingestion_batches(tenant_id, id),
  FOREIGN KEY (tenant_id, subject_id) REFERENCES public.subjects(tenant_id, id),
  FOREIGN KEY (tenant_id, corrects_observation_id) REFERENCES public.observations(tenant_id, id)
);
CREATE INDEX observations_series_idx ON public.observations(tenant_id, subject_id, indicator_key, observed_at);

CREATE TABLE public.audit_log (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  tenant_id uuid,
  actor_id uuid,
  action text NOT NULL,
  entity_type text NOT NULL,
  entity_id uuid,
  details jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX audit_log_tenant_time_idx ON public.audit_log(tenant_id, created_at DESC);

-- ===== Grants =====
REVOKE ALL ON public.tenants, public.memberships, public.subjects, public.value_profiles, public.indicators,
  public.ingestion_batches, public.observations, public.audit_log FROM anon, authenticated;
GRANT SELECT ON public.tenants, public.memberships, public.audit_log TO authenticated;
GRANT SELECT, INSERT, UPDATE ON public.subjects, public.ingestion_batches TO authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.value_profiles, public.indicators TO authenticated;
GRANT SELECT, INSERT ON public.observations TO authenticated;
GRANT ALL ON public.tenants, public.memberships, public.subjects, public.value_profiles, public.indicators,
  public.ingestion_batches, public.observations, public.audit_log TO service_role;

-- ===== Helper functions (caller-scoped, no third-party enumeration) =====
CREATE FUNCTION public.is_tenant_member(_tenant_id uuid) RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public AS $$
  SELECT EXISTS (SELECT 1 FROM public.memberships m WHERE m.tenant_id = _tenant_id AND m.user_id = auth.uid())
$$;

CREATE FUNCTION public.has_tenant_role(_tenant_id uuid, _roles public.member_role[]) RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public AS $$
  SELECT EXISTS (SELECT 1 FROM public.memberships m WHERE m.tenant_id = _tenant_id AND m.user_id = auth.uid() AND m.role = ANY(_roles))
$$;

CREATE FUNCTION public.my_tenant_role(_tenant_id uuid) RETURNS public.member_role
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public AS $$
  SELECT m.role FROM public.memberships m WHERE m.tenant_id = _tenant_id AND m.user_id = auth.uid()
$$;

-- invoker on purpose: true only when running inside a SECURITY DEFINER routine or as service
CREATE FUNCTION public._cw_is_privileged() RETURNS boolean
LANGUAGE sql STABLE SET search_path = public AS $$
  SELECT current_user NOT IN ('authenticated','anon')
$$;

-- ===== Trigger functions =====
CREATE FUNCTION public._cw_touch() RETURNS trigger LANGUAGE plpgsql SET search_path = public AS $$
BEGIN NEW.updated_at := now(); RETURN NEW; END $$;

CREATE FUNCTION public._cw_lock_columns() RETURNS trigger LANGUAGE plpgsql SET search_path = public AS $$
DECLARE n jsonb := to_jsonb(NEW); o jsonb := to_jsonb(OLD); k text;
BEGIN
  FOREACH k IN ARRAY ARRAY['id','tenant_id','created_by','created_at','subject_unit_type','user_id'] LOOP
    IF (n->k) IS DISTINCT FROM (o->k) THEN
      RAISE EXCEPTION 'column % is immutable', k USING ERRCODE = '42501';
    END IF;
  END LOOP;
  RETURN NEW;
END $$;

CREATE FUNCTION public._cw_set_creator() RETURNS trigger LANGUAGE plpgsql SET search_path = public AS $$
BEGIN
  IF NOT public._cw_is_privileged() THEN
    NEW := jsonb_populate_record(NEW, jsonb_build_object('created_by', auth.uid()));
  END IF;
  RETURN NEW;
END $$;

CREATE FUNCTION public._cw_membership_guard() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $$
BEGIN
  IF OLD.role = 'admin' AND (TG_OP = 'DELETE' OR NEW.role <> 'admin') THEN
    PERFORM 1 FROM public.tenants t WHERE t.id = OLD.tenant_id FOR UPDATE;
    IF FOUND AND NOT EXISTS (
      SELECT 1 FROM public.memberships m
      WHERE m.tenant_id = OLD.tenant_id AND m.role = 'admin' AND m.id <> OLD.id
    ) THEN
      RAISE EXCEPTION 'cannot remove or demote the last admin of a tenant' USING ERRCODE = '42501';
    END IF;
  END IF;
  IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
  RETURN NEW;
END $$;

CREATE FUNCTION public._cw_value_profile_guard() RETURNS trigger LANGUAGE plpgsql SET search_path = public AS $$
DECLARE v_priv boolean := public._cw_is_privileged();
BEGIN
  IF TG_OP = 'INSERT' THEN
    IF NOT v_priv THEN
      IF NEW.status <> 'draft' OR NEW.approved_by IS NOT NULL OR NEW.approved_at IS NOT NULL THEN
        RAISE EXCEPTION 'new value profiles must be drafts; approval requires approve_value_profile()' USING ERRCODE = '42501';
      END IF;
      NEW.created_by := auth.uid();
      SELECT coalesce(max(vp.version), 0) + 1 INTO NEW.version FROM public.value_profiles vp WHERE vp.subject_id = NEW.subject_id;
    END IF;
    RETURN NEW;
  END IF;

  IF TG_OP = 'DELETE' THEN
    IF NOT EXISTS (SELECT 1 FROM public.tenants t WHERE t.id = OLD.tenant_id) THEN RETURN OLD; END IF;
    IF OLD.status <> 'draft' THEN
      RAISE EXCEPTION 'approved or superseded value profiles cannot be deleted' USING ERRCODE = '42501';
    END IF;
    RETURN OLD;
  END IF;

  IF NEW.subject_id IS DISTINCT FROM OLD.subject_id OR NEW.version IS DISTINCT FROM OLD.version THEN
    RAISE EXCEPTION 'subject and version of a value profile are immutable' USING ERRCODE = '42501';
  END IF;

  IF OLD.status = 'draft' THEN
    IF NOT v_priv AND (NEW.status <> 'draft' OR NEW.approved_by IS DISTINCT FROM OLD.approved_by OR NEW.approved_at IS DISTINCT FROM OLD.approved_at) THEN
      RAISE EXCEPTION 'only approve_value_profile() can approve a value profile' USING ERRCODE = '42501';
    END IF;
    RETURN NEW;
  ELSIF OLD.status = 'approved' THEN
    IF v_priv AND NEW.status = 'superseded'
       AND NEW.expected_value IS NOT DISTINCT FROM OLD.expected_value
       AND NEW.notes IS NOT DISTINCT FROM OLD.notes
       AND NEW.approved_by IS NOT DISTINCT FROM OLD.approved_by
       AND NEW.approved_at IS NOT DISTINCT FROM OLD.approved_at THEN
      RETURN NEW;
    END IF;
    RAISE EXCEPTION 'approved value profile is immutable; create a new version' USING ERRCODE = '42501';
  ELSE
    RAISE EXCEPTION 'superseded value profile is immutable' USING ERRCODE = '42501';
  END IF;
END $$;

CREATE FUNCTION public._cw_indicator_guard() RETURNS trigger LANGUAGE plpgsql SET search_path = public AS $$
DECLARE v_pid uuid; v_status public.profile_status;
BEGIN
  IF TG_OP = 'DELETE' THEN v_pid := OLD.value_profile_id; ELSE v_pid := NEW.value_profile_id; END IF;
  IF TG_OP = 'UPDATE' AND NEW.value_profile_id IS DISTINCT FROM OLD.value_profile_id THEN
    RAISE EXCEPTION 'indicator cannot move between value profiles' USING ERRCODE = '42501';
  END IF;
  SELECT vp.status INTO v_status FROM public.value_profiles vp WHERE vp.id = v_pid;
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

CREATE FUNCTION public._cw_observation_ingest() RETURNS trigger LANGUAGE plpgsql SET search_path = public AS $$
DECLARE v_hash text; v_existing text;
BEGIN
  NEW.ingested_at := now();
  IF NOT public._cw_is_privileged() THEN NEW.created_by := auth.uid(); END IF;
  v_hash := encode(sha256(convert_to(jsonb_build_object(
    'subject_id', NEW.subject_id,
    'indicator_key', NEW.indicator_key,
    'value_numeric', trim_scale(NEW.value_numeric),
    'value_text', NEW.value_text,
    'unit', NEW.unit,
    'source', NEW.source,
    'observed_at', to_char(NEW.observed_at AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.US"Z"'),
    'payload', NEW.payload,
    'corrects', NEW.corrects_observation_id
  )::text, 'UTF8')), 'hex');
  NEW.payload_hash := v_hash;

  SELECT o.payload_hash INTO v_existing FROM public.observations o
   WHERE o.tenant_id = NEW.tenant_id AND o.idempotency_key = NEW.idempotency_key;
  IF FOUND THEN
    IF v_existing = v_hash THEN
      RETURN NULL; -- identical replay: no-op
    END IF;
    RAISE EXCEPTION 'idempotency conflict: key already used with different content' USING ERRCODE = '23505';
  END IF;

  IF NEW.corrects_observation_id IS NOT NULL THEN
    PERFORM 1 FROM public.observations o
     WHERE o.id = NEW.corrects_observation_id AND o.tenant_id = NEW.tenant_id
       AND o.subject_id = NEW.subject_id AND o.indicator_key = NEW.indicator_key;
    IF NOT FOUND THEN
      RAISE EXCEPTION 'a correction must reference an observation of the same tenant, subject and indicator' USING ERRCODE = '23503';
    END IF;
  END IF;
  RETURN NEW;
END $$;

CREATE FUNCTION public._cw_append_only() RETURNS trigger LANGUAGE plpgsql SET search_path = public AS $$
BEGIN
  IF TG_OP = 'DELETE' AND TG_TABLE_NAME = 'observations'
     AND NOT EXISTS (SELECT 1 FROM public.tenants t WHERE t.id = OLD.tenant_id) THEN
    RETURN OLD; -- tenant removal cascade
  END IF;
  RAISE EXCEPTION '% is append-only', TG_TABLE_NAME USING ERRCODE = '42501';
END $$;

CREATE FUNCTION public._cw_audit() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $$
DECLARE r jsonb; o jsonb; v_tenant uuid; d jsonb := '{}'::jsonb; k text;
BEGIN
  IF TG_OP = 'DELETE' THEN r := to_jsonb(OLD); ELSE r := to_jsonb(NEW); END IF;
  IF TG_OP = 'UPDATE' THEN o := to_jsonb(OLD); END IF;
  IF TG_TABLE_NAME = 'tenants' THEN v_tenant := (r->>'id')::uuid; ELSE v_tenant := (r->>'tenant_id')::uuid; END IF;
  FOREACH k IN ARRAY ARRAY['user_id','role','status','version','key','external_ref','idempotency_key','source',
                           'subject_id','value_profile_id','batch_id','corrects_observation_id','subject_unit_type'] LOOP
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

CREATE FUNCTION public._cw_audit_immutable() RETURNS trigger LANGUAGE plpgsql SET search_path = public AS $$
BEGIN RAISE EXCEPTION 'audit_log is immutable' USING ERRCODE = '42501'; END $$;

-- ===== Triggers =====
CREATE TRIGGER tenants_lock BEFORE UPDATE ON public.tenants FOR EACH ROW EXECUTE FUNCTION public._cw_lock_columns();
CREATE TRIGGER tenants_audit AFTER INSERT OR UPDATE OR DELETE ON public.tenants FOR EACH ROW EXECUTE FUNCTION public._cw_audit();

CREATE TRIGGER memberships_lock BEFORE UPDATE ON public.memberships FOR EACH ROW EXECUTE FUNCTION public._cw_lock_columns();
CREATE TRIGGER memberships_touch BEFORE UPDATE ON public.memberships FOR EACH ROW EXECUTE FUNCTION public._cw_touch();
CREATE TRIGGER memberships_guard BEFORE UPDATE OR DELETE ON public.memberships FOR EACH ROW EXECUTE FUNCTION public._cw_membership_guard();
CREATE TRIGGER memberships_audit AFTER INSERT OR UPDATE OR DELETE ON public.memberships FOR EACH ROW EXECUTE FUNCTION public._cw_audit();

CREATE TRIGGER subjects_creator BEFORE INSERT ON public.subjects FOR EACH ROW EXECUTE FUNCTION public._cw_set_creator();
CREATE TRIGGER subjects_lock BEFORE UPDATE ON public.subjects FOR EACH ROW EXECUTE FUNCTION public._cw_lock_columns();
CREATE TRIGGER subjects_touch BEFORE UPDATE ON public.subjects FOR EACH ROW EXECUTE FUNCTION public._cw_touch();
CREATE TRIGGER subjects_audit AFTER INSERT OR UPDATE OR DELETE ON public.subjects FOR EACH ROW EXECUTE FUNCTION public._cw_audit();

CREATE TRIGGER value_profiles_guard BEFORE INSERT OR UPDATE OR DELETE ON public.value_profiles FOR EACH ROW EXECUTE FUNCTION public._cw_value_profile_guard();
CREATE TRIGGER value_profiles_lock BEFORE UPDATE ON public.value_profiles FOR EACH ROW EXECUTE FUNCTION public._cw_lock_columns();
CREATE TRIGGER value_profiles_touch BEFORE UPDATE ON public.value_profiles FOR EACH ROW EXECUTE FUNCTION public._cw_touch();
CREATE TRIGGER value_profiles_audit AFTER INSERT OR UPDATE OR DELETE ON public.value_profiles FOR EACH ROW EXECUTE FUNCTION public._cw_audit();

CREATE TRIGGER indicators_guard BEFORE INSERT OR UPDATE OR DELETE ON public.indicators FOR EACH ROW EXECUTE FUNCTION public._cw_indicator_guard();
CREATE TRIGGER indicators_lock BEFORE UPDATE ON public.indicators FOR EACH ROW EXECUTE FUNCTION public._cw_lock_columns();
CREATE TRIGGER indicators_touch BEFORE UPDATE ON public.indicators FOR EACH ROW EXECUTE FUNCTION public._cw_touch();
CREATE TRIGGER indicators_audit AFTER INSERT OR UPDATE OR DELETE ON public.indicators FOR EACH ROW EXECUTE FUNCTION public._cw_audit();

CREATE TRIGGER batches_creator BEFORE INSERT ON public.ingestion_batches FOR EACH ROW EXECUTE FUNCTION public._cw_set_creator();
CREATE TRIGGER batches_lock BEFORE UPDATE ON public.ingestion_batches FOR EACH ROW EXECUTE FUNCTION public._cw_lock_columns();
CREATE TRIGGER batches_touch BEFORE UPDATE ON public.ingestion_batches FOR EACH ROW EXECUTE FUNCTION public._cw_touch();
CREATE TRIGGER batches_audit AFTER INSERT OR UPDATE OR DELETE ON public.ingestion_batches FOR EACH ROW EXECUTE FUNCTION public._cw_audit();

CREATE TRIGGER observations_ingest BEFORE INSERT ON public.observations FOR EACH ROW EXECUTE FUNCTION public._cw_observation_ingest();
CREATE TRIGGER observations_append_only BEFORE UPDATE OR DELETE ON public.observations FOR EACH ROW EXECUTE FUNCTION public._cw_append_only();
CREATE TRIGGER observations_audit AFTER INSERT ON public.observations FOR EACH ROW EXECUTE FUNCTION public._cw_audit();

CREATE TRIGGER audit_log_immutable BEFORE UPDATE OR DELETE ON public.audit_log FOR EACH ROW EXECUTE FUNCTION public._cw_audit_immutable();
CREATE TRIGGER audit_log_no_truncate BEFORE TRUNCATE ON public.audit_log FOR EACH STATEMENT EXECUTE FUNCTION public._cw_audit_immutable();

-- ===== RPCs =====
CREATE FUNCTION public.create_tenant(_name text, _subject_unit_type public.subject_unit_type) RETURNS uuid
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $$
DECLARE v_uid uuid := auth.uid(); v_id uuid;
BEGIN
  IF v_uid IS NULL THEN RAISE EXCEPTION 'authentication required' USING ERRCODE = '28000'; END IF;
  INSERT INTO public.tenants(name, subject_unit_type, created_by) VALUES (btrim(_name), _subject_unit_type, v_uid) RETURNING id INTO v_id;
  INSERT INTO public.memberships(tenant_id, user_id, role) VALUES (v_id, v_uid, 'admin');
  RETURN v_id;
END $$;

CREATE FUNCTION public.add_tenant_member(_tenant_id uuid, _user_id uuid, _role public.member_role) RETURNS uuid
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $$
DECLARE v_id uuid;
BEGIN
  IF auth.uid() IS NULL THEN RAISE EXCEPTION 'authentication required' USING ERRCODE = '28000'; END IF;
  IF NOT public.has_tenant_role(_tenant_id, ARRAY['admin']::public.member_role[]) THEN
    RAISE EXCEPTION 'not authorized' USING ERRCODE = '42501';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM auth.users u WHERE u.id = _user_id) THEN
    RAISE EXCEPTION 'user not found' USING ERRCODE = 'P0002';
  END IF;
  IF EXISTS (SELECT 1 FROM public.memberships m WHERE m.tenant_id = _tenant_id AND m.user_id = _user_id) THEN
    RAISE EXCEPTION 'user is already a member; use set_member_role' USING ERRCODE = '23505';
  END IF;
  INSERT INTO public.memberships(tenant_id, user_id, role) VALUES (_tenant_id, _user_id, _role) RETURNING id INTO v_id;
  RETURN v_id;
END $$;

CREATE FUNCTION public.set_member_role(_tenant_id uuid, _user_id uuid, _role public.member_role) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $$
BEGIN
  IF auth.uid() IS NULL THEN RAISE EXCEPTION 'authentication required' USING ERRCODE = '28000'; END IF;
  IF NOT public.has_tenant_role(_tenant_id, ARRAY['admin']::public.member_role[]) THEN
    RAISE EXCEPTION 'not authorized' USING ERRCODE = '42501';
  END IF;
  PERFORM 1 FROM public.tenants t WHERE t.id = _tenant_id FOR UPDATE;
  UPDATE public.memberships SET role = _role WHERE tenant_id = _tenant_id AND user_id = _user_id;
  IF NOT FOUND THEN RAISE EXCEPTION 'membership not found' USING ERRCODE = 'P0002'; END IF;
END $$;

CREATE FUNCTION public.remove_tenant_member(_tenant_id uuid, _user_id uuid) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $$
BEGIN
  IF auth.uid() IS NULL THEN RAISE EXCEPTION 'authentication required' USING ERRCODE = '28000'; END IF;
  IF NOT (public.has_tenant_role(_tenant_id, ARRAY['admin']::public.member_role[])
          OR (_user_id = auth.uid() AND public.is_tenant_member(_tenant_id))) THEN
    RAISE EXCEPTION 'not authorized' USING ERRCODE = '42501';
  END IF;
  PERFORM 1 FROM public.tenants t WHERE t.id = _tenant_id FOR UPDATE;
  DELETE FROM public.memberships WHERE tenant_id = _tenant_id AND user_id = _user_id;
  IF NOT FOUND THEN RAISE EXCEPTION 'membership not found' USING ERRCODE = 'P0002'; END IF;
END $$;

CREATE FUNCTION public.approve_value_profile(_profile_id uuid) RETURNS public.value_profiles
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $$
DECLARE v public.value_profiles;
BEGIN
  IF auth.uid() IS NULL THEN RAISE EXCEPTION 'authentication required' USING ERRCODE = '28000'; END IF;
  SELECT * INTO v FROM public.value_profiles WHERE id = _profile_id FOR UPDATE;
  IF NOT FOUND OR NOT public.has_tenant_role(v.tenant_id, ARRAY['admin']::public.member_role[]) THEN
    RAISE EXCEPTION 'not authorized' USING ERRCODE = '42501';
  END IF;
  IF v.status <> 'draft' THEN RAISE EXCEPTION 'only draft value profiles can be approved' USING ERRCODE = '22023'; END IF;
  IF NOT EXISTS (SELECT 1 FROM public.indicators i WHERE i.value_profile_id = v.id) THEN
    RAISE EXCEPTION 'a value profile needs at least one indicator before approval' USING ERRCODE = '22023';
  END IF;
  PERFORM 1 FROM public.subjects s WHERE s.id = v.subject_id FOR UPDATE;
  UPDATE public.value_profiles SET status = 'superseded' WHERE subject_id = v.subject_id AND status = 'approved';
  UPDATE public.value_profiles SET status = 'approved', approved_by = auth.uid(), approved_at = now()
   WHERE id = v.id RETURNING * INTO v;
  RETURN v;
END $$;

CREATE FUNCTION public.create_value_profile_version(_from_profile_id uuid) RETURNS uuid
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $$
DECLARE src public.value_profiles; v_new uuid; v_version int;
BEGIN
  IF auth.uid() IS NULL THEN RAISE EXCEPTION 'authentication required' USING ERRCODE = '28000'; END IF;
  SELECT * INTO src FROM public.value_profiles WHERE id = _from_profile_id;
  IF NOT FOUND OR NOT public.has_tenant_role(src.tenant_id, ARRAY['admin','operator']::public.member_role[]) THEN
    RAISE EXCEPTION 'not authorized' USING ERRCODE = '42501';
  END IF;
  PERFORM 1 FROM public.subjects s WHERE s.id = src.subject_id FOR UPDATE;
  SELECT coalesce(max(version), 0) + 1 INTO v_version FROM public.value_profiles WHERE subject_id = src.subject_id;
  INSERT INTO public.value_profiles(tenant_id, subject_id, version, status, expected_value, notes, created_by)
  VALUES (src.tenant_id, src.subject_id, v_version, 'draft', src.expected_value, src.notes, auth.uid())
  RETURNING id INTO v_new;
  INSERT INTO public.indicators(tenant_id, value_profile_id, key, name, definition, unit, direction, baseline, target,
                                deterioration_threshold, evaluation_window_days, min_denominator)
  SELECT tenant_id, v_new, key, name, definition, unit, direction, baseline, target,
         deterioration_threshold, evaluation_window_days, min_denominator
    FROM public.indicators WHERE value_profile_id = src.id;
  RETURN v_new;
END $$;

-- ===== Function grants =====
REVOKE ALL ON FUNCTION public.is_tenant_member(uuid), public.has_tenant_role(uuid, public.member_role[]),
  public.my_tenant_role(uuid), public._cw_is_privileged(),
  public.create_tenant(text, public.subject_unit_type), public.add_tenant_member(uuid, uuid, public.member_role),
  public.set_member_role(uuid, uuid, public.member_role), public.remove_tenant_member(uuid, uuid),
  public.approve_value_profile(uuid), public.create_value_profile_version(uuid) FROM PUBLIC, anon;
GRANT EXECUTE ON FUNCTION public.is_tenant_member(uuid), public.has_tenant_role(uuid, public.member_role[]),
  public.my_tenant_role(uuid), public._cw_is_privileged(),
  public.create_tenant(text, public.subject_unit_type), public.add_tenant_member(uuid, uuid, public.member_role),
  public.set_member_role(uuid, uuid, public.member_role), public.remove_tenant_member(uuid, uuid),
  public.approve_value_profile(uuid), public.create_value_profile_version(uuid) TO authenticated, service_role;
REVOKE ALL ON FUNCTION public._cw_touch(), public._cw_lock_columns(), public._cw_set_creator(), public._cw_membership_guard(),
  public._cw_value_profile_guard(), public._cw_indicator_guard(), public._cw_observation_ingest(), public._cw_append_only(),
  public._cw_audit(), public._cw_audit_immutable() FROM PUBLIC, anon, authenticated;

-- ===== RLS =====
ALTER TABLE public.tenants ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.memberships ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.subjects ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.value_profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.indicators ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.ingestion_batches ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.observations ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.audit_log ENABLE ROW LEVEL SECURITY;

CREATE POLICY tenants_select ON public.tenants FOR SELECT TO authenticated USING (public.is_tenant_member(id));
CREATE POLICY memberships_select ON public.memberships FOR SELECT TO authenticated USING (public.is_tenant_member(tenant_id));

CREATE POLICY subjects_select ON public.subjects FOR SELECT TO authenticated USING (public.is_tenant_member(tenant_id));
CREATE POLICY subjects_insert ON public.subjects FOR INSERT TO authenticated
  WITH CHECK (public.has_tenant_role(tenant_id, '{admin,operator}'::public.member_role[]));
CREATE POLICY subjects_update ON public.subjects FOR UPDATE TO authenticated
  USING (public.has_tenant_role(tenant_id, '{admin,operator}'::public.member_role[]))
  WITH CHECK (public.has_tenant_role(tenant_id, '{admin,operator}'::public.member_role[]));

CREATE POLICY value_profiles_select ON public.value_profiles FOR SELECT TO authenticated USING (public.is_tenant_member(tenant_id));
CREATE POLICY value_profiles_insert ON public.value_profiles FOR INSERT TO authenticated
  WITH CHECK (public.has_tenant_role(tenant_id, '{admin,operator}'::public.member_role[]) AND status = 'draft');
CREATE POLICY value_profiles_update ON public.value_profiles FOR UPDATE TO authenticated
  USING (public.has_tenant_role(tenant_id, '{admin,operator}'::public.member_role[]) AND status = 'draft')
  WITH CHECK (public.has_tenant_role(tenant_id, '{admin,operator}'::public.member_role[]) AND status = 'draft');
CREATE POLICY value_profiles_delete ON public.value_profiles FOR DELETE TO authenticated
  USING (public.has_tenant_role(tenant_id, '{admin,operator}'::public.member_role[]) AND status = 'draft');

CREATE POLICY indicators_select ON public.indicators FOR SELECT TO authenticated USING (public.is_tenant_member(tenant_id));
CREATE POLICY indicators_insert ON public.indicators FOR INSERT TO authenticated
  WITH CHECK (public.has_tenant_role(tenant_id, '{admin,operator}'::public.member_role[]));
CREATE POLICY indicators_update ON public.indicators FOR UPDATE TO authenticated
  USING (public.has_tenant_role(tenant_id, '{admin,operator}'::public.member_role[]))
  WITH CHECK (public.has_tenant_role(tenant_id, '{admin,operator}'::public.member_role[]));
CREATE POLICY indicators_delete ON public.indicators FOR DELETE TO authenticated
  USING (public.has_tenant_role(tenant_id, '{admin,operator}'::public.member_role[]));

CREATE POLICY batches_select ON public.ingestion_batches FOR SELECT TO authenticated USING (public.is_tenant_member(tenant_id));
CREATE POLICY batches_insert ON public.ingestion_batches FOR INSERT TO authenticated
  WITH CHECK (public.has_tenant_role(tenant_id, '{admin,operator}'::public.member_role[]));
CREATE POLICY batches_update ON public.ingestion_batches FOR UPDATE TO authenticated
  USING (public.has_tenant_role(tenant_id, '{admin,operator}'::public.member_role[]))
  WITH CHECK (public.has_tenant_role(tenant_id, '{admin,operator}'::public.member_role[]));

CREATE POLICY observations_select ON public.observations FOR SELECT TO authenticated USING (public.is_tenant_member(tenant_id));
CREATE POLICY observations_insert ON public.observations FOR INSERT TO authenticated
  WITH CHECK (public.has_tenant_role(tenant_id, '{admin,operator}'::public.member_role[]));

CREATE POLICY audit_log_select ON public.audit_log FOR SELECT TO authenticated USING (public.is_tenant_member(tenant_id));
