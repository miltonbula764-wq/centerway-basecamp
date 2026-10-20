-- PROVISIONAL number: 0025 is still pending hosted installation. Reconcile numbering before merge.
-- At 100 SaaS / 1,000 clients / 100k observations, the shared Core's generic plan
-- took seconds while the same authenticated projection/custom plan took milliseconds.
-- Preserve classifier, signatures, RLS and permissions; scope planning to this one engine.
ALTER FUNCTION public._core_followup_engine(uuid,text,text,text,text,integer,uuid,uuid)
 SET plan_cache_mode = 'force_custom_plan';


-- Timestamps are not commit/order watermarks: C01 uses transaction_timestamp(),
-- while checked_at uses clock_timestamp(). A concurrent/long transaction may
-- commit new immutable inputs whose timestamp predates the review preparation.
-- Hash immutable identities, under the caller's existing RLS, without classifying
-- or modifying any business record. Missing tokens invalidate older snapshots.
CREATE FUNCTION public._review_data_token(_tenant uuid,_subject uuid,_indicator text,_source jsonb)
RETURNS text LANGUAGE sql STABLE SECURITY INVOKER SET search_path=public AS $$
 SELECT md5(jsonb_build_array(
  (SELECT md5(coalesce(string_agg(id::text,',' ORDER BY id),'')) FROM public.observations WHERE tenant_id=_tenant AND subject_id=_subject),
  (SELECT md5(coalesce(string_agg(id::text,',' ORDER BY id),'')) FROM public.c02_runs WHERE tenant_id=_tenant AND subject_id=_subject),
  (SELECT md5(coalesce(string_agg(id::text,',' ORDER BY id),'')) FROM public.c04_configurations WHERE tenant_id=_tenant AND subject_id=_subject AND indicator_key=_indicator),
  (SELECT md5(coalesce(string_agg(id::text,',' ORDER BY id),'')) FROM public.c04_evaluations WHERE tenant_id=_tenant AND subject_id=_subject AND configuration_id=(_source->>'configuration_id')::uuid),
  (SELECT md5(coalesce(string_agg(id::text,',' ORDER BY id),'')) FROM public.cw_operational_events WHERE tenant_id=_tenant AND case_id=(_source->>'case_id')::uuid),
  (SELECT md5(coalesce(string_agg(id::text,',' ORDER BY id),'')) FROM public.cw_case_events WHERE tenant_id=_tenant AND case_id=(_source->>'case_id')::uuid)
 )::text);
$$;
REVOKE ALL ON FUNCTION public._review_data_token(uuid,uuid,text,jsonb) FROM PUBLIC,anon,service_role;
GRANT EXECUTE ON FUNCTION public._review_data_token(uuid,uuid,text,jsonb) TO authenticated;

CREATE OR REPLACE FUNCTION public._review_store(_tenant uuid,q jsonb,f jsonb,_cycle uuid) RETURNS void LANGUAGE plpgsql SET search_path=public AS $$
DECLARE old public.cw_review_entries;h text;new_revision integer;entry uuid;
BEGIN
 f:=f||jsonb_build_object('data_token',public._review_data_token(_tenant,(q->>'subject_id')::uuid,q->>'indicator_key',q));
 q:=q-ARRAY['can_prepare','review_due','tenant_name'];
 h:=encode(sha256(convert_to(jsonb_build_array(q,f)::text,'UTF8')),'hex');
 SELECT * INTO old FROM public.cw_review_entries WHERE tenant_id=_tenant AND entry_key=q->>'entry_key' FOR UPDATE;
 IF FOUND AND old.fingerprint=h THEN
  UPDATE public.cw_review_entries SET seen_cycle=_cycle,checked_at=clock_timestamp() WHERE id=old.id; RETURN;
 END IF;
 new_revision:=coalesce(old.revision,0)+1;
 INSERT INTO public.cw_review_entries(tenant_id,entry_key,subject_id,indicator_key,revision,source,facts,fingerprint,seen_cycle,checked_at)
 VALUES(_tenant,q->>'entry_key',(q->>'subject_id')::uuid,q->>'indicator_key',new_revision,q,f,h,_cycle,clock_timestamp())
 ON CONFLICT(tenant_id,entry_key) DO UPDATE SET revision=excluded.revision,source=excluded.source,facts=excluded.facts,
  fingerprint=excluded.fingerprint,seen_cycle=excluded.seen_cycle,checked_at=excluded.checked_at RETURNING id INTO entry;
 INSERT INTO public.cw_review_events(tenant_id,entry_id,revision,source,facts) VALUES(_tenant,entry,new_revision,q,f);
