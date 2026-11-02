"""SQLite audit log of every ticket the app answers."""
import hashlib
import json
import sqlite3
import time
import uuid
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
CFG = yaml.safe_load(open(ROOT / "config.yaml"))
DB = ROOT / CFG["paths"]["audit_log"]

SCHEMA = """CREATE TABLE IF NOT EXISTS tickets (
  ticket_id TEXT PRIMARY KEY, ts TEXT, requester TEXT, role TEXT, question TEXT, action TEXT, sql TEXT,
  result_hash TEXT, row_count INTEGER, model TEXT, setup TEXT, latency_ms INTEGER, cost_usd REAL,
  confidence TEXT, approved_by TEXT, status TEXT)"""


def _con():
    con = sqlite3.connect(DB)
    con.execute(SCHEMA)
    return con


def log_ticket(resp, question, setup, requester, role) -> str:
    tid = uuid.uuid4().hex[:12]
    rows = resp.rows or []
    with _con() as con:
        con.execute("INSERT INTO tickets VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (
            tid, time.strftime("%Y-%m-%d %H:%M:%S"), requester, role, question, resp.action, resp.sql,
            hashlib.sha256(json.dumps(rows, default=str).encode()).hexdigest()[:16], len(rows), resp.model_used,
            setup, resp.latency_ms, resp.cost_usd, resp.confidence, None,
            "needs_review" if resp.confidence == "low" or resp.error else "answered"))
    return tid


def set_status(ticket_id, status, by):
    with _con() as con:
        con.execute("UPDATE tickets SET status = ?, approved_by = ? WHERE ticket_id = ?", (status, by, ticket_id))


def recent(limit=200):
    with _con() as con:
        cur = con.execute("SELECT * FROM tickets ORDER BY ts DESC LIMIT ?", (limit,))
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]
