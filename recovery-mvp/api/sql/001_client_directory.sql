-- C02 transport read port. Apply once as administrator after engine migrations 001–008.
-- No direct app SELECT grant on clients, no changes to engine tables or RLS.
BEGIN;
CREATE FUNCTION centerway.list_authorized_clients(
  p_tenant uuid, p_clients uuid[], p_after uuid, p_limit integer
) RETURNS TABLE(client_id uuid, display_name text)
LANGUAGE plpgsql STABLE SECURITY DEFINER
SET search_path=pg_catalog,centerway,pg_temp AS $$
BEGIN
  IF NOT centerway.allowed(p_tenant) THEN
    RAISE EXCEPTION 'forbidden' USING ERRCODE='42501';
  END IF;
  IF p_limit IS NULL OR p_limit < 1 OR p_limit > 100 THEN
    RAISE EXCEPTION 'invalid page limit' USING ERRCODE='22023';
  END IF;
  -- session_user remains the real login even inside this definer read helper.
  -- p_clients narrows tenant visibility; HTTP supplies its server-provisioned scope.
  RETURN QUERY SELECT c.client_id, c.name::text FROM centerway.clients c
    WHERE c.tenant_id=p_tenant AND c.client_id=ANY(p_clients)
      AND (p_after IS NULL OR c.client_id>p_after)
    ORDER BY c.client_id LIMIT p_limit+1;
END $$;
REVOKE ALL ON FUNCTION centerway.list_authorized_clients(uuid,uuid[],uuid,integer) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION centerway.list_authorized_clients(uuid,uuid[],uuid,integer) TO centerway_api;
COMMIT;
