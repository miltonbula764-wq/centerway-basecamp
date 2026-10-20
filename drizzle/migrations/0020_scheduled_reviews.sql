-- Monitoring only. No C01-C10 writes, user impersonation, or automatic evaluations.
-- One shared Core projection: preserve the existing query and human-facing invoker contract.
ALTER FUNCTION public.core_followup_queue(uuid,text,text,text,text,integer) RENAME TO _core_followup_projection;
DO $extract$
DECLARE src text; anchor text:='IF NOT public.is_tenant_member(_tenant_id) THEN';
BEGIN
 SELECT pg_get_functiondef('public._core_followup_projection(uuid,text,text,text,text,integer)'::regprocedure) INTO src;
 IF position(anchor IN src)=0 THEN RAISE EXCEPTION 'Core projection authorization anchor changed'; END IF;
 -- Internal SECURITY DEFINER monitoring may read the same projection without fabricating auth.uid().
 -- Direct authenticated callers still run under their own RLS and membership.
 EXECUTE replace(src,anchor,'IF NOT public.is_tenant_member(_tenant_id) AND NOT public._cw_is_privileged() THEN');
END $extract$;
REVOKE ALL ON FUNCTION public._core_followup_projection(uuid,text,text,text,text,integer) FROM PUBLIC,anon,authenticated,service_role;
GRANT EXECUTE ON FUNCTION public._core_followup_projection(uuid,text,text,text,text,integer) TO authenticated;
CREATE FUNCTION public.core_followup_queue(_tenant_id uuid,_client text DEFAULT '',_indicator text DEFAULT '',_category text DEFAULT '',_after text DEFAULT '',_limit integer DEFAULT 25)
RETURNS jsonb LANGUAGE plpgsql STABLE SECURITY INVOKER SET search_path=public AS $$
BEGIN
 IF NOT public.is_tenant_member(_tenant_id) THEN RAISE EXCEPTION 'tenant_membership_required' USING ERRCODE='42501'; END IF;
 RETURN public._core_followup_projection(_tenant_id,_client,_indicator,_category,_after,_limit);
END $$;
REVOKE ALL ON FUNCTION public.core_followup_queue(uuid,text,text,text,text,integer) FROM PUBLIC,anon,authenticated,service_role;
GRANT EXECUTE ON FUNCTION public.core_followup_queue(uuid,text,text,text,text,integer) TO authenticated;

