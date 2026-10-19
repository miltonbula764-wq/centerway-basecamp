-- Read-only operational projection. No case transitions, backfill or policy changes.
CREATE INDEX c04_evaluations_followup_idx ON public.c04_evaluations(tenant_id,configuration_id,created_at DESC,id DESC);
CREATE INDEX cw_operational_events_followup_idx ON public.cw_operational_events(tenant_id,case_id,command,sequence DESC);

CREATE FUNCTION public.core_followup_queue(
  _tenant_id uuid, _client text DEFAULT '', _indicator text DEFAULT '', _category text DEFAULT '',
  _after text DEFAULT '', _limit integer DEFAULT 25
) RETURNS jsonb LANGUAGE plpgsql STABLE SECURITY INVOKER SET search_path=public AS $$
DECLARE result jsonb; now_at timestamptz:=clock_timestamp(); writer boolean; administrator boolean;
BEGIN
  IF NOT public.is_tenant_member(_tenant_id) THEN RAISE EXCEPTION 'tenant_membership_required' USING ERRCODE='42501'; END IF;
  IF _limit IS NULL OR _limit NOT BETWEEN 1 AND 100 OR _client IS NULL OR length(_client)>200
    OR _indicator IS NULL OR length(_indicator)>200 OR _after IS NULL OR length(_after)>500
    OR _category IS NULL OR _category NOT IN ('','information_pending','contradiction','assessment_review','investigation_planning','authorization_execution','waiting_observation','results_review','result_open','closed') THEN
    RAISE EXCEPTION 'invalid_queue_filter' USING ERRCODE='22023'; END IF;
  writer:=public.has_tenant_role(_tenant_id,ARRAY['admin','operator']::public.member_role[]);
  administrator:=public.has_tenant_role(_tenant_id,ARRAY['admin']::public.member_role[]);
  WITH subjects AS MATERIALIZED (
    SELECT s.* FROM public.subjects s WHERE s.tenant_id=_tenant_id
      AND (_client='' OR strpos(lower(coalesce(s.display_name,'')||' '||s.external_ref),lower(_client))>0)
  ), latest_config AS MATERIALIZED (
    SELECT DISTINCT ON (c.subject_id,c.indicator_key) c.* FROM public.c04_configurations c
      JOIN subjects s ON s.id=c.subject_id WHERE c.tenant_id=_tenant_id ORDER BY c.subject_id,c.indicator_key,c.version DESC
  ), axes AS (
    SELECT c.subject_id,c.indicator_key FROM latest_config c
    UNION
    SELECT s.id,i.key FROM subjects s JOIN public.tenant_value_profiles p ON p.tenant_id=s.tenant_id AND p.status='approved'
      JOIN public.profile_indicators i ON i.tenant_id=p.tenant_id AND i.profile_id=p.id AND i.classification='outcome'
  ), assessment_rows AS (
    SELECT 'assessment:'||x.subject_id||':'||x.indicator_key AS entry_key, 'c04'::text AS kind,
      x.subject_id,x.indicator_key,c.id AS configuration_id,c.version AS configuration_version,a.id AS evaluation_id,
      NULL::uuid AS case_id,NULL::integer AS case_version,coalesce(a.result,'not_evaluated') AS state,
      CASE WHEN a.configuration_state='contradiction' OR (c.definition->>'compatibility'='contradiction' AND c.definition->>'compatibility_ref' IS NOT NULL) THEN 'contradiction'
        WHEN a.core_disposition='assessment_available' THEN 'assessment_review' ELSE 'information_pending' END AS category,
      CASE WHEN c.id IS NULL THEN 'document_goal' WHEN cardinality(c.pending_fields)>0 OR a.configuration_state IN ('missing_documentation','contradiction') THEN 'review_configuration'
        WHEN a.id IS NULL THEN 'evaluate' WHEN a.core_disposition='assessment_available' THEN 'review_eligibility' ELSE 'collect_evidence' END AS next_action,
      coalesce(a.details->'reasons','[]'::jsonb)||coalesce(to_jsonb(c.pending_fields),'[]'::jsonb)
        ||CASE WHEN c.id IS NULL THEN '["configuration_missing"]'::jsonb WHEN a.id IS NULL THEN '["evaluation_missing"]'::jsonb ELSE '[]'::jsonb END AS reasons,
      jsonb_build_object('configuration_state',a.configuration_state,'result',a.result,'evidence',a.evidence,
        'missing_documentation',a.details->'missing_documentation','definition',c.definition,'evaluation_as_of',a.details->'as_of') AS basis,
      (c.definition->>'deadline')::timestamptz AS review_at,'objective_deadline'::text AS review_kind,
      coalesce(a.created_at,c.created_at) AS updated_at,
      a.id IS NOT NULL AND EXISTS(SELECT FROM public.observations o WHERE o.tenant_id=_tenant_id AND o.subject_id=x.subject_id
        AND o.ingested_at>(a.details->>'data_cutoff')::timestamptz
        AND (o.indicator_key=x.indicator_key OR o.indicator_key IN(SELECT i.denominator_indicator_key FROM public.profile_indicators i WHERE i.tenant_id=_tenant_id AND i.profile_id=c.profile_id AND i.key=x.indicator_key))) AS stale,
      'c04-numeric-v1'::text AS contract
    FROM axes x LEFT JOIN latest_config c ON c.subject_id=x.subject_id AND c.indicator_key=x.indicator_key
    LEFT JOIN LATERAL(SELECT a.* FROM public.c04_evaluations a WHERE a.tenant_id=_tenant_id AND a.configuration_id=c.id ORDER BY a.created_at DESC,a.id DESC LIMIT 1) a ON true
    WHERE NOT EXISTS(SELECT FROM public.cw_operational_cases k WHERE k.tenant_id=_tenant_id AND k.evaluation_id=a.id)
  ), case_context AS (
    SELECT k.*,c.indicator_key,c.version AS configuration_version,c.profile_id,c.definition,a.bundle_id AS baseline_bundle,
      f.details AS finding,p.id AS plan_id,ap.details AS approval,ap.created_by AS approver,
      ex.details AS execution,cmp.details AS comparison,ev.details AS last_details,ev.created_at AS updated_at,
      EXISTS(SELECT FROM latest_config lc WHERE lc.subject_id=k.subject_id AND lc.indicator_key=c.indicator_key AND lc.version>c.version) AS revised,
      EXISTS(SELECT FROM jsonb_array_elements(coalesce(f.details->'evidence','[]')) ref JOIN public.observations o
        ON o.tenant_id=_tenant_id AND o.corrects_observation_id=(ref->>'id')::uuid) AS corrected,
      coalesce(ap.details->>'plan_event_id'=p.id::text AND (ap.details->>'valid_until')::timestamptz>now_at
        AND EXISTS(SELECT FROM public.memberships m WHERE m.tenant_id=_tenant_id AND m.user_id=ap.created_by AND m.role='admin'),false) AS authorized
    FROM public.cw_operational_cases k JOIN subjects s ON s.id=k.subject_id
    JOIN public.c04_configurations c ON c.tenant_id=k.tenant_id AND c.id=k.configuration_id
    JOIN public.c04_evaluations a ON a.tenant_id=k.tenant_id AND a.id=k.evaluation_id
    LEFT JOIN LATERAL(SELECT * FROM public.cw_operational_events e WHERE e.tenant_id=_tenant_id AND e.case_id=k.id AND e.command='investigate' ORDER BY sequence DESC LIMIT 1) f ON true
    LEFT JOIN LATERAL(SELECT * FROM public.cw_operational_events e WHERE e.tenant_id=_tenant_id AND e.case_id=k.id AND e.command='plan' ORDER BY sequence DESC LIMIT 1) p ON true
    LEFT JOIN LATERAL(SELECT * FROM public.cw_operational_events e WHERE e.tenant_id=_tenant_id AND e.case_id=k.id AND e.command='approve' ORDER BY sequence DESC LIMIT 1) ap ON true
    LEFT JOIN LATERAL(SELECT * FROM public.cw_operational_events e WHERE e.tenant_id=_tenant_id AND e.case_id=k.id AND e.command='record_execution' ORDER BY sequence DESC LIMIT 1) ex ON true
    LEFT JOIN LATERAL(SELECT * FROM public.cw_operational_events e WHERE e.tenant_id=_tenant_id AND e.case_id=k.id AND e.command='observe' ORDER BY sequence DESC LIMIT 1) cmp ON true
    LEFT JOIN LATERAL(SELECT * FROM public.cw_operational_events e WHERE e.tenant_id=_tenant_id AND e.case_id=k.id ORDER BY sequence DESC LIMIT 1) ev ON true
    WHERE k.tenant_id=_tenant_id
  ), case_rows AS (
    SELECT 'case:'||k.id AS entry_key,'operational'::text AS kind,k.subject_id,k.indicator_key,k.configuration_id,k.configuration_version,k.evaluation_id,
      k.id AS case_id,k.version AS case_version,k.state,
      CASE WHEN k.state='closed_resolved' THEN 'closed'
        WHEN k.revised OR (k.corrected AND k.execution IS NULL) OR k.state='needs_information' THEN 'information_pending'
        WHEN k.state IN ('investigation','hypothesis','impediment_confirmed') THEN 'investigation_planning'
        WHEN k.state IN ('awaiting_approval','approved') THEN 'authorization_execution'
        WHEN k.state='waiting_observation' AND (k.execution->>'wait_until')::timestamptz>now_at THEN 'waiting_observation'
        WHEN k.state='remain_open' OR (k.state='observed' AND (k.comparison->>'result' IS DISTINCT FROM 'achieved' OR k.comparison->>'sufficient' IS DISTINCT FROM 'true')) THEN 'result_open'
        ELSE 'results_review' END AS category,
      CASE WHEN k.state='closed_resolved' THEN 'consult_history'
        WHEN k.revised THEN 'review_historical_contract'
        WHEN k.execution IS NULL AND (k.corrected OR k.state IN ('investigation','needs_information','hypothesis')) THEN 'investigate'
        WHEN k.state='impediment_confirmed' THEN 'plan'
        WHEN k.state='awaiting_approval' OR (k.state='approved' AND NOT k.authorized) THEN 'authorize'
        WHEN k.state='approved' THEN 'record_execution'
        WHEN k.state='observed' THEN 'decide'
        WHEN (k.execution->>'wait_until')::timestamptz>now_at THEN 'wait'
        WHEN EXISTS(SELECT FROM public.c03_bundles b WHERE b.tenant_id=_tenant_id AND b.subject_id=k.subject_id
          AND b.id<>k.baseline_bundle AND (k.comparison IS NULL OR b.id::text<>k.comparison->>'bundle_id')) THEN 'compare'
        ELSE 'collect_evidence' END AS next_action,
      coalesce(k.last_details->'reasons','[]'::jsonb)
        ||CASE WHEN k.revised THEN '["configuration_revision_requires_review"]'::jsonb ELSE '[]'::jsonb END
        ||CASE WHEN k.corrected THEN '["investigation_evidence_changed"]'::jsonb ELSE '[]'::jsonb END
        ||CASE WHEN k.state='approved' AND NOT k.authorized THEN '["valid_authorization_required"]'::jsonb ELSE '[]'::jsonb END
        ||CASE WHEN k.state='waiting_observation' THEN '["window_end_does_not_prove_measurement_sufficiency"]'::jsonb ELSE '[]'::jsonb END AS reasons,
      jsonb_build_object('opening',k.opening_definition,'last_event',k.last_details,'comparison_result',k.comparison->'result',
        'comparison_sufficient',k.comparison->'sufficient','authorization_valid',k.authorized,'authorization_until',k.approval->'valid_until') AS basis,
      (k.execution->>'wait_until')::timestamptz AS review_at,'observation_window'::text AS review_kind,k.updated_at,
      k.revised OR k.corrected OR EXISTS(SELECT FROM public.observations o WHERE o.tenant_id=_tenant_id AND o.subject_id=k.subject_id
        AND k.comparison IS NOT NULL AND (o.ingested_at>(k.comparison->>'data_cutoff')::timestamptz
          OR o.observed_at>=(SELECT max((w->>'end')::timestamptz) FROM jsonb_array_elements(k.comparison#>'{after,windows}') w))
        AND (o.indicator_key=k.indicator_key OR o.indicator_key IN(SELECT i.denominator_indicator_key FROM public.profile_indicators i WHERE i.tenant_id=_tenant_id AND i.profile_id=k.profile_id AND i.key=k.indicator_key)
          OR o.indicator_key IN(SELECT ref->>'indicator_key' FROM jsonb_array_elements(coalesce(k.finding->'evidence','[]')) ref))) AS stale,
      k.contract_version AS contract FROM case_context k
  ), legacy_rows AS (
    -- Preserve the separate pilot contract. Only route to its existing dossier; no general actions inferred.
    SELECT 'legacy:'||k.id,'legacy',k.subject_id,'report_hours',NULL::uuid,NULL::integer,NULL::uuid,k.id,k.version,k.state,
      CASE WHEN k.state='closed_resolved' THEN 'closed' WHEN k.state='needs_information' THEN 'information_pending'
        WHEN k.state IN ('investigation','impediment_found') THEN 'investigation_planning'
        WHEN k.state IN ('awaiting_approval','approved') THEN 'authorization_execution'
        WHEN k.state='waiting_observation' AND (ex.details->>'wait_until')::timestamptz>now_at THEN 'waiting_observation'
        WHEN k.state='remain_open' OR (k.state='observed' AND ev.details->>'sufficient' IS DISTINCT FROM 'true') THEN 'result_open' ELSE 'results_review' END,
      'consult_pilot',jsonb_build_array('specific_pilot_contract'),jsonb_build_object('last_event',ev.details),
      (ex.details->>'wait_until')::timestamptz,'observation_window',ev.created_at,false,k.policy_version
    FROM public.cw_cases k JOIN subjects s ON s.id=k.subject_id
    LEFT JOIN LATERAL(SELECT * FROM public.cw_case_events e WHERE e.tenant_id=_tenant_id AND e.case_id=k.id AND e.command='record_execution' ORDER BY sequence DESC LIMIT 1) ex ON true
    LEFT JOIN LATERAL(SELECT * FROM public.cw_case_events e WHERE e.tenant_id=_tenant_id AND e.case_id=k.id ORDER BY sequence DESC LIMIT 1) ev ON true
    WHERE k.tenant_id=_tenant_id
  ), all_rows AS (
    SELECT * FROM assessment_rows UNION ALL SELECT * FROM case_rows UNION ALL SELECT * FROM legacy_rows
  ), page AS MATERIALIZED (
    SELECT r.*,s.display_name,s.external_ref,t.name AS tenant_name,
      CASE WHEN r.next_action IN ('document_goal','review_configuration','review_eligibility','review_historical_contract','authorize','decide') THEN administrator
        WHEN r.next_action IN ('evaluate','collect_evidence','investigate','plan','record_execution','compare') THEN writer ELSE false END AS can_prepare,
      CASE WHEN r.next_action IN ('document_goal','review_configuration','review_eligibility','review_historical_contract','authorize','decide') THEN 'admin'
        WHEN r.next_action IN ('evaluate','collect_evidence','investigate','plan','record_execution','compare') THEN 'admin_or_operator' ELSE 'read' END AS required_role
    FROM all_rows r JOIN subjects s ON s.id=r.subject_id JOIN public.tenants t ON t.id=_tenant_id
    WHERE (_category='' OR r.category=_category) AND (_indicator='' OR strpos(lower(r.indicator_key),lower(_indicator))>0)
      AND r.entry_key COLLATE "C">_after COLLATE "C"
    ORDER BY r.entry_key COLLATE "C" LIMIT _limit+1
  ), visible AS (SELECT * FROM page ORDER BY entry_key COLLATE "C" LIMIT _limit)
  SELECT jsonb_build_object('server_now',now_at,'tenant_id',_tenant_id,'items',coalesce((SELECT jsonb_agg(to_jsonb(v)||jsonb_build_object(
      'review_due',v.review_at IS NOT NULL AND v.review_at<=now_at,'tenant_id',_tenant_id) ORDER BY v.entry_key COLLATE "C") FROM visible v),'[]'::jsonb),
    'has_more',(SELECT count(*)>_limit FROM page),'next_cursor',(SELECT entry_key FROM visible ORDER BY entry_key COLLATE "C" DESC LIMIT 1)) INTO result;
  RETURN result;
END $$;
REVOKE ALL ON FUNCTION public.core_followup_queue(uuid,text,text,text,text,integer) FROM PUBLIC,anon;
GRANT EXECUTE ON FUNCTION public.core_followup_queue(uuid,text,text,text,text,integer) TO authenticated;
NOTIFY pgrst,'reload schema';