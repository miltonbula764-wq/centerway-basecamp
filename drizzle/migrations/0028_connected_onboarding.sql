-- Connected onboarding: additive backend capability. No C01-C10 algorithm changes.
CREATE SCHEMA connected_private;
REVOKE ALL ON SCHEMA connected_private FROM PUBLIC,anon,authenticated,service_role;
CREATE ROLE centerway_connector_backend NOLOGIN NOINHERIT;
GRANT USAGE ON SCHEMA connected_private,public,auth TO centerway_connector_backend;
GRANT centerway_connector_backend TO postgres;

CREATE FUNCTION connected_private.actor_valid(_tenant uuid,_actor uuid,_membership uuid,_session uuid)
RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog,public,auth,pg_temp AS $$
 SELECT auth.uid()=_actor AND nullif(current_setting('request.jwt.claims',true),'')::jsonb->>'session_id'=_session::text
 AND EXISTS(SELECT FROM public.memberships WHERE id=_membership AND tenant_id=_tenant AND user_id=_actor AND role='admin')
 AND EXISTS(SELECT FROM auth.sessions s WHERE s.id=_session AND s.user_id=_actor
   AND ((to_jsonb(s)->>'not_after') IS NULL OR (to_jsonb(s)->>'not_after')::timestamptz>clock_timestamp()))
$$;
CREATE FUNCTION connected_private.actor(_tenant uuid) RETURNS jsonb
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path=pg_catalog,public,auth,pg_temp AS $$
DECLARE m public.memberships;s uuid;
BEGIN
 s:=nullif(nullif(current_setting('request.jwt.claims',true),'')::jsonb->>'session_id','')::uuid;
 SELECT * INTO m FROM public.memberships WHERE tenant_id=_tenant AND user_id=auth.uid() AND role='admin';
 IF NOT FOUND OR NOT connected_private.actor_valid(_tenant,m.user_id,m.id,s) THEN
  RAISE EXCEPTION 'connector_admin_session_required' USING ERRCODE='42501'; END IF;
 RETURN jsonb_build_object('actor_id',m.user_id,'membership_id',m.id,'session_id',s);
END $$;

