-- Additive team invitations; existing membership contracts retained and authorization serialized.
CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE TABLE public.tenant_invitations (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), tenant_id uuid NOT NULL REFERENCES public.tenants(id),
 email text NOT NULL CHECK(email=lower(btrim(email)) AND length(email)<=254), role public.member_role NOT NULL,
 token_hash text NOT NULL UNIQUE CHECK(token_hash ~ '^[0-9a-f]{64}$'),
 operation_id uuid NOT NULL, request_hash text NOT NULL, UNIQUE(tenant_id,operation_id),
 expires_at timestamptz NOT NULL CHECK(isfinite(expires_at)),
 status text NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','accepted','revoked')),
 created_by uuid NOT NULL, created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 accepted_by uuid, accepted_at timestamptz, acceptance_operation_id uuid,
 revoked_by uuid, revoked_at timestamptz,
 CHECK((status='accepted')=(accepted_by IS NOT NULL AND accepted_at IS NOT NULL AND acceptance_operation_id IS NOT NULL)),
 CHECK((status='revoked')=(revoked_at IS NOT NULL))
);
CREATE INDEX tenant_invitations_page_idx ON public.tenant_invitations(tenant_id,id);
CREATE INDEX tenant_invitations_pending_email_idx ON public.tenant_invitations(tenant_id,email) WHERE status='pending';
REVOKE ALL ON public.tenant_invitations FROM PUBLIC,anon,authenticated;
-- Even administrators cannot fetch hashes through REST or SELECT *.
GRANT SELECT(id,tenant_id,email,role,expires_at,status,created_by,created_at,accepted_by,accepted_at,revoked_by,revoked_at) ON public.tenant_invitations TO authenticated;
ALTER TABLE public.tenant_invitations ENABLE ROW LEVEL SECURITY;
CREATE POLICY administrator_read ON public.tenant_invitations FOR SELECT TO authenticated
 USING(public.has_tenant_role(tenant_id,ARRAY['admin']::public.member_role[]));
CREATE FUNCTION public._team_invitation_guard() RETURNS trigger LANGUAGE plpgsql SET search_path=public AS $$
BEGIN
 IF TG_OP='DELETE' OR OLD.status<>'pending' OR NEW.status NOT IN ('accepted','revoked')
 OR (to_jsonb(OLD)-ARRAY['status','accepted_by','accepted_at','acceptance_operation_id','revoked_by','revoked_at'])
 IS DISTINCT FROM (to_jsonb(NEW)-ARRAY['status','accepted_by','accepted_at','acceptance_operation_id','revoked_by','revoked_at']) THEN
  RAISE EXCEPTION 'invitation_history_immutable' USING ERRCODE='42501'; END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER immutable_identity BEFORE UPDATE OR DELETE ON public.tenant_invitations FOR EACH ROW EXECUTE FUNCTION public._team_invitation_guard();
-- Existing allow-listed audit writer excludes email, token/hash and request payloads.
CREATE TRIGGER audit AFTER INSERT OR UPDATE ON public.tenant_invitations FOR EACH ROW EXECUTE FUNCTION public._cw_audit();

CREATE FUNCTION public._team_verified_email() RETURNS text LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path=public AS $$
DECLARE mail text;
BEGIN
 IF auth.uid() IS NULL THEN RAISE EXCEPTION 'authentication_required' USING ERRCODE='28000'; END IF;
 SELECT lower(btrim(u.email)) INTO mail FROM auth.users u WHERE u.id=auth.uid() AND u.email_confirmed_at IS NOT NULL
  AND u.email_confirmed_at<=clock_timestamp() AND u.deleted_at IS NULL AND (u.banned_until IS NULL OR u.banned_until<=clock_timestamp());
 IF mail IS NULL OR mail='' THEN RAISE EXCEPTION 'verified_email_required' USING ERRCODE='42501'; END IF;
 RETURN mail;
END $$;
CREATE FUNCTION public._team_token_hash(_token text) RETURNS text LANGUAGE plpgsql IMMUTABLE SET search_path=public AS $$
BEGIN
 IF _token IS NULL OR _token !~ '^[0-9a-f]{64}$' THEN RAISE EXCEPTION 'invitation_unavailable' USING ERRCODE='22023'; END IF;
 RETURN encode(sha256(convert_to(_token,'UTF8')),'hex');
END $$;

