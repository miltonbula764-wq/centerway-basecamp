-- Provisional 0022: depends on the pending 0020 -> 0021 installation. No reconciliation marker.
CREATE TABLE public.cw_case_assignments (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),tenant_id uuid NOT NULL,case_id uuid NOT NULL,
 revision integer NOT NULL CHECK(revision>0),assignee_id uuid,assignee_membership_id uuid,
 reason text NOT NULL,reference text NOT NULL,created_by uuid NOT NULL,created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 operation_id uuid NOT NULL,request_hash text NOT NULL,UNIQUE(tenant_id,id),UNIQUE(case_id,revision),UNIQUE(tenant_id,operation_id),
 CHECK((assignee_id IS NULL)=(assignee_membership_id IS NULL)),
 FOREIGN KEY(tenant_id,case_id) REFERENCES public.cw_operational_cases(tenant_id,id)
);
CREATE INDEX cw_case_assignments_latest ON public.cw_case_assignments(tenant_id,case_id,revision DESC);
CREATE TABLE public.cw_notifications (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),tenant_id uuid NOT NULL REFERENCES public.tenants(id),recipient_id uuid NOT NULL,recipient_membership_id uuid NOT NULL,
 source_kind text NOT NULL,source_id uuid NOT NULL,kind text NOT NULL,required_role text NOT NULL CHECK(required_role IN ('read','admin_or_operator','admin')),
 subject_id uuid,case_id uuid,payload jsonb NOT NULL,created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 UNIQUE(tenant_id,id),UNIQUE(tenant_id,recipient_membership_id,source_kind,source_id,kind),
 FOREIGN KEY(tenant_id,subject_id) REFERENCES public.subjects(tenant_id,id),FOREIGN KEY(tenant_id,case_id) REFERENCES public.cw_operational_cases(tenant_id,id)
);
CREATE INDEX cw_notifications_inbox ON public.cw_notifications(tenant_id,recipient_id,created_at DESC,id DESC);
CREATE TABLE public.cw_notification_reads (
 tenant_id uuid NOT NULL,notification_id uuid NOT NULL,recipient_id uuid NOT NULL,created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 PRIMARY KEY(tenant_id,notification_id,recipient_id),FOREIGN KEY(tenant_id,notification_id) REFERENCES public.cw_notifications(tenant_id,id)
);
CREATE TABLE public.cw_notification_jobs (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),tenant_id uuid NOT NULL REFERENCES public.tenants(id),source_kind text NOT NULL CHECK(source_kind IN ('assignment','core','review','attempt')),
 source_id uuid NOT NULL,created_at timestamptz NOT NULL DEFAULT clock_timestamp(),status text NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','failed','completed','skipped')),
 attempts integer NOT NULL DEFAULT 0,error_code text,next_try_at timestamptz NOT NULL DEFAULT clock_timestamp(),finished_at timestamptz,
 UNIQUE(tenant_id,id),UNIQUE(tenant_id,source_kind,source_id)
);
CREATE INDEX cw_notification_jobs_due ON public.cw_notification_jobs(tenant_id,next_try_at,id) WHERE status IN ('pending','failed');
CREATE TABLE public.cw_notification_attempts (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),tenant_id uuid NOT NULL,job_id uuid NOT NULL,number integer NOT NULL,
 status text NOT NULL CHECK(status IN ('completed','failed','skipped')),error_code text,created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 UNIQUE(job_id,number),FOREIGN KEY(tenant_id,job_id) REFERENCES public.cw_notification_jobs(tenant_id,id)
);
DO $$ DECLARE t text;BEGIN
 FOREACH t IN ARRAY ARRAY['cw_case_assignments','cw_notifications','cw_notification_reads','cw_notification_jobs','cw_notification_attempts'] LOOP
  EXECUTE format('REVOKE ALL ON public.%I FROM PUBLIC,anon,authenticated,service_role,centerway_review_scheduler',t);
  EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY',t);
  EXECUTE format('GRANT SELECT ON public.%I TO authenticated',t);
  IF t<>'cw_notification_jobs' THEN EXECUTE format('CREATE TRIGGER immutable BEFORE UPDATE OR DELETE ON public.%I FOR EACH ROW EXECUTE FUNCTION public._c02_immutable()',t); END IF;
 END LOOP;
