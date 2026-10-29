BEGIN;
-- Immutable rule editions and structured observations; new IDs replace configuration/data.
CREATE TABLE centerway.discovery_rules (
 tenant_id uuid NOT NULL REFERENCES centerway.companies, id uuid NOT NULL,
 category centerway.label NOT NULL, purpose text NOT NULL CHECK(purpose IN ('condition_met','requirement_applies')),
 assertion boolean NOT NULL, actor name NOT NULL, recorded_at timestamptz NOT NULL,
 PRIMARY KEY(tenant_id,id)
);
CREATE TABLE centerway.discovery_inputs (
 tenant_id uuid NOT NULL, client_id uuid NOT NULL, id uuid NOT NULL,
 contract_id uuid NOT NULL, contract_revision integer NOT NULL,
 factor jsonb NOT NULL CHECK(jsonb_typeof(factor)='object'),
 evidence jsonb NOT NULL CHECK(jsonb_typeof(evidence)='array' AND jsonb_array_length(evidence)>0),
 actor name NOT NULL, recorded_at timestamptz NOT NULL,
 PRIMARY KEY(tenant_id,client_id,id),
 FOREIGN KEY(tenant_id,client_id,contract_id,contract_revision) REFERENCES centerway.contract_versions(tenant_id,client_id,id,revision)
);
CREATE TABLE centerway.discoveries (
 tenant_id uuid NOT NULL, client_id uuid NOT NULL, id uuid NOT NULL,
 detection_id uuid NOT NULL, input_id uuid NOT NULL, rule_id uuid NOT NULL,
 investigation_id uuid NOT NULL, factor_id uuid NOT NULL,
 actor name NOT NULL, recorded_at timestamptz NOT NULL,
 PRIMARY KEY(tenant_id,client_id,id),
 UNIQUE(tenant_id,client_id,detection_id,input_id,rule_id),
 FOREIGN KEY(tenant_id,client_id,detection_id) REFERENCES centerway.detection_runs(tenant_id,client_id,id),
 FOREIGN KEY(tenant_id,client_id,input_id) REFERENCES centerway.discovery_inputs(tenant_id,client_id,id),
 FOREIGN KEY(tenant_id,rule_id) REFERENCES centerway.discovery_rules(tenant_id,id),
 FOREIGN KEY(tenant_id,client_id,investigation_id) REFERENCES centerway.investigations(tenant_id,client_id,id)
);
DO $$ DECLARE t text; BEGIN
 FOREACH t IN ARRAY ARRAY['discovery_rules','discovery_inputs','discoveries'] LOOP
 EXECUTE format('ALTER TABLE centerway.%I ENABLE ROW LEVEL SECURITY',t);
 EXECUTE format('ALTER TABLE centerway.%I FORCE ROW LEVEL SECURITY',t);
 EXECUTE format('CREATE POLICY tenant_access ON centerway.%I USING(centerway.allowed(tenant_id)) WITH CHECK(centerway.allowed(tenant_id))',t);
 EXECUTE format('CREATE TRIGGER immutable BEFORE UPDATE OR DELETE OR TRUNCATE ON centerway.%I FOR EACH STATEMENT EXECUTE FUNCTION centerway.immutable()',t);
 EXECUTE format('CREATE TRIGGER audit AFTER INSERT ON centerway.%I FOR EACH ROW EXECUTE FUNCTION centerway.audit_insert()',t);
 EXECUTE format('GRANT SELECT ON centerway.%I TO centerway_api',t);
 END LOOP;
END $$;
CREATE FUNCTION centerway.register_discovery_rule(t uuid,i uuid,c text,p text,a boolean) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,centerway,pg_temp AS $$
BEGIN
 IF NOT coalesce(centerway.allowed(t),false) THEN RAISE EXCEPTION 'not_authorized' USING ERRCODE='42501'; END IF;
 INSERT INTO centerway.discovery_rules VALUES(t,i,c,p,a,session_user,clock_timestamp());
END $$;
CREATE FUNCTION centerway.register_discovery_input(t uuid,c uuid,i uuid,k uuid,r integer,f jsonb,e jsonb) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,centerway,pg_temp AS $$
BEGIN
 IF NOT coalesce(centerway.allowed(t),false) THEN RAISE EXCEPTION 'not_authorized' USING ERRCODE='42501'; END IF;
 IF jsonb_typeof(e) IS DISTINCT FROM 'array' OR jsonb_array_length(e) NOT BETWEEN 1 AND 100
 OR jsonb_typeof(f) IS DISTINCT FROM 'object' THEN RAISE EXCEPTION 'invalid_input'; END IF;
 -- Full domain validation is delegated atomically to the existing F03 port at routing.
 INSERT INTO centerway.discovery_inputs VALUES(t,c,i,k,r,f,e,session_user,clock_timestamp());
