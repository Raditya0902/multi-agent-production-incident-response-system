"""SQLite checkpoints at the boundary between diagnosis and execution."""

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
import json
import os
from pathlib import Path
import sqlite3
from uuid import uuid4

from agents.state import IncidentState


@dataclass(frozen=True)
class PendingApproval:
    run_id: str
    state: IncidentState
    agent_log: dict[str, int]
    started_at: datetime
    revision: int = 0


class ApprovalStore:
    def __init__(self, path: Path | None = None):
        self.path = path if path is not None else Path(os.getenv("HITL_DB_PATH", "./hitl.db"))

    @contextmanager
    def _connection(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        os.close(os.open(self.path, os.O_CREAT | os.O_WRONLY, 0o600))
        conn = sqlite3.connect(self.path)
        try:
            with conn:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS pending_approvals (
                        run_id TEXT PRIMARY KEY, revision INTEGER NOT NULL,
                        state TEXT NOT NULL, agent_log TEXT NOT NULL, started_at TEXT NOT NULL
                    )
                """)
                yield conn
        finally:
            conn.close()

    def save(self, state: IncidentState, agent_log: dict[str, int], started_at: datetime) -> str:
        run_id = uuid4().hex
        with self._connection() as conn:
            conn.execute(
                "INSERT INTO pending_approvals VALUES (?, 0, ?, ?, ?)",
                (run_id, json.dumps(state), json.dumps(agent_log), started_at.isoformat()),
            )
        return run_id

    def load(self, run_id: str) -> PendingApproval | None:
        with self._connection() as conn:
            row = conn.execute(
                "SELECT revision, state, agent_log, started_at FROM pending_approvals WHERE run_id = ?",
                (run_id,),
            ).fetchone()
        if row is None:
            return None
        revision, state, agent_log, started_at = row
        return PendingApproval(
            run_id, json.loads(state), json.loads(agent_log), datetime.fromisoformat(started_at), revision,
        )

    def revise(self, run_id: str, revision: int, state: IncidentState) -> bool:
        with self._connection() as conn:
            result = conn.execute(
                "UPDATE pending_approvals SET state = ?, revision = revision + 1 "
                "WHERE run_id = ? AND revision = ?",
                (json.dumps(state), run_id, revision),
            )
            return result.rowcount == 1

    def consume(self, run_id: str, revision: int) -> bool:
        """Claim the exact reviewed revision once, for approval or cancellation."""
        with self._connection() as conn:
            result = conn.execute(
                "DELETE FROM pending_approvals WHERE run_id = ? AND revision = ?",
                (run_id, revision),
            )
            return result.rowcount == 1