-- NOLOGIN capability role: no data grants, no membership in authenticated/service_role.
CREATE ROLE centerway_review_scheduler NOLOGIN NOINHERIT;
GRANT USAGE ON SCHEMA public TO centerway_review_scheduler;
GRANT centerway_review_scheduler TO postgres;
CREATE TABLE public.cw_review_scans (
 tenant_id uuid PRIMARY KEY REFERENCES public.tenants(id), cursor text NOT NULL DEFAULT '',
 cycle_id uuid NOT NULL DEFAULT gen_random_uuid(), phase text NOT NULL DEFAULT 'scan' CHECK(phase IN ('scan','retire')),
 next_poll_at timestamptz NOT NULL DEFAULT clock_timestamp(), last_attempt_at timestamptz,last_success_at timestamptz,
 last_error text, last_cycle_at timestamptz
);
CREATE INDEX cw_review_scans_due ON public.cw_review_scans(next_poll_at,tenant_id);
CREATE TABLE public.cw_review_entries (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),tenant_id uuid NOT NULL REFERENCES public.tenants(id),
 entry_key text NOT NULL,subject_id uuid NOT NULL,indicator_key text NOT NULL,
 revision integer NOT NULL CHECK(revision>0), source jsonb NOT NULL, facts jsonb NOT NULL, fingerprint text NOT NULL,
 seen_cycle uuid NOT NULL,checked_at timestamptz NOT NULL, UNIQUE(tenant_id,id),UNIQUE(tenant_id,entry_key),
 FOREIGN KEY(tenant_id,subject_id) REFERENCES public.subjects(tenant_id,id)
);
CREATE INDEX cw_review_entries_cycle ON public.cw_review_entries(tenant_id,seen_cycle,entry_key);
CREATE TABLE public.cw_review_events (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),tenant_id uuid NOT NULL,entry_id uuid NOT NULL,revision integer NOT NULL,
 source jsonb NOT NULL,facts jsonb NOT NULL,created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 UNIQUE(entry_id,revision),FOREIGN KEY(tenant_id,entry_id) REFERENCES public.cw_review_entries(tenant_id,id)
);
CREATE TABLE public.cw_review_attempts (
 id uuid PRIMARY KEY,tenant_id uuid NOT NULL REFERENCES public.tenants(id),started_at timestamptz NOT NULL,finished_at timestamptz NOT NULL,
 status text NOT NULL CHECK(status IN ('completed','failed')),processed integer NOT NULL,error_code text,
 actor_kind text NOT NULL CHECK(actor_kind IN ('human','scheduler')),actor_id uuid,
 cursor_before text NOT NULL,cursor_after text NOT NULL,
 UNIQUE(tenant_id,id),CHECK((actor_kind='human')=(actor_id IS NOT NULL))
);
CREATE INDEX cw_review_attempts_recent ON public.cw_review_attempts(tenant_id,finished_at DESC,id);
DO $$ DECLARE t text; BEGIN
 FOREACH t IN ARRAY ARRAY['cw_review_scans','cw_review_entries','cw_review_events','cw_review_attempts'] LOOP
  EXECUTE format('REVOKE ALL ON public.%I FROM PUBLIC,anon,authenticated,service_role,centerway_review_scheduler',t);
  EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY',t);
  EXECUTE format('GRANT SELECT ON public.%I TO authenticated',t);
  EXECUTE format('CREATE POLICY tenant_read ON public.%I FOR SELECT TO authenticated USING(public.is_tenant_member(tenant_id))',t);
 END LOOP;
 FOREACH t IN ARRAY ARRAY['cw_review_events','cw_review_attempts'] LOOP
  EXECUTE format('CREATE TRIGGER immutable BEFORE UPDATE OR DELETE ON public.%I FOR EACH ROW EXECUTE FUNCTION public._c02_immutable()',t);
 END LOOP;
END $$;
CREATE TRIGGER identity BEFORE UPDATE ON public.cw_review_entries FOR EACH ROW EXECUTE FUNCTION public._cw_lock_columns();
CREATE TRIGGER identity BEFORE UPDATE ON public.cw_review_scans FOR EACH ROW EXECUTE FUNCTION public._cw_lock_columns();
CREATE FUNCTION public._review_register_tenant() RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER SET search_path=public AS $$
BEGIN INSERT INTO public.cw_review_scans(tenant_id) VALUES(NEW.id); RETURN NEW; END $$;
CREATE TRIGGER review_scan AFTER INSERT ON public.tenants FOR EACH ROW EXECUTE FUNCTION public._review_register_tenant();
INSERT INTO public.cw_review_scans(tenant_id) SELECT id FROM public.tenants;

