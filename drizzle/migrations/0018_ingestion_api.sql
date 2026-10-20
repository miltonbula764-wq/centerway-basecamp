-- Additive API v1. C01 validation/write core below is extracted from effective 0003 + 0004 without a second engine.
CREATE TABLE public.ingestion_credentials (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),tenant_id uuid NOT NULL REFERENCES public.tenants(id),
 name text NOT NULL CHECK(length(btrim(name)) BETWEEN 1 AND 200),source text NOT NULL CHECK(length(btrim(source)) BETWEEN 1 AND 200),
 secret_hash text NOT NULL CHECK(secret_hash ~ '^[0-9a-f]{64}$'),expires_at timestamptz NOT NULL CHECK(isfinite(expires_at)),
 revoked_at timestamptz,revoked_by uuid,rotated_from uuid,created_by uuid NOT NULL,created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 operation_id uuid NOT NULL,request_hash text NOT NULL,UNIQUE(tenant_id,id),UNIQUE(tenant_id,operation_id),
 bucket_at timestamptz,bucket_count integer NOT NULL DEFAULT 0,limit_logged boolean NOT NULL DEFAULT false,
 last_used_at timestamptz,last_status integer,
 FOREIGN KEY(tenant_id,rotated_from) REFERENCES public.ingestion_credentials(tenant_id,id)
);
CREATE INDEX ingestion_credentials_tenant_idx ON public.ingestion_credentials(tenant_id,id);
ALTER TABLE public.ingestion_batches ADD COLUMN integration_credential_id uuid;
ALTER TABLE public.observations ADD COLUMN integration_credential_id uuid;
ALTER TABLE public.ingestion_batches ADD CONSTRAINT batch_integration_fk FOREIGN KEY(tenant_id,integration_credential_id) REFERENCES public.ingestion_credentials(tenant_id,id);
ALTER TABLE public.observations ADD CONSTRAINT observation_integration_fk FOREIGN KEY(tenant_id,integration_credential_id) REFERENCES public.ingestion_credentials(tenant_id,id);
CREATE TABLE public.ingestion_api_requests (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),tenant_id uuid NOT NULL REFERENCES public.tenants(id),credential_id uuid NOT NULL,
 operation_id uuid NOT NULL,payload_hash text NOT NULL,batch_id uuid,http_status integer NOT NULL,result jsonb NOT NULL,
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),UNIQUE(tenant_id,operation_id),
 FOREIGN KEY(tenant_id,credential_id) REFERENCES public.ingestion_credentials(tenant_id,id),
 FOREIGN KEY(tenant_id,batch_id) REFERENCES public.ingestion_batches(tenant_id,id)
);
CREATE TABLE public.ingestion_api_events (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),tenant_id uuid NOT NULL REFERENCES public.tenants(id),credential_id uuid NOT NULL,
 operation_id uuid,batch_id uuid,http_status integer NOT NULL,code text NOT NULL,
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 FOREIGN KEY(tenant_id,credential_id) REFERENCES public.ingestion_credentials(tenant_id,id),
 FOREIGN KEY(tenant_id,batch_id) REFERENCES public.ingestion_batches(tenant_id,id)
);
CREATE INDEX ingestion_api_events_tenant_idx ON public.ingestion_api_events(tenant_id,created_at DESC,id DESC);
DO $$ DECLARE t text; BEGIN
 FOREACH t IN ARRAY ARRAY['ingestion_credentials','ingestion_api_requests','ingestion_api_events'] LOOP
  EXECUTE format('REVOKE ALL ON public.%I FROM PUBLIC,anon,authenticated,service_role',t);
  EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY',t);
  EXECUTE format('CREATE POLICY admin_read ON public.%I FOR SELECT TO authenticated USING(public.has_tenant_role(tenant_id,ARRAY[''admin'']::public.member_role[]))',t);
 END LOOP;
END $$;
GRANT SELECT(id,tenant_id,name,source,expires_at,revoked_at,revoked_by,rotated_from,created_by,created_at,last_used_at,last_status) ON public.ingestion_credentials TO authenticated;
GRANT SELECT ON public.ingestion_api_requests,public.ingestion_api_events TO authenticated;
CREATE TRIGGER immutable BEFORE UPDATE OR DELETE ON public.ingestion_api_requests FOR EACH ROW EXECUTE FUNCTION public._c02_immutable();
CREATE TRIGGER immutable BEFORE UPDATE OR DELETE ON public.ingestion_api_events FOR EACH ROW EXECUTE FUNCTION public._c02_immutable();

