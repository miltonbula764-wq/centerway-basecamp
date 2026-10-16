-- Restore the reviewed C01-C03 client ACL contract, including PUBLIC inheritance.
-- Explicit object list: does not touch auth/storage/extensions, platform roles,
-- schema privileges, default ACLs, policies, data, functions' bodies or history.
-- Run this entire file in ONE transaction (migration runner or psql --single-transaction).
-- Reapplicable. Keep _cw_is_privileged executable: invoker triggers call it as authenticated.

-- Defaults are deliberately not changed: they belong to the shared platform creator
-- roles and affect unrelated future objects. Every future migration must declare ACLs.
-- Unexpected inherited roles must be investigated, not revoked globally here.
DO $guard$
BEGIN
  IF EXISTS (
    SELECT 1 FROM pg_attribute a JOIN pg_class c ON c.oid=a.attrelid
    WHERE c.relnamespace='public'::regnamespace AND a.attnum>0 AND a.attacl IS NOT NULL
      AND c.relname IN ('tenants','memberships','subjects','value_profiles','indicators',
        'tenant_value_profiles','profile_indicators','ingestion_batches','observations',
        'audit_log','c02_runs','c02_results','c03_bundles','c03_indicators','c03_refs','c03_attempts')
  ) THEN
    RAISE EXCEPTION 'Unexpected column ACLs: review before applying 0011';
  END IF;
  IF EXISTS (
    SELECT 1 FROM pg_auth_members m
    WHERE m.member IN ('anon'::regrole, 'authenticated'::regrole)
  ) THEN
    RAISE EXCEPTION 'Unexpected client role memberships: review inherited privileges before applying 0011';
  END IF;
END
$guard$;


REVOKE ALL PRIVILEGES ON TABLE
  public.tenants, public.memberships, public.subjects,
  public.value_profiles, public.indicators, public.tenant_value_profiles,
  public.profile_indicators, public.ingestion_batches, public.observations,
  public.audit_log, public.c02_runs, public.c02_results,
  public.c03_bundles, public.c03_indicators, public.c03_refs, public.c03_attempts
FROM PUBLIC, anon, authenticated;

GRANT SELECT ON TABLE
  public.tenants, public.memberships, public.audit_log,
  public.ingestion_batches, public.observations, public.c02_runs, public.c02_results,
  public.c03_bundles, public.c03_indicators, public.c03_refs, public.c03_attempts
TO authenticated;
GRANT SELECT, INSERT, UPDATE ON public.subjects TO authenticated;
GRANT SELECT, UPDATE, DELETE ON public.tenant_value_profiles TO authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.profile_indicators TO authenticated;
-- Legacy per-subject profiles intentionally receive no client grants.

-- Both sequences are used by owner-executed RPCs/audit triggers, not the browser.
REVOKE ALL PRIVILEGES ON SEQUENCE public.audit_log_id_seq, public.c03_refs_id_seq
FROM PUBLIC, anon, authenticated;

