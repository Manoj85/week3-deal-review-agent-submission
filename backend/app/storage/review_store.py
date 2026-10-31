"""Small durable catalog; LangGraph checkpoints hold the actual revision state."""

import json
import sqlite3
import time
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4


class ReviewNotFound(Exception):
    pass


class ReviewConflict(Exception):
    pass


def now() -> str:
    return datetime.now(UTC).isoformat()


class ReviewStore:
    def __init__(self, directory: Path):
        directory.mkdir(parents=True, exist_ok=True)
        self.path = directory / "reviews.sqlite3"
        with self.connection() as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("""CREATE TABLE IF NOT EXISTS review_index (
                review_id TEXT PRIMARY KEY, created_at TEXT NOT NULL,
                initial_request TEXT NOT NULL, mode TEXT NOT NULL,
                lock_token TEXT, lock_until REAL)""")

    @contextmanager
    def connection(self):
        conn = sqlite3.connect(self.path, timeout=10)
        conn.row_factory = sqlite3.Row
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def create(self, request: dict, mode: str) -> dict:
        row = {
            "review_id": str(uuid4()),
            "created_at": now(),
            "initial_request": json.dumps(request),
            "mode": mode,
        }
        with self.connection() as conn:
            conn.execute(
                "INSERT INTO review_index (review_id,created_at,initial_request,mode) VALUES (?,?,?,?)",
                (row["review_id"], row["created_at"], row["initial_request"], mode),
            )
        return row

    def get(self, review_id: str) -> dict:
        with self.connection() as conn:
            row = conn.execute(
                "SELECT * FROM review_index WHERE review_id=?", (review_id,)
            ).fetchone()
        if row is None:
            raise ReviewNotFound("Saved review was not found.")
        return dict(row)

    def list_ids(self, limit: int) -> list[str]:
        with self.connection() as conn:
            return [
                row["review_id"]
                for row in conn.execute(
                    "SELECT review_id FROM review_index ORDER BY created_at DESC LIMIT ?", (limit,)
                )
            ]

    @contextmanager
    def claim(self, review_id: str):
        token = str(uuid4())
        with self.connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT lock_token,lock_until FROM review_index WHERE review_id=?", (review_id,)
            ).fetchone()
            if row is None:
                raise ReviewNotFound("Saved review was not found.")
            if row["lock_token"] and (row["lock_until"] or 0) > time.time():
                raise ReviewConflict(
                    "Another operation is running for this review. Wait before retrying."
                )
            # Longer than the bounded twelve 60-second model calls in a revision.
            conn.execute(
                "UPDATE review_index SET lock_token=?,lock_until=? WHERE review_id=?",
                (token, time.time() + 1800, review_id),
            )
        try:
            yield
        finally:
            with self.connection() as conn:
                conn.execute(
                    "UPDATE review_index SET lock_token=NULL,lock_until=NULL WHERE review_id=? AND lock_token=?",
                    (review_id, token),
                )