-- Existing audit entries are untouched. New C01 rows use immutable row provenance, never caller-supplied GUCs.
CREATE OR REPLACE FUNCTION public._cw_audit() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $$
DECLARE r jsonb; o jsonb; v_tenant uuid; d jsonb := '{}'::jsonb; k text; v_actor uuid:=auth.uid();
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
  IF TG_TABLE_NAME IN ('observations','ingestion_batches') THEN
    IF r->>'integration_credential_id' IS NOT NULL THEN
      v_actor:=NULL;d:=d||jsonb_build_object('actor_kind','integration','integration_credential_id',r->'integration_credential_id');
    ELSE d:=d||jsonb_build_object('actor_kind',CASE WHEN v_actor IS NULL THEN 'system_unknown' ELSE 'human' END); END IF;
  END IF;
  INSERT INTO public.audit_log(tenant_id, actor_id, action, entity_type, entity_id, details)
  VALUES (v_tenant, v_actor, lower(TG_OP), TG_TABLE_NAME, (r->>'id')::uuid, d);
  RETURN NULL;
END $$;


CREATE FUNCTION public._c01_import(
  _tenant_id uuid, _expected_profile_id uuid, _source text,
  _coverage_start timestamptz, _coverage_end timestamptz, _coverage_declared boolean,
  _file_name text, _rows jsonb, _integration_credential_id uuid)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $$
DECLARE
  v_uid uuid := CASE WHEN _integration_credential_id IS NULL THEN auth.uid() ELSE NULL END;
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
          IF v_subject IS NOT NULL AND v_ind.id IS NOT NULL THEN
            v_errs := v_errs || public._cw_correction_issues(_tenant_id, v_subject, v_ind.id, v_unit, v_src, v_obs, v_corr,
              v_valid @> jsonb_build_array(jsonb_build_object('corr', v_corr)));
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
        row_count, profile_id, profile_version, contract_snapshot, created_by, integration_credential_id)
      VALUES (_tenant_id, v_src, 'processing', _coverage_start, _coverage_end, true, _file_name,
        v_n, v_prof.id, v_prof.version, v_snapshot, v_uid, _integration_credential_id) RETURNING id INTO v_batch;
      FOR r IN SELECT value FROM jsonb_array_elements(v_valid) LOOP
        BEGIN
          v_new := NULL;
          INSERT INTO public.observations(tenant_id, batch_id, subject_id, indicator_key, value_numeric, value_text, unit, source,
            observed_at, idempotency_key, payload, corrects_observation_id, created_by, integration_credential_id)
          VALUES (_tenant_id, v_batch, (r ->> 'subject_id')::uuid, r ->> 'key', (r ->> 'num')::numeric, r ->> 'txt', r ->> 'unit', v_src,
            (r ->> 'observed_at')::timestamptz, r ->> 'idem',
            jsonb_build_object('profile_version', v_prof.version, 'contract', 'centerway_csv_v1'),
            (r ->> 'corr')::uuid, v_uid, _integration_credential_id)
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
      row_count, rejected_count, errors, profile_id, profile_version, contract_snapshot, created_by, integration_credential_id)
    VALUES (_tenant_id, v_src, 'failed', _coverage_start, _coverage_end, true, _file_name,
      v_n, v_rejected, v_errors, v_prof.id, v_prof.version, v_snapshot, v_uid, _integration_credential_id) RETURNING id INTO v_batch;
    v_status := 'failed';
  END IF;

  RETURN jsonb_build_object('batch_id', v_batch, 'status', v_status, 'row_count', v_n,
    'inserted', v_ins, 'duplicates', v_dup, 'rejected', v_rejected, 'errors', v_errors,
    'profile_version', v_prof.version);
END $$;


