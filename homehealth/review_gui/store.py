"""SQLite-backed local review state; source case files are never opened for write."""

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


STATUSES = {"ready", "approved", "edited", "needs_clinician_review", "excluded", "unavailable"}


class ReviewStore:
    def __init__(self, path: Path | str):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.executescript("""
                CREATE TABLE IF NOT EXISTS review_cases (
                    case_id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    draft_json TEXT
                );
                CREATE TABLE IF NOT EXISTS audit_events (
                    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    case_id TEXT NOT NULL,
                    reviewer TEXT NOT NULL,
                    action TEXT NOT NULL,
                    detail_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
            """)
            columns = {row[1] for row in connection.execute("PRAGMA table_info(review_cases)")}
            if "draft_json" not in columns:
                connection.execute("ALTER TABLE review_cases ADD COLUMN draft_json TEXT")

    def _connect(self):
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        return connection

    def ensure_case(self, case_id: str, status: str = "ready") -> None:
        self._validate_status(status)
        with self._connect() as connection:
            connection.execute("INSERT OR IGNORE INTO review_cases(case_id, status, updated_at) VALUES (?, ?, ?)", (case_id, status, self._now()))

    def set_status(self, case_id: str, status: str) -> None:
        self._validate_status(status)
        with self._connect() as connection:
            result = connection.execute("UPDATE review_cases SET status = ?, updated_at = ? WHERE case_id = ?", (status, self._now(), case_id))
            if result.rowcount != 1:
                raise ValueError("unknown review case")

    def status_for(self, case_id: str) -> str | None:
        with self._connect() as connection:
            row = connection.execute("SELECT status FROM review_cases WHERE case_id = ?", (case_id,)).fetchone()
        return None if row is None else row["status"]

    def set_draft(self, case_id: str, draft: dict) -> None:
        if not isinstance(draft, dict):
            raise ValueError("draft must be an object")
        with self._connect() as connection:
            result = connection.execute(
                "UPDATE review_cases SET draft_json = ?, updated_at = ? WHERE case_id = ?",
                (json.dumps(draft, sort_keys=True), self._now(), case_id),
            )
            if result.rowcount != 1:
                raise ValueError("unknown review case")

    def draft_for(self, case_id: str) -> dict:
        with self._connect() as connection:
            row = connection.execute("SELECT draft_json FROM review_cases WHERE case_id = ?", (case_id,)).fetchone()
        if row is None or row["draft_json"] is None:
            return {}
        return json.loads(row["draft_json"])

    def audit(self, case_id: str, reviewer: str, action: str, detail: dict) -> None:
        if not reviewer.strip() or not action.strip():
            raise ValueError("reviewer and action are required")
        with self._connect() as connection:
            connection.execute("INSERT INTO audit_events(case_id, reviewer, action, detail_json, created_at) VALUES (?, ?, ?, ?, ?)", (case_id, reviewer, action, json.dumps(detail, sort_keys=True), self._now()))

    def audit_for(self, case_id: str) -> list[dict]:
        with self._connect() as connection:
            rows = connection.execute("SELECT case_id, reviewer, action, detail_json, created_at FROM audit_events WHERE case_id = ? ORDER BY event_id", (case_id,)).fetchall()
        return [{**dict(row), "detail": json.loads(row["detail_json"])} for row in rows]

    @staticmethod
    def _validate_status(status: str) -> None:
        if status not in STATUSES:
            raise ValueError("unsupported review status")

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()