-- Bounded source pages. Core state/actions come solely from the shared projection.
-- Additional measurement axes include usage/context, without inventing C04 goals for them.
CREATE FUNCTION public._review_sources(_tenant uuid,_after text) RETURNS jsonb LANGUAGE plpgsql SET search_path=public AS $$
DECLARE core jsonb;items jsonb;more boolean;
BEGIN
 core:=public._core_followup_projection(_tenant,'','','',_after,50);
 WITH measurements AS (
  SELECT jsonb_build_object('entry_key','measurement:'||s.id||':'||i.key,'kind','measurement','tenant_id',_tenant,
   'subject_id',s.id,'display_name',s.display_name,'external_ref',s.external_ref,'indicator_key',i.key,
   'profile_id',p.id,'state','measurement_review','next_action','collect_evidence','contract','c02-v2') AS item
  FROM public.subjects s JOIN public.tenant_value_profiles p ON p.tenant_id=s.tenant_id AND p.status='approved'
  JOIN public.profile_indicators i ON i.tenant_id=p.tenant_id AND i.profile_id=p.id
  WHERE s.tenant_id=_tenant AND ('measurement:'||s.id||':'||i.key) COLLATE "C">_after COLLATE "C"
  ORDER BY ('measurement:'||s.id||':'||i.key) COLLATE "C" LIMIT 51
 ), combined AS (
  SELECT value AS item FROM jsonb_array_elements(core->'items') UNION ALL SELECT item FROM measurements
 ), page AS (SELECT item FROM combined ORDER BY (item->>'entry_key') COLLATE "C" LIMIT 51)
 SELECT coalesce(jsonb_agg(item ORDER BY (item->>'entry_key') COLLATE "C") FILTER(WHERE n<=50),'[]'),count(*)>50 INTO items,more
 FROM (SELECT item,row_number() OVER(ORDER BY (item->>'entry_key') COLLATE "C") n FROM page) numbered;
 RETURN jsonb_build_object('items',items,'has_more',more OR (core->>'has_more')::boolean);
END $$;

-- Preparation facts only: no sufficiency, eligibility, priority, SLA or causal inference.
CREATE FUNCTION public._review_facts(_tenant uuid,q jsonb) RETURNS jsonb LANGUAGE plpgsql STABLE SET search_path=public AS $$
DECLARE c public.c04_configurations;a public.c04_evaluations;pi public.profile_indicators;r public.c02_runs;
 profile uuid;subject uuid:=(q->>'subject_id')::uuid;indicator text:=q->>'indicator_key';now_at timestamptz:=clock_timestamp();
 latest_at timestamptz;next_measurement timestamptz;unanalysed boolean:=false;missing_anchor boolean:=false;missing_cadence boolean:=false;
 due timestamptz;deadline timestamptz;reasons text[]:='{}';status text:='current';token jsonb;changed boolean:=false;
