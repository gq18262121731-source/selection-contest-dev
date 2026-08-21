from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator


def resolve_sqlite_path(database_url: str) -> Path:
    """Resolve sqlite database path from project database URL."""

    if database_url.startswith("sqlite+aiosqlite:///"):
        raw_path = database_url.replace("sqlite+aiosqlite:///", "", 1)
    elif database_url.startswith("sqlite:///"):
        raw_path = database_url.replace("sqlite:///", "", 1)
    else:
        raw_path = database_url
    path = Path(raw_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


class SQLiteRepositoryBase:
    """Shared sqlite repository helper."""

    def __init__(self, database_url: str) -> None:
        self.database_path = resolve_sqlite_path(database_url)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        return connection

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        """Open a write transaction that can be shared across repositories."""

        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    @contextmanager
    def connection_scope(
        self,
        connection: sqlite3.Connection | None = None,
    ) -> Iterator[sqlite3.Connection]:
        """Reuse a caller-owned transaction or commit a local connection."""

        if connection is not None:
            yield connection
            return
        with self._connect() as local_connection:
            yield local_connection
            local_connection.commit()

    def _initialize(self) -> None:
        raise NotImplementedError

    @staticmethod
    def dump_json(payload: dict[str, Any]) -> str:
        return json.dumps(payload, ensure_ascii=False)

    @staticmethod
    def load_json(payload: str | bytes | bytearray | None) -> dict[str, Any]:
        if payload in (None, ""):
            return {}
        if isinstance(payload, (bytes, bytearray)):
            payload = payload.decode("utf-8")
        return json.loads(str(payload))
