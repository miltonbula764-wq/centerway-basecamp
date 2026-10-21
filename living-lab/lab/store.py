import hashlib
import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY,value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS controls(id INTEGER PRIMARY KEY CHECK(id=1),paused INTEGER NOT NULL DEFAULT 0);
INSERT OR IGNORE INTO controls(id) VALUES(1);
CREATE TABLE IF NOT EXISTS clients(ref TEXT PRIMARY KEY,cohort TEXT NOT NULL,active INTEGER NOT NULL DEFAULT 1);
CREATE TABLE IF NOT EXISTS ticks(slot INTEGER PRIMARY KEY,generated_at REAL NOT NULL,provenance TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY,slot INTEGER,client TEXT,kind TEXT NOT NULL,truth TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS measurements(
 id TEXT PRIMARY KEY,slot INTEGER NOT NULL,client TEXT NOT NULL,indicator TEXT NOT NULL,
 observed_at REAL NOT NULL,value TEXT NOT NULL,available_at REAL NOT NULL,provenance TEXT NOT NULL,
 corrects TEXT REFERENCES measurements(id),observation_id TEXT UNIQUE,
 batch_id TEXT,FOREIGN KEY(client) REFERENCES clients(ref));
CREATE TABLE IF NOT EXISTS outbox(
 id TEXT PRIMARY KEY,payload TEXT NOT NULL,payload_hash TEXT NOT NULL,
 state TEXT NOT NULL CHECK(state IN ('pending','leased','sent','blocked')),
 created_at REAL NOT NULL,due_at REAL NOT NULL,lease_until REAL,lease_token TEXT,
 tries INTEGER NOT NULL DEFAULT 0,last_code TEXT);
CREATE TABLE IF NOT EXISTS attempts(
 id INTEGER PRIMARY KEY,batch_id TEXT NOT NULL,started_at REAL NOT NULL,
 finished_at REAL,http_status INTEGER,code TEXT NOT NULL,request_id TEXT,
 inserted INTEGER,duplicates INTEGER,rejected INTEGER,details TEXT);
CREATE INDEX IF NOT EXISTS due_batches ON outbox(state,due_at);
CREATE INDEX IF NOT EXISTS quota_attempts ON attempts(started_at);
CREATE TABLE IF NOT EXISTS technical_errors(id INTEGER PRIMARY KEY,at REAL NOT NULL,code TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS comparisons(
 id INTEGER PRIMARY KEY,imported_at REAL NOT NULL,external_id TEXT UNIQUE NOT NULL,
 client TEXT NOT NULL,indicator TEXT NOT NULL,observed_until REAL NOT NULL,
 actual_result TEXT NOT NULL,evidence_ref TEXT NOT NULL);
"""


def connect(path):
    db = sqlite3.connect(path, timeout=3, isolation_level=None)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys=ON")
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA synchronous=FULL")
    return db


@contextmanager
def transaction(db):
    db.execute("BEGIN IMMEDIATE")
    try:
        yield
        db.execute("COMMIT")
    except BaseException:
        db.execute("ROLLBACK")
        raise


def initialize(cfg, company):
    directory = Path(cfg["state_dir"])
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    directory.chmod(0o700)
    path = directory / (company["id"] + ".sqlite3")
    db = connect(path)
    try:
        db.executescript(SCHEMA)
        # Changing transport/profile/source/seed never retargets existing batches.
        bound = {
            k: company[k]
            for k in ("id", "seed", "clients", "profile_id", "source", "endpoint")
        }
        bound.update(
            mode=cfg["mode"],
            interval_seconds=cfg["interval_seconds"],
            engine="living-v1",
        )
        digest = hashlib.sha256(json.dumps(bound, sort_keys=True).encode()).hexdigest()
        with transaction(db):
            old = db.execute("SELECT value FROM meta WHERE key='binding'").fetchone()
            if old and old["value"] != digest:
                raise ValueError("state_binding_changed_archive_and_review_new_epoch")
            db.execute("INSERT OR IGNORE INTO meta VALUES('binding',?)", (digest,))
        path.chmod(0o600)
    finally:
        db.close()
    return path


def event(db, slot, client, kind, truth):
    db.execute(
        "INSERT INTO events(slot,client,kind,truth) VALUES(?,?,?,?)",
        (slot, client, kind, json.dumps(truth, sort_keys=True)),
    )
