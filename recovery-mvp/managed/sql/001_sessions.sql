-- Install once as the database owner; never by a runtime identity.
BEGIN;
CREATE ROLE cw_session_store NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
CREATE SCHEMA cw_sessions;
REVOKE ALL ON SCHEMA cw_sessions FROM PUBLIC;
GRANT USAGE ON SCHEMA cw_sessions TO cw_session_store;
CREATE TABLE cw_sessions.sessions (
  digest text PRIMARY KEY CHECK (digest ~ '^[0-9a-f]{64}$'),
  username text NOT NULL CHECK (length(username) BETWEEN 1 AND 64),
  version text NOT NULL CHECK (version ~ '^[0-9a-f]{64}$'),
  expires double precision NOT NULL CHECK (expires > 0 AND expires < 'Infinity'::float8)
);
CREATE INDEX ON cw_sessions.sessions (username, expires DESC);
GRANT SELECT,INSERT,DELETE ON cw_sessions.sessions TO cw_session_store;
COMMIT;