END $$;
CREATE POLICY tenant_read ON public.cw_case_assignments FOR SELECT TO authenticated USING(public.is_tenant_member(tenant_id));
CREATE POLICY recipient_read ON public.cw_notifications FOR SELECT TO authenticated USING(recipient_id=auth.uid() AND EXISTS(
 SELECT FROM public.memberships m WHERE m.tenant_id=cw_notifications.tenant_id AND m.id=cw_notifications.recipient_membership_id AND m.user_id=auth.uid()
 AND (required_role='read' OR m.role='admin' OR (required_role='admin_or_operator' AND m.role='operator'))));
CREATE POLICY recipient_read ON public.cw_notification_reads FOR SELECT TO authenticated USING(recipient_id=auth.uid() AND EXISTS(SELECT FROM public.cw_notifications n WHERE n.tenant_id=cw_notification_reads.tenant_id AND n.id=notification_id));
CREATE POLICY admin_read ON public.cw_notification_jobs FOR SELECT TO authenticated USING(public.has_tenant_role(tenant_id,ARRAY['admin']::public.member_role[]));
CREATE POLICY admin_read ON public.cw_notification_attempts FOR SELECT TO authenticated USING(public.has_tenant_role(tenant_id,ARRAY['admin']::public.member_role[]));
CREATE TRIGGER audit AFTER INSERT ON public.cw_case_assignments FOR EACH ROW EXECUTE FUNCTION public._cw_audit();

-- One Core classifier, now with an exact subject scope for private notification/my-work queries.
-- Public and scheduler interfaces keep their existing signatures and same membership/RLS guards.
DO $$ DECLARE src text;anchor text;BEGIN
 SELECT pg_get_functiondef('public._core_followup_projection(uuid,text,text,text,text,integer)'::regprocedure) INTO src;
 anchor:='SELECT s.* FROM public.subjects s WHERE s.tenant_id=_tenant_id';
 IF position(anchor IN src)=0 THEN RAISE EXCEPTION 'Core subject scope changed';END IF;
 src:='CREATE FUNCTION public._core_followup_engine(_tenant_id uuid,_client text,_indicator text,_category text,_after text,_limit integer,_subject_id uuid,_case_id uuid)'||substring(src FROM position(E'\n' IN src));
 src:=replace(src,anchor,anchor||' AND (_subject_id IS NULL OR s.id=_subject_id)');
 src:=replace(src,'WHERE NOT EXISTS(SELECT FROM public.cw_operational_cases k','WHERE _case_id IS NULL AND NOT EXISTS(SELECT FROM public.cw_operational_cases k');
 src:=replace(src,'WHERE k.tenant_id=_tenant_id','WHERE k.tenant_id=_tenant_id AND (_case_id IS NULL OR k.id=_case_id)');EXECUTE src;
END $$;
REVOKE ALL ON FUNCTION public._core_followup_engine(uuid,text,text,text,text,integer,uuid,uuid) FROM PUBLIC,anon,authenticated,service_role,centerway_review_scheduler;
GRANT EXECUTE ON FUNCTION public._core_followup_engine(uuid,text,text,text,text,integer,uuid,uuid) TO authenticated;
CREATE OR REPLACE FUNCTION public._core_followup_projection(_tenant_id uuid,_client text DEFAULT '',_indicator text DEFAULT '',_category text DEFAULT '',_after text DEFAULT '',_limit integer DEFAULT 25)
RETURNS jsonb LANGUAGE sql STABLE SECURITY INVOKER SET search_path=public AS $$ SELECT public._core_followup_engine(_tenant_id,_client,_indicator,_category,_after,_limit,NULL,NULL) $$;