CREATE TABLE connected_private.connections (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),tenant_id uuid NOT NULL REFERENCES public.tenants(id),
 actor_id uuid NOT NULL,membership_id uuid NOT NULL,session_id uuid NOT NULL,
 status text NOT NULL DEFAULT 'not_connected' CHECK(status IN ('not_connected','authorization_pending','connected','needs_mapping','insufficient_data','active','failed','revoked')),
 context jsonb NOT NULL DEFAULT '{}',region text CHECK(region IN ('us','eu')),project_id bigint,project_name text,
 issuer text,secret_cipher text,token_expires_at timestamptz,credential_id uuid,
 source text NOT NULL,preview jsonb NOT NULL DEFAULT '{}',selection jsonb NOT NULL DEFAULT '{}',
 profile_id uuid,revision int NOT NULL DEFAULT 1,watermarks jsonb NOT NULL DEFAULT '{}',
 next_run_at timestamptz NOT NULL DEFAULT now(),last_attempt_at timestamptz,last_success_at timestamptz,last_error text,
 consent_at timestamptz,revoked_at timestamptz,created_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE(tenant_id,id),FOREIGN KEY(tenant_id,profile_id) REFERENCES public.tenant_value_profiles(tenant_id,id),
 CHECK(secret_cipher IS NULL OR secret_cipher LIKE 'v1.%')
);
CREATE UNIQUE INDEX connected_one_live ON connected_private.connections(tenant_id) WHERE status<>'revoked';
CREATE INDEX connected_ready ON connected_private.connections(next_run_at,id) WHERE status='active';
CREATE TABLE connected_private.oauth_states (
 id uuid PRIMARY KEY,state_hash text NOT NULL UNIQUE,nonce_hash text NOT NULL,verifier_cipher text NOT NULL,
 tenant_id uuid NOT NULL,connection_id uuid NOT NULL,actor_id uuid NOT NULL,membership_id uuid NOT NULL,session_id uuid NOT NULL,
 region text NOT NULL,issuer text NOT NULL,expires_at timestamptz NOT NULL,consumed_at timestamptz,
 FOREIGN KEY(tenant_id,connection_id) REFERENCES connected_private.connections(tenant_id,id),
 CHECK(verifier_cipher LIKE 'v1.%')
);
CREATE INDEX connected_state_expiry ON connected_private.oauth_states(expires_at);
CREATE TABLE connected_private.batches (
 id uuid PRIMARY KEY,tenant_id uuid NOT NULL,connection_id uuid NOT NULL,actor_id uuid NOT NULL,membership_id uuid NOT NULL,session_id uuid NOT NULL,
 revision int NOT NULL,profile_id uuid NOT NULL,payload jsonb NOT NULL,payload_hash text NOT NULL,
 status text NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','completed','blocked')),
 due_at timestamptz NOT NULL DEFAULT now(),created_at timestamptz NOT NULL DEFAULT now(),
 FOREIGN KEY(tenant_id,connection_id) REFERENCES connected_private.connections(tenant_id,id),
 FOREIGN KEY(tenant_id,profile_id) REFERENCES public.tenant_value_profiles(tenant_id,id),
 UNIQUE(connection_id,payload_hash)
);
CREATE INDEX connected_pending ON connected_private.batches(connection_id,due_at) WHERE status='pending';
CREATE TABLE connected_private.measurements (
 tenant_id uuid NOT NULL,connection_id uuid NOT NULL,actor_id uuid NOT NULL,membership_id uuid NOT NULL,session_id uuid NOT NULL,
 revision int NOT NULL,external_ref text NOT NULL,indicator_key text NOT NULL,observed_at timestamptz NOT NULL,
 value_numeric numeric NOT NULL,observation_key text NOT NULL,batch_id uuid NOT NULL REFERENCES connected_private.batches(id),
 previous_key text,PRIMARY KEY(connection_id,revision,external_ref,indicator_key,observed_at),
 FOREIGN KEY(tenant_id,connection_id) REFERENCES connected_private.connections(tenant_id,id)
);
CREATE TABLE connected_private.attempts (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,tenant_id uuid NOT NULL,connection_id uuid NOT NULL,
 actor_id uuid NOT NULL,membership_id uuid NOT NULL,session_id uuid NOT NULL,
 kind text NOT NULL CHECK(kind IN ('oauth','discovery','sync','c01','revocation')),
 operation_id uuid,started_at timestamptz NOT NULL DEFAULT clock_timestamp(),finished_at timestamptz,
 status text NOT NULL,code text,http_status int,details jsonb NOT NULL DEFAULT '{}',
 FOREIGN KEY(tenant_id,connection_id) REFERENCES connected_private.connections(tenant_id,id)
);
CREATE INDEX connected_attempt_paging ON connected_private.attempts(connection_id,id DESC);
CREATE INDEX connected_quotas ON connected_private.attempts(connection_id,kind,started_at);
CREATE TABLE connected_private.revocations (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),tenant_id uuid NOT NULL,connection_id uuid NOT NULL,
 issuer text NOT NULL,secret_cipher text NOT NULL,created_at timestamptz NOT NULL DEFAULT now(),
 tries int NOT NULL DEFAULT 0,next_try_at timestamptz NOT NULL DEFAULT now(),last_error text
);
ALTER TABLE connected_private.revocations ENABLE ROW LEVEL SECURITY;
ALTER TABLE connected_private.revocations FORCE ROW LEVEL SECURITY;
CREATE POLICY server_revocation_queue ON connected_private.revocations TO centerway_connector_backend USING(true) WITH CHECK(true);