CREATE FUNCTION public.create_tenant_invitation(_tenant_id uuid,_email text,_role public.member_role,_expires_at timestamptz,_operation_id uuid)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=public,extensions,pg_temp AS $$
DECLARE mail text:=lower(btrim(_email)); h text; secret text; v public.tenant_invitations;
BEGIN
 PERFORM 1 FROM public.tenants WHERE id=_tenant_id FOR UPDATE;
 IF NOT public.has_tenant_role(_tenant_id,ARRAY['admin']::public.member_role[]) THEN RAISE EXCEPTION 'admin_required' USING ERRCODE='42501'; END IF;
 IF mail IS NULL OR length(mail)>254 OR mail !~ '^[^[:space:]@]+@[^[:space:]@]+\.[^[:space:]@]+$' OR _role IS NULL OR _operation_id IS NULL OR _expires_at IS NULL THEN
  RAISE EXCEPTION 'invalid_invitation' USING ERRCODE='22023'; END IF;
 h:=encode(sha256(convert_to(jsonb_build_array(mail,_role,extract(epoch FROM _expires_at))::text,'UTF8')),'hex');
 SELECT * INTO v FROM public.tenant_invitations WHERE tenant_id=_tenant_id AND operation_id=_operation_id;
 IF FOUND THEN
  IF v.request_hash<>h THEN RAISE EXCEPTION 'idempotency_conflict' USING ERRCODE='22023'; END IF;
  -- Tokens cannot be recovered from a hash. Replays return identity only, never rotate or duplicate.
  RETURN jsonb_build_object('id',v.id,'token',NULL,'status',v.status,'expires_at',v.expires_at);
 END IF;
 IF NOT isfinite(_expires_at) OR _expires_at<=clock_timestamp() OR _expires_at>clock_timestamp()+interval '30 days' THEN
  RAISE EXCEPTION 'invitation_expiry_required' USING ERRCODE='22023'; END IF;
 secret:=encode(gen_random_bytes(32),'hex');
 INSERT INTO public.tenant_invitations(tenant_id,email,role,token_hash,operation_id,request_hash,expires_at,created_by)
 VALUES(_tenant_id,mail,_role,public._team_token_hash(secret),_operation_id,h,_expires_at,auth.uid()) RETURNING * INTO v;
 RETURN jsonb_build_object('id',v.id,'token',secret,'status',v.status,'expires_at',v.expires_at);
END $$;
CREATE FUNCTION public.revoke_tenant_invitation(_tenant_id uuid,_invitation_id uuid) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path=public AS $$
DECLARE v public.tenant_invitations;
BEGIN
 PERFORM 1 FROM public.tenants WHERE id=_tenant_id FOR UPDATE;
 IF NOT public.has_tenant_role(_tenant_id,ARRAY['admin']::public.member_role[]) THEN RAISE EXCEPTION 'admin_required' USING ERRCODE='42501'; END IF;
 SELECT * INTO v FROM public.tenant_invitations WHERE tenant_id=_tenant_id AND id=_invitation_id FOR UPDATE;
 IF NOT FOUND THEN RAISE EXCEPTION 'invitation_unavailable' USING ERRCODE='22023'; END IF;
 IF v.status='revoked' THEN RETURN; END IF;
 IF v.status='accepted' THEN RAISE EXCEPTION 'invitation_already_accepted_remove_member' USING ERRCODE='22023'; END IF;
 UPDATE public.tenant_invitations SET status='revoked',revoked_by=auth.uid(),revoked_at=clock_timestamp() WHERE id=v.id;
END $$;
CREATE FUNCTION public.inspect_tenant_invitation(_token text) RETURNS jsonb
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path=public AS $$
DECLARE mail text:=public._team_verified_email(); v public.tenant_invitations;
BEGIN
 SELECT * INTO v FROM public.tenant_invitations WHERE token_hash=public._team_token_hash(_token) AND email=mail
  AND status='pending' AND expires_at>clock_timestamp();
 IF NOT FOUND OR NOT EXISTS(SELECT FROM public.memberships m WHERE m.tenant_id=v.tenant_id AND m.user_id=v.created_by AND m.role='admin') THEN
  RAISE EXCEPTION 'invitation_unavailable' USING ERRCODE='22023'; END IF;
 RETURN jsonb_build_object('id',v.id,'tenant_id',v.tenant_id,'tenant_name',(SELECT name FROM public.tenants WHERE id=v.tenant_id),
  'role',v.role,'expires_at',v.expires_at,'already_member',public.is_tenant_member(v.tenant_id));
