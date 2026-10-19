-- Real authenticated/anon database roles. Caller owns the disposable DB; all probes rollback.
CREATE FUNCTION pg_temp.team_as(uid uuid,sql text) RETURNS text LANGUAGE plpgsql AS $$
DECLARE answer text;
BEGIN
 PERFORM set_config('request.jwt.claims',CASE WHEN uid IS NULL THEN '{"role":"anon"}' ELSE jsonb_build_object('role','authenticated','sub',uid,'email_verified',true)::text END,true);
 PERFORM set_config('role',CASE WHEN uid IS NULL THEN 'anon' ELSE 'authenticated' END,true);
 EXECUTE sql INTO answer; RESET ROLE; RETURN answer;
EXCEPTION WHEN OTHERS THEN RESET ROLE; RAISE;
END $$;
CREATE FUNCTION pg_temp.team_denied(uid uuid,sql text,state text DEFAULT '42501') RETURNS void LANGUAGE plpgsql AS $$
BEGIN
 BEGIN PERFORM pg_temp.team_as(uid,sql);
 EXCEPTION WHEN OTHERS THEN IF SQLSTATE=state THEN RETURN; END IF; RAISE; END;
 RAISE EXCEPTION 'unexpected success in rejected team operation';
END $$;
CREATE FUNCTION pg_temp.invite(actor uuid,t uuid,email text,role public.member_role DEFAULT 'operator',expires timestamptz DEFAULT clock_timestamp()+interval '1 hour',op uuid DEFAULT gen_random_uuid()) RETURNS jsonb LANGUAGE plpgsql AS $$
BEGIN RETURN pg_temp.team_as(actor,format('SELECT public.create_tenant_invitation(%L,%L,%L,%L,%L)',t,email,role,expires,op))::jsonb; END $$;
CREATE FUNCTION pg_temp.accept(uid uuid,token text,op uuid DEFAULT gen_random_uuid()) RETURNS jsonb LANGUAGE plpgsql AS $$
BEGIN RETURN pg_temp.team_as(uid,format('SELECT public.accept_tenant_invitation(%L,%L)',token,op))::jsonb; END $$;
CREATE FUNCTION pg_temp.core_fingerprint() RETURNS text LANGUAGE plpgsql AS $$
DECLARE r record; data jsonb:='{}'; value text;
BEGIN
 FOR r IN SELECT tablename FROM pg_tables WHERE schemaname='public' AND tablename NOT IN ('tenants','memberships','audit_log','tenant_invitations') ORDER BY tablename LOOP
  EXECUTE format('SELECT coalesce(jsonb_agg(to_jsonb(x) ORDER BY to_jsonb(x)::text),''[]'')::text FROM public.%I x',r.tablename) INTO value;
  data:=data||jsonb_build_object(r.tablename,value);
 END LOOP;
 RETURN encode(sha256(convert_to(data::text,'UTF8')),'hex');
