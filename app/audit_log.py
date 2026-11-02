"""SQLite audit log of every ticket the app answers.

One row per ticket. In compare mode the row is the QueryForge (S4) answer and the
baseline (S1) result is stored on it as a JSON `comparison` field, not as its own row.
"""
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
DEDUP_SECONDS = 10

SCHEMA = """CREATE TABLE IF NOT EXISTS tickets (
  ticket_id TEXT PRIMARY KEY, ts TEXT, requester TEXT, role TEXT, question TEXT, action TEXT, sql TEXT,
  result_hash TEXT, row_count INTEGER, model TEXT, setup TEXT, latency_ms INTEGER, cost_usd REAL,
  confidence TEXT, approved_by TEXT, status TEXT, comparison TEXT, ts_epoch REAL)"""

# Status set automatically from the agent's action; Approve / Flag move a pending answer on.
AUTO_STATUS = {"refuse": "refused", "clarify": "awaiting requester"}
STATUSES = ("pending", "approved", "flagged", "refused", "awaiting requester")
_LEGACY = {"answered": "pending", "needs_review": "pending"}  # statuses written by earlier versions


def _con():
    con = sqlite3.connect(DB)
    con.execute(SCHEMA)
    cols = {r[1] for r in con.execute("PRAGMA table_info(tickets)")}
    for col, typ in (("comparison", "TEXT"), ("ts_epoch", "REAL")):  # migrate logs from earlier versions
        if col not in cols:
            con.execute(f"ALTER TABLE tickets ADD COLUMN {col} {typ}")
    return con


def _hash(rows):
    return hashlib.sha256(json.dumps(rows or [], default=str).encode()).hexdigest()[:16]


def summarize_comparison(setup, resp) -> dict:
    """Compact record of the comparison run (e.g. the S1 baseline) stored on the ticket."""
    return {"setup": setup, "action": resp.action, "row_count": len(resp.rows or []),
            "result_hash": _hash(resp.rows), "error": resp.error, "sql": resp.sql,
            "rows": (resp.rows or [])[:5], "cost_usd": resp.cost_usd, "latency_ms": resp.latency_ms}


def log_ticket(resp, question, setup, requester, role, comparison: dict | None = None) -> str:
    """Insert one ticket row and return its id. A repeat of the same question and setup within
    DEDUP_SECONDS returns the existing ticket instead of writing a duplicate row."""
    now = time.time()
    norm = " ".join(question.lower().split())
    with _con() as con:
        recent = con.execute("SELECT ticket_id, question FROM tickets WHERE setup = ? AND ts_epoch >= ?",
                             (setup, now - DEDUP_SECONDS)).fetchall()
        for tid, q in recent:
            if " ".join((q or "").lower().split()) == norm:
                return tid
        tid = uuid.uuid4().hex[:12]
        rows = resp.rows or []
        con.execute(
            "INSERT INTO tickets (ticket_id, ts, requester, role, question, action, sql, result_hash, row_count, model, "
            "setup, latency_ms, cost_usd, confidence, approved_by, status, comparison, ts_epoch) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (tid, time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(now)), requester, role, question, resp.action,
             resp.sql, _hash(rows), len(rows), resp.model_used, setup, resp.latency_ms, resp.cost_usd,
             resp.confidence, None, AUTO_STATUS.get(resp.action, "pending"),
             json.dumps(comparison, default=str) if comparison else None, now))
    return tid


def set_status(ticket_id, status, by):
    with _con() as con:
        con.execute("UPDATE tickets SET status = ?, approved_by = ? WHERE ticket_id = ?", (status, by, ticket_id))


def recent(limit=500, status=None):
    with _con() as con:
        cur = con.execute("SELECT * FROM tickets ORDER BY COALESCE(ts_epoch, 0) DESC, ts DESC LIMIT ?", (limit,))
        cols = [d[0] for d in cur.description]
        rows = [dict(zip(cols, r)) for r in cur.fetchall()]
    for r in rows:
        r["status"] = _LEGACY.get(r["status"], r["status"])
        r["comparison"] = json.loads(r["comparison"]) if r.get("comparison") else None
    return [r for r in rows if status in (None, r["status"])]