DO $$ DECLARE t text;BEGIN
 FOREACH t IN ARRAY ARRAY['connections','oauth_states','batches','measurements','attempts'] LOOP
  EXECUTE format('ALTER TABLE connected_private.%I ENABLE ROW LEVEL SECURITY',t);
  EXECUTE format('ALTER TABLE connected_private.%I FORCE ROW LEVEL SECURITY',t);
  EXECUTE format('CREATE POLICY owner_admin_session ON connected_private.%I TO centerway_connector_backend USING (connected_private.actor_valid(tenant_id,actor_id,membership_id,session_id)) WITH CHECK (connected_private.actor_valid(tenant_id,actor_id,membership_id,session_id))',t);
 END LOOP;
END $$;
REVOKE ALL ON ALL TABLES IN SCHEMA connected_private FROM PUBLIC,anon,authenticated,service_role;
REVOKE ALL ON ALL SEQUENCES IN SCHEMA connected_private FROM PUBLIC,anon,authenticated,service_role;
GRANT SELECT,INSERT,UPDATE,DELETE ON ALL TABLES IN SCHEMA connected_private TO centerway_connector_backend;
GRANT USAGE,SELECT ON ALL SEQUENCES IN SCHEMA connected_private TO centerway_connector_backend;

CREATE FUNCTION connected_private.tenant_unit(_tenant uuid) RETURNS text
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path=pg_catalog,public,pg_temp AS $$
BEGIN PERFORM connected_private.actor(_tenant); RETURN (SELECT subject_unit_type::text FROM public.tenants WHERE id=_tenant);END $$;
CREATE FUNCTION connected_private.approved_profile(_tenant uuid) RETURNS uuid
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path=pg_catalog,public,pg_temp AS $$
BEGIN PERFORM connected_private.actor(_tenant); RETURN (SELECT id FROM public.tenant_value_profiles WHERE tenant_id=_tenant AND status='approved');END $$;
CREATE FUNCTION connected_private.summary(_tenant uuid) RETURNS jsonb
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path=pg_catalog,public,connected_private,pg_temp AS $$
DECLARE a jsonb;c connected_private.connections;
BEGIN
 a:=connected_private.actor(_tenant);
 SELECT * INTO c FROM connected_private.connections WHERE tenant_id=_tenant ORDER BY created_at DESC LIMIT 1;
 IF NOT FOUND THEN RETURN jsonb_build_object('status','not_connected');END IF;
 IF c.status='revoked' THEN RETURN jsonb_build_object('status','revoked');END IF;
 IF c.actor_id<>auth.uid() OR c.membership_id::text<>a->>'membership_id' OR c.session_id::text<>a->>'session_id' THEN
  RETURN jsonb_build_object('status','revoked','needs_reauthorization',true,'project_name',c.project_name);END IF;
 RETURN jsonb_build_object('id',c.id,'status',c.status,'context',c.context,'region',c.region,
  'project_id',c.project_id,'project_name',c.project_name,'preview',c.preview-'remote_groups',
  'selection',c.selection,'profile_id',c.profile_id,'source',c.source,'revision',c.revision,
  'last_error',c.last_error,'last_success_at',c.last_success_at,'next_run_at',c.next_run_at,
  'watermarks',c.watermarks,
  'profile_issues',CASE WHEN c.profile_id IS NOT NULL THEN to_jsonb(public.value_profile_approval_issues(c.profile_id)) ELSE '[]' END,
  'pending_batches',(SELECT count(*) FROM connected_private.batches WHERE connection_id=c.id AND status='pending'),
  'recent_attempts',coalesce((SELECT jsonb_agg(x ORDER BY id DESC) FROM (SELECT id,kind,status,code,http_status,started_at,finished_at,details FROM connected_private.attempts WHERE connection_id=c.id ORDER BY id DESC LIMIT 20)x),'[]'));
END $$;

