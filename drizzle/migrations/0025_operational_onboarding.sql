-- Read-only onboarding projection. No progress flags, writes, automatic approval or alternate evaluator.
CREATE FUNCTION public.operational_onboarding(_tenant_id uuid,_subject_id uuid DEFAULT NULL,_after_subject uuid DEFAULT NULL,_after_indicator text DEFAULT '',_limit integer DEFAULT 25)
RETURNS jsonb LANGUAGE plpgsql STABLE SECURITY INVOKER SET search_path=public AS $$
DECLARE approved public.tenant_value_profiles;draft public.tenant_value_profiles;subject public.subjects;
 clients jsonb;entries jsonb;more_clients boolean;more_indicators boolean;role public.member_role;
BEGIN
 IF NOT public.is_tenant_member(_tenant_id) THEN RAISE EXCEPTION 'tenant_membership_required' USING ERRCODE='42501';END IF;
 IF _limit IS NULL OR _limit NOT BETWEEN 1 AND 100 OR _after_indicator IS NULL OR length(_after_indicator)>64 THEN RAISE EXCEPTION 'invalid_onboarding_filter' USING ERRCODE='22023';END IF;
 SELECT m.role INTO role FROM public.memberships m WHERE m.tenant_id=_tenant_id AND m.user_id=auth.uid();
 SELECT * INTO approved FROM public.tenant_value_profiles WHERE tenant_id=_tenant_id AND status='approved' ORDER BY version DESC LIMIT 1;
 SELECT * INTO draft FROM public.tenant_value_profiles WHERE tenant_id=_tenant_id AND status='draft' ORDER BY version DESC LIMIT 1;
 IF _subject_id IS NOT NULL THEN
  SELECT * INTO subject FROM public.subjects WHERE tenant_id=_tenant_id AND id=_subject_id;
  IF subject.id IS NULL THEN RAISE EXCEPTION 'subject_unavailable' USING ERRCODE='22023';END IF;
 ELSE SELECT * INTO subject FROM public.subjects WHERE tenant_id=_tenant_id ORDER BY id LIMIT 1;END IF;
 SELECT coalesce(jsonb_agg(to_jsonb(x)-'n' ORDER BY id) FILTER(WHERE n<=_limit),'[]'),count(*)>_limit INTO clients,more_clients FROM(
  SELECT s.id,s.tenant_id,s.display_name,s.external_ref,row_number() OVER(ORDER BY s.id)n FROM public.subjects s
  WHERE s.tenant_id=_tenant_id AND (_after_subject IS NULL OR s.id>_after_subject) ORDER BY s.id LIMIT _limit+1)x;
 WITH axes AS (
  SELECT i.* FROM public.profile_indicators i WHERE i.tenant_id=_tenant_id AND i.profile_id=approved.id AND i.classification='outcome'
    AND i.key COLLATE "C">_after_indicator COLLATE "C" ORDER BY i.key COLLATE "C" LIMIT _limit+1
 ), page AS (
  SELECT jsonb_build_object('tenant_id',_tenant_id,'subject_id',subject.id,'indicator_key',i.key,'name',i.name,'unit',i.unit,
   'configuration',CASE WHEN c.id IS NULL THEN NULL ELSE jsonb_build_object('id',c.id,'version',c.version,'profile_id',c.profile_id,'pending_fields',c.pending_fields,'compatibility',c.definition->>'compatibility') END,
   'profile_changed',coalesce(c.profile_id<>approved.id,false),
   'has_observations',EXISTS(SELECT FROM public.observations o WHERE o.tenant_id=_tenant_id AND o.subject_id=subject.id AND o.indicator_key=i.key),
   'new_observations',EXISTS(SELECT FROM public.observations o WHERE o.tenant_id=_tenant_id AND o.subject_id=subject.id AND o.indicator_key=i.key AND (r.id IS NULL OR o.ingested_at>r.data_cutoff)),
   'run',CASE WHEN r.id IS NULL THEN NULL ELSE jsonb_build_object('id',r.id,'as_of',r.as_of,'data_cutoff',r.data_cutoff,'status',cr.status,'reasons',cr.reasons) END,
   'bundle',CASE WHEN b.id IS NULL THEN NULL ELSE jsonb_build_object('id',b.id,'status',ci.status,'reasons',ci.reasons) END,
   'evaluation',CASE WHEN e.id IS NULL THEN NULL ELSE jsonb_build_object('id',e.id,'bundle_id',e.bundle_id,'configuration_state',e.configuration_state,'evidence',e.evidence,'result',e.result,'core_disposition',e.core_disposition,'reasons',e.details->'reasons') END
  ) item,i.key,row_number() OVER(ORDER BY i.key COLLATE "C")n
  FROM axes i
  LEFT JOIN LATERAL(SELECT * FROM public.c04_configurations c WHERE c.tenant_id=_tenant_id AND c.subject_id=subject.id AND c.indicator_key=i.key ORDER BY version DESC LIMIT 1)c ON true
  LEFT JOIN LATERAL(SELECT * FROM public.c02_runs r WHERE r.tenant_id=_tenant_id AND r.subject_id=subject.id AND r.profile_id=approved.id ORDER BY created_at DESC,data_cutoff DESC,id DESC LIMIT 1)r ON true
  LEFT JOIN public.c02_results cr ON cr.tenant_id=_tenant_id AND cr.run_id=r.id AND cr.indicator_key=i.key
  LEFT JOIN LATERAL(SELECT * FROM public.c03_bundles b WHERE b.tenant_id=_tenant_id AND b.run_id=r.id ORDER BY created_at DESC,id DESC LIMIT 1)b ON true
  LEFT JOIN public.c03_indicators ci ON ci.tenant_id=_tenant_id AND ci.bundle_id=b.id AND ci.indicator_key=i.key
  LEFT JOIN LATERAL(SELECT * FROM public.c04_evaluations e WHERE e.tenant_id=_tenant_id AND e.configuration_id=c.id ORDER BY created_at DESC,id DESC LIMIT 1)e ON true
 ) SELECT coalesce(jsonb_agg(item ORDER BY key COLLATE "C") FILTER(WHERE n<=_limit),'[]'),count(*)>_limit INTO entries,more_indicators FROM page;
 RETURN jsonb_build_object('tenant_id',_tenant_id,'role',role,'server_now',clock_timestamp(),
  'approved_profile',CASE WHEN approved.id IS NULL THEN NULL ELSE jsonb_build_object('id',approved.id,'version',approved.version,'promise',approved.promise) END,
  'draft_profile',CASE WHEN draft.id IS NULL THEN NULL ELSE jsonb_build_object('id',draft.id,'version',draft.version,'issues',to_jsonb(public.value_profile_approval_issues(draft.id))) END,
  'subjects',clients,'has_more_subjects',more_clients,'subject',CASE WHEN subject.id IS NULL THEN NULL ELSE jsonb_build_object('id',subject.id,'tenant_id',subject.tenant_id,'external_ref',subject.external_ref,'display_name',subject.display_name) END,
  'indicators',entries,'has_more_indicators',more_indicators);
END $$;
REVOKE ALL ON FUNCTION public.operational_onboarding(uuid,uuid,uuid,text,integer) FROM PUBLIC,anon,authenticated,service_role,centerway_review_scheduler;
GRANT EXECUTE ON FUNCTION public.operational_onboarding(uuid,uuid,uuid,text,integer) TO authenticated;
NOTIFY pgrst,'reload schema';
