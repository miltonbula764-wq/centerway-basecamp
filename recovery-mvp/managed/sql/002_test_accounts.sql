-- Additive migration. Apply once only to the existing synthetic demonstration.
-- Never grant business schema or role-management permissions to the session runtime.
BEGIN;
CREATE TABLE cw_sessions.test_accounts (
  username text PRIMARY KEY CHECK (username ~ '^[a-z][a-z0-9_]{2,31}$'),
  password_hash text NOT NULL CHECK (password_hash ~ '^[0-9a-f]{32}:[0-9a-f]{128}$')
);
REVOKE ALL ON cw_sessions.test_accounts FROM PUBLIC;
GRANT SELECT, INSERT ON cw_sessions.test_accounts TO cw_session_store;
COMMIT;
