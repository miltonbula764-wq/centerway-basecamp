BEGIN;
CREATE TABLE centerway.recovery_plans (
 tenant_id uuid NOT NULL, client_id uuid NOT NULL, id uuid NOT NULL,
 decision_id uuid NOT NULL, contract_id uuid NOT NULL, pre_revision integer NOT NULL, post_revision integer NOT NULL,
 reason centerway.label NOT NULL, actor name NOT NULL, recorded_at timestamptz NOT NULL,
 PRIMARY KEY(tenant_id,client_id,id),
 FOREIGN KEY(tenant_id,client_id,decision_id) REFERENCES centerway.intervention_decisions(tenant_id,client_id,id),
 FOREIGN KEY(tenant_id,client_id,contract_id,pre_revision) REFERENCES centerway.contract_versions(tenant_id,client_id,id,revision),
 FOREIGN KEY(tenant_id,client_id,contract_id,post_revision) REFERENCES centerway.contract_versions(tenant_id,client_id,id,revision)
);
CREATE TABLE centerway.recovery_runs (
 tenant_id uuid NOT NULL, client_id uuid NOT NULL, plan_id uuid NOT NULL, id uuid NOT NULL,
 algorithm text NOT NULL CHECK(algorithm='f05-v1'), as_of timestamptz NOT NULL CHECK(isfinite(as_of)),
 revision integer NOT NULL CHECK(revision>0), revision_of uuid, input_hash text NOT NULL CHECK(input_hash ~ '^[0-9a-f]{64}$'),
 input_snapshot jsonb NOT NULL, result jsonb NOT NULL, actor name NOT NULL, recorded_at timestamptz NOT NULL,
 PRIMARY KEY(tenant_id,client_id,plan_id,id),
 CHECK((revision=1)=(revision_of IS NULL)),
 UNIQUE(tenant_id,client_id,plan_id,as_of,input_hash), UNIQUE(tenant_id,client_id,plan_id,as_of,revision),
 FOREIGN KEY(tenant_id,client_id,plan_id) REFERENCES centerway.recovery_plans(tenant_id,client_id,id),
 FOREIGN KEY(tenant_id,client_id,plan_id,revision_of) REFERENCES centerway.recovery_runs(tenant_id,client_id,plan_id,id)
);
DO $$ DECLARE t text; BEGIN
 FOREACH t IN ARRAY ARRAY['recovery_plans','recovery_runs'] LOOP
 EXECUTE format('ALTER TABLE centerway.%I ENABLE ROW LEVEL SECURITY',t);
 EXECUTE format('ALTER TABLE centerway.%I FORCE ROW LEVEL SECURITY',t);
 EXECUTE format('CREATE POLICY tenant_access ON centerway.%I USING(centerway.allowed(tenant_id)) WITH CHECK(centerway.allowed(tenant_id))',t);
 EXECUTE format('CREATE TRIGGER immutable BEFORE UPDATE OR DELETE OR TRUNCATE ON centerway.%I FOR EACH STATEMENT EXECUTE FUNCTION centerway.immutable()',t);
 EXECUTE format('CREATE TRIGGER audit AFTER INSERT ON centerway.%I FOR EACH ROW EXECUTE FUNCTION centerway.audit_insert()',t);
 EXECUTE format('GRANT SELECT ON centerway.%I TO centerway_api',t);
 END LOOP;
END $$;
CREATE FUNCTION centerway.create_recovery_plan(t uuid,c uuid,id uuid,d uuid,pre integer,post integer,why text) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,centerway,pg_temp AS $$
DECLARE original centerway.contract_versions; before_c centerway.contract_versions; after_c centerway.contract_versions;
 anchor timestamptz; plan centerway.recovery_plans;