BEGIN
 IF q->>'kind'='legacy' THEN
  due:=(q->>'review_at')::timestamptz;
  status:=CASE WHEN q->>'state'='closed_resolved' THEN 'closed' WHEN due>now_at THEN 'waiting'
   WHEN q->>'state' IN ('waiting_observation','observed') AND due<=now_at THEN 'available' ELSE 'pending' END;
  RETURN jsonb_build_object('status',status,'review_at',due,'reasons',jsonb_build_array('specific_pilot_contract'),'source_token',q->'case_version');
 END IF;
 IF q->>'configuration_id' IS NOT NULL THEN
  SELECT * INTO c FROM public.c04_configurations WHERE tenant_id=_tenant AND id=(q->>'configuration_id')::uuid;
  SELECT * INTO a FROM public.c04_evaluations WHERE tenant_id=_tenant AND configuration_id=c.id ORDER BY created_at DESC,id DESC LIMIT 1;
  profile:=c.profile_id;deadline:=(c.definition->>'deadline')::timestamptz;
  changed:=EXISTS(SELECT FROM public.c04_configurations WHERE tenant_id=_tenant AND subject_id=subject AND indicator_key=indicator AND version>c.version);
 ELSE profile:=(q->>'profile_id')::uuid; END IF;
 SELECT * INTO pi FROM public.profile_indicators WHERE tenant_id=_tenant AND profile_id=profile AND key=indicator;
 SELECT * INTO r FROM public.c02_runs WHERE tenant_id=_tenant AND subject_id=subject AND profile_id=profile ORDER BY as_of DESC,data_cutoff DESC,id DESC LIMIT 1;
 -- Match the existing C02 measurement fingerprint, including compatible historical profiles.
 WITH dependencies AS (
  SELECT i.* FROM public.profile_indicators i WHERE i.tenant_id=_tenant AND i.profile_id=profile
   AND (i.key=indicator OR i.key=pi.denominator_indicator_key)
 ), dates AS (
  SELECT i.key,i.expected_cadence_days,max(o.observed_at) observed,max(o.ingested_at) ingested,
   coalesce(bool_or(r.id IS NULL OR o.ingested_at>r.data_cutoff OR o.observed_at>=r.as_of),false) fresh
  FROM dependencies i LEFT JOIN (
   public.observations o JOIN public.ingestion_batches b ON b.tenant_id=o.tenant_id AND b.id=o.batch_id
   JOIN public.profile_indicators original ON original.tenant_id=b.tenant_id AND original.profile_id=b.profile_id AND original.key=o.indicator_key
  ) ON o.tenant_id=_tenant AND o.subject_id=subject AND o.indicator_key=i.key
   AND (c.id IS NULL OR c.definition->>'source' IS NULL OR o.source=c.definition->>'source')
   AND public._c02_fingerprint(original)=public._c02_fingerprint(i)
  GROUP BY i.key,i.expected_cadence_days
 ) SELECT max(ingested),min(observed+expected_cadence_days*interval '1 day'),coalesce(bool_or(fresh),false),
   coalesce(bool_or(observed IS NULL),true),coalesce(bool_or(expected_cadence_days IS NULL),true)
 INTO latest_at,next_measurement,unanalysed,missing_anchor,missing_cadence FROM dates;
 IF unanalysed THEN reasons:=array_append(reasons,'new_measurements_not_analysed'); END IF;
 IF next_measurement<=now_at THEN reasons:=array_append(reasons,'documented_measurement_cadence_elapsed'); END IF;
 IF missing_anchor THEN reasons:=array_append(reasons,'measurement_anchor_missing'); END IF;
 IF missing_cadence THEN reasons:=array_append(reasons,'measurement_cadence_missing'); END IF;
 IF changed THEN reasons:=array_append(reasons,'configuration_revision_requires_review'); END IF;
 IF q->>'kind'='measurement' THEN
  due:=next_measurement;
  status:=CASE WHEN unanalysed OR next_measurement<=now_at THEN 'available' WHEN missing_anchor OR missing_cadence THEN 'pending' ELSE 'waiting' END;
 ELSIF q->>'kind'='c04' THEN
  due:=deadline;
  IF deadline<=now_at AND (a.id IS NULL OR (a.details->>'as_of')::timestamptz<deadline) THEN reasons:=array_append(reasons,'documented_objective_deadline_reached'); END IF;
  IF a.id IS NULL THEN reasons:=array_append(reasons,'evaluation_missing'); END IF;
  IF a.evidence='insufficient' THEN reasons:=array_append(reasons,'new_evidence_required'); END IF;
  status:=CASE WHEN changed OR c.id IS NULL OR cardinality(c.pending_fields)>0 OR a.configuration_state IN ('contradiction','missing_documentation','not_checkable') THEN 'pending'
   WHEN unanalysed OR next_measurement<=now_at OR (deadline<=now_at AND (a.id IS NULL OR (a.details->>'as_of')::timestamptz<deadline)) THEN 'available'
   WHEN a.id IS NULL OR a.evidence='insufficient' THEN 'pending' WHEN deadline>now_at THEN 'waiting' ELSE 'current' END;
 ELSE
  due:=(q->>'review_at')::timestamptz;
  status:=CASE WHEN q->>'state'='closed_resolved' THEN 'closed'
   WHEN changed OR q->>'category' IN ('information_pending','contradiction') THEN 'pending'
   WHEN due>now_at THEN 'waiting'
   WHEN q->>'state'='waiting_observation' AND due<=now_at THEN 'available'
   WHEN q->>'category'='result_open' THEN CASE WHEN unanalysed OR coalesce((q->>'stale')::boolean,false) THEN 'available' ELSE 'pending' END
   WHEN q->>'category'='results_review' THEN 'available' ELSE 'pending' END;
  IF q->>'category'='result_open' THEN reasons:=array_append(reasons,'new_evidence_required'); END IF;
  IF due<=now_at THEN reasons:=array_append(reasons,'observation_window_elapsed_not_proof'); END IF;
 END IF;
 -- Stable identifiers and dates only: repeated scans don't fabricate revisions merely as time passes.
 token:=jsonb_build_object('latest_ingested_at',latest_at,'run_id',r.id,'run_as_of',r.as_of,'data_cutoff',r.data_cutoff,
  'configuration_id',c.id,'evaluation_id',a.id,'configuration_changed',changed,'next_measurement_at',next_measurement);
 RETURN jsonb_build_object('status',status,'review_at',due,'next_measurement_at',next_measurement,
  'reasons',to_jsonb(reasons)||coalesce(q->'reasons','[]'::jsonb),'source_token',token);