-- Bootstrap is separate from C01: existing authorized draft/approval operations,
-- followed by explicitly confirmed subjects. No measurements are inserted here.
CREATE FUNCTION connected_private.prepare_profile(_connection uuid,_selection jsonb) RETURNS uuid
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,public,connected_private,pg_temp AS $$
DECLARE c connected_private.connections;p uuid;i jsonb;g jsonb;known jsonb;
BEGIN
 SELECT * INTO c FROM connected_private.connections WHERE id=_connection;
 PERFORM connected_private.actor(c.tenant_id);
 PERFORM 1 FROM public.tenants WHERE id=c.tenant_id FOR UPDATE;
 SELECT * INTO c FROM connected_private.connections WHERE id=_connection FOR UPDATE;
 IF NOT connected_private.actor_valid(c.tenant_id,c.actor_id,c.membership_id,c.session_id) OR c.status NOT IN ('needs_mapping','insufficient_data','connected')
   OR c.preview->>'group_type' IS NULL OR _selection->>'confirmed' IS DISTINCT FROM 'true'
   OR coalesce(jsonb_array_length(_selection->'groups'),0) NOT BETWEEN 1 AND 200
   OR coalesce(jsonb_array_length(_selection->'metrics'),0) NOT BETWEEN 1 AND 5 THEN
  RAISE EXCEPTION 'confirmed_mapping_required' USING ERRCODE='22023'; END IF;
 IF c.profile_id IS NOT NULL THEN
  IF c.selection<>_selection THEN RAISE EXCEPTION 'mapping_already_prepared_disconnect_to_revise' USING ERRCODE='22023'; END IF;
  RETURN c.profile_id;
 END IF;
 FOR g IN SELECT value FROM jsonb_array_elements(_selection->'groups') LOOP
  SELECT value INTO known FROM jsonb_array_elements(c.preview->'groups') WHERE value->>'ref'=g->>'ref';
  IF known IS NULL OR length(btrim(g->>'name')) NOT BETWEEN 1 AND 300 THEN RAISE EXCEPTION 'unknown_group' USING ERRCODE='22023';END IF;
 END LOOP;
 IF _selection->>'existing_profile_id' IS NOT NULL THEN
  p:=(_selection->>'existing_profile_id')::uuid;
  IF NOT EXISTS(SELECT FROM public.tenant_value_profiles WHERE tenant_id=c.tenant_id AND id=p AND status='approved') THEN
   RAISE EXCEPTION 'approved_profile_required' USING ERRCODE='22023';END IF;
 ELSE
  p:=public.create_value_profile_draft(c.tenant_id,c.context->>'promise',c.context->>'promise');
 END IF;
 FOR i IN SELECT value FROM jsonb_array_elements(_selection->'metrics') LOOP
  SELECT value INTO known FROM jsonb_array_elements(c.preview->'metrics') WHERE value->>'event'=i->>'event';
  IF known IS NULL THEN RAISE EXCEPTION 'unobserved_metric' USING ERRCODE='22023';END IF;
  IF _selection->>'existing_profile_id' IS NULL THEN
   INSERT INTO public.profile_indicators(tenant_id,profile_id,key,name,definition,classification,unit,direction,
    aggregation,expected_cadence_days,denominator_mode,baseline_method,baseline_value,baseline_min_period_days,
    observation_window_days,comparison_window_days,min_coverage_pct,min_denominator,target_value,
    deterioration_kind,deterioration_operator,deterioration_value,deterioration_consecutive_windows,
    recovery_kind,recovery_operator,recovery_value,recovery_consecutive_windows)
   VALUES(c.tenant_id,p,i->>'key',i->>'name','Contagem diária UTC do evento '||(i->>'event')||' ligado ao grupo confirmado. Atividade não comprova resultado por si só.',
    (i->>'classification')::public.indicator_class,'events',(i->>'direction')::public.indicator_direction,
    'sum',1,'observation_count',(i->>'baseline_method')::public.baseline_method,(i->>'baseline_value')::numeric,(i->>'baseline_min_period_days')::int,
    (i->>'observation_window_days')::int,(i->>'comparison_window_days')::int,(i->>'min_coverage_pct')::numeric,(i->>'min_denominator')::int,(i->>'target_value')::numeric,
    (i->>'deterioration_kind')::public.rule_kind,(i->>'deterioration_operator')::public.rule_operator,(i->>'deterioration_value')::numeric,(i->>'deterioration_consecutive_windows')::int,
    (i->>'recovery_kind')::public.rule_kind,(i->>'recovery_operator')::public.rule_operator,(i->>'recovery_value')::numeric,(i->>'recovery_consecutive_windows')::int);
  ELSE
   IF NOT EXISTS(SELECT FROM public.profile_indicators WHERE tenant_id=c.tenant_id AND profile_id=p AND key=i->>'key'
      AND unit='events' AND value_type='numeric' AND aggregation='sum' AND expected_cadence_days=1) THEN
    RAISE EXCEPTION 'incompatible_indicator' USING ERRCODE='22023';END IF;
  END IF;
 END LOOP;
 UPDATE connected_private.connections SET profile_id=p,selection=_selection,status='needs_mapping' WHERE id=c.id;
 RETURN p;