CREATE FUNCTION public._assignment_valid(a public.cw_case_assignments) RETURNS boolean LANGUAGE sql STABLE SET search_path=public AS $$
 SELECT EXISTS(SELECT FROM public.memberships m WHERE m.tenant_id=a.tenant_id AND m.user_id=a.assignee_id AND m.id=a.assignee_membership_id AND m.role IN ('admin','operator'))
$$;
CREATE FUNCTION public._notification_put(_tenant uuid,_user uuid,_source text,_source_id uuid,_kind text,_role text,_subject uuid,_case uuid,_payload jsonb)
RETURNS void LANGUAGE sql SET search_path=public AS $$
 INSERT INTO public.cw_notifications(tenant_id,recipient_id,recipient_membership_id,source_kind,source_id,kind,required_role,subject_id,case_id,payload)
 SELECT _tenant,m.user_id,m.id,_source,_source_id,_kind,_role,_subject,_case,_payload FROM public.memberships m WHERE m.tenant_id=_tenant AND m.user_id=_user
 AND (_role='read' OR m.role='admin' OR (_role='admin_or_operator' AND m.role='operator'))
 ON CONFLICT(tenant_id,recipient_membership_id,source_kind,source_id,kind) DO NOTHING
$$;
CREATE FUNCTION public._notification_deliver(j public.cw_notification_jobs) RETURNS boolean LANGUAGE plpgsql SET search_path=public AS $$
DECLARE a public.cw_case_assignments;old public.cw_case_assignments;e public.cw_operational_events;r public.cw_review_events;attempt public.cw_review_attempts;
 c public.cw_operational_cases;q jsonb;source jsonb;facts jsonb;kind text;required text:='admin_or_operator';subject uuid;cid uuid;u record;p jsonb;origin text:=j.source_kind;origin_id uuid:=j.source_id;