END $$;

CREATE FUNCTION public._review_store(_tenant uuid,q jsonb,f jsonb,_cycle uuid) RETURNS void LANGUAGE plpgsql SET search_path=public AS $$
DECLARE old public.cw_review_entries;h text;new_revision integer;entry uuid;
BEGIN
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

CREATE FUNCTION public._review_process(_tenant uuid,_request uuid,_actor uuid) RETURNS jsonb LANGUAGE plpgsql SET search_path=public AS $$
DECLARE scan public.cw_review_scans;attempt public.cw_review_attempts;p jsonb;q jsonb;e record;n integer:=0;started timestamptz:=clock_timestamp();code text;done boolean:=false;
BEGIN
 SELECT * INTO scan FROM public.cw_review_scans WHERE tenant_id=_tenant FOR UPDATE;
 SELECT * INTO attempt FROM public.cw_review_attempts WHERE tenant_id=_tenant AND id=_request;
 IF FOUND THEN RETURN to_jsonb(attempt); END IF;
 BEGIN
  IF scan.phase='scan' THEN
   p:=public._review_sources(_tenant,scan.cursor);
   FOR q IN SELECT value FROM jsonb_array_elements(p->'items') LOOP
    PERFORM public._review_store(_tenant,q,public._review_facts(_tenant,q),scan.cycle_id);n:=n+1;
   END LOOP;
   UPDATE public.cw_review_scans SET cursor=coalesce(q->>'entry_key',cursor),phase=CASE WHEN (p->>'has_more')::boolean THEN 'scan' ELSE 'retire' END WHERE tenant_id=_tenant;
  ELSE
   FOR e IN SELECT * FROM public.cw_review_entries WHERE tenant_id=_tenant AND seen_cycle<>scan.cycle_id AND facts->>'status'<>'retired' ORDER BY entry_key COLLATE "C" LIMIT 50 LOOP
    PERFORM public._review_store(_tenant,e.source,jsonb_build_object('status','retired','reasons',jsonb_build_array('source_no_longer_current')),scan.cycle_id);n:=n+1;
   END LOOP;
   done:=n<50;
   IF done THEN UPDATE public.cw_review_scans SET cursor='',phase='scan',cycle_id=gen_random_uuid(),last_cycle_at=clock_timestamp() WHERE tenant_id=_tenant; END IF;
  END IF;
 EXCEPTION WHEN OTHERS THEN GET STACKED DIAGNOSTICS code=RETURNED_SQLSTATE;n:=0; END;
 UPDATE public.cw_review_scans SET last_attempt_at=started,last_success_at=CASE WHEN code IS NULL THEN clock_timestamp() ELSE last_success_at END,
  last_error=code,next_poll_at=CASE WHEN code IS NOT NULL OR done THEN clock_timestamp()+interval '1 minute' ELSE clock_timestamp() END WHERE tenant_id=_tenant;
 INSERT INTO public.cw_review_attempts(id,tenant_id,started_at,finished_at,status,processed,error_code,actor_kind,actor_id,cursor_before,cursor_after)
 SELECT _request,_tenant,started,clock_timestamp(),CASE WHEN code IS NULL THEN 'completed' ELSE 'failed' END,n,code,
  CASE WHEN _actor IS NULL THEN 'scheduler' ELSE 'human' END,_actor,scan.cursor,cursor FROM public.cw_review_scans WHERE tenant_id=_tenant RETURNING * INTO attempt;
 RETURN to_jsonb(attempt);
