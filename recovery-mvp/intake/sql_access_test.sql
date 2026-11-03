-- Run only in disposable api/test.sh PostgreSQL after HTTP test provisioning.
\set ON_ERROR_STOP on
BEGIN;
SET SESSION AUTHORIZATION http_alice;
SELECT centerway.append_posthog_outcome_import(
 'a1000000-0000-0000-0000-000000000001',
 'e1000000-0000-0000-0000-000000000001',
 7, 'workflow_completed', 0,
 '2026-01-01T00:00:00Z', '2026-01-02T00:00:00Z',
 '[{"customer":"synthetic-client-a","count":5}]'::jsonb
);
-- Idempotent identical replay.
SELECT centerway.append_posthog_outcome_import(
 'a1000000-0000-0000-0000-000000000001',
 'e1000000-0000-0000-0000-000000000001',
 7, 'workflow_completed', 0,
 '2026-01-01T00:00:00Z', '2026-01-02T00:00:00Z',
 '[{"customer":"synthetic-client-a","count":5}]'::jsonb
);
DO $$
DECLARE n integer;
BEGIN
    SELECT count(*) INTO n FROM centerway.outcome_imports
      WHERE tenant_id='a1000000-0000-0000-0000-000000000001';
    IF n <> 1 THEN RAISE EXCEPTION 'duplicate_insert_not_idempotent'; END IF;
    IF has_table_privilege(session_user,'centerway.outcome_imports','INSERT')
       OR has_table_privilege(session_user,'centerway.outcome_imports','UPDATE')
       OR has_table_privilege(session_user,'centerway.outcome_imports','DELETE')
    THEN RAISE EXCEPTION 'direct_mutation_granted'; END IF;
    BEGIN
        PERFORM centerway.append_posthog_outcome_import(
           'a1000000-0000-0000-0000-000000000001',
           'e1000000-0000-0000-0000-000000000001', 7, 'workflow_completed', 0,
           '2026-01-01T00:00:00Z', '2026-01-02T00:00:00Z',
           '[{"customer":"synthetic-client-a","count":6}]'::jsonb);
        RAISE EXCEPTION 'replay_mutation_was_accepted';
    EXCEPTION WHEN unique_violation THEN NULL;
    END;
    BEGIN
        PERFORM centerway.append_posthog_outcome_import(
           'b1000000-0000-0000-0000-000000000001',
           'e1000000-0000-0000-0000-000000000002', 7, 'workflow_completed', 0,
           '2026-01-01T00:00:00Z', '2026-01-02T00:00:00Z', '[]'::jsonb);
        RAISE EXCEPTION 'cross_tenant_write_was_accepted';
    EXCEPTION WHEN insufficient_privilege THEN NULL;
    END;
    BEGIN
        PERFORM centerway.append_posthog_outcome_import(
           'a1000000-0000-0000-0000-000000000001',
           'e1000000-0000-0000-0000-000000000003', 7, 'workflow_completed', 0,
           '2026-01-03T00:00:00Z', '2026-01-04T00:00:00Z',
           '[{"customer":"synthetic-client-a","count":1},{"customer":"synthetic-client-a","count":1}]'::jsonb);
        RAISE EXCEPTION 'duplicate_customers_accepted';
    EXCEPTION WHEN invalid_parameter_value THEN NULL;
    END;
END $$;
ROLLBACK;
BEGIN;
SET SESSION AUTHORIZATION http_bob;
DO $$
DECLARE n integer;
BEGIN
    SELECT count(*) INTO n FROM centerway.outcome_imports
      WHERE tenant_id='a1000000-0000-0000-0000-000000000001';
    IF n <> 0 THEN RAISE EXCEPTION 'cross_tenant_read_visible'; END IF;
END $$;
ROLLBACK;
