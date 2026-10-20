-- Depends on 0020 (GitHub history). No reconciliation marker or rewrite of installed history.
-- Cycle boundaries partition immutable events; no historical case/event is rewritten.
ALTER TABLE public.cw_operational_events ADD CONSTRAINT cwop_events_cycle_ref UNIQUE(tenant_id,case_id,id);
CREATE TABLE public.cw_operational_cycles (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), tenant_id uuid NOT NULL, case_id uuid NOT NULL,
 number integer NOT NULL CHECK(number>0), start_sequence integer NOT NULL CHECK(start_sequence>=0),
 reason text NOT NULL, reference text NOT NULL, previous_decision_id uuid,
 created_by uuid NOT NULL, created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 UNIQUE(tenant_id,case_id,id), UNIQUE(case_id,number), UNIQUE(case_id,start_sequence),
 FOREIGN KEY(tenant_id,case_id) REFERENCES public.cw_operational_cases(tenant_id,id),
 FOREIGN KEY(tenant_id,case_id,previous_decision_id) REFERENCES public.cw_operational_events(tenant_id,case_id,id),
 CHECK((number=1 AND start_sequence=0 AND previous_decision_id IS NULL) OR (number>1 AND start_sequence>0 AND previous_decision_id IS NOT NULL))
);
REVOKE ALL ON public.cw_operational_cycles FROM PUBLIC,anon,authenticated,service_role;
GRANT SELECT ON public.cw_operational_cycles TO authenticated;
ALTER TABLE public.cw_operational_cycles ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_read ON public.cw_operational_cycles FOR SELECT TO authenticated USING(public.is_tenant_member(tenant_id));
CREATE TRIGGER immutable BEFORE UPDATE OR DELETE ON public.cw_operational_cycles FOR EACH ROW EXECUTE FUNCTION public._c02_immutable();
-- Historical first-cycle metadata is derived from the original human opening, not invented history.
INSERT INTO public.cw_operational_cycles(id,tenant_id,case_id,number,start_sequence,reason,reference,created_by,created_at)
 SELECT id,tenant_id,id,1,0,opening_definition->>'eligibility_reason',opening_definition->>'eligibility_ref',created_by,created_at FROM public.cw_operational_cases;
CREATE FUNCTION public._cwop_initial_cycle() RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER SET search_path=public AS $$
BEGIN
 INSERT INTO public.cw_operational_cycles(id,tenant_id,case_id,number,start_sequence,reason,reference,created_by,created_at)
 VALUES(NEW.id,NEW.tenant_id,NEW.id,1,0,NEW.opening_definition->>'eligibility_reason',NEW.opening_definition->>'eligibility_ref',NEW.created_by,NEW.created_at);
 RETURN NEW;
END $$;
REVOKE ALL ON FUNCTION public._cwop_initial_cycle() FROM PUBLIC,anon,authenticated,service_role;
CREATE TRIGGER initial_cycle AFTER INSERT ON public.cw_operational_cases FOR EACH ROW EXECUTE FUNCTION public._cwop_initial_cycle();
CREATE TRIGGER audit AFTER INSERT ON public.cw_operational_cycles FOR EACH ROW EXECUTE FUNCTION public._cw_audit();