END $$;


CREATE OR REPLACE FUNCTION public.scheduled_reviews(_tenant_id uuid,_status text DEFAULT '',_indicator text DEFAULT '',_after text DEFAULT '',_limit integer DEFAULT 25)
RETURNS jsonb LANGUAGE plpgsql STABLE SECURITY INVOKER SET search_path=public AS $$
DECLARE items jsonb;more boolean;next_key text;BEGIN
 IF NOT public.is_tenant_member(_tenant_id) THEN RAISE EXCEPTION 'tenant_membership_required' USING ERRCODE='42501'; END IF;
 IF _limit IS NULL OR _limit NOT BETWEEN 1 AND 100 OR _status IS NULL OR _status NOT IN ('','pending','available','waiting','current','closed','retired') OR _indicator IS NULL OR length(_indicator)>200 OR _after IS NULL OR length(_after)>500 THEN RAISE EXCEPTION 'invalid_review_filter' USING ERRCODE='22023'; END IF;
 WITH page AS (SELECT e.*,
  ((facts->>'data_token' IS DISTINCT FROM public._review_data_token(e.tenant_id,e.subject_id,e.indicator_key,e.source))
   OR coalesce((facts->>'status'='waiting' AND least((facts->>'review_at')::timestamptz,(facts->>'next_measurement_at')::timestamptz)<=clock_timestamp()),false)
   OR EXISTS(SELECT FROM public.observations o WHERE o.tenant_id=e.tenant_id AND o.subject_id=e.subject_id AND o.ingested_at>e.checked_at)
   OR EXISTS(SELECT FROM public.c02_runs r WHERE r.tenant_id=e.tenant_id AND r.subject_id=e.subject_id AND r.created_at>e.checked_at)
   OR EXISTS(SELECT FROM public.c04_configurations c WHERE c.tenant_id=e.tenant_id AND c.subject_id=e.subject_id AND c.indicator_key=e.indicator_key AND c.created_at>e.checked_at)
   OR EXISTS(SELECT FROM public.c04_evaluations a WHERE a.tenant_id=e.tenant_id AND a.subject_id=e.subject_id AND a.configuration_id=(e.source->>'configuration_id')::uuid AND a.created_at>e.checked_at)
   OR EXISTS(SELECT FROM public.cw_operational_events c WHERE c.tenant_id=e.tenant_id AND c.case_id=(e.source->>'case_id')::uuid AND c.created_at>e.checked_at)
   OR EXISTS(SELECT FROM public.cw_case_events c WHERE c.tenant_id=e.tenant_id AND c.case_id=(e.source->>'case_id')::uuid AND c.created_at>e.checked_at)) AS needs_refresh
 FROM public.cw_review_entries e WHERE tenant_id=_tenant_id AND entry_key COLLATE "C">_after COLLATE "C"
  AND (_status='' OR facts->>'status'=_status) AND (_indicator='' OR strpos(lower(indicator_key),lower(_indicator))>0) ORDER BY entry_key COLLATE "C" LIMIT _limit+1),
 numbered AS (SELECT *,row_number() OVER(ORDER BY entry_key COLLATE "C") n FROM page)
 SELECT coalesce(jsonb_agg(to_jsonb(numbered)-'n'-'fingerprint'-'seen_cycle' ORDER BY entry_key COLLATE "C") FILTER(WHERE n<=_limit),'[]'),count(*)>_limit,
  max(entry_key COLLATE "C") FILTER(WHERE n<=_limit) INTO items,more,next_key FROM numbered;
 RETURN jsonb_build_object('tenant_id',_tenant_id,'server_now',clock_timestamp(),'items',items,'has_more',more,'next_cursor',next_key,
  'scan',(SELECT to_jsonb(s) FROM public.cw_review_scans s WHERE tenant_id=_tenant_id),
  'attempts',coalesce((SELECT jsonb_agg(x ORDER BY finished_at DESC,id) FROM (SELECT * FROM public.cw_review_attempts WHERE tenant_id=_tenant_id ORDER BY finished_at DESC,id LIMIT 5)x),'[]'));
END $$;

NOTIFY pgrst,'reload schema';