REVOKE ALL PRIVILEGES ON FUNCTION public._c02_cmp(numeric,public.rule_operator,numeric) FROM PUBLIC, anon, authenticated;
REVOKE ALL PRIVILEGES ON FUNCTION public._c02_effective(uuid,uuid,text,text,uuid[],timestamp with time zone) FROM PUBLIC, anon, authenticated;
REVOKE ALL PRIVILEGES ON FUNCTION public._c02_fingerprint(public.profile_indicators) FROM PUBLIC, anon, authenticated;
REVOKE ALL PRIVILEGES ON FUNCTION public._c02_immutable() FROM PUBLIC, anon, authenticated;
REVOKE ALL PRIVILEGES ON FUNCTION public._c02_window(uuid,uuid,text,text,uuid[],public.c02_aggregation,integer,public.c02_denominator_mode,text,text,uuid[],numeric,integer,timestamp with time zone,timestamp with time zone,timestamp with time zone) FROM PUBLIC, anon, authenticated;
REVOKE ALL PRIVILEGES ON FUNCTION public._c02v2_effective(uuid,uuid,text,text,uuid[],timestamp with time zone) FROM PUBLIC, anon, authenticated;
REVOKE ALL PRIVILEGES ON FUNCTION public._c02v2_window(uuid,uuid,text,text,uuid[],public.c02_aggregation,integer,public.c02_denominator_mode,text,text,uuid[],integer,numeric,numeric,integer,timestamp with time zone,timestamp with time zone,timestamp with time zone) FROM PUBLIC, anon, authenticated;
REVOKE ALL PRIVILEGES ON FUNCTION public._c03_assemble(public.c02_runs,uuid,text,integer,uuid) FROM PUBLIC, anon, authenticated;
REVOKE ALL PRIVILEGES ON FUNCTION public._c03_build(uuid,uuid,integer) FROM PUBLIC, anon, authenticated;
REVOKE ALL PRIVILEGES ON FUNCTION public._c03_payload_hash(public.observations) FROM PUBLIC, anon, authenticated;
REVOKE ALL PRIVILEGES ON FUNCTION public._c03_reject(text) FROM PUBLIC, anon, authenticated;
REVOKE ALL PRIVILEGES ON FUNCTION public._cw_append_only() FROM PUBLIC, anon, authenticated;
REVOKE ALL PRIVILEGES ON FUNCTION public._cw_audit_immutable() FROM PUBLIC, anon, authenticated;
REVOKE ALL PRIVILEGES ON FUNCTION public._cw_audit() FROM PUBLIC, anon, authenticated;
REVOKE ALL PRIVILEGES ON FUNCTION public._cw_correction_issues(uuid,uuid,uuid,text,text,timestamp with time zone,uuid,boolean) FROM PUBLIC, anon, authenticated;
REVOKE ALL PRIVILEGES ON FUNCTION public._cw_indicator_guard() FROM PUBLIC, anon, authenticated;
REVOKE ALL PRIVILEGES ON FUNCTION public._cw_is_privileged() FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public._cw_is_privileged() TO authenticated;
REVOKE ALL PRIVILEGES ON FUNCTION public._cw_lock_columns() FROM PUBLIC, anon, authenticated;
REVOKE ALL PRIVILEGES ON FUNCTION public._cw_membership_guard() FROM PUBLIC, anon, authenticated;
REVOKE ALL PRIVILEGES ON FUNCTION public._cw_observation_ingest() FROM PUBLIC, anon, authenticated;
REVOKE ALL PRIVILEGES ON FUNCTION public._cw_profile_indicator_guard() FROM PUBLIC, anon, authenticated;
REVOKE ALL PRIVILEGES ON FUNCTION public._cw_set_creator() FROM PUBLIC, anon, authenticated;
REVOKE ALL PRIVILEGES ON FUNCTION public._cw_touch() FROM PUBLIC, anon, authenticated;
REVOKE ALL PRIVILEGES ON FUNCTION public._cw_tvp_guard() FROM PUBLIC, anon, authenticated;
REVOKE ALL PRIVILEGES ON FUNCTION public._cw_value_profile_guard() FROM PUBLIC, anon, authenticated;
REVOKE ALL PRIVILEGES ON FUNCTION public.add_tenant_member(uuid,uuid,public.member_role) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.add_tenant_member(uuid,uuid,public.member_role) TO authenticated;
REVOKE ALL PRIVILEGES ON FUNCTION public.approve_value_profile(uuid) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.approve_value_profile(uuid) TO authenticated;
REVOKE ALL PRIVILEGES ON FUNCTION public.build_evidence_bundle(uuid,uuid) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.build_evidence_bundle(uuid,uuid) TO authenticated;
REVOKE ALL PRIVILEGES ON FUNCTION public.create_tenant(text,public.subject_unit_type) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.create_tenant(text,public.subject_unit_type) TO authenticated;
REVOKE ALL PRIVILEGES ON FUNCTION public.create_value_profile_draft(uuid,text,text) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.create_value_profile_draft(uuid,text,text) TO authenticated;
REVOKE ALL PRIVILEGES ON FUNCTION public.create_value_profile_version(uuid) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.create_value_profile_version(uuid) TO authenticated;
REVOKE ALL PRIVILEGES ON FUNCTION public.effective_value_profile(uuid) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.effective_value_profile(uuid) TO authenticated;
REVOKE ALL PRIVILEGES ON FUNCTION public.has_tenant_role(uuid,public.member_role[]) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.has_tenant_role(uuid,public.member_role[]) TO authenticated;
REVOKE ALL PRIVILEGES ON FUNCTION public.import_observations(uuid,uuid,text,timestamp with time zone,timestamp with time zone,boolean,text,jsonb) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.import_observations(uuid,uuid,text,timestamp with time zone,timestamp with time zone,boolean,text,jsonb) TO authenticated;
REVOKE ALL PRIVILEGES ON FUNCTION public.is_tenant_member(uuid) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.is_tenant_member(uuid) TO authenticated;
REVOKE ALL PRIVILEGES ON FUNCTION public.my_tenant_role(uuid) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.my_tenant_role(uuid) TO authenticated;
REVOKE ALL PRIVILEGES ON FUNCTION public.remove_tenant_member(uuid,uuid) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.remove_tenant_member(uuid,uuid) TO authenticated;
REVOKE ALL PRIVILEGES ON FUNCTION public.run_deterioration_analysis(uuid,uuid,uuid,timestamp with time zone) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.run_deterioration_analysis(uuid,uuid,uuid,timestamp with time zone) TO authenticated;
REVOKE ALL PRIVILEGES ON FUNCTION public.set_member_role(uuid,uuid,public.member_role) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.set_member_role(uuid,uuid,public.member_role) TO authenticated;
REVOKE ALL PRIVILEGES ON FUNCTION public.value_profile_approval_issues(uuid) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.value_profile_approval_issues(uuid) TO authenticated;