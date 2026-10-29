BEGIN;
-- Administrative provisioning only. No application RPC can grant itself authority.
CREATE TABLE centerway.sandbox_flags (
 tenant_id uuid NOT NULL, client_id uuid NOT NULL, id uuid NOT NULL,
 environment text NOT NULL CHECK(environment='isolated_synthetic'), value boolean NOT NULL,
 last_execution uuid, PRIMARY KEY(tenant_id,client_id,id),
 FOREIGN KEY(tenant_id,client_id) REFERENCES centerway.clients(tenant_id,client_id)
);
CREATE TABLE centerway.intervention_catalog (
 tenant_id uuid NOT NULL REFERENCES centerway.companies, id uuid NOT NULL,
 name centerway.label NOT NULL, category centerway.label NOT NULL,
 scope text NOT NULL CHECK(scope IN ('internal','external','mixed')),
 control text NOT NULL CHECK(control IN ('saas','client','third_party')),
 action text NOT NULL CHECK(action='set_synthetic_flag'),
 expected_value boolean NOT NULL, desired_value boolean NOT NULL,
 risk integer NOT NULL CHECK(risk BETWEEN 0 AND 3), priority integer NOT NULL,
 PRIMARY KEY(tenant_id,id), CHECK(expected_value<>desired_value)
);
CREATE TABLE centerway.intervention_policies (
 tenant_id uuid NOT NULL, client_id uuid NOT NULL, id uuid NOT NULL,
 catalog_id uuid NOT NULL, resource_id uuid NOT NULL, principal name NOT NULL,
 valid_from timestamptz NOT NULL, valid_until timestamptz NOT NULL,
 max_attempts integer NOT NULL CHECK(max_attempts>0), max_risk integer NOT NULL CHECK(max_risk BETWEEN 0 AND 3),
 max_report_age interval NOT NULL CHECK(max_report_age>interval '0'),
 max_observation_age interval NOT NULL CHECK(max_observation_age>interval '0'),
 PRIMARY KEY(tenant_id,client_id,id),
 FOREIGN KEY(tenant_id,catalog_id) REFERENCES centerway.intervention_catalog(tenant_id,id),
 FOREIGN KEY(tenant_id,client_id,resource_id) REFERENCES centerway.sandbox_flags(tenant_id,client_id,id),
 CHECK(isfinite(valid_from) AND isfinite(valid_until) AND valid_from<valid_until)
);
CREATE TABLE centerway.intervention_revocations (
 tenant_id uuid NOT NULL, client_id uuid NOT NULL, policy_id uuid NOT NULL,
 reason centerway.label NOT NULL, PRIMARY KEY(tenant_id,client_id,policy_id),
 FOREIGN KEY(tenant_id,client_id,policy_id) REFERENCES centerway.intervention_policies(tenant_id,client_id,id)
);
CREATE TABLE centerway.intervention_decisions (
 tenant_id uuid NOT NULL, client_id uuid NOT NULL, id uuid NOT NULL, investigation_id uuid NOT NULL, report_id uuid NOT NULL,
 factor_id uuid, policy_id uuid, status text NOT NULL CHECK(status IN ('blocked','executed','failed')),
 reason text NOT NULL, actor name NOT NULL, recorded_at timestamptz NOT NULL,
 PRIMARY KEY(tenant_id,client_id,id),
 FOREIGN KEY(tenant_id,client_id,investigation_id,report_id) REFERENCES centerway.investigation_runs(tenant_id,client_id,investigation_id,id),
 FOREIGN KEY(tenant_id,client_id,policy_id) REFERENCES centerway.intervention_policies(tenant_id,client_id,id)
);
CREATE TABLE centerway.intervention_executions (
 tenant_id uuid NOT NULL, client_id uuid NOT NULL, id uuid NOT NULL,
 decision_id uuid NOT NULL, resource_id uuid NOT NULL, before_value boolean NOT NULL, after_value boolean NOT NULL,
 undo_of uuid, actor name NOT NULL, recorded_at timestamptz NOT NULL,
 PRIMARY KEY(tenant_id,client_id,id), UNIQUE(tenant_id,client_id,undo_of),
 FOREIGN KEY(tenant_id,client_id,decision_id) REFERENCES centerway.intervention_decisions(tenant_id,client_id,id),
 FOREIGN KEY(tenant_id,client_id,resource_id) REFERENCES centerway.sandbox_flags(tenant_id,client_id,id),
 FOREIGN KEY(tenant_id,client_id,undo_of) REFERENCES centerway.intervention_executions(tenant_id,client_id,id)
);
-- One successful application per factor/investigation, across report/cat/policy changes.
CREATE UNIQUE INDEX intervention_once ON centerway.intervention_decisions(tenant_id,client_id,investigation_id,factor_id) WHERE status='executed';
DO $$ DECLARE t text; BEGIN
 FOREACH t IN ARRAY ARRAY['sandbox_flags','intervention_catalog','intervention_policies','intervention_revocations','intervention_decisions','intervention_executions'] LOOP
 EXECUTE format('ALTER TABLE centerway.%I ENABLE ROW LEVEL SECURITY',t);
 EXECUTE format('ALTER TABLE centerway.%I FORCE ROW LEVEL SECURITY',t);
 EXECUTE format('CREATE POLICY tenant_access ON centerway.%I USING(centerway.allowed(tenant_id)) WITH CHECK(centerway.allowed(tenant_id))',t);
 EXECUTE format('CREATE TRIGGER audit AFTER INSERT ON centerway.%I FOR EACH ROW EXECUTE FUNCTION centerway.audit_insert()',t);
 IF t<>'sandbox_flags' THEN
 EXECUTE format('CREATE TRIGGER immutable BEFORE UPDATE OR DELETE OR TRUNCATE ON centerway.%I FOR EACH STATEMENT EXECUTE FUNCTION centerway.immutable()',t);
 END IF;
 EXECUTE format('GRANT SELECT ON centerway.%I TO centerway_api',t);
 END LOOP;
END $$;
CREATE TRIGGER audit_update AFTER UPDATE ON centerway.sandbox_flags FOR EACH ROW EXECUTE FUNCTION centerway.audit_insert();
CREATE FUNCTION centerway._lock_intervention_configuration() RETURNS trigger
LANGUAGE plpgsql SET search_path=pg_catalog AS $$ BEGIN
 PERFORM pg_advisory_xact_lock(hashtextextended(NEW.tenant_id::text||'f04',0)); RETURN NEW;
END $$;
CREATE TRIGGER serialize BEFORE INSERT ON centerway.intervention_revocations FOR EACH ROW EXECUTE FUNCTION centerway._lock_intervention_configuration();
REVOKE ALL ON FUNCTION centerway._lock_intervention_configuration() FROM PUBLIC;
CREATE FUNCTION centerway.run_intervention(t uuid,c uuid,i uuid,r uuid) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,centerway,pg_temp AS $$
DECLARE report centerway.investigation_runs; fresh jsonb; chosen record; n integer; did uuid:=gen_random_uuid();
 reason text; status text:='blocked'; fid uuid; pid uuid; eid uuid; current_flag boolean; result centerway.intervention_decisions;
BEGIN
 IF NOT coalesce(centerway.allowed(t),false) THEN RAISE EXCEPTION 'not_authorized' USING ERRCODE='42501'; END IF;
 -- Shared lock protocol for execution/undo; serializes quota and duplicate checks.
 PERFORM pg_advisory_xact_lock(hashtextextended(t::text||'f04',0));
 SELECT * INTO STRICT report FROM centerway.investigation_runs WHERE (tenant_id,client_id,investigation_id,id)=(t,c,i,r);
 LOCK TABLE centerway.investigation_factor_versions,centerway.investigation_evidence_versions,centerway.investigation_verification_versions IN SHARE MODE;
 fresh:=centerway.run_investigation(t,c,i,clock_timestamp());
 IF fresh->>'input_hash'<>report.input_hash THEN reason:='stale_report';
 ELSIF report.result->>'status'<>'impedimento_demonstrado' THEN reason:='uncertain_investigation';
 ELSE
 SELECT count(*) INTO n FROM (
 SELECT p.id FROM jsonb_array_elements(report.result->'intervention_candidates') x
 JOIN centerway.intervention_catalog a ON a.tenant_id=t AND a.category=x->>'category' AND a.scope=x->>'scope' AND a.control=x->>'control'
 JOIN centerway.intervention_policies p ON p.tenant_id=t AND p.client_id=c AND p.catalog_id=a.id
 WHERE p.principal=session_user AND clock_timestamp()>=p.valid_from AND clock_timestamp()<p.valid_until
 AND a.risk<=p.max_risk AND clock_timestamp()-report.recorded_at<=p.max_report_age
 AND NOT EXISTS(SELECT 1 FROM centerway.intervention_revocations v WHERE (v.tenant_id,v.client_id,v.policy_id)=(t,c,p.id))
 AND NOT EXISTS(SELECT 1 FROM centerway.intervention_decisions d WHERE (d.tenant_id,d.client_id,d.investigation_id,d.factor_id)=(t,c,i,(x->>'factor_id')::uuid) AND d.status='executed')
 AND (SELECT count(*) FROM centerway.intervention_decisions d WHERE (d.tenant_id,d.client_id,d.policy_id)=(t,c,p.id) AND d.status IN ('executed','failed'))<p.max_attempts
 AND EXISTS(SELECT 1 FROM jsonb_array_elements(report.input_snapshot->'factors') f WHERE f->'factor'->'id'=x->'factor_id'
 AND clock_timestamp()-(f->'factor'->>'assessment_at')::timestamptz<=p.max_observation_age)
 ) eligible;
 -- Materialize eligibility once for selection using the same predicates via a private viewless query below.
 IF n=0 THEN reason:='no_authorized_eligible_action';
 ELSE
 -- Reuse a ranked candidate list. Filters above are repeated via policy validation per candidate.
 FOR chosen IN SELECT p.*,a.risk,a.priority,a.expected_value,a.desired_value,(x->>'factor_id')::uuid factor
 FROM jsonb_array_elements(report.result->'intervention_candidates') x
 JOIN centerway.intervention_catalog a ON a.tenant_id=t AND a.category=x->>'category' AND a.scope=x->>'scope' AND a.control=x->>'control'
 JOIN centerway.intervention_policies p ON (p.tenant_id,p.client_id,p.catalog_id)=(t,c,a.id)
 WHERE p.principal=session_user AND clock_timestamp()>=p.valid_from AND clock_timestamp()<p.valid_until
 AND a.risk<=p.max_risk AND clock_timestamp()-report.recorded_at<=p.max_report_age
 AND NOT EXISTS(SELECT 1 FROM centerway.intervention_revocations v WHERE (v.tenant_id,v.client_id,v.policy_id)=(t,c,p.id))
 AND NOT EXISTS(SELECT 1 FROM centerway.intervention_decisions d WHERE (d.tenant_id,d.client_id,d.investigation_id,d.factor_id)=(t,c,i,(x->>'factor_id')::uuid) AND d.status='executed')
 AND (SELECT count(*) FROM centerway.intervention_decisions d WHERE (d.tenant_id,d.client_id,d.policy_id)=(t,c,p.id) AND d.status IN ('executed','failed'))<p.max_attempts
 AND EXISTS(SELECT 1 FROM jsonb_array_elements(report.input_snapshot->'factors') f WHERE f->'factor'->'id'=x->'factor_id' AND clock_timestamp()-(f->'factor'->>'assessment_at')::timestamptz<=p.max_observation_age)
 ORDER BY a.priority,p.id LIMIT 1 LOOP
 fid:=chosen.factor; pid:=chosen.id;
 -- Explicit priority is the catalogue's deterministic preference; UUID breaks equal priorities.
 SELECT value INTO STRICT current_flag FROM centerway.sandbox_flags WHERE (tenant_id,client_id,id)=(t,c,chosen.resource_id) FOR UPDATE;
 IF clock_timestamp()>=chosen.valid_until THEN status:='failed'; reason:='authorization_expired';
 ELSIF current_flag<>chosen.expected_value THEN status:='failed'; reason:='resource_precondition_failed';
 ELSE
 status:='executed'; reason:='synthetic_execution_only'; eid:=gen_random_uuid();
 END IF;
 END LOOP;
 IF pid IS NULL THEN reason:='authorization_changed'; END IF;
 END IF;
 END IF;
 INSERT INTO centerway.intervention_decisions VALUES(t,c,did,i,r,fid,pid,status,reason,session_user,clock_timestamp()) RETURNING * INTO result;
 IF status='executed' THEN
 INSERT INTO centerway.intervention_executions VALUES(t,c,eid,did,chosen.resource_id,current_flag,chosen.desired_value,NULL,session_user,clock_timestamp());
 UPDATE centerway.sandbox_flags SET value=chosen.desired_value,last_execution=eid WHERE (tenant_id,client_id,id)=(t,c,chosen.resource_id);
 END IF;
 RETURN to_jsonb(result)||jsonb_build_object('execution_id',eid,'value_recovery','not_evaluated');
END $$;
CREATE FUNCTION centerway.undo_intervention(t uuid,c uuid,e uuid) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,centerway,pg_temp AS $$
DECLARE original centerway.intervention_executions; existing centerway.intervention_executions; new_id uuid:=gen_random_uuid(); head uuid;
BEGIN
 IF NOT coalesce(centerway.allowed(t),false) THEN RAISE EXCEPTION 'not_authorized' USING ERRCODE='42501'; END IF;
 PERFORM pg_advisory_xact_lock(hashtextextended(t::text||'f04',0));
 SELECT * INTO STRICT original FROM centerway.intervention_executions WHERE (tenant_id,client_id,id)=(t,c,e);
 IF original.actor<>session_user OR original.undo_of IS NOT NULL THEN RAISE EXCEPTION 'undo_not_authorized' USING ERRCODE='42501'; END IF;
 SELECT * INTO existing FROM centerway.intervention_executions WHERE (tenant_id,client_id,undo_of)=(t,c,e);
 IF FOUND THEN RETURN to_jsonb(existing); END IF;
 SELECT last_execution INTO head FROM centerway.sandbox_flags WHERE (tenant_id,client_id,id)=(t,c,original.resource_id) FOR UPDATE;
 IF head IS DISTINCT FROM e THEN RAISE EXCEPTION 'resource_changed'; END IF;
 INSERT INTO centerway.intervention_executions VALUES(t,c,new_id,original.decision_id,original.resource_id,original.after_value,original.before_value,e,session_user,clock_timestamp()) RETURNING * INTO existing;
 UPDATE centerway.sandbox_flags SET value=original.before_value,last_execution=new_id WHERE (tenant_id,client_id,id)=(t,c,original.resource_id);
 RETURN to_jsonb(existing);
END $$;
REVOKE ALL ON FUNCTION centerway.run_intervention(uuid,uuid,uuid,uuid) FROM PUBLIC;
REVOKE ALL ON FUNCTION centerway.undo_intervention(uuid,uuid,uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION centerway.run_intervention(uuid,uuid,uuid,uuid) TO centerway_api;
GRANT EXECUTE ON FUNCTION centerway.undo_intervention(uuid,uuid,uuid) TO centerway_api;
COMMIT;