END $$;

CREATE FUNCTION connected_private.activate(_connection uuid) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,public,connected_private,extensions,pg_temp AS $$
DECLARE c connected_private.connections;g jsonb;i jsonb;k jsonb;p public.tenant_value_profiles;
BEGIN
 SELECT * INTO c FROM connected_private.connections WHERE id=_connection;
 PERFORM connected_private.actor(c.tenant_id);
 PERFORM 1 FROM public.tenants WHERE id=c.tenant_id FOR UPDATE;
 SELECT * INTO c FROM connected_private.connections WHERE id=_connection FOR UPDATE;
 IF NOT connected_private.actor_valid(c.tenant_id,c.actor_id,c.membership_id,c.session_id) OR c.status='revoked' OR c.selection->>'confirmed' IS DISTINCT FROM 'true' THEN
  RAISE EXCEPTION 'confirmed_mapping_required' USING ERRCODE='42501';END IF;
 SELECT * INTO p FROM public.tenant_value_profiles WHERE tenant_id=c.tenant_id AND id=c.profile_id;
 IF p.status='draft' THEN PERFORM public.approve_value_profile(p.id);END IF;
 IF NOT EXISTS(SELECT FROM public.tenant_value_profiles WHERE tenant_id=c.tenant_id AND id=c.profile_id AND status='approved') THEN
  RAISE EXCEPTION 'approved_profile_required' USING ERRCODE='22023';END IF;
 FOR g IN SELECT value FROM jsonb_array_elements(c.selection->'groups') LOOP
  INSERT INTO public.subjects(tenant_id,external_ref,display_name,created_by)
   VALUES(c.tenant_id,g->>'ref',g->>'name',auth.uid()) ON CONFLICT(tenant_id,external_ref) DO NOTHING;
 END LOOP;
 IF c.credential_id IS NULL THEN
  k:=public.create_ingestion_credential(c.tenant_id,'PostHog · ligação autorizada',c.source,clock_timestamp()+interval '30 days',c.id);
  UPDATE connected_private.connections SET credential_id=(k->>'id')::uuid WHERE id=c.id;
 ELSE k:=jsonb_build_object('id',c.credential_id,'secret',NULL);END IF;
 RETURN k;
END $$;

