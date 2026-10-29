BEGIN;
CREATE TABLE centerway.operation_receipts (
 tenant_id uuid NOT NULL, client_id uuid NOT NULL, request_id uuid NOT NULL,
 operation text NOT NULL, arguments jsonb NOT NULL, status text NOT NULL CHECK(status IN ('completed','error')),
 result jsonb NOT NULL, actor name NOT NULL, recorded_at timestamptz NOT NULL,
 PRIMARY KEY(tenant_id,client_id,request_id),
 FOREIGN KEY(tenant_id,client_id) REFERENCES centerway.clients(tenant_id,client_id)
);
ALTER TABLE centerway.operation_receipts ENABLE ROW LEVEL SECURITY;
ALTER TABLE centerway.operation_receipts FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_access ON centerway.operation_receipts USING(centerway.allowed(tenant_id)) WITH CHECK(centerway.allowed(tenant_id));
CREATE TRIGGER immutable BEFORE UPDATE OR DELETE OR TRUNCATE ON centerway.operation_receipts FOR EACH STATEMENT EXECUTE FUNCTION centerway.immutable();
CREATE TRIGGER audit AFTER INSERT ON centerway.operation_receipts FOR EACH ROW EXECUTE FUNCTION centerway.audit_insert();
GRANT SELECT ON centerway.operation_receipts TO centerway_api;
CREATE FUNCTION centerway.operate(t uuid,c uuid,request uuid,op text,args jsonb) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,centerway,pg_temp SET timezone='UTC' SET datestyle='ISO, YMD' AS $$
DECLARE receipt centerway.operation_receipts; result jsonb; status text:='completed'; fields text[]; code text; message text;
BEGIN
 IF NOT coalesce(centerway.allowed(t),false) THEN RAISE EXCEPTION 'not_authorized' USING ERRCODE='42501'; END IF;
 IF request IS NULL OR op IS NULL OR args IS NULL OR jsonb_typeof(args)<>'object' THEN RAISE EXCEPTION 'invalid_operation'; END IF;
 PERFORM 1 FROM centerway.clients WHERE (tenant_id,client_id)=(t,c);
 IF NOT FOUND THEN RAISE EXCEPTION 'client_not_found'; END IF;
 PERFORM pg_advisory_xact_lock(hashtextextended(t::text||c::text||request::text||'f06',0));
 SELECT * INTO receipt FROM centerway.operation_receipts WHERE (tenant_id,client_id,request_id)=(t,c,request);
 IF FOUND THEN
 IF receipt.actor<>session_user OR receipt.operation<>op OR receipt.arguments<>args THEN
 RAISE EXCEPTION 'request_identity_conflict' USING ERRCODE='22023'; END IF;
 RETURN to_jsonb(receipt);
 END IF;
 -- Each handler calls the existing engine. Its subtransaction rolls back completely on error.
 BEGIN
 fields:=CASE op
 WHEN 'append_value' THEN ARRAY['kind','id','expected_revision','reason','data']
 WHEN 'detect' THEN ARRAY['contract_id','revisions','as_of','required_periods']
 WHEN 'discover_company' THEN ARRAY['as_of']
 WHEN 'open_investigation' THEN ARRAY['id','detection_id','contract_revision','question']
 WHEN 'append_investigation' THEN ARRAY['investigation_id','kind','id','expected_revision','reason','data']
 WHEN 'investigate' THEN ARRAY['investigation_id','as_of']
 WHEN 'intervene' THEN ARRAY['investigation_id','report_id']
 WHEN 'undo' THEN ARRAY['execution_id']
 WHEN 'plan_recovery' THEN ARRAY['id','decision_id','pre_revision','post_revision','reason']
 WHEN 'evaluate_recovery' THEN ARRAY['plan_id','as_of'] ELSE NULL END;
 IF fields IS NULL OR EXISTS(SELECT 1 FROM jsonb_object_keys(args) k WHERE NOT k=ANY(fields))
 OR EXISTS(SELECT 1 FROM unnest(fields) k WHERE NOT args ? k OR args->k='null'::jsonb) THEN
 RAISE EXCEPTION 'invalid_operation_arguments' USING ERRCODE='22023'; END IF;
 CASE op
 WHEN 'append_value' THEN result:=centerway.append_version(t,c,args->>'kind',(args->>'id')::uuid,(args->>'expected_revision')::integer,args->>'reason',args->'data');
 WHEN 'detect' THEN result:=centerway.run_detection(t,c,(args->>'contract_id')::uuid,ARRAY(SELECT value::integer FROM jsonb_array_elements_text(args->'revisions')),(args->>'as_of')::timestamptz,(args->>'required_periods')::integer);
 WHEN 'discover_company' THEN result:=centerway.discover_impediments(t,(args->>'as_of')::timestamptz);
 WHEN 'open_investigation' THEN result:=centerway.open_investigation(t,c,(args->>'id')::uuid,(args->>'detection_id')::uuid,(args->>'contract_revision')::integer,args->>'question');
 WHEN 'append_investigation' THEN result:=centerway.append_investigation_record(t,c,(args->>'investigation_id')::uuid,args->>'kind',(args->>'id')::uuid,(args->>'expected_revision')::integer,args->>'reason',args->'data');
 WHEN 'investigate' THEN result:=centerway.run_investigation(t,c,(args->>'investigation_id')::uuid,(args->>'as_of')::timestamptz);
 WHEN 'intervene' THEN result:=centerway.run_intervention(t,c,(args->>'investigation_id')::uuid,(args->>'report_id')::uuid);
 WHEN 'undo' THEN result:=centerway.undo_intervention(t,c,(args->>'execution_id')::uuid);
 WHEN 'plan_recovery' THEN result:=centerway.create_recovery_plan(t,c,(args->>'id')::uuid,(args->>'decision_id')::uuid,(args->>'pre_revision')::integer,(args->>'post_revision')::integer,args->>'reason');
 WHEN 'evaluate_recovery' THEN result:=centerway.evaluate_recovery(t,c,(args->>'plan_id')::uuid,(args->>'as_of')::timestamptz);
 END CASE;
 EXCEPTION WHEN OTHERS THEN
 GET STACKED DIAGNOSTICS code=RETURNED_SQLSTATE,message=MESSAGE_TEXT;
 status:='error'; result:=jsonb_build_object('sqlstate',code,'message',message);
 END;
 INSERT INTO centerway.operation_receipts VALUES(t,c,request,op,args,status,result,session_user,clock_timestamp()) RETURNING * INTO receipt;
 RETURN to_jsonb(receipt);