END $$;
CREATE FUNCTION centerway.discover_impediments(t uuid,cutoff timestamptz) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,centerway,pg_temp SET timezone='UTC' AS $$
DECLARE m record; link centerway.discoveries; v jsonb; report jsonb; output jsonb:='[]'; iid uuid; fid uuid;
BEGIN
 IF NOT coalesce(centerway.allowed(t),false) THEN RAISE EXCEPTION 'not_authorized' USING ERRCODE='42501'; END IF;
 IF cutoff IS NULL OR NOT isfinite(cutoff) OR cutoff>clock_timestamp() THEN RAISE EXCEPTION 'invalid_cutoff'; END IF;
 -- One tenant batch includes every client and every pinned detection available at cutoff.
 PERFORM pg_advisory_xact_lock(hashtextextended(t::text||'discovery-v1',0));
 FOR m IN
 SELECT d.id detection_id,o.*,r.id rule_id FROM centerway.discovery_inputs o
 JOIN centerway.discovery_rules r ON r.tenant_id=o.tenant_id AND r.category=o.factor->>'category'
 JOIN centerway.detection_runs d ON (d.tenant_id,d.client_id,d.contract_id)=(o.tenant_id,o.client_id,o.contract_id)
 WHERE o.tenant_id=t AND o.recorded_at<=cutoff AND r.recorded_at<=cutoff AND d.recorded_at<=cutoff
 AND EXISTS(SELECT 1 FROM jsonb_array_elements(d.result->'periods') x WHERE (x->>'contract_revision')::integer=o.contract_revision
  AND (x->>'state'='deterioracao_demonstrada' OR x->'comparison'->>'status'='worsening'))
 AND EXISTS(SELECT 1 FROM jsonb_array_elements(o.evidence) x WHERE x->>'purpose'=r.purpose
  AND x->'assertion'=to_jsonb(r.assertion) AND x->>'kind'<>'usage_context')
 ORDER BY o.client_id,d.id,o.id,r.id
 LOOP
 SELECT * INTO link FROM centerway.discoveries WHERE (tenant_id,client_id,detection_id,input_id,rule_id)=
 (t,m.client_id,m.detection_id,m.id,m.rule_id);
 IF NOT FOUND THEN
 iid:=gen_random_uuid(); fid:=gen_random_uuid();
 PERFORM centerway.open_investigation(t,m.client_id,iid,m.detection_id,m.contract_revision,m.factor->>'hypothesis');
 PERFORM centerway.append_investigation_record(t,m.client_id,iid,'factor',fid,0,'discovery-v1: explicit input factor',m.factor);
 FOR v IN SELECT x FROM jsonb_array_elements(m.evidence) x LOOP
 -- No verification records are created. The original ingestion actor remains in discovery_inputs.
 PERFORM centerway.append_investigation_record(t,m.client_id,iid,'evidence',gen_random_uuid(),0,
 'discovery-v1: input '||m.id::text,v||jsonb_build_object('factor_id',fid,'factor_revision',1));
 END LOOP;
 INSERT INTO centerway.discoveries VALUES(t,m.client_id,gen_random_uuid(),m.detection_id,m.id,m.rule_id,iid,fid,session_user,clock_timestamp()) RETURNING * INTO link;
 END IF;
 -- Fresh F03 evaluation permits actual subsequent human reviews; cutoff limits discovery inputs,
 -- while the report cutoff is explicitly its own current time, returned in the report.
 report:=centerway.run_investigation(t,m.client_id,link.investigation_id,clock_timestamp());
 output:=output||jsonb_build_array(jsonb_build_object('origin',to_jsonb(link),'report',report));
 END LOOP;
 RETURN jsonb_build_object('algorithm','discovery-v1','discovery_cutoff',cutoff,'discoveries',output);
END $$;
REVOKE ALL ON FUNCTION centerway.register_discovery_rule(uuid,uuid,text,text,boolean) FROM PUBLIC;
REVOKE ALL ON FUNCTION centerway.register_discovery_input(uuid,uuid,uuid,uuid,integer,jsonb,jsonb) FROM PUBLIC;
REVOKE ALL ON FUNCTION centerway.discover_impediments(uuid,timestamptz) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION centerway.register_discovery_rule(uuid,uuid,text,text,boolean) TO centerway_api;
GRANT EXECUTE ON FUNCTION centerway.register_discovery_input(uuid,uuid,uuid,uuid,integer,jsonb,jsonb) TO centerway_api;
GRANT EXECUTE ON FUNCTION centerway.discover_impediments(uuid,timestamptz) TO centerway_api;
COMMIT;
