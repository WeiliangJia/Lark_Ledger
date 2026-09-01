from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class TokenSet:
    access_token: str
    access_expires_at: int
    refresh_token: str
    refresh_expires_at: int
    scope: str


class StateStore:
    def __init__(self, path: Path, *, token_db_path: Path | None = None):
        self.path = path
        self.token_db_path = token_db_path or path
        path.parent.mkdir(parents=True, exist_ok=True)
        self.token_db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connection(path) as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS pending_batches (
                    batch_id TEXT PRIMARY KEY,
                    table_id TEXT NOT NULL,
                    operation TEXT NOT NULL,
                    client_token TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    keys_json TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending'
                );
                """
            )

        # This schema intentionally matches dms_lark_sync_tool so both tools can
        # share one rotating user OAuth token without invalidating each other.
        with self._connection(self.token_db_path) as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS oauth_tokens (
                    singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
                    access_token TEXT NOT NULL,
                    access_expires_at INTEGER NOT NULL,
                    refresh_token TEXT NOT NULL,
                    refresh_expires_at INTEGER NOT NULL,
                    scope TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                """
            )

    def _connect(self, path: Path) -> sqlite3.Connection:
        connection = sqlite3.connect(path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        return connection

    @contextmanager
    def _connection(self, path: Path | None = None):
        connection = self._connect(path or self.path)
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def save_tokens(self, tokens: TokenSet) -> None:
        with self._connection(self.token_db_path) as connection:
            connection.execute(
                """
                INSERT INTO oauth_tokens(
                    singleton, access_token, access_expires_at, refresh_token,
                    refresh_expires_at, scope, updated_at
                ) VALUES(1, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(singleton) DO UPDATE SET
                    access_token=excluded.access_token,
                    access_expires_at=excluded.access_expires_at,
                    refresh_token=excluded.refresh_token,
                    refresh_expires_at=excluded.refresh_expires_at,
                    scope=excluded.scope,
                    updated_at=excluded.updated_at
                """,
                (
                    tokens.access_token,
                    tokens.access_expires_at,
                    tokens.refresh_token,
                    tokens.refresh_expires_at,
                    tokens.scope,
                    datetime.now(timezone.utc).isoformat(),
                ),
            )

    def load_tokens(self) -> TokenSet | None:
        with self._connection(self.token_db_path) as connection:
            row = connection.execute(
                """
                SELECT access_token, access_expires_at, refresh_token,
                       refresh_expires_at, scope
                FROM oauth_tokens WHERE singleton=1
                """
            ).fetchone()
        return TokenSet(**dict(row)) if row else None

    def save_pending(
        self,
        *,
        batch_id: str,
        table_id: str,
        operation: str,
        client_token: str,
        payload: list[dict[str, Any]],
        keys: list[str],
    ) -> None:
        with self._connection() as connection:
            connection.execute(
                """
                INSERT INTO pending_batches(batch_id, table_id, operation, client_token, payload, keys_json)
                VALUES(?, ?, ?, ?, ?, ?)
                """,
                (
                    batch_id,
                    table_id,
                    operation,
                    client_token,
                    json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
                    json.dumps(keys, ensure_ascii=False, separators=(",", ":")),
                ),
            )

    def confirm_pending(self, batch_id: str) -> None:
        with self._connection() as connection:
            connection.execute("UPDATE pending_batches SET status='confirmed' WHERE batch_id=?", (batch_id,))

    def pending(self) -> list[dict[str, Any]]:
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT * FROM pending_batches WHERE status='pending' ORDER BY rowid"
            ).fetchall()
        return [
            {
                **dict(row),
                "payload": json.loads(row["payload"]),
                "keys": json.loads(row["keys_json"]),
            }
            for row in rows
        ]