END $$;

-- The existence check on clients needs a privileged, scoped helper (clients has no app SELECT).
CREATE FUNCTION centerway._journey_client_exists(t uuid,c uuid) RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog,centerway,pg_temp AS $$
 SELECT centerway.allowed(t) AND EXISTS(SELECT 1 FROM centerway.clients x WHERE (x.tenant_id,x.client_id)=(t,c))
$$;
GRANT EXECUTE ON FUNCTION centerway._journey_client_exists(uuid,uuid) TO centerway_api;
REVOKE ALL ON FUNCTION centerway._journey_client_exists(uuid,uuid) FROM PUBLIC;
CREATE FUNCTION centerway.client_journey(t uuid,c uuid) RETURNS jsonb
LANGUAGE sql STABLE SECURITY INVOKER SET search_path=pg_catalog,centerway,pg_temp SET timezone='UTC' AS $$
WITH investigations AS (
 SELECT i.*,r.result,r.input_snapshot evidence_snapshot,r.id report_id,r.as_of FROM centerway.investigations i
 LEFT JOIN LATERAL(SELECT * FROM centerway.investigation_runs x
 WHERE (x.tenant_id,x.client_id,x.investigation_id)=(i.tenant_id,i.client_id,i.id)
 ORDER BY x.recorded_at DESC,x.id DESC LIMIT 1) r ON true
 WHERE (i.tenant_id,i.client_id)=(t,c)
), plans AS (
 SELECT p.*,r.result,r.input_snapshot evidence_snapshot,r.id report_id,r.as_of FROM centerway.recovery_plans p
 LEFT JOIN LATERAL(SELECT * FROM centerway.recovery_runs x
 WHERE (x.tenant_id,x.client_id,x.plan_id)=(p.tenant_id,p.client_id,p.id)
 ORDER BY x.recorded_at DESC,x.id DESC LIMIT 1) r ON true
 WHERE (p.tenant_id,p.client_id)=(t,c)
)
SELECT jsonb_build_object('contract_version','f06-v1','tenant_id',t,'client_id',c,
 'authorization_basis','engine_checks_required_at_execution','causal_attribution','not_established',
 'contracts',coalesce((SELECT jsonb_agg(to_jsonb(x) ORDER BY x.id,x.revision) FROM centerway.contract_versions x WHERE (x.tenant_id,x.client_id)=(t,c)),'[]'::jsonb),
 'sources',coalesce((SELECT jsonb_agg(to_jsonb(x) ORDER BY x.id,x.revision) FROM centerway.source_versions x WHERE (x.tenant_id,x.client_id)=(t,c)),'[]'::jsonb),
 'evidence_history',coalesce((SELECT jsonb_agg(to_jsonb(x) ORDER BY x.id,x.revision) FROM centerway.evidence_versions x WHERE (x.tenant_id,x.client_id)=(t,c)),'[]'::jsonb),
 'detections',coalesce((SELECT jsonb_agg(to_jsonb(x) ORDER BY x.recorded_at,x.id) FROM centerway.detection_runs x WHERE (x.tenant_id,x.client_id)=(t,c)),'[]'::jsonb),
 'investigations',coalesce((SELECT jsonb_agg(to_jsonb(x) ORDER BY x.id) FROM investigations x),'[]'::jsonb),
 'decisions',coalesce((SELECT jsonb_agg(to_jsonb(x) ORDER BY x.recorded_at,x.id) FROM centerway.intervention_decisions x WHERE (x.tenant_id,x.client_id)=(t,c)),'[]'::jsonb),
 'executions',coalesce((SELECT jsonb_agg(to_jsonb(x) ORDER BY x.recorded_at,x.id) FROM centerway.intervention_executions x WHERE (x.tenant_id,x.client_id)=(t,c)),'[]'::jsonb),
 'recovery_plans',coalesce((SELECT jsonb_agg(to_jsonb(x) ORDER BY x.id) FROM plans x),'[]'::jsonb),
 'operations',coalesce((SELECT jsonb_agg(to_jsonb(x) ORDER BY x.recorded_at,x.request_id) FROM centerway.operation_receipts x WHERE (x.tenant_id,x.client_id)=(t,c)),'[]'::jsonb),
 'work_items',coalesce((SELECT jsonb_agg(x) FROM (
 SELECT jsonb_build_object('stage','contract','next','append_value','needed','explicit_value_contract_and_source') x
 WHERE NOT EXISTS(SELECT 1 FROM centerway.contract_versions WHERE (tenant_id,client_id)=(t,c))
 UNION ALL SELECT jsonb_build_object('stage','detection','contract_id',cv.id,'next','detect','needed','explicit_revisions_cutoff_and_period_policy')
 FROM (SELECT DISTINCT id FROM centerway.contract_versions WHERE (tenant_id,client_id)=(t,c)) cv
 WHERE NOT EXISTS(SELECT 1 FROM centerway.detection_runs d WHERE (d.tenant_id,d.client_id,d.contract_id)=(t,c,cv.id))
 UNION ALL SELECT jsonb_build_object('stage','investigation','detection_id',d.id,'next','supply_context_or_open_investigation','needed','explicit_factors_and_contextual_evidence')
 FROM centerway.detection_runs d WHERE (d.tenant_id,d.client_id)=(t,c)
 AND NOT EXISTS(SELECT 1 FROM centerway.investigations i WHERE (i.tenant_id,i.client_id,i.detection_id)=(t,c,d.id))
 UNION ALL SELECT jsonb_build_object('stage','investigation','investigation_id',i.id,'next',CASE WHEN i.report_id IS NULL THEN 'investigate' WHEN i.result->>'status'='inconclusivo' THEN 'supply_evidence_or_verification' WHEN i.result->>'status'='impedimento_demonstrado' AND jsonb_array_length(i.result->'intervention_candidates')>0 THEN 'review_intervention_authorization' ELSE 'review_investigation_conclusion' END,
 'blockers',i.result->'contradictions','needed',i.result->'missing_information','report_id',i.report_id,'as_of',i.as_of)
 FROM investigations i WHERE NOT EXISTS(SELECT 1 FROM centerway.intervention_decisions d WHERE (d.tenant_id,d.client_id,d.investigation_id)=(t,c,i.id) AND d.status='executed')
 UNION ALL SELECT jsonb_build_object('stage','intervention','decision_id',d.id,'next',CASE WHEN d.status='executed' THEN 'plan_recovery' ELSE 'review_execution_blocker' END,'blocker',d.reason)
 FROM centerway.intervention_decisions d WHERE (d.tenant_id,d.client_id)=(t,c)
 AND NOT EXISTS(SELECT 1 FROM centerway.recovery_plans p WHERE (p.tenant_id,p.client_id,p.decision_id)=(t,c,d.id))
 UNION ALL SELECT jsonb_build_object('stage','recovery','plan_id',p.id,'next',CASE WHEN p.report_id IS NULL THEN 'evaluate_recovery' WHEN p.result->>'status'='resultado_inconclusivo' THEN 'supply_outcome_evidence_and_reevaluate' ELSE 'review_observed_recovery' END,'result',p.result,'as_of',p.as_of)
 FROM plans p
 ) q),'[]'::jsonb))
WHERE centerway._journey_client_exists(t,c)
$$;
REVOKE ALL ON FUNCTION centerway.operate(uuid,uuid,uuid,text,jsonb) FROM PUBLIC;
REVOKE ALL ON FUNCTION centerway.client_journey(uuid,uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION centerway.operate(uuid,uuid,uuid,text,jsonb) TO centerway_api;
GRANT EXECUTE ON FUNCTION centerway.client_journey(uuid,uuid) TO centerway_api;
COMMIT;