BEGIN
 IF j.source_kind='assignment' THEN
  SELECT * INTO a FROM public.cw_case_assignments WHERE tenant_id=j.tenant_id AND id=j.source_id;
  SELECT * INTO c FROM public.cw_operational_cases WHERE tenant_id=j.tenant_id AND id=a.case_id;
  SELECT * INTO old FROM public.cw_case_assignments WHERE case_id=a.case_id AND revision=a.revision-1;
  p:=jsonb_build_object('assignment_id',a.id,'revision',a.revision,'reason',a.reason,'reference',a.reference,'assignee_id',a.assignee_id,'previous_assignee_id',old.assignee_id);
  IF public._assignment_valid(a) THEN PERFORM public._notification_put(j.tenant_id,a.assignee_id,'assignment',a.id,'case_assigned','admin_or_operator',c.subject_id,c.id,p);END IF;
  IF old.assignee_id IS NOT NULL AND old.assignee_id IS DISTINCT FROM a.assignee_id THEN PERFORM public._notification_put(j.tenant_id,old.assignee_id,'assignment',a.id,'responsibility_changed','read',c.subject_id,c.id,p);END IF;
  RETURN true;
 ELSIF j.source_kind='core' THEN
  SELECT * INTO e FROM public.cw_operational_events WHERE tenant_id=j.tenant_id AND id=j.source_id;
  SELECT * INTO c FROM public.cw_operational_cases WHERE tenant_id=j.tenant_id AND id=e.case_id;
  SELECT value INTO q FROM jsonb_array_elements(public._core_followup_engine(j.tenant_id,'','','','',100,c.subject_id,c.id)->'items') WHERE value->>'case_id'=c.id::text;
  IF q->>'next_action' IS DISTINCT FROM 'authorize' OR NOT EXISTS(SELECT FROM public.cw_operational_events p WHERE p.case_id=c.id AND p.command='plan' AND p.id=e.id
    AND p.sequence=(SELECT max(sequence) FROM public.cw_operational_events p2 WHERE p2.case_id=c.id AND p2.command='plan')
    AND p.sequence>=(SELECT max(start_sequence) FROM public.cw_operational_cycles WHERE case_id=c.id)) THEN RETURN false;END IF;
  kind:='authorization_needed';required:='admin';subject:=c.subject_id;cid:=c.id;p:=jsonb_build_object('event_id',e.id,'sequence',e.sequence,'cycle_id',q#>'{basis,cycle_id}','next_action',q->'next_action');
 ELSIF j.source_kind='review' THEN
  SELECT * INTO r FROM public.cw_review_events WHERE tenant_id=j.tenant_id AND id=j.source_id;
  -- A historical event is not presented as a currently available action after being superseded.
  IF NOT EXISTS(SELECT FROM public.cw_review_entries x WHERE x.tenant_id=j.tenant_id AND x.id=r.entry_id AND x.revision=r.revision) THEN RETURN false;END IF;
  source:=r.source;facts:=r.facts;
  IF source->>'kind'='legacy' THEN RETURN false;END IF;
  subject:=(source->>'subject_id')::uuid;cid:=(source->>'case_id')::uuid;
  IF cid IS NOT NULL THEN
   SELECT * INTO c FROM public.cw_operational_cases WHERE tenant_id=j.tenant_id AND id=cid;
   IF c.version IS DISTINCT FROM (source->>'case_version')::int THEN RETURN false;END IF;
  END IF;
  kind:=CASE WHEN source->>'next_action'='authorize' THEN 'authorization_needed'
    WHEN facts->>'status'='available' AND facts->'reasons' ? 'observation_window_elapsed_not_proof' THEN 'observation_ended'
    WHEN facts->'reasons' ? 'new_measurements_not_analysed' THEN 'evidence_review'
    WHEN facts->>'status'='available' THEN 'review_available' ELSE NULL END;
  IF kind IS NULL OR facts->>'status' IN ('closed','retired') THEN RETURN false;END IF;
  required:=CASE WHEN source->>'required_role'='admin' THEN 'admin' ELSE 'admin_or_operator' END;
  p:=jsonb_build_object('entry_id',r.entry_id,'revision',r.revision,'source',source,'facts',facts);
  -- The plan and its monitor snapshot share the same persisted occurrence.
  IF kind='authorization_needed' AND cid IS NOT NULL THEN
   SELECT ev.id INTO origin_id FROM public.cw_operational_events ev WHERE ev.tenant_id=j.tenant_id AND ev.case_id=cid
    AND ev.command=CASE WHEN source->>'state'='approved' THEN 'approve' ELSE 'plan' END
    AND ev.sequence>=(SELECT max(start_sequence) FROM public.cw_operational_cycles WHERE case_id=cid) ORDER BY sequence DESC LIMIT 1;
   IF origin_id IS NULL THEN RETURN false;END IF;origin:='core';
   p:=p||jsonb_build_object('event_id',origin_id);
  END IF;
 ELSE
  SELECT * INTO attempt FROM public.cw_review_attempts WHERE tenant_id=j.tenant_id AND id=j.source_id;
  IF attempt.status IS DISTINCT FROM 'failed' THEN RETURN false;END IF;
  kind:='operational_failure';required:='admin';p:=jsonb_build_object('attempt_id',attempt.id,'error_code',attempt.error_code,'finished_at',attempt.finished_at);
 END IF;
 IF cid IS NOT NULL THEN SELECT * INTO a FROM public.cw_case_assignments WHERE tenant_id=j.tenant_id AND case_id=cid ORDER BY revision DESC LIMIT 1;END IF;
 IF required<>'admin' AND public._assignment_valid(a) THEN
  PERFORM public._notification_put(j.tenant_id,a.assignee_id,origin,origin_id,kind,required,subject,cid,p);
 ELSE
  FOR u IN SELECT user_id FROM public.memberships WHERE tenant_id=j.tenant_id AND role='admin' LOOP
   PERFORM public._notification_put(j.tenant_id,u.user_id,origin,origin_id,kind,required,subject,cid,p);
  END LOOP;
 END IF;
 RETURN true;
END $$;
CREATE FUNCTION public._notification_process(_tenant uuid,_limit integer DEFAULT 25) RETURNS jsonb LANGUAGE plpgsql SET search_path=public AS $$
DECLARE j public.cw_notification_jobs;n integer:=0;code text;result text;delivered boolean;BEGIN
 FOR j IN SELECT * FROM public.cw_notification_jobs WHERE tenant_id=_tenant AND status IN ('pending','failed') AND next_try_at<=clock_timestamp() ORDER BY next_try_at,id LIMIT _limit FOR UPDATE SKIP LOCKED LOOP
  code:=NULL;
  BEGIN delivered:=public._notification_deliver(j);result:=CASE WHEN delivered THEN 'completed' ELSE 'skipped' END;
  EXCEPTION WHEN OTHERS THEN GET STACKED DIAGNOSTICS code=RETURNED_SQLSTATE;result:='failed';END;
  UPDATE public.cw_notification_jobs SET status=result,attempts=attempts+1,error_code=code,finished_at=clock_timestamp(),next_try_at=clock_timestamp()+CASE WHEN code IS NULL THEN interval '0 seconds' ELSE interval '1 minute' END WHERE id=j.id;
  INSERT INTO public.cw_notification_attempts(tenant_id,job_id,number,status,error_code) VALUES(_tenant,j.id,j.attempts+1,result,code);n:=n+1;
 END LOOP;RETURN jsonb_build_object('processed',n);
END $$;
CREATE FUNCTION public._notification_enqueue() RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER SET search_path=public AS $$
DECLARE source text:=TG_ARGV[0];j public.cw_notification_jobs;BEGIN
 IF source='core' THEN IF NEW.command<>'plan' THEN RETURN NEW;END IF;END IF;
 IF source='attempt' THEN IF NEW.status<>'failed' THEN RETURN NEW;END IF;END IF;
 INSERT INTO public.cw_notification_jobs(tenant_id,source_kind,source_id) VALUES(NEW.tenant_id,source,NEW.id) ON CONFLICT DO NOTHING RETURNING * INTO j;
 -- Assignment notices are atomic with that decision. Never lock other jobs while holding tenant UPDATE.
 IF source='assignment' AND j.id IS NOT NULL THEN
  PERFORM public._notification_deliver(j);
  UPDATE public.cw_notification_jobs SET status='completed',attempts=1,finished_at=clock_timestamp() WHERE id=j.id;
  INSERT INTO public.cw_notification_attempts(tenant_id,job_id,number,status) VALUES(NEW.tenant_id,j.id,1,'completed');
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER notify_assignment AFTER INSERT ON public.cw_case_assignments FOR EACH ROW EXECUTE FUNCTION public._notification_enqueue('assignment');
CREATE TRIGGER notify_plan AFTER INSERT ON public.cw_operational_events FOR EACH ROW EXECUTE FUNCTION public._notification_enqueue('core');
CREATE TRIGGER notify_review AFTER INSERT ON public.cw_review_events FOR EACH ROW EXECUTE FUNCTION public._notification_enqueue('review');
CREATE TRIGGER notify_review_failure AFTER INSERT ON public.cw_review_attempts FOR EACH ROW EXECUTE FUNCTION public._notification_enqueue('attempt');
DO $$ DECLARE src text;anchor text:=' RETURN to_jsonb(attempt);'||E'\nEND';BEGIN
 SELECT pg_get_functiondef('public._review_process(uuid,uuid,uuid)'::regprocedure) INTO src;
 IF position(anchor IN src)=0 THEN RAISE EXCEPTION 'Review processor integration anchor changed';END IF;
 EXECUTE replace(src,anchor,' PERFORM public._notification_process(_tenant,25);'||E'\n'||anchor);
END $$;
CREATE FUNCTION public.assign_operational_case(_tenant_id uuid,_case_id uuid,_assignee_id uuid,_reason text,_reference text,_expected_revision integer,_operation_id uuid)
RETURNS uuid LANGUAGE plpgsql SECURITY DEFINER SET search_path=public AS $$
DECLARE previous public.cw_case_assignments;m public.memberships;h text;v uuid;BEGIN
 PERFORM 1 FROM public.tenants WHERE id=_tenant_id FOR UPDATE;
 IF NOT public.has_tenant_role(_tenant_id,ARRAY['admin']::public.member_role[]) THEN RAISE EXCEPTION 'admin_required' USING ERRCODE='42501';END IF;
 IF _operation_id IS NULL OR _expected_revision IS NULL THEN RAISE EXCEPTION 'operation_and_revision_required' USING ERRCODE='22023';END IF;
 PERFORM 1 FROM public.cw_operational_cases WHERE tenant_id=_tenant_id AND id=_case_id;
 IF NOT FOUND THEN RAISE EXCEPTION 'case_not_found' USING ERRCODE='22023';END IF;
 h:=encode(sha256(convert_to(jsonb_build_array(_case_id,_assignee_id,_reason,_reference,_expected_revision)::text,'UTF8')),'hex');
 SELECT * INTO previous FROM public.cw_case_assignments WHERE tenant_id=_tenant_id AND operation_id=_operation_id;
 IF FOUND THEN IF previous.request_hash<>h THEN RAISE EXCEPTION 'idempotency_conflict' USING ERRCODE='22023';END IF;RETURN previous.id;END IF;
 SELECT * INTO previous FROM public.cw_case_assignments WHERE tenant_id=_tenant_id AND case_id=_case_id ORDER BY revision DESC LIMIT 1;
 IF coalesce(previous.revision,0)<>_expected_revision THEN RAISE EXCEPTION 'assignment_version_conflict' USING ERRCODE='PT409';END IF;
 IF previous.id IS NOT NULL AND previous.assignee_id IS NOT DISTINCT FROM _assignee_id AND (_assignee_id IS NULL OR public._assignment_valid(previous)) THEN RAISE EXCEPTION 'assignment_unchanged' USING ERRCODE='22023';END IF;
 PERFORM public._cwop_text(jsonb_build_object('reason',_reason),'reason');PERFORM public._cwop_reference(jsonb_build_object('reference',_reference),'reference');
 IF _assignee_id IS NOT NULL THEN
  SELECT * INTO m FROM public.memberships WHERE tenant_id=_tenant_id AND user_id=_assignee_id AND role IN ('admin','operator');
  IF m.id IS NULL THEN RAISE EXCEPTION 'authorized_tenant_member_required' USING ERRCODE='22023';END IF;
 END IF;
 INSERT INTO public.cw_case_assignments(tenant_id,case_id,revision,assignee_id,assignee_membership_id,reason,reference,created_by,operation_id,request_hash)
 VALUES(_tenant_id,_case_id,coalesce(previous.revision,0)+1,_assignee_id,m.id,_reason,_reference,auth.uid(),_operation_id,h) RETURNING id INTO v;RETURN v;
END $$;
CREATE FUNCTION public.case_responsibility(_tenant_id uuid,_case_id uuid,_before integer DEFAULT NULL,_limit integer DEFAULT 25)
RETURNS jsonb LANGUAGE plpgsql STABLE SECURITY INVOKER SET search_path=public AS $$
DECLARE current public.cw_case_assignments;items jsonb;more boolean;BEGIN
 IF NOT public.is_tenant_member(_tenant_id) THEN RAISE EXCEPTION 'tenant_membership_required' USING ERRCODE='42501';END IF;
 IF _limit IS NULL OR _limit NOT BETWEEN 1 AND 100 OR (_before IS NOT NULL AND _before<1) THEN RAISE EXCEPTION 'invalid_assignment_filter' USING ERRCODE='22023';END IF;
 IF NOT EXISTS(SELECT FROM public.cw_operational_cases WHERE tenant_id=_tenant_id AND id=_case_id) THEN RAISE EXCEPTION 'case_not_found' USING ERRCODE='22023';END IF;
 SELECT * INTO current FROM public.cw_case_assignments WHERE tenant_id=_tenant_id AND case_id=_case_id ORDER BY revision DESC LIMIT 1;
 SELECT coalesce(jsonb_agg(to_jsonb(x)-'n' ORDER BY revision DESC) FILTER(WHERE n<=_limit),'[]'),count(*)>_limit INTO items,more
 FROM(SELECT a.*,row_number() OVER(ORDER BY revision DESC)n FROM public.cw_case_assignments a WHERE tenant_id=_tenant_id AND case_id=_case_id AND (_before IS NULL OR revision<_before) ORDER BY revision DESC LIMIT _limit+1)x;
 RETURN jsonb_build_object('tenant_id',_tenant_id,'case_id',_case_id,'current',CASE WHEN current.id IS NULL THEN NULL ELSE to_jsonb(current) END,'valid',public._assignment_valid(current),'items',items,'has_more',more);
END $$;
CREATE FUNCTION public.my_operational_work(_tenant_id uuid,_after uuid DEFAULT NULL,_limit integer DEFAULT 25)
RETURNS jsonb LANGUAGE plpgsql STABLE SECURITY INVOKER SET search_path=public AS $$
DECLARE items jsonb:='[]';a record;q jsonb;n integer:=0;last_id uuid;more boolean:=false;BEGIN
 IF NOT public.is_tenant_member(_tenant_id) THEN RAISE EXCEPTION 'tenant_membership_required' USING ERRCODE='42501';END IF;
 IF _limit IS NULL OR _limit NOT BETWEEN 1 AND 100 THEN RAISE EXCEPTION 'invalid_work_filter' USING ERRCODE='22023';END IF;
 FOR a IN SELECT k.* FROM public.cw_operational_cases k JOIN LATERAL(SELECT x.* FROM public.cw_case_assignments x WHERE x.tenant_id=_tenant_id AND x.case_id=k.id ORDER BY revision DESC LIMIT 1)x ON true
 WHERE k.tenant_id=_tenant_id AND x.assignee_id=auth.uid() AND public._assignment_valid(x) AND (_after IS NULL OR k.id>_after) ORDER BY k.id LIMIT _limit+1 LOOP
  n:=n+1;IF n>_limit THEN more:=true;EXIT;END IF;
  SELECT value INTO q FROM jsonb_array_elements(public._core_followup_engine(_tenant_id,'','','','',100,a.subject_id,a.id)->'items') WHERE value->>'case_id'=a.id::text;
  items:=items||jsonb_build_array(q);last_id:=a.id;
 END LOOP;
 RETURN jsonb_build_object('tenant_id',_tenant_id,'user_id',auth.uid(),'items',items,'has_more',more,'next_cursor',last_id);
END $$;
CREATE FUNCTION public.notification_inbox(_tenant_id uuid,_unread_only boolean DEFAULT false,_before timestamptz DEFAULT NULL,_before_id uuid DEFAULT NULL,_limit integer DEFAULT 25)
RETURNS jsonb LANGUAGE plpgsql STABLE SECURITY INVOKER SET search_path=public AS $$
DECLARE items jsonb;more boolean;unread bigint;BEGIN
 IF NOT public.is_tenant_member(_tenant_id) THEN RAISE EXCEPTION 'tenant_membership_required' USING ERRCODE='42501';END IF;
 IF _limit IS NULL OR _limit NOT BETWEEN 1 AND 100 OR _unread_only IS NULL OR ((_before IS NULL)<>(_before_id IS NULL)) THEN RAISE EXCEPTION 'invalid_inbox_filter' USING ERRCODE='22023';END IF;
 SELECT count(*) INTO unread FROM public.cw_notifications n WHERE tenant_id=_tenant_id AND NOT EXISTS(SELECT FROM public.cw_notification_reads r WHERE r.tenant_id=n.tenant_id AND r.notification_id=n.id AND r.recipient_id=auth.uid());
 SELECT coalesce(jsonb_agg(to_jsonb(x)-'n' ORDER BY created_at DESC,id DESC) FILTER(WHERE n<=_limit),'[]'),count(*)>_limit INTO items,more FROM(
  SELECT n.*,EXISTS(SELECT FROM public.cw_notification_reads r WHERE r.tenant_id=n.tenant_id AND r.notification_id=n.id AND r.recipient_id=auth.uid()) AS is_read,
   row_number() OVER(ORDER BY n.created_at DESC,n.id DESC)n FROM public.cw_notifications n WHERE tenant_id=_tenant_id
   AND (_before IS NULL OR (n.created_at,n.id)<(_before,_before_id))
   AND (NOT _unread_only OR NOT EXISTS(SELECT FROM public.cw_notification_reads r WHERE r.tenant_id=n.tenant_id AND r.notification_id=n.id AND r.recipient_id=auth.uid()))
   ORDER BY n.created_at DESC,n.id DESC LIMIT _limit+1)x;
 RETURN jsonb_build_object('tenant_id',_tenant_id,'user_id',auth.uid(),'items',items,'has_more',more,'unread_count',unread,'processing',coalesce((SELECT jsonb_agg(x ORDER BY next_try_at,id) FROM (SELECT id,status,error_code,attempts,next_try_at FROM public.cw_notification_jobs WHERE tenant_id=_tenant_id AND status IN ('failed','pending') ORDER BY next_try_at,id LIMIT 5)x),'[]'));
END $$;
CREATE FUNCTION public.mark_notification_read(_tenant_id uuid,_notification_id uuid) RETURNS void LANGUAGE plpgsql SECURITY DEFINER SET search_path=public AS $$
BEGIN
 -- SECURITY DEFINER must explicitly enforce the same recipient, membership incarnation and role as RLS.
 IF NOT EXISTS(SELECT FROM public.cw_notifications n JOIN public.memberships m ON m.tenant_id=n.tenant_id AND m.id=n.recipient_membership_id AND m.user_id=auth.uid()
  WHERE n.tenant_id=_tenant_id AND n.id=_notification_id AND n.recipient_id=auth.uid()
   AND (n.required_role='read' OR m.role='admin' OR (n.required_role='admin_or_operator' AND m.role='operator'))) THEN RAISE EXCEPTION 'notification_unavailable' USING ERRCODE='42501';END IF;
 INSERT INTO public.cw_notification_reads(tenant_id,notification_id,recipient_id) VALUES(_tenant_id,_notification_id,auth.uid()) ON CONFLICT DO NOTHING;
END $$;
CREATE FUNCTION public.prepare_operational_notifications(_tenant_id uuid) RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=public AS $$
BEGIN
 PERFORM 1 FROM public.tenants WHERE id=_tenant_id FOR SHARE;
 IF NOT public.has_tenant_role(_tenant_id,ARRAY['admin','operator']::public.member_role[]) THEN RAISE EXCEPTION 'write_role_required' USING ERRCODE='42501';END IF;
 RETURN public._notification_process(_tenant_id,25);
END $$;
REVOKE ALL ON FUNCTION public._assignment_valid(public.cw_case_assignments),public._notification_put(uuid,uuid,text,uuid,text,text,uuid,uuid,jsonb),public._notification_deliver(public.cw_notification_jobs),public._notification_process(uuid,integer),public._notification_enqueue(),public.assign_operational_case(uuid,uuid,uuid,text,text,integer,uuid),public.case_responsibility(uuid,uuid,integer,integer),public.my_operational_work(uuid,uuid,integer),public.notification_inbox(uuid,boolean,timestamptz,uuid,integer),public.mark_notification_read(uuid,uuid),public.prepare_operational_notifications(uuid) FROM PUBLIC,anon,authenticated,service_role,centerway_review_scheduler;
GRANT EXECUTE ON FUNCTION public._assignment_valid(public.cw_case_assignments),public.assign_operational_case(uuid,uuid,uuid,text,text,integer,uuid),public.case_responsibility(uuid,uuid,integer,integer),public.my_operational_work(uuid,uuid,integer),public.notification_inbox(uuid,boolean,timestamptz,uuid,integer),public.mark_notification_read(uuid,uuid),public.prepare_operational_notifications(uuid) TO authenticated;
NOTIFY pgrst,'reload schema';