END $$;
DO $test$
DECLARE f jsonb:=current_setting('cw.review_fixture')::jsonb;t uuid:=(f#>>'{team,tenant}')::uuid;other_t uuid:=(f#>>'{team,otherTenant}')::uuid;
 admin uuid:=(f#>>'{team,users,admin,id}')::uuid;candidate uuid:=(f#>>'{team,users,invitee,id}')::uuid;other_u uuid:=(f#>>'{team,users,other,id}')::uuid;
 viewer uuid:=(f#>>'{team,users,viewer,id}')::uuid;unverified uuid:=(f#>>'{team,users,unverified,id}')::uuid;second_admin uuid:=(f#>>'{team,users,secondAdmin,id}')::uuid;
 email text:=f#>>'{team,users,invitee,email}';v jsonb;replayed jsonb;r jsonb;item jsonb;before text;op uuid:=gen_random_uuid();expiry timestamptz:=clock_timestamp()+interval '1 hour';inv_id uuid;accepted_count int;
BEGIN
 before:=pg_temp.core_fingerprint();
 v:=pg_temp.invite(admin,t,'  '||upper(email)||'  ','operator',expiry,op);
 IF v->>'token' !~ '^[0-9a-f]{64}$' THEN RAISE EXCEPTION 'token entropy/format'; END IF;
 inv_id:=(v->>'id')::uuid;
 IF (SELECT token_hash FROM public.tenant_invitations WHERE id=inv_id)<>encode(sha256(convert_to(v->>'token','UTF8')),'hex') THEN RAISE EXCEPTION 'not stored as hash'; END IF;
 IF EXISTS(SELECT FROM public.tenant_invitations x WHERE to_jsonb(x)::text LIKE '%'||(v->>'token')||'%') OR EXISTS(SELECT FROM public.audit_log WHERE details::text LIKE '%'||(v->>'token')||'%') THEN RAISE EXCEPTION 'raw token leaked to persistence'; END IF;
 replayed:=pg_temp.invite(admin,t,email,'operator',expiry,op);
 IF replayed->>'id'<>v->>'id' OR replayed->>'token' IS NOT NULL THEN RAISE EXCEPTION 'create replay duplicated/retained token'; END IF;
 PERFORM pg_temp.team_denied(admin,format('SELECT public.create_tenant_invitation(%L,%L,''admin'',%L,%L)',t,email,expiry,op),'22023');
 PERFORM pg_temp.team_denied(viewer,format('SELECT public.create_tenant_invitation(%L,%L,''admin'',%L,%L)',t,email,expiry,gen_random_uuid()));
 PERFORM pg_temp.team_denied(other_u,format('SELECT public.create_tenant_invitation(%L,%L,''operator'',%L,%L)',t,email,expiry,gen_random_uuid()));
 PERFORM pg_temp.team_denied(NULL,format('SELECT public.inspect_tenant_invitation(%L)',v->>'token'));
 PERFORM pg_temp.team_denied(other_u,format('SELECT public.inspect_tenant_invitation(%L)',v->>'token'),'22023');
 PERFORM pg_temp.team_denied(other_u,format('SELECT public.accept_tenant_invitation(%L,%L)',v->>'token',gen_random_uuid()),'22023');
 PERFORM pg_temp.team_denied(admin,'SELECT token_hash FROM public.tenant_invitations');
 PERFORM pg_temp.team_denied(viewer,'SELECT token_hash FROM public.tenant_invitations');
 IF pg_temp.team_as(viewer,format('SELECT count(id) FROM public.tenant_invitations WHERE tenant_id=%L',t))::int<>0 THEN RAISE EXCEPTION 'viewer invitation email disclosure'; END IF;
 IF pg_temp.team_as(other_u,format('SELECT count(id) FROM public.tenant_invitations WHERE tenant_id=%L',t))::int<>0 THEN RAISE EXCEPTION 'cross tenant invitation disclosure'; END IF;
 PERFORM pg_temp.team_denied(admin,'UPDATE public.tenant_invitations SET email=email');
 PERFORM pg_temp.team_denied(admin,'DELETE FROM public.tenant_invitations');
 r:=pg_temp.team_as(candidate,format('SELECT public.inspect_tenant_invitation(%L)',v->>'token'))::jsonb;
 IF r->>'tenant_id'<>t::text OR r->>'role'<>'operator' THEN RAISE EXCEPTION 'preview identity/role wrong'; END IF;
 op:=gen_random_uuid();r:=pg_temp.accept(candidate,v->>'token',op);
 IF r->>'tenant_id'<>t::text OR r->>'role'<>'operator' THEN RAISE EXCEPTION 'accept identity/role wrong'; END IF;
 replayed:=pg_temp.accept(candidate,v->>'token',op);
 IF (SELECT count(*) FROM public.memberships WHERE tenant_id=t AND user_id=candidate)<>1 THEN RAISE EXCEPTION 'duplicate membership'; END IF;
 IF NOT EXISTS(SELECT FROM public.audit_log WHERE entity_type='tenant_invitations' AND entity_id=inv_id AND actor_id=candidate AND details->>'status'='accepted') THEN RAISE EXCEPTION 'accept audit absent'; END IF;
 PERFORM pg_temp.team_denied(candidate,format('SELECT public.accept_tenant_invitation(%L,%L)',v->>'token',gen_random_uuid()),'22023');
 PERFORM pg_temp.team_denied(candidate,format('SELECT public.set_member_role(%L,%L,''admin'')',t,candidate));
 PERFORM pg_temp.team_denied(candidate,format('SELECT public.open_operational_case(%L,%L,%L,''{}'')',t,gen_random_uuid(),gen_random_uuid()));
 PERFORM pg_temp.team_denied(viewer,format('INSERT INTO public.subjects(tenant_id,external_ref,created_by) VALUES(%L,''forbidden'',%L)',t,viewer));
 PERFORM pg_temp.team_denied(candidate,format('SELECT public.list_team_members(%L)',other_t));
 IF pg_temp.team_as(candidate,format('SELECT count(*) FROM public.list_team_members(%L) WHERE email IS NOT NULL',t))::int<>0 THEN RAISE EXCEPTION 'operator private email exposure'; END IF;
 IF pg_temp.team_as(admin,format('SELECT count(*) FROM public.list_team_members(%L) WHERE email IS NOT NULL',t))::int<3 THEN RAISE EXCEPTION 'admin cannot identify own members'; END IF;
 -- Existing role never overwritten by a new invite, including an invitation proposing admin.
 v:=pg_temp.invite(admin,t,email,'admin');r:=pg_temp.accept(candidate,v->>'token');
 IF r->>'role'<>'operator' THEN RAISE EXCEPTION 'invite escalated existing member'; END IF;
 PERFORM pg_temp.team_as(admin,format('SELECT public.set_member_role(%L,%L,''viewer'')',t,candidate));
 IF (SELECT role FROM public.memberships WHERE tenant_id=t AND user_id=candidate)<>'viewer' THEN RAISE EXCEPTION 'role update failed'; END IF;
 PERFORM pg_temp.team_denied(candidate,format('INSERT INTO public.subjects(tenant_id,external_ref,created_by) VALUES(%L,''forbidden'',%L)',t,candidate));
 v:=pg_temp.invite(admin,t,email);
 PERFORM pg_temp.team_as(admin,format('SELECT public.remove_tenant_member(%L,%L)',t,candidate));
 IF pg_temp.team_as(candidate,format('SELECT public.is_tenant_member(%L)',t))::boolean THEN RAISE EXCEPTION 'removed access retained'; END IF;
 PERFORM pg_temp.team_denied(candidate,format('SELECT public.list_team_members(%L)',t));
 PERFORM pg_temp.team_denied(candidate,format('SELECT public.accept_tenant_invitation(%L,%L)',v->>'token',gen_random_uuid()),'22023');
 -- Email confirmation is read from auth.users; forged verified metadata in claims is insufficient.
 UPDATE auth.users SET email_confirmed_at=NULL WHERE id=unverified;
 v:=pg_temp.invite(admin,t,f#>>'{team,users,unverified,email}');
 PERFORM pg_temp.team_denied(unverified,format('SELECT public.inspect_tenant_invitation(%L)',v->>'token'));
 PERFORM pg_temp.team_denied(unverified,format('SELECT public.accept_tenant_invitation(%L,%L)',v->>'token',gen_random_uuid()));
 v:=pg_temp.invite(admin,t,email);
 PERFORM pg_temp.team_as(admin,format('SELECT public.revoke_tenant_invitation(%L,%L)',t,v->>'id'));
 PERFORM pg_temp.team_as(admin,format('SELECT public.revoke_tenant_invitation(%L,%L)',t,v->>'id')); -- idempotent
 PERFORM pg_temp.team_denied(candidate,format('SELECT public.accept_tenant_invitation(%L,%L)',v->>'token',gen_random_uuid()),'22023');
 v:=pg_temp.invite(admin,t,email,'operator',clock_timestamp()+interval '1 second');
 PERFORM pg_sleep(1.1);
 PERFORM pg_temp.team_denied(candidate,format('SELECT public.accept_tenant_invitation(%L,%L)',v->>'token',gen_random_uuid()),'22023');
 IF pg_temp.team_as(admin,format('SELECT count(*) FROM public.list_tenant_invitations(%L) WHERE id=%L AND status=''expired''',t,v->>'id'))::int<>1 THEN RAISE EXCEPTION 'expiry list uses wrong clock'; END IF;
 PERFORM pg_temp.team_denied(admin,format('SELECT public.remove_tenant_member(%L,%L)',t,admin));
 PERFORM pg_temp.team_denied(admin,format('SELECT public.set_member_role(%L,%L,''operator'')',t,admin));
 -- Revoking an inviter's admin role permanently revokes its still-pending invitations.
 v:=pg_temp.invite(admin,t,email);
 PERFORM pg_temp.team_as(admin,format('SELECT public.add_tenant_member(%L,%L,''admin'')',t,second_admin));
 PERFORM pg_temp.team_as(second_admin,format('SELECT public.set_member_role(%L,%L,''operator'')',t,admin));
 IF (SELECT status FROM public.tenant_invitations WHERE id=(v->>'id')::uuid)<>'revoked' THEN RAISE EXCEPTION 'grantor revocation left live invitation'; END IF;
 PERFORM pg_temp.team_denied(candidate,format('SELECT public.accept_tenant_invitation(%L,%L)',v->>'token',gen_random_uuid()),'22023');
 PERFORM pg_temp.team_denied(admin,format('SELECT public.create_tenant_invitation(%L,%L,''operator'',%L,%L)',t,email,expiry,gen_random_uuid()));
 IF before<>pg_temp.core_fingerprint() THEN RAISE EXCEPTION 'team management modified C01-C10 data'; END IF;
 RAISE NOTICE 'Team SQL review passed: hash-only tokens, real roles/RLS, idempotency, verified email binding, expiry/revocation/reuse, private emails, role escalation, removal, last-admin and unchanged C01-C10.';
END $test$;