CREATE FUNCTION connected_private.receipt(_connection uuid,_key text) RETURNS jsonb
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path=pg_catalog,public,connected_private,pg_temp AS $$
DECLARE c connected_private.connections;r public.observations;
BEGIN
 SELECT * INTO c FROM connected_private.connections WHERE id=_connection;
 IF NOT connected_private.actor_valid(c.tenant_id,c.actor_id,c.membership_id,c.session_id) THEN RAISE EXCEPTION 'admin_required' USING ERRCODE='42501';END IF;
 SELECT * INTO r FROM public.observations WHERE tenant_id=c.tenant_id AND source=c.source AND idempotency_key=_key;
 IF NOT FOUND THEN RETURN NULL;END IF;
 RETURN jsonb_build_object('id',r.id,'subject_id',r.subject_id,'indicator_key',r.indicator_key,'observed_at',r.observed_at);
END $$;

CREATE FUNCTION connected_private.disconnect(_tenant uuid) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,public,connected_private,pg_temp AS $$
DECLARE c connected_private.connections;
BEGIN
 PERFORM connected_private.actor(_tenant);
 PERFORM 1 FROM public.tenants WHERE id=_tenant FOR UPDATE;
 FOR c IN SELECT * FROM connected_private.connections WHERE tenant_id=_tenant AND status<>'revoked' FOR UPDATE LOOP
  IF c.secret_cipher IS NOT NULL THEN INSERT INTO connected_private.revocations(tenant_id,connection_id,issuer,secret_cipher) VALUES(c.tenant_id,c.id,c.issuer,c.secret_cipher);END IF;
  IF c.credential_id IS NOT NULL THEN PERFORM public.revoke_ingestion_credential(c.tenant_id,c.credential_id);END IF;
  UPDATE connected_private.connections SET status='revoked',revoked_at=clock_timestamp(),secret_cipher=NULL,preview='{}',selection='{}' WHERE id=c.id;
  UPDATE connected_private.batches SET status='blocked' WHERE connection_id=c.id AND status='pending';
 END LOOP;
END $$;

CREATE FUNCTION connected_private.invalidate_membership() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,public,connected_private,pg_temp AS $$
DECLARE c connected_private.connections;
BEGIN
 IF TG_OP='UPDATE' AND NEW.role='admin' AND NEW.id=OLD.id AND NEW.user_id=OLD.user_id AND NEW.tenant_id=OLD.tenant_id THEN RETURN NEW;END IF;
 FOR c IN SELECT * FROM connected_private.connections WHERE membership_id=OLD.id AND status<>'revoked' FOR UPDATE LOOP
  IF c.secret_cipher IS NOT NULL THEN INSERT INTO connected_private.revocations(tenant_id,connection_id,issuer,secret_cipher) VALUES(c.tenant_id,c.id,c.issuer,c.secret_cipher);END IF;
  -- Security invalidation of this connector's own key, never a general import path.
  UPDATE public.ingestion_credentials SET revoked_at=clock_timestamp() WHERE tenant_id=c.tenant_id AND id=c.credential_id AND revoked_at IS NULL;
  UPDATE connected_private.connections SET status='revoked',revoked_at=clock_timestamp(),secret_cipher=NULL,preview='{}',selection='{}' WHERE id=c.id;
  UPDATE connected_private.batches SET status='blocked' WHERE connection_id=c.id AND status='pending';
 END LOOP;
 IF TG_OP='DELETE' THEN RETURN OLD;ELSE RETURN NEW;END IF;
END $$;
CREATE TRIGGER connected_membership_invalidation AFTER UPDATE OR DELETE ON public.memberships FOR EACH ROW EXECUTE FUNCTION connected_private.invalidate_membership();

