"""
SQLite-backed incident history.
All I/O goes through this module — the rest of the app never touches sqlite3 directly.
"""
import json
import os
import sqlite3
from datetime import datetime, timezone
from typing import Optional

from dotenv import load_dotenv

load_dotenv()

DB_PATH = os.getenv("INCIDENT_DB_PATH", "./incidents.db")


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row  # rows behave like dicts
    return conn


def init_db() -> None:
    """Create the incidents table and apply any schema migrations."""
    with _connect() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS incidents (
                id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp           TEXT    NOT NULL,
                status              TEXT,
                severity            TEXT    DEFAULT 'P2',
                severity_reason     TEXT    DEFAULT '',
                correlated_error    TEXT,
                root_cause          TEXT,
                relevant_files      TEXT,   -- JSON array
                code_patch          TEXT,
                patch_explanation   TEXT,
                test_results        TEXT,
                tests_passed        INTEGER,  -- 0 or 1
                retry_count         INTEGER,
                affected_customers  TEXT,   -- JSON array
                customer_replies    TEXT,   -- JSON array
                postmortem_report   TEXT,
                escalate_to_human   INTEGER,  -- 0 or 1
                run_time_seconds    REAL
            )
        """)
        # Migration: add severity columns to existing databases
        for col, default in (("severity", "'P2'"), ("severity_reason", "''")):
            try:
                conn.execute(f"ALTER TABLE incidents ADD COLUMN {col} TEXT DEFAULT {default}")
            except sqlite3.OperationalError:
                pass  # column already exists


def save_incident(state: dict, run_time_seconds: float) -> int:
    """
    Persist a completed pipeline run.
    Returns the new row's id.
    """
    init_db()
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    with _connect() as conn:
        cursor = conn.execute(
            """
            INSERT INTO incidents (
                timestamp, status, severity, severity_reason,
                correlated_error, root_cause,
                relevant_files, code_patch, patch_explanation,
                test_results, tests_passed, retry_count,
                affected_customers, customer_replies,
                postmortem_report, escalate_to_human, run_time_seconds
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                timestamp,
                state.get("status", ""),
                state.get("severity", "P2"),
                state.get("severity_reason", ""),
                state.get("correlated_error", ""),
                state.get("root_cause", ""),
                json.dumps(state.get("relevant_files", [])),
                state.get("code_patch", ""),
                state.get("patch_explanation", ""),
                state.get("test_results", ""),
                int(bool(state.get("tests_passed", False))),
                state.get("retry_count", 0),
                json.dumps(state.get("affected_customers", [])),
                json.dumps(state.get("customer_replies", [])),
                state.get("postmortem_report", ""),
                int(bool(state.get("escalate_to_human", False))),
                run_time_seconds,
            ),
        )
        return cursor.lastrowid


def list_incidents(limit: int = 50) -> list[dict]:
    """
    Return summary rows for the history table, newest first.
    Each row has all columns but postmortem_report and test_results truncated.
    """
    init_db()
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT
                id, timestamp, status, severity, severity_reason,
                correlated_error, affected_customers,
                tests_passed, retry_count, run_time_seconds, escalate_to_human
            FROM incidents
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

    result = []
    for row in rows:
        d = dict(row)
        d["affected_customers"] = json.loads(d["affected_customers"] or "[]")
        result.append(d)
    return result


def get_incident(incident_id: int) -> Optional[dict]:
    """Return the full record for a single incident, or None if not found."""
    init_db()
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM incidents WHERE id = ?", (incident_id,)
        ).fetchone()

    if row is None:
        return None

    d = dict(row)
    for key in ("relevant_files", "affected_customers", "customer_replies"):
        d[key] = json.loads(d.get(key) or "[]")
    d["tests_passed"] = bool(d["tests_passed"])
    d["escalate_to_human"] = bool(d["escalate_to_human"])
    return d


def delete_incident(incident_id: int) -> None:
    init_db()
    with _connect() as conn:
        conn.execute("DELETE FROM incidents WHERE id = ?", (incident_id,))


def export_as_postmortem_doc(incident_id: int) -> str:
    """Return a markdown string for the incident suitable for RAG ingestion."""
    incident = get_incident(incident_id)
    if not incident:
        return ""

    files = ", ".join(incident.get("relevant_files") or []) or "unknown"
    customers = ", ".join(incident.get("affected_customers") or []) or "none"
    outcome = "resolved" if incident.get("tests_passed") else "escalated"

    return f"""# Incident #{incident_id} — {incident.get('correlated_error', 'Unknown error')}

**Date:** {incident.get('timestamp', '')}
**Severity:** {incident.get('severity', 'P2')}
**Outcome:** {outcome}
**Affected files:** {files}
**Affected customers:** {customers}

## Root Cause

{incident.get('root_cause', 'Not identified.')}

## Fix Applied

{incident.get('patch_explanation', 'No explanation recorded.')}

## Postmortem

{incident.get('postmortem_report', '')}
"""


def delete_all_incidents() -> None:
    init_db()
    with _connect() as conn:
        conn.execute("DELETE FROM incidents")


def get_analytics_data() -> list[dict]:
    """Return lightweight rows for all incidents (oldest first) for dashboard charts."""
    init_db()
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT
                id, timestamp, severity, status,
                tests_passed, escalate_to_human,
                retry_count, run_time_seconds,
                affected_customers
            FROM incidents
            ORDER BY id ASC
            """
        ).fetchall()
    result = []
    for row in rows:
        d = dict(row)
        d["affected_customers"] = json.loads(d["affected_customers"] or "[]")
        d["tests_passed"] = bool(d["tests_passed"])
        d["escalate_to_human"] = bool(d["escalate_to_human"])
        result.append(d)
    return result
