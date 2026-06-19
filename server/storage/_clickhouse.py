"""ClickHouse-backed Storage. Columnar, append-only, scales horizontally.

URL format: clickhouse://user:password@host:9000/database
Use port 9000 for the native protocol (clickhouse-driver) — NOT 8123 (HTTP).
"""

from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse
from uuid import UUID

from clickhouse_driver import Client  # type: ignore[import-untyped]

from tracelens.models import Trace


_TABLE_DDL = """
CREATE TABLE IF NOT EXISTS traces (
    id              UUID,
    timestamp       DateTime64(3, 'UTC'),
    model           LowCardinality(String),
    function        Nullable(String),
    latency_ms      Float64,
    prompt_tokens   Nullable(UInt32),
    completion_tokens Nullable(UInt32),
    total_tokens    Nullable(UInt32),
    cost_usd        Nullable(Float64),
    prompt          Nullable(String),
    completion      Nullable(String),
    error           Nullable(String),
    metadata_json   String DEFAULT '{}'
)
ENGINE = MergeTree()
PARTITION BY toYYYYMM(timestamp)
ORDER BY (model, timestamp)
TTL toDateTime(timestamp) + INTERVAL 90 DAY
SETTINGS index_granularity = 8192
"""


_COLUMNS = (
    "id",
    "timestamp",
    "model",
    "function",
    "latency_ms",
    "prompt_tokens",
    "completion_tokens",
    "total_tokens",
    "cost_usd",
    "prompt",
    "completion",
    "error",
    "metadata_json",
)


class ClickHouseStorage:
    def __init__(self, database_url: str) -> None:
        self._url = database_url
        parsed = urlparse(database_url)
        self._database = (parsed.path or "/default").lstrip("/") or "default"
        self._client_kwargs: dict[str, Any] = {
            "host": parsed.hostname or "localhost",
            "port": parsed.port or 9000,
            "user": parsed.username or "default",
            "password": parsed.password or "",
            "database": self._database,
        }
        # clickhouse-driver clients are NOT thread-safe; gate per-call.
        self._lock = threading.Lock()

    def _client(self) -> Client:
        return Client(**self._client_kwargs)

    def init(self) -> None:
        # Make sure the database itself exists, then the table.
        bootstrap_kwargs = dict(self._client_kwargs)
        bootstrap_kwargs["database"] = "default"
        Client(**bootstrap_kwargs).execute(
            f"CREATE DATABASE IF NOT EXISTS {self._database}"
        )
        self._client().execute(_TABLE_DDL)

    def insert_trace(self, trace: Trace) -> None:
        row = _trace_to_row(trace)
        with self._lock:
            self._client().execute(
                f"INSERT INTO traces ({', '.join(_COLUMNS)}) VALUES",
                [row],
                types_check=True,
            )

    def get_trace(self, trace_id: UUID) -> Trace | None:
        with self._lock:
            rows = self._client().execute(
                f"SELECT {', '.join(_COLUMNS)} FROM traces WHERE id = %(id)s LIMIT 1",
                {"id": trace_id},
            )
        return _row_to_trace(rows[0]) if rows else None

    def list_traces(
        self,
        *,
        since: datetime,
        model: str | None,
        only_errors: bool,
        limit: int,
    ) -> list[Trace]:
        where = ["timestamp >= %(since)s"]
        params: dict[str, Any] = {"since": since, "limit": limit}
        if model:
            where.append("model = %(model)s")
            params["model"] = model
        if only_errors:
            where.append("error IS NOT NULL")
        sql = (
            f"SELECT {', '.join(_COLUMNS)} FROM traces "
            f"WHERE {' AND '.join(where)} "
            f"ORDER BY timestamp DESC LIMIT %(limit)s"
        )
        with self._lock:
            rows = self._client().execute(sql, params)
        return [_row_to_trace(r) for r in rows]

    def query_window(
        self,
        *,
        since: datetime,
        model: str | None,
    ) -> list[Trace]:
        where = ["timestamp >= %(since)s"]
        params: dict[str, Any] = {"since": since}
        if model:
            where.append("model = %(model)s")
            params["model"] = model
        sql = (
            f"SELECT {', '.join(_COLUMNS)} FROM traces "
            f"WHERE {' AND '.join(where)}"
        )
        with self._lock:
            rows = self._client().execute(sql, params)
        return [_row_to_trace(r) for r in rows]

    def describe(self) -> str:
        return self._url.split("@")[-1]


def _trace_to_row(t: Trace) -> dict[str, Any]:
    return {
        "id": t.id,
        "timestamp": t.timestamp,
        "model": t.model,
        "function": t.function,
        "latency_ms": t.latency_ms,
        "prompt_tokens": t.prompt_tokens,
        "completion_tokens": t.completion_tokens,
        "total_tokens": t.total_tokens,
        "cost_usd": t.cost_usd,
        "prompt": t.prompt,
        "completion": t.completion,
        "error": t.error,
        "metadata_json": json.dumps(t.metadata),
    }


def _row_to_trace(row: tuple) -> Trace:
    # Order matches _COLUMNS.
    (
        trace_id,
        timestamp,
        model,
        function,
        latency_ms,
        prompt_tokens,
        completion_tokens,
        total_tokens,
        cost_usd,
        prompt,
        completion,
        error,
        metadata_json,
    ) = row
    ts: datetime = timestamp if isinstance(timestamp, datetime) else datetime.fromisoformat(str(timestamp))
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return Trace(
        id=trace_id if isinstance(trace_id, UUID) else UUID(str(trace_id)),
        timestamp=ts,
        model=model,
        function=function,
        latency_ms=latency_ms,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens,
        cost_usd=cost_usd,
        prompt=prompt,
        completion=completion,
        error=error,
        metadata=json.loads(metadata_json or "{}"),
    )