END $$;
CREATE FUNCTION public.accept_tenant_invitation(_token text,_operation_id uuid) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=public AS $$
DECLARE mail text; h text:=public._team_token_hash(_token); tid uuid; v public.tenant_invitations; m public.memberships; was_member boolean;
BEGIN
 IF _operation_id IS NULL THEN RAISE EXCEPTION 'operation_id_required' USING ERRCODE='22023'; END IF;
 IF auth.uid() IS NULL THEN RAISE EXCEPTION 'authentication_required' USING ERRCODE='28000'; END IF;
 SELECT tenant_id INTO tid FROM public.tenant_invitations WHERE token_hash=h;
 IF tid IS NULL THEN RAISE EXCEPTION 'invitation_unavailable' USING ERRCODE='22023'; END IF;
 -- Same tenant lock as administrative RPCs: accept, revoke, role change and removal serialize.
 PERFORM 1 FROM public.tenants WHERE id=tid FOR UPDATE;
 SELECT * INTO v FROM public.tenant_invitations WHERE token_hash=h AND tenant_id=tid FOR UPDATE;
 PERFORM 1 FROM auth.users WHERE id=auth.uid() FOR SHARE;
 mail:=public._team_verified_email();
 IF v.email IS DISTINCT FROM mail THEN RAISE EXCEPTION 'invitation_unavailable' USING ERRCODE='22023'; END IF;
 SELECT * INTO m FROM public.memberships WHERE tenant_id=tid AND user_id=auth.uid();
 IF v.status='accepted' AND v.accepted_by=auth.uid() AND v.acceptance_operation_id=_operation_id AND m.id IS NOT NULL THEN
  RETURN jsonb_build_object('tenant_id',tid,'role',m.role,'already_member',true); END IF;
 IF v.status<>'pending' OR v.expires_at<=clock_timestamp() OR NOT EXISTS(SELECT FROM public.memberships
   WHERE tenant_id=tid AND user_id=v.created_by AND role='admin') THEN
  RAISE EXCEPTION 'invitation_unavailable' USING ERRCODE='22023'; END IF;
 was_member:=m.id IS NOT NULL;
 -- Accepting an invite never overwrites an existing member's role.
 IF m.id IS NULL THEN
  INSERT INTO public.memberships(tenant_id,user_id,role) VALUES(tid,auth.uid(),v.role) RETURNING * INTO m;
 END IF;
 UPDATE public.tenant_invitations SET status='accepted',accepted_by=auth.uid(),accepted_at=clock_timestamp(),acceptance_operation_id=_operation_id WHERE id=v.id;
 RETURN jsonb_build_object('tenant_id',tid,'role',m.role,'already_member',was_member);
END $$;

CREATE FUNCTION public.list_team_members(_tenant_id uuid,_after uuid DEFAULT NULL,_limit integer DEFAULT 50)
RETURNS TABLE(id uuid,tenant_id uuid,user_id uuid,role public.member_role,created_at timestamptz,email text)
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path=public AS $$
BEGIN
 IF NOT public.is_tenant_member(_tenant_id) THEN RAISE EXCEPTION 'tenant_membership_required' USING ERRCODE='42501'; END IF;
 IF _limit IS NULL OR _limit NOT BETWEEN 1 AND 101 THEN RAISE EXCEPTION 'invalid_page' USING ERRCODE='22023'; END IF;
 RETURN QUERY SELECT m.id,m.tenant_id,m.user_id,m.role,m.created_at,
  CASE WHEN public.has_tenant_role(_tenant_id,ARRAY['admin']::public.member_role[]) THEN u.email::text ELSE NULL END
  FROM public.memberships m JOIN auth.users u ON u.id=m.user_id WHERE m.tenant_id=_tenant_id AND (_after IS NULL OR m.id>_after) ORDER BY m.id LIMIT _limit;
END $$;
CREATE FUNCTION public.list_tenant_invitations(_tenant_id uuid,_after uuid DEFAULT NULL,_limit integer DEFAULT 50)
RETURNS TABLE(id uuid,tenant_id uuid,email text,role public.member_role,status text,expires_at timestamptz,created_at timestamptz,server_now timestamptz)
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path=public AS $$
DECLARE now_at timestamptz:=clock_timestamp();
BEGIN
 IF NOT public.has_tenant_role(_tenant_id,ARRAY['admin']::public.member_role[]) THEN RAISE EXCEPTION 'admin_required' USING ERRCODE='42501'; END IF;
 IF _limit IS NULL OR _limit NOT BETWEEN 1 AND 101 THEN RAISE EXCEPTION 'invalid_page' USING ERRCODE='22023'; END IF;
 RETURN QUERY SELECT v.id,v.tenant_id,v.email,v.role,CASE WHEN v.status='pending' AND v.expires_at<=now_at THEN 'expired' ELSE v.status END,
  v.expires_at,v.created_at,now_at FROM public.tenant_invitations v WHERE v.tenant_id=_tenant_id AND (_after IS NULL OR v.id>_after) ORDER BY v.id LIMIT _limit;
END $$;

