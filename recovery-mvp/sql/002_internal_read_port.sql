BEGIN;
-- Read port for future engines: exact contract plus its evidence/assessment history.
-- SECURITY INVOKER deliberately keeps the caller's SELECT grants and RLS policies.
CREATE FUNCTION centerway.read_contract_context(p_tenant uuid, p_client uuid, p_id uuid, p_revision integer)
RETURNS jsonb LANGUAGE sql STABLE SECURITY INVOKER SET search_path = pg_catalog, centerway, pg_temp AS $$
 SELECT jsonb_build_object(
   'contract', to_jsonb(c),
   'source', (SELECT to_jsonb(s) FROM centerway.source_versions s
     WHERE (s.tenant_id,s.client_id,s.id,s.revision) = (c.tenant_id,c.client_id,c.source_id,c.source_revision)),
   'evidence_history', coalesce((SELECT jsonb_agg(to_jsonb(e) ORDER BY e.id,e.revision)
     FROM centerway.evidence_versions e
     WHERE (e.tenant_id,e.client_id,e.contract_id,e.contract_revision) = (c.tenant_id,c.client_id,c.id,c.revision)), '[]'::jsonb),
   'assessment_history', coalesce((SELECT jsonb_agg(to_jsonb(a) ORDER BY a.id,a.revision)
     FROM centerway.assessment_versions a
     WHERE (a.tenant_id,a.client_id,a.contract_id,a.contract_revision) = (c.tenant_id,c.client_id,c.id,c.revision)), '[]'::jsonb))
 FROM centerway.contract_versions c
 WHERE (c.tenant_id,c.client_id,c.id,c.revision) = (p_tenant,p_client,p_id,p_revision)
$$;
REVOKE ALL ON FUNCTION centerway.read_contract_context(uuid,uuid,uuid,integer) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION centerway.read_contract_context(uuid,uuid,uuid,integer) TO centerway_api;
COMMIT;