BEGIN
 IF NOT coalesce(centerway.allowed(t),false) THEN RAISE EXCEPTION 'not_authorized' USING ERRCODE='42501'; END IF;
 SELECT cv.* INTO STRICT original FROM centerway.intervention_decisions dec
 JOIN centerway.investigations inv ON (inv.tenant_id,inv.client_id,inv.id)=(dec.tenant_id,dec.client_id,dec.investigation_id)
 JOIN centerway.contract_versions cv ON (cv.tenant_id,cv.client_id,cv.id,cv.revision)=(inv.tenant_id,inv.client_id,inv.contract_id,inv.contract_revision)
 WHERE (dec.tenant_id,dec.client_id,dec.id)=(t,c,d);
 SELECT * INTO STRICT before_c FROM centerway.contract_versions cv WHERE (cv.tenant_id,cv.client_id,cv.id,cv.revision)=(t,c,original.id,pre);
 SELECT * INTO STRICT after_c FROM centerway.contract_versions cv WHERE (cv.tenant_id,cv.client_id,cv.id,cv.revision)=(t,c,original.id,post);
 SELECT coalesce((SELECT e.recorded_at FROM centerway.intervention_executions e WHERE (e.tenant_id,e.client_id,e.decision_id)=(t,c,d) AND e.undo_of IS NULL),dec.recorded_at)
 INTO anchor FROM centerway.intervention_decisions dec WHERE (dec.tenant_id,dec.client_id,dec.id)=(t,c,d);
 IF before_c.period_end>anchor OR after_c.period_start<anchor
 OR before_c.period_end-before_c.period_start<>after_c.period_end-after_c.period_start
 OR (to_jsonb(before_c)-ARRAY['revision','period_start','period_end','actor','recorded_at','reason'])<>
    (to_jsonb(after_c)-ARRAY['revision','period_start','period_end','actor','recorded_at','reason'])
 OR (to_jsonb(original)-ARRAY['revision','period_start','period_end','actor','recorded_at','reason'])<>
    (to_jsonb(after_c)-ARRAY['revision','period_start','period_end','actor','recorded_at','reason']) THEN
 RAISE EXCEPTION 'incompatible_recovery_windows' USING ERRCODE='23514'; END IF;
 INSERT INTO centerway.recovery_plans VALUES(t,c,id,d,original.id,pre,post,why,session_user,clock_timestamp()) RETURNING * INTO plan;
 RETURN to_jsonb(plan);
END $$;
CREATE FUNCTION centerway.evaluate_recovery(t uuid,c uuid,p uuid,cutoff timestamptz) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,centerway,pg_temp SET timezone='UTC' SET datestyle='ISO, YMD' AS $$
DECLARE plan centerway.recovery_plans; detection jsonb; snapshot jsonb; b jsonb; a jsonb; contract jsonb;
 fingerprint text; prev centerway.recovery_runs; created centerway.recovery_runs;
 status text:='resultado_inconclusivo'; reason text; improvement boolean; minimum_met boolean; baseline_met boolean;
 delta numeric; successful boolean; reversed boolean; result jsonb;