-- Fail closed if the installed engine has diverged. Only identity/provenance and
-- the two caller-specific authorization checks may differ; all validation stays exact.
DO $equivalence$
DECLARE installed text; extracted text;
BEGIN
 SELECT prosrc INTO installed FROM pg_proc WHERE oid='public.import_observations(uuid,uuid,text,timestamptz,timestamptz,boolean,text,jsonb)'::regprocedure;
 SELECT prosrc INTO extracted FROM pg_proc WHERE oid='public._c01_import(uuid,uuid,text,timestamptz,timestamptz,boolean,text,jsonb,uuid)'::regprocedure;
 installed:=replace(installed,$authorization$  IF v_uid IS NULL THEN RAISE EXCEPTION 'authentication required' USING ERRCODE = '28000'; END IF;
  IF NOT public.has_tenant_role(_tenant_id, ARRAY['admin','operator']::public.member_role[]) THEN
    RAISE EXCEPTION 'not authorized' USING ERRCODE = '42501';
  END IF;
$authorization$,'');
 extracted:=replace(extracted,'CASE WHEN _integration_credential_id IS NULL THEN auth.uid() ELSE NULL END','auth.uid()');
 extracted:=replace(extracted,'created_by, integration_credential_id','created_by');
 extracted:=replace(extracted,'v_uid, _integration_credential_id','v_uid');
 IF installed IS DISTINCT FROM extracted THEN RAISE EXCEPTION 'Installed C01 differs from extracted engine; review required before migration'; END IF;
END $equivalence$;

CREATE OR REPLACE FUNCTION public.import_observations(
 _tenant_id uuid,_expected_profile_id uuid,_source text,_coverage_start timestamptz,_coverage_end timestamptz,_coverage_declared boolean,_file_name text,_rows jsonb)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=public AS $$
BEGIN
 IF auth.uid() IS NULL THEN RAISE EXCEPTION 'authentication required' USING ERRCODE='28000'; END IF;
 PERFORM 1 FROM public.tenants WHERE id=_tenant_id FOR UPDATE;
 IF NOT public.has_tenant_role(_tenant_id,ARRAY['admin','operator']::public.member_role[]) THEN RAISE EXCEPTION 'not authorized' USING ERRCODE='42501'; END IF;
 RETURN public._c01_import(_tenant_id,_expected_profile_id,_source,_coverage_start,_coverage_end,_coverage_declared,_file_name,_rows,NULL);
END $$;
REVOKE ALL ON FUNCTION public._c01_import(uuid,uuid,text,timestamptz,timestamptz,boolean,text,jsonb,uuid) FROM PUBLIC,anon,authenticated,service_role;

CREATE FUNCTION public._ingestion_credential_guard() RETURNS trigger LANGUAGE plpgsql SET search_path=public AS $$
BEGIN
 IF TG_OP='DELETE' OR (to_jsonb(NEW)-ARRAY['revoked_at','revoked_by','bucket_at','bucket_count','limit_logged','last_used_at','last_status']) IS DISTINCT FROM
 (to_jsonb(OLD)-ARRAY['revoked_at','revoked_by','bucket_at','bucket_count','limit_logged','last_used_at','last_status'])
 OR (OLD.revoked_at IS NOT NULL AND (NEW.revoked_at IS DISTINCT FROM OLD.revoked_at OR NEW.revoked_by IS DISTINCT FROM OLD.revoked_by)) THEN
  RAISE EXCEPTION 'credential_identity_immutable' USING ERRCODE='42501'; END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER identity_guard BEFORE UPDATE OR DELETE ON public.ingestion_credentials FOR EACH ROW EXECUTE FUNCTION public._ingestion_credential_guard();
CREATE FUNCTION public._ingestion_credential_audit() RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER SET search_path=public AS $$
BEGIN
 INSERT INTO public.audit_log(tenant_id,actor_id,action,entity_type,entity_id,details) VALUES(NEW.tenant_id,auth.uid(),lower(TG_OP),'ingestion_credentials',NEW.id,
 jsonb_build_object('actor_kind','human','scope','c01_ingest','source',NEW.source,'revoked',NEW.revoked_at IS NOT NULL,'rotated_from',NEW.rotated_from));
 RETURN NULL;
END $$;
CREATE TRIGGER audit AFTER INSERT OR UPDATE OF revoked_at ON public.ingestion_credentials FOR EACH ROW EXECUTE FUNCTION public._ingestion_credential_audit();