END $$;
CREATE FUNCTION public.process_review_schedule(_limit integer DEFAULT 10) RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=public SET TimeZone='UTC' AS $$
DECLARE t record;results jsonb:='[]';BEGIN
 IF _limit IS NULL OR _limit NOT BETWEEN 1 AND 20 THEN RAISE EXCEPTION 'invalid_scheduler_limit' USING ERRCODE='22023'; END IF;
 FOR t IN SELECT tenant_id FROM public.cw_review_scans WHERE next_poll_at<=clock_timestamp() ORDER BY next_poll_at,tenant_id LIMIT _limit FOR UPDATE SKIP LOCKED LOOP
  results:=results||jsonb_build_array(public._review_process(t.tenant_id,gen_random_uuid(),NULL));
 END LOOP;
 RETURN jsonb_build_object('attempts',results);
END $$;
CREATE FUNCTION public.prepare_scheduled_reviews(_tenant_id uuid,_operation_id uuid) RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=public SET TimeZone='UTC' AS $$
BEGIN
 PERFORM 1 FROM public.tenants WHERE id=_tenant_id FOR SHARE;
 IF NOT public.has_tenant_role(_tenant_id,ARRAY['admin','operator']::public.member_role[]) THEN RAISE EXCEPTION 'review_writer_required' USING ERRCODE='42501'; END IF;
 IF _operation_id IS NULL THEN RAISE EXCEPTION 'operation_id_required' USING ERRCODE='22023'; END IF;
 RETURN public._review_process(_tenant_id,_operation_id,auth.uid());
END $$;
CREATE FUNCTION public.scheduled_reviews(_tenant_id uuid,_status text DEFAULT '',_indicator text DEFAULT '',_after text DEFAULT '',_limit integer DEFAULT 25)
RETURNS jsonb LANGUAGE plpgsql STABLE SECURITY INVOKER SET search_path=public AS $$
DECLARE items jsonb;more boolean;next_key text;BEGIN
 IF NOT public.is_tenant_member(_tenant_id) THEN RAISE EXCEPTION 'tenant_membership_required' USING ERRCODE='42501'; END IF;
 IF _limit IS NULL OR _limit NOT BETWEEN 1 AND 100 OR _status IS NULL OR _status NOT IN ('','pending','available','waiting','current','closed','retired') OR _indicator IS NULL OR length(_indicator)>200 OR _after IS NULL OR length(_after)>500 THEN RAISE EXCEPTION 'invalid_review_filter' USING ERRCODE='22023'; END IF;
 WITH page AS (SELECT e.*,
  (coalesce((facts->>'status'='waiting' AND least((facts->>'review_at')::timestamptz,(facts->>'next_measurement_at')::timestamptz)<=clock_timestamp()),false)
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
REVOKE ALL ON FUNCTION public._review_register_tenant(),public._review_sources(uuid,text),public._review_facts(uuid,jsonb),public._review_store(uuid,jsonb,jsonb,uuid),public._review_process(uuid,uuid,uuid),public.process_review_schedule(integer),public.prepare_scheduled_reviews(uuid,uuid),public.scheduled_reviews(uuid,text,text,text,integer) FROM PUBLIC,anon,authenticated,service_role,centerway_review_scheduler;
GRANT EXECUTE ON FUNCTION public.process_review_schedule(integer) TO centerway_review_scheduler;
GRANT EXECUTE ON FUNCTION public.prepare_scheduled_reviews(uuid,uuid),public.scheduled_reviews(uuid,text,text,text,integer) TO authenticated;
NOTIFY pgrst,'reload schema';