BEGIN
 IF NOT coalesce(centerway.allowed(t),false) THEN RAISE EXCEPTION 'not_authorized' USING ERRCODE='42501'; END IF;
 IF cutoff IS NULL OR NOT isfinite(cutoff) OR cutoff>clock_timestamp() THEN RAISE EXCEPTION 'invalid_cutoff'; END IF;
 PERFORM pg_advisory_xact_lock(hashtextextended(t::text||c::text||p::text||'f05',0));
 SELECT * INTO STRICT plan FROM centerway.recovery_plans WHERE (tenant_id,client_id,id)=(t,c,p) AND recorded_at<=cutoff;
 detection:=centerway.run_detection(t,c,plan.contract_id,ARRAY[plan.pre_revision,plan.post_revision],cutoff,2);
 SELECT jsonb_build_object('plan',to_jsonb(plan),'detection',detection,'decision',to_jsonb(d),
 'executions',coalesce((SELECT jsonb_agg(to_jsonb(e) ORDER BY e.recorded_at,e.id) FROM centerway.intervention_executions e
 WHERE (e.tenant_id,e.client_id,e.decision_id)=(t,c,plan.decision_id) AND e.recorded_at<=cutoff),'[]'::jsonb))
 INTO snapshot FROM centerway.intervention_decisions d WHERE (d.tenant_id,d.client_id,d.id)=(t,c,plan.decision_id);
 fingerprint:=encode(sha256(convert_to(snapshot::text,'UTF8')),'hex');
 SELECT * INTO created FROM centerway.recovery_runs WHERE (tenant_id,client_id,plan_id,as_of,input_hash)=(t,c,p,cutoff,fingerprint);
 IF FOUND THEN RETURN to_jsonb(created); END IF;
 SELECT x INTO b FROM jsonb_array_elements(detection->'result'->'periods') x WHERE (x->>'contract_revision')::integer=plan.pre_revision;
 SELECT x INTO a FROM jsonb_array_elements(detection->'result'->'periods') x WHERE (x->>'contract_revision')::integer=plan.post_revision;
 SELECT x->'contract' INTO contract FROM jsonb_array_elements(detection->'input_snapshot') x WHERE (x->'contract'->>'revision')::integer=plan.post_revision;
 successful:=snapshot->'decision'->>'status'='executed' AND EXISTS(SELECT 1 FROM jsonb_array_elements(snapshot->'executions') x WHERE x->>'undo_of' IS NULL);
 reversed:=EXISTS(SELECT 1 FROM jsonb_array_elements(snapshot->'executions') x WHERE x->>'undo_of' IS NOT NULL AND (x->>'recorded_at')::timestamptz<=(contract->>'period_end')::timestamptz);
 IF NOT successful THEN reason:='intervention_not_executed';
 ELSIF reversed THEN reason:='intervention_reversed_before_window_end';
 ELSIF b->>'state'='resultado_inconclusivo' OR a->>'state'='resultado_inconclusivo' THEN reason:='insufficient_or_conflicting_outcome_evidence';
 ELSE
 delta:=(a->>'observed_value')::numeric-(b->>'observed_value')::numeric;
 improvement:=CASE WHEN contract->>'direction'='higher' THEN delta>0 ELSE delta<0 END;
 minimum_met:=a->>'state'='valor_demonstrado';
 baseline_met:=CASE WHEN contract->>'direction'='higher' THEN (a->>'observed_value')::numeric>=(contract->>'baseline')::numeric
 ELSE (a->>'observed_value')::numeric<=(contract->>'baseline')::numeric END;
 IF b->>'state'='valor_demonstrado' THEN reason:='no_prior_contractual_shortfall';
 ELSIF minimum_met THEN status:='recuperacao_completa'; reason:='contractual_minimum_restored';
 ELSIF improvement THEN status:='recuperacao_parcial'; reason:='improvement_below_contractual_minimum';
 ELSE status:='ausencia_de_recuperacao'; reason:='no_observed_improvement'; END IF;
 END IF;
 result:=jsonb_build_object('status',status,'reason',reason,'execution_succeeded',successful,
 'improvement_observed',improvement,'minimum_met',minimum_met,'baseline_met',baseline_met,'delta',delta,
 'before',b,'after',a,'baseline',contract->'baseline','minimum_acceptable',contract->'minimum_acceptable',
 'causal_attribution','not_established','independent_verification','not_established','evidence_basis','producer_declared_outcomes');
 SELECT * INTO prev FROM centerway.recovery_runs WHERE (tenant_id,client_id,plan_id,as_of)=(t,c,p,cutoff) ORDER BY revision DESC LIMIT 1;
 INSERT INTO centerway.recovery_runs VALUES(t,c,p,gen_random_uuid(),'f05-v1',cutoff,coalesce(prev.revision,0)+1,prev.id,fingerprint,snapshot,result,session_user,clock_timestamp()) RETURNING * INTO created;
 RETURN to_jsonb(created);
END $$;
CREATE FUNCTION centerway.read_recovery_context(t uuid,c uuid,p uuid,r uuid) RETURNS jsonb
LANGUAGE sql STABLE SECURITY INVOKER SET search_path=pg_catalog,centerway,pg_temp SET timezone='UTC' AS $$
 SELECT to_jsonb(x) FROM centerway.recovery_runs x WHERE (tenant_id,client_id,plan_id,id)=(t,c,p,r)
$$;
REVOKE ALL ON FUNCTION centerway.create_recovery_plan(uuid,uuid,uuid,uuid,integer,integer,text) FROM PUBLIC;
REVOKE ALL ON FUNCTION centerway.evaluate_recovery(uuid,uuid,uuid,timestamptz) FROM PUBLIC;
REVOKE ALL ON FUNCTION centerway.read_recovery_context(uuid,uuid,uuid,uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION centerway.create_recovery_plan(uuid,uuid,uuid,uuid,integer,integer,text) TO centerway_api;
GRANT EXECUTE ON FUNCTION centerway.evaluate_recovery(uuid,uuid,uuid,timestamptz) TO centerway_api;
GRANT EXECUTE ON FUNCTION centerway.read_recovery_context(uuid,uuid,uuid,uuid) TO centerway_api;
COMMIT;