CREATE FUNCTION connected_private.worker_candidates() RETURNS SETOF jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,public,auth,connected_private,pg_temp AS $$
DECLARE c connected_private.connections;
BEGIN
 FOR c IN SELECT * FROM connected_private.connections WHERE status='active' AND next_run_at<=clock_timestamp() ORDER BY next_run_at,id LIMIT 20 LOOP
  IF NOT EXISTS(SELECT FROM public.memberships WHERE id=c.membership_id AND tenant_id=c.tenant_id AND user_id=c.actor_id AND role='admin')
    OR NOT EXISTS(SELECT FROM auth.sessions s WHERE id=c.session_id AND user_id=c.actor_id AND ((to_jsonb(s)->>'not_after') IS NULL OR (to_jsonb(s)->>'not_after')::timestamptz>clock_timestamp())) THEN
   IF c.secret_cipher IS NOT NULL THEN INSERT INTO connected_private.revocations(tenant_id,connection_id,issuer,secret_cipher) VALUES(c.tenant_id,c.id,c.issuer,c.secret_cipher);END IF;
   UPDATE public.ingestion_credentials SET revoked_at=clock_timestamp() WHERE id=c.credential_id AND tenant_id=c.tenant_id AND revoked_at IS NULL;
   UPDATE connected_private.connections SET status='revoked',revoked_at=clock_timestamp(),secret_cipher=NULL,preview='{}',selection='{}' WHERE id=c.id;
  ELSE RETURN NEXT jsonb_build_object('tenant',c.tenant_id,'sub',c.actor_id,'session_id',c.session_id);END IF;
 END LOOP;
END $$;
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA connected_private FROM PUBLIC,anon,authenticated,service_role;
GRANT EXECUTE ON FUNCTION connected_private.actor_valid(uuid,uuid,uuid,uuid),connected_private.actor(uuid),connected_private.summary(uuid),
 connected_private.prepare_profile(uuid,jsonb),connected_private.activate(uuid),connected_private.receipt(uuid,text),connected_private.disconnect(uuid),connected_private.worker_candidates() TO centerway_connector_backend;

GRANT EXECUTE ON FUNCTION connected_private.tenant_unit(uuid),connected_private.approved_profile(uuid) TO centerway_connector_backend;

CREATE FUNCTION connected_private.guard_history() RETURNS trigger
LANGUAGE plpgsql SET search_path=pg_catalog,pg_temp AS $$
BEGIN
 IF TG_OP='DELETE' OR TG_TABLE_NAME='attempts' THEN RAISE EXCEPTION 'connector_history_immutable' USING ERRCODE='42501';END IF;
 IF (to_jsonb(NEW)->'tenant_id') IS DISTINCT FROM (to_jsonb(OLD)->'tenant_id') OR
    (to_jsonb(NEW)->'connection_id') IS DISTINCT FROM (to_jsonb(OLD)->'connection_id') OR
    (to_jsonb(NEW)->'actor_id') IS DISTINCT FROM (to_jsonb(OLD)->'actor_id') OR
    (to_jsonb(NEW)->'membership_id') IS DISTINCT FROM (to_jsonb(OLD)->'membership_id') OR
    (to_jsonb(NEW)->'session_id') IS DISTINCT FROM (to_jsonb(OLD)->'session_id') THEN
  RAISE EXCEPTION 'connector_identity_immutable' USING ERRCODE='42501';END IF;
 IF TG_TABLE_NAME='batches' AND (to_jsonb(NEW)->'payload' IS DISTINCT FROM to_jsonb(OLD)->'payload' OR to_jsonb(NEW)->'payload_hash' IS DISTINCT FROM to_jsonb(OLD)->'payload_hash' OR to_jsonb(NEW)->'id' IS DISTINCT FROM to_jsonb(OLD)->'id') THEN
  RAISE EXCEPTION 'connector_request_immutable' USING ERRCODE='42501';END IF;
 RETURN NEW;
END $$;
DO $$ DECLARE t text;BEGIN FOREACH t IN ARRAY ARRAY['connections','oauth_states','batches','measurements','attempts'] LOOP
 EXECUTE format('CREATE TRIGGER connected_history_guard BEFORE UPDATE OR DELETE ON connected_private.%I FOR EACH ROW EXECUTE FUNCTION connected_private.guard_history()',t);
END LOOP;END $$;
REVOKE ALL ON FUNCTION connected_private.guard_history() FROM PUBLIC,anon,authenticated,service_role;