CREATE FUNCTION public.create_ingestion_credential(_tenant_id uuid,_name text,_source text,_expires_at timestamptz,_operation_id uuid,_rotate_from uuid DEFAULT NULL)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=public,extensions,pg_temp AS $$
DECLARE c public.ingestion_credentials;old public.ingestion_credentials; h text; secret text; v_id uuid:=gen_random_uuid();
BEGIN
 PERFORM 1 FROM public.tenants WHERE id=_tenant_id FOR UPDATE;
 IF NOT public.has_tenant_role(_tenant_id,ARRAY['admin']::public.member_role[]) THEN RAISE EXCEPTION 'admin_required' USING ERRCODE='42501'; END IF;
 IF _operation_id IS NULL OR _name IS NULL OR length(btrim(_name)) NOT BETWEEN 1 AND 200 OR _source IS NULL OR length(btrim(_source)) NOT BETWEEN 1 AND 200 OR _expires_at IS NULL THEN RAISE EXCEPTION 'invalid_credential' USING ERRCODE='22023'; END IF;
 h:=encode(sha256(convert_to(jsonb_build_array(btrim(_name),btrim(_source),extract(epoch FROM _expires_at),_rotate_from)::text,'UTF8')),'hex');
 SELECT * INTO c FROM public.ingestion_credentials WHERE tenant_id=_tenant_id AND operation_id=_operation_id;
 IF FOUND THEN
  IF c.request_hash<>h THEN RAISE EXCEPTION 'idempotency_conflict' USING ERRCODE='22023'; END IF;
  RETURN jsonb_build_object('id',c.id,'secret',NULL);
 END IF;
 IF NOT isfinite(_expires_at) OR _expires_at<=clock_timestamp() OR _expires_at>clock_timestamp()+interval '365 days' THEN RAISE EXCEPTION 'credential_expiry_required' USING ERRCODE='22023'; END IF;
 IF _rotate_from IS NOT NULL THEN
  SELECT * INTO old FROM public.ingestion_credentials WHERE tenant_id=_tenant_id AND id=_rotate_from FOR UPDATE;
  IF NOT FOUND OR old.revoked_at IS NOT NULL OR old.source<>btrim(_source) THEN RAISE EXCEPTION 'rotation_requires_current_source' USING ERRCODE='22023'; END IF;
 END IF;
 secret:='cw_ingest_v1_'||v_id||'.'||encode(gen_random_bytes(32),'hex');
 INSERT INTO public.ingestion_credentials(id,tenant_id,name,source,secret_hash,expires_at,created_by,operation_id,request_hash,rotated_from)
 VALUES(v_id,_tenant_id,btrim(_name),btrim(_source),encode(sha256(convert_to(secret,'UTF8')),'hex'),_expires_at,auth.uid(),_operation_id,h,_rotate_from);
 IF _rotate_from IS NOT NULL THEN UPDATE public.ingestion_credentials SET revoked_at=clock_timestamp(),revoked_by=auth.uid() WHERE id=_rotate_from; END IF;
 RETURN jsonb_build_object('id',v_id,'secret',secret);
END $$;
CREATE FUNCTION public.revoke_ingestion_credential(_tenant_id uuid,_credential_id uuid) RETURNS void LANGUAGE plpgsql SECURITY DEFINER SET search_path=public AS $$
BEGIN
 PERFORM 1 FROM public.tenants WHERE id=_tenant_id FOR UPDATE;
 IF NOT public.has_tenant_role(_tenant_id,ARRAY['admin']::public.member_role[]) THEN RAISE EXCEPTION 'admin_required' USING ERRCODE='42501'; END IF;
 IF NOT EXISTS(SELECT FROM public.ingestion_credentials WHERE tenant_id=_tenant_id AND id=_credential_id) THEN RAISE EXCEPTION 'credential_not_found' USING ERRCODE='22023'; END IF;
 UPDATE public.ingestion_credentials SET revoked_at=clock_timestamp(),revoked_by=auth.uid() WHERE tenant_id=_tenant_id AND id=_credential_id AND revoked_at IS NULL;
END $$;