-- Keep the established command engine and every C05-C10 validation. Only scope its event lookups
-- and add the explicit human continuation transition. Guard extraction anchors against drift.
DO $extend$
DECLARE src text;anchor text;
BEGIN
 SELECT pg_get_functiondef('public.command_operational_case(uuid,uuid,integer,uuid,text,jsonb)'::regprocedure) INTO src;
 anchor:='DECLARE c public.cw_operational_cases;';
 IF position(anchor IN src)=0 OR position('single_intervention_cycle' IN src)=0 THEN RAISE EXCEPTION 'command engine changed; review cycle integration'; END IF;
 src:=replace(src,anchor,anchor||' cycle public.cw_operational_cycles;');
 anchor:='  SELECT * INTO cfg FROM public.c04_configurations WHERE tenant_id=_tenant_id AND id=c.configuration_id;';
 IF position(anchor IN src)=0 THEN RAISE EXCEPTION 'configuration anchor changed'; END IF;
 src:=replace(src,anchor,$branch$
  SELECT * INTO cycle FROM public.cw_operational_cycles WHERE tenant_id=_tenant_id AND case_id=c.id ORDER BY number DESC LIMIT 1;
  IF cycle.id IS NULL THEN RAISE EXCEPTION 'cycle_metadata_missing' USING ERRCODE='22023'; END IF;
  IF _command='start_cycle' THEN
    IF NOT public.has_tenant_role(_tenant_id,ARRAY['admin']::public.member_role[]) THEN RAISE EXCEPTION 'admin_required' USING ERRCODE='42501'; END IF;
    IF c.state<>'remain_open' THEN RAISE EXCEPTION 'remain_open_required' USING ERRCODE='22023'; END IF;
    PERFORM public._cwop_keys(_payload,ARRAY['reason','reference']);
    PERFORM public._cwop_text(_payload,'reason'); PERFORM public._cwop_reference(_payload,'reference');
    IF EXISTS(SELECT FROM public.c04_configurations pinned JOIN public.c04_configurations newer
      ON newer.tenant_id=pinned.tenant_id AND newer.subject_id=pinned.subject_id AND newer.indicator_key=pinned.indicator_key AND newer.version>pinned.version
      WHERE pinned.tenant_id=_tenant_id AND pinned.id=c.configuration_id) THEN
      RAISE EXCEPTION 'configuration_revision_requires_review' USING ERRCODE='22023'; END IF;
    SELECT * INTO comparison FROM public.cw_operational_events WHERE tenant_id=_tenant_id AND case_id=c.id AND sequence=c.version
      AND sequence>=cycle.start_sequence AND command='decide' AND to_state='remain_open';
    IF comparison.id IS NULL THEN RAISE EXCEPTION 'continuation_decision_required' USING ERRCODE='22023'; END IF;
    INSERT INTO public.cw_operational_cycles(tenant_id,case_id,number,start_sequence,reason,reference,previous_decision_id,created_by)
    VALUES(_tenant_id,c.id,cycle.number+1,c.version+1,_payload->>'reason',_payload->>'reference',comparison.id,auth.uid()) RETURNING * INTO cycle;
    INSERT INTO public.cw_operational_events(tenant_id,subject_id,case_id,sequence,operation_id,request_hash,command,from_state,to_state,details,created_by)
    VALUES(_tenant_id,c.subject_id,c.id,c.version+1,_operation_id,h,'start_cycle',c.state,'investigation',
      _payload||jsonb_build_object('cycle_id',cycle.id,'cycle_number',cycle.number,'previous_decision_id',comparison.id,'configuration_id',c.configuration_id),auth.uid()) RETURNING id INTO v_id;
    UPDATE public.cw_operational_cases SET state='investigation',version=version+1 WHERE id=c.id;
    RETURN v_id;
  END IF;
$branch$||anchor);
 src:=replace(src,'WHERE case_id=c.id AND command=','WHERE case_id=c.id AND sequence>=cycle.start_sequence AND command=');
 src:=replace(src,'''single_intervention_cycle''','''cycle_already_executed''');
 -- An application version conflict is not a PostgreSQL serialization retry. PostgREST retries
 -- SQLSTATE 40001; use its explicit HTTP409 state to return the conflict without a retry loop.
 src:=replace(src,'''case_version_conflict'' USING ERRCODE=''40001''','''case_version_conflict'' USING ERRCODE=''PT409''');
 anchor:='c.state,next_state,d,auth.uid()';
 IF position(anchor IN src)=0 THEN RAISE EXCEPTION 'event persistence anchor changed'; END IF;
 src:=replace(src,anchor,'c.state,next_state,d||jsonb_build_object(''cycle_id'',cycle.id,''cycle_number'',cycle.number),auth.uid()');
 EXECUTE src;
END $extend$;

-- Central and scheduler share this projection. Ignore every earlier cycle's authorization,
-- execution, investigation and comparison when orienting the current cycle.
DO $projection$
DECLARE src text;anchor text;ctx text;
BEGIN
 SELECT pg_get_functiondef('public._core_followup_projection(uuid,text,text,text,text,integer)'::regprocedure) INTO src;
 anchor:='SELECT k.*,c.indicator_key';
 IF position(anchor IN src)=0 THEN RAISE EXCEPTION 'Core projection changed'; END IF;
 src:=replace(src,anchor,'SELECT k.*,cy.id AS cycle_id,cy.number AS cycle_number,c.indicator_key');
 anchor:='FROM public.cw_operational_cases k JOIN subjects s ON s.id=k.subject_id';
 IF position(anchor IN src)=0 THEN RAISE EXCEPTION 'Core cycle join anchor changed'; END IF;
 src:=replace(src,anchor,anchor||' JOIN LATERAL(SELECT * FROM public.cw_operational_cycles cy WHERE cy.tenant_id=k.tenant_id AND cy.case_id=k.id ORDER BY number DESC LIMIT 1) cy ON true');
 ctx:=split_part(split_part(src,'), case_context AS (',2),'), case_rows AS (',1);
 IF ctx='' THEN RAISE EXCEPTION 'Core context boundary changed'; END IF;
 src:=replace(src,ctx,replace(ctx,'e.case_id=k.id AND','e.case_id=k.id AND e.sequence>=cy.start_sequence AND'));
 anchor:='jsonb_build_object(''opening'',k.opening_definition';
 IF position(anchor IN src)=0 THEN RAISE EXCEPTION 'Core basis anchor changed'; END IF;
 src:=replace(src,anchor,'jsonb_build_object(''cycle_id'',k.cycle_id,''cycle_number'',k.cycle_number,''opening'',k.opening_definition');
 EXECUTE src;