-- Reuse existing RPCs, taking the lock BEFORE the final authorization check.
CREATE OR REPLACE FUNCTION public.add_tenant_member(_tenant_id uuid,_user_id uuid,_role public.member_role) RETURNS uuid
LANGUAGE plpgsql SECURITY DEFINER SET search_path=public AS $$
DECLARE v_id uuid;
BEGIN
 IF auth.uid() IS NULL THEN RAISE EXCEPTION 'authentication required' USING ERRCODE='28000'; END IF;
 PERFORM 1 FROM public.tenants WHERE id=_tenant_id FOR UPDATE;
 IF NOT public.has_tenant_role(_tenant_id,ARRAY['admin']::public.member_role[]) THEN RAISE EXCEPTION 'not authorized' USING ERRCODE='42501'; END IF;
 IF NOT EXISTS(SELECT FROM auth.users WHERE id=_user_id) THEN RAISE EXCEPTION 'user not found' USING ERRCODE='P0002'; END IF;
 IF EXISTS(SELECT FROM public.memberships WHERE tenant_id=_tenant_id AND user_id=_user_id) THEN RAISE EXCEPTION 'user is already a member; use set_member_role' USING ERRCODE='23505'; END IF;
 INSERT INTO public.memberships(tenant_id,user_id,role) VALUES(_tenant_id,_user_id,_role) RETURNING id INTO v_id;
 RETURN v_id;
END $$;
CREATE OR REPLACE FUNCTION public.set_member_role(_tenant_id uuid,_user_id uuid,_role public.member_role) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path=public AS $$
BEGIN
 IF auth.uid() IS NULL THEN RAISE EXCEPTION 'authentication required' USING ERRCODE='28000'; END IF;
 PERFORM 1 FROM public.tenants WHERE id=_tenant_id FOR UPDATE;
 IF NOT public.has_tenant_role(_tenant_id,ARRAY['admin']::public.member_role[]) THEN RAISE EXCEPTION 'not authorized' USING ERRCODE='42501'; END IF;
 IF _role IS NULL THEN RAISE EXCEPTION 'role_required' USING ERRCODE='22023'; END IF;
 IF NOT EXISTS(SELECT FROM public.memberships WHERE tenant_id=_tenant_id AND user_id=_user_id) THEN RAISE EXCEPTION 'membership not found' USING ERRCODE='P0002'; END IF;
 UPDATE public.memberships SET role=_role WHERE tenant_id=_tenant_id AND user_id=_user_id AND role<>_role;
END $$;
CREATE OR REPLACE FUNCTION public.remove_tenant_member(_tenant_id uuid,_user_id uuid) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path=public AS $$
BEGIN
 IF auth.uid() IS NULL THEN RAISE EXCEPTION 'authentication required' USING ERRCODE='28000'; END IF;
 PERFORM 1 FROM public.tenants WHERE id=_tenant_id FOR UPDATE;
 IF NOT(public.has_tenant_role(_tenant_id,ARRAY['admin']::public.member_role[]) OR (_user_id=auth.uid() AND public.is_tenant_member(_tenant_id))) THEN
  RAISE EXCEPTION 'not authorized' USING ERRCODE='42501'; END IF;
 DELETE FROM public.memberships WHERE tenant_id=_tenant_id AND user_id=_user_id;
 IF NOT FOUND THEN RAISE EXCEPTION 'membership not found' USING ERRCODE='P0002'; END IF;
END $$;
CREATE FUNCTION public._team_revoke_pending_access() RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER SET search_path=public AS $$
BEGIN
 IF TG_OP='DELETE' OR (OLD.role='admin' AND NEW.role<>'admin') THEN
  UPDATE public.tenant_invitations SET status='revoked',revoked_by=auth.uid(),revoked_at=clock_timestamp()
   WHERE tenant_id=OLD.tenant_id AND status='pending' AND (created_by=OLD.user_id
    OR (TG_OP='DELETE' AND email=(SELECT lower(btrim(u.email)) FROM auth.users u WHERE u.id=OLD.user_id)));
 END IF;
 IF TG_OP='DELETE' THEN RETURN OLD; END IF; RETURN NEW;
END $$;
CREATE TRIGGER revoke_pending_access AFTER UPDATE OF role OR DELETE ON public.memberships FOR EACH ROW EXECUTE FUNCTION public._team_revoke_pending_access();
REVOKE ALL ON FUNCTION public._team_invitation_guard(),public._team_verified_email(),public._team_token_hash(text),public._team_revoke_pending_access() FROM PUBLIC,anon,authenticated;
REVOKE ALL ON FUNCTION public.create_tenant_invitation(uuid,text,public.member_role,timestamptz,uuid),public.revoke_tenant_invitation(uuid,uuid),public.inspect_tenant_invitation(text),public.accept_tenant_invitation(text,uuid),public.list_team_members(uuid,uuid,integer),public.list_tenant_invitations(uuid,uuid,integer) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.create_tenant_invitation(uuid,text,public.member_role,timestamptz,uuid),public.revoke_tenant_invitation(uuid,uuid),public.inspect_tenant_invitation(text),public.accept_tenant_invitation(text,uuid),public.list_team_members(uuid,uuid,integer),public.list_tenant_invitations(uuid,uuid,integer) TO authenticated;
NOTIFY pgrst,'reload schema';