-- Narrow key-authenticated RPC, not a general database key. No impersonation or JWT/GUC rewriting.
CREATE FUNCTION public.ingest_external_observations(_credential text,_operation_id uuid,_payload jsonb)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=public AS $$
DECLARE c public.ingestion_credentials;cid uuid;now_at timestamptz;bucket timestamptz;r jsonb;cached public.ingestion_api_requests;
 code text;status integer;payload_hash text;profile uuid;start_at timestamptz;end_at timestamptz;row jsonb;batch uuid;
BEGIN
 IF _credential IS NULL OR _credential !~ '^cw_ingest_v1_[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\.[0-9a-f]{64}$' THEN
  RETURN jsonb_build_object('http_status',401,'body',jsonb_build_object('code','credential_invalid')); END IF;
 cid:=substr(split_part(_credential,'.',1),14)::uuid;
 SELECT * INTO c FROM public.ingestion_credentials WHERE id=cid AND secret_hash=encode(sha256(convert_to(_credential,'UTF8')),'hex');
 IF NOT FOUND THEN RETURN jsonb_build_object('http_status',401,'body',jsonb_build_object('code','credential_invalid')); END IF;
 PERFORM 1 FROM public.tenants WHERE id=c.tenant_id FOR UPDATE;
 SELECT * INTO c FROM public.ingestion_credentials WHERE id=cid FOR UPDATE;
 now_at:=clock_timestamp();bucket:=date_trunc('minute',now_at);
 IF c.bucket_at IS DISTINCT FROM bucket THEN
  UPDATE public.ingestion_credentials SET bucket_at=bucket,bucket_count=0,limit_logged=false WHERE id=cid;
  c.bucket_count:=0;c.limit_logged:=false;
 END IF;
 IF c.revoked_at IS NOT NULL OR c.expires_at<=now_at THEN
  IF NOT c.limit_logged THEN
   INSERT INTO public.ingestion_api_events(tenant_id,credential_id,operation_id,http_status,code) VALUES(c.tenant_id,cid,_operation_id,401,'credential_invalid');
   UPDATE public.ingestion_credentials SET limit_logged=true,last_status=401 WHERE id=cid;
  END IF;
  RETURN jsonb_build_object('http_status',401,'body',jsonb_build_object('code','credential_invalid'));
 END IF;
 IF c.bucket_count>=30 THEN
  IF NOT c.limit_logged THEN
   INSERT INTO public.ingestion_api_events(tenant_id,credential_id,operation_id,http_status,code) VALUES(c.tenant_id,cid,_operation_id,429,'rate_limited');
   UPDATE public.ingestion_credentials SET limit_logged=true,last_status=429 WHERE id=cid;
  END IF;
  RETURN jsonb_build_object('http_status',429,'body',jsonb_build_object('code','rate_limited','retry_after',greatest(1,ceil(extract(epoch FROM(bucket+interval '1 minute'-now_at)))::int)));
 END IF;
 UPDATE public.ingestion_credentials SET bucket_count=bucket_count+1,last_used_at=now_at WHERE id=cid;
 payload_hash:=encode(sha256(convert_to(coalesce(_payload,'null')::text,'UTF8')),'hex');
 SELECT * INTO cached FROM public.ingestion_api_requests WHERE tenant_id=c.tenant_id AND operation_id=_operation_id;
 IF FOUND THEN
  IF btrim(_payload->>'source') IS DISTINCT FROM c.source THEN status:=400;r:=jsonb_build_object('code','invalid_batch');code:='invalid_batch';
  ELSIF cached.payload_hash<>payload_hash THEN status:=409;r:=jsonb_build_object('code','request_idempotency_conflict');code:='request_idempotency_conflict';
  ELSE status:=cached.http_status;r:=cached.result;batch:=cached.batch_id;code:='replayed'; END IF;
 ELSE
  BEGIN
   IF _operation_id IS NULL OR _payload IS NULL OR jsonb_typeof(_payload)<>'object' THEN RAISE EXCEPTION 'invalid_api_payload' USING ERRCODE='22023'; END IF;
   IF octet_length(_payload::text)>2000000 THEN status:=413;RAISE EXCEPTION 'payload_too_large' USING ERRCODE='22023'; END IF;
   IF EXISTS(SELECT FROM jsonb_object_keys(_payload) k WHERE k NOT IN ('profile_id','source','coverage','rows'))
    OR jsonb_typeof(_payload->'profile_id') IS DISTINCT FROM 'string' OR jsonb_typeof(_payload->'source') IS DISTINCT FROM 'string'
    OR btrim(_payload->>'source') IS DISTINCT FROM c.source OR jsonb_typeof(_payload->'coverage') IS DISTINCT FROM 'object'
    OR EXISTS(SELECT FROM jsonb_object_keys(_payload->'coverage') k WHERE k NOT IN ('start','end','declared'))
    OR (_payload#>'{coverage,declared}') IS DISTINCT FROM 'true'::jsonb
    OR coalesce(_payload#>>'{coverage,start}','') !~ '^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2}(\.\d{1,6})?)?(Z|[+-]\d{2}:\d{2})$'
    OR coalesce(_payload#>>'{coverage,end}','') !~ '^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2}(\.\d{1,6})?)?(Z|[+-]\d{2}:\d{2})$'
    OR jsonb_typeof(_payload->'rows') IS DISTINCT FROM 'array' THEN RAISE EXCEPTION 'invalid_api_payload' USING ERRCODE='22023'; END IF;
   FOR row IN SELECT value FROM jsonb_array_elements(_payload->'rows') LOOP
    IF jsonb_typeof(row)='object' AND EXISTS(SELECT FROM jsonb_object_keys(row) k WHERE k NOT IN ('line','subject_external_ref','indicator_key','observed_at','value_numeric','value_text','unit','idempotency_key','corrects_observation_id')) THEN RAISE EXCEPTION 'invalid_api_payload' USING ERRCODE='22023'; END IF;
   END LOOP;
   profile:=(_payload->>'profile_id')::uuid;start_at:=(_payload#>>'{coverage,start}')::timestamptz;end_at:=(_payload#>>'{coverage,end}')::timestamptz;
   r:=public._c01_import(c.tenant_id,profile,c.source,start_at,end_at,true,'api-v1',_payload->'rows',cid);
   batch:=(r->>'batch_id')::uuid;
   status:=CASE WHEN r->>'status'='completed' THEN 200 WHEN r->'errors' @> '[{"errors":["idempotency_conflict"]}]'::jsonb THEN 409 ELSE 422 END;
   code:=CASE WHEN status=200 THEN 'completed' WHEN status=409 THEN 'observation_idempotency_conflict' ELSE 'validation_failed' END;
   r:=r||jsonb_build_object('code',code);
  EXCEPTION WHEN invalid_parameter_value OR invalid_text_representation OR datetime_field_overflow OR invalid_datetime_format OR numeric_value_out_of_range THEN
   status:=coalesce(status,400);code:=CASE WHEN status=413 THEN 'payload_too_large' ELSE 'invalid_batch' END;r:=jsonb_build_object('code',code);
  END;
  IF _operation_id IS NOT NULL THEN
   INSERT INTO public.ingestion_api_requests(tenant_id,credential_id,operation_id,payload_hash,batch_id,http_status,result) VALUES(c.tenant_id,cid,_operation_id,payload_hash,batch,status,r);
  END IF;
 END IF;
 INSERT INTO public.ingestion_api_events(tenant_id,credential_id,operation_id,batch_id,http_status,code) VALUES(c.tenant_id,cid,_operation_id,batch,status,code);
 UPDATE public.ingestion_credentials SET last_status=status WHERE id=cid;
 RETURN jsonb_build_object('http_status',status,'body',r);
END $$;
REVOKE ALL ON FUNCTION public._ingestion_credential_guard(),public._ingestion_credential_audit() FROM PUBLIC,anon,authenticated,service_role;
REVOKE ALL ON FUNCTION public.create_ingestion_credential(uuid,text,text,timestamptz,uuid,uuid),public.revoke_ingestion_credential(uuid,uuid),public.ingest_external_observations(text,uuid,jsonb) FROM PUBLIC,anon,authenticated,service_role;
GRANT EXECUTE ON FUNCTION public.create_ingestion_credential(uuid,text,text,timestamptz,uuid,uuid),public.revoke_ingestion_credential(uuid,uuid) TO authenticated;
GRANT EXECUTE ON FUNCTION public.ingest_external_observations(text,uuid,jsonb) TO anon,authenticated;
NOTIFY pgrst,'reload schema';