END $projection$;

-- Fully tenant-scoped, paginated history plus current/selected cycle heads. No mutation on read.
CREATE FUNCTION public.operational_cycle_history(_tenant_id uuid,_case_id uuid,_cycle_id uuid DEFAULT NULL,_before_cycle integer DEFAULT NULL,_after_event integer DEFAULT -1,_limit integer DEFAULT 25)
RETURNS jsonb LANGUAGE plpgsql STABLE SECURITY INVOKER SET search_path=public AS $$
DECLARE c public.cw_operational_cases;active public.cw_operational_cycles;chosen public.cw_operational_cycles;
 end_sequence integer;cycles jsonb;events jsonb;heads jsonb;more_cycles boolean;more_events boolean;
BEGIN
 IF NOT public.is_tenant_member(_tenant_id) THEN RAISE EXCEPTION 'tenant_membership_required' USING ERRCODE='42501'; END IF;
 IF _limit IS NULL OR _limit NOT BETWEEN 1 AND 100 OR _after_event IS NULL OR _after_event< -1 OR (_before_cycle IS NOT NULL AND _before_cycle<1) THEN RAISE EXCEPTION 'invalid_history_filter' USING ERRCODE='22023'; END IF;
 SELECT * INTO c FROM public.cw_operational_cases WHERE tenant_id=_tenant_id AND id=_case_id;
 IF c.id IS NULL THEN RAISE EXCEPTION 'case_not_found' USING ERRCODE='22023'; END IF;
 SELECT * INTO active FROM public.cw_operational_cycles WHERE tenant_id=_tenant_id AND case_id=c.id ORDER BY number DESC LIMIT 1;
 SELECT * INTO chosen FROM public.cw_operational_cycles WHERE tenant_id=_tenant_id AND case_id=c.id AND id=coalesce(_cycle_id,active.id);
 IF chosen.id IS NULL THEN RAISE EXCEPTION 'cycle_not_found' USING ERRCODE='22023'; END IF;
 SELECT min(start_sequence) INTO end_sequence FROM public.cw_operational_cycles WHERE tenant_id=_tenant_id AND case_id=c.id AND number>chosen.number;
 end_sequence:=coalesce(end_sequence,c.version+1);
 SELECT coalesce(jsonb_agg(to_jsonb(x)-'n' ORDER BY number DESC) FILTER(WHERE n<=_limit),'[]'),count(*)>_limit INTO cycles,more_cycles
 FROM(SELECT cy.*,row_number() OVER(ORDER BY number DESC) n FROM public.cw_operational_cycles cy WHERE tenant_id=_tenant_id AND case_id=c.id AND (_before_cycle IS NULL OR number<_before_cycle) ORDER BY number DESC LIMIT _limit+1)x;
 SELECT coalesce(jsonb_agg(to_jsonb(x)-'n' ORDER BY sequence) FILTER(WHERE n<=_limit),'[]'),count(*)>_limit INTO events,more_events
 FROM(SELECT e.*,row_number() OVER(ORDER BY sequence) n FROM public.cw_operational_events e WHERE tenant_id=_tenant_id AND case_id=c.id AND sequence>=chosen.start_sequence AND sequence<end_sequence AND sequence>_after_event ORDER BY sequence LIMIT _limit+1)x;
 SELECT coalesce(jsonb_object_agg(command,to_jsonb(x)),'{}') INTO heads FROM(
  SELECT DISTINCT ON(command) e.* FROM public.cw_operational_events e WHERE tenant_id=_tenant_id AND case_id=c.id AND sequence>=chosen.start_sequence AND sequence<end_sequence ORDER BY command,sequence DESC)x;
 RETURN jsonb_build_object('tenant_id',_tenant_id,'case_id',c.id,'subject_id',c.subject_id,'case_version',c.version,'current',to_jsonb(active),'selected',to_jsonb(chosen),
  'cycles',cycles,'has_more_cycles',more_cycles,'events',events,'has_more_events',more_events,'heads',heads);
END $$;
REVOKE ALL ON FUNCTION public.operational_cycle_history(uuid,uuid,uuid,integer,integer,integer) FROM PUBLIC,anon,authenticated,service_role;
GRANT EXECUTE ON FUNCTION public.operational_cycle_history(uuid,uuid,uuid,integer,integer,integer) TO authenticated;
NOTIFY pgrst,'reload schema';
