"""Opaque token digests only. SQLite remains the default local store."""
import os
import sqlite3
import stat
import time
from pathlib import Path

import psycopg
from psycopg.conninfo import conninfo_to_dict


class SQLiteSessions:
    def __init__(self, path):
        self.path = Path(path)
        fd = os.open(self.path, os.O_CREAT | os.O_RDWR, 0o600)
        os.close(fd)
        if stat.S_IMODE(self.path.stat().st_mode) & 0o077:
            raise ValueError('session database must be private')
        with sqlite3.connect(self.path) as db:
            db.execute('CREATE TABLE IF NOT EXISTS sessions (digest TEXT PRIMARY KEY, username TEXT, version TEXT, expires REAL)')

    def get(self, digest):
        with sqlite3.connect(self.path) as db:
            return db.execute('SELECT username,version,expires FROM sessions WHERE digest=?', (digest,)).fetchone()

    def put(self, digest, username, version, expires):
        with sqlite3.connect(self.path) as db:
            db.execute('BEGIN IMMEDIATE')
            db.execute('DELETE FROM sessions WHERE expires<=?', (time.time(),))
            db.execute('DELETE FROM sessions WHERE username=? AND digest NOT IN (SELECT digest FROM sessions WHERE username=? ORDER BY expires DESC,digest LIMIT 9)', (username, username))
            db.execute('INSERT INTO sessions VALUES (?,?,?,?)', (digest, username, version, expires))

    def delete(self, digest):
        with sqlite3.connect(self.path) as db:
            db.execute('DELETE FROM sessions WHERE digest=?', (digest,))


class PostgresSessions:
    def __init__(self, config, demo=False):
        self.dsn, self.principal = config['dsn'], config['principal']
        if not demo and conninfo_to_dict(self.dsn).get('sslmode') != 'verify-full':
            raise ValueError('verified session database TLS required')
        # Provisioning is administrative and separate; runtime never creates tables/roles.
        with self.connect() as db:
            row = db.execute("""SELECT session_user::text,current_user::text,
                r.rolsuper OR r.rolbypassrls OR r.rolcreaterole OR r.rolcreatedb OR r.rolreplication,
                pg_has_role(session_user,'centerway_api','MEMBER'),
                has_schema_privilege(session_user,'centerway','USAGE'),
                has_schema_privilege(session_user,'cw_sessions','CREATE'),
                EXISTS(SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
                       WHERE n.nspname IN ('cw_sessions','centerway') AND c.relowner=r.oid),
                EXISTS(SELECT 1 FROM pg_database WHERE datname=current_database() AND datdba=r.oid)
                FROM pg_roles r WHERE rolname=session_user""").fetchone()
            if not row or row[:2] != (self.principal, self.principal) or any(row[2:]):
                raise ValueError('session database identity rejected')
            db.execute('SELECT digest FROM cw_sessions.sessions LIMIT 0')

    def connect(self):
        db = psycopg.connect(self.dsn, connect_timeout=10)
        db.execute("SET LOCAL statement_timeout='15s'")
        db.execute("SET LOCAL lock_timeout='5s'")
        return db

    def get(self, digest):
        with self.connect() as db:
            return db.execute('SELECT username,version,expires FROM cw_sessions.sessions WHERE digest=%s', (digest,)).fetchone()

    def put(self, digest, username, version, expires):
        with self.connect() as db:
            # Serialize same-user login bursts across workers/instances; at most ten sessions.
            db.execute('SELECT pg_advisory_xact_lock(hashtextextended(%s, 678))', (username,))
            db.execute('DELETE FROM cw_sessions.sessions WHERE expires<=%s', (time.time(),))
            db.execute('DELETE FROM cw_sessions.sessions WHERE username=%s AND digest NOT IN (SELECT digest FROM cw_sessions.sessions WHERE username=%s ORDER BY expires DESC,digest LIMIT 9)', (username, username))
            db.execute('INSERT INTO cw_sessions.sessions VALUES (%s,%s,%s,%s)', (digest, username, version, expires))

    def delete(self, digest):
        with self.connect() as db:
            db.execute('DELETE FROM cw_sessions.sessions WHERE digest=%s', (digest,))


def session_store(config):
    if config.get('session_store', 'sqlite') == 'sqlite':
        return SQLiteSessions(config['session_db'])
    if config['session_store'] != 'postgres':
        raise ValueError('unknown session store')
    return PostgresSessions(config['session_postgres'], config.get('demo', False))
