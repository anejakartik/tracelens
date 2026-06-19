"""SQLAlchemy/SQLModel-backed Storage. Default for local dev (SQLite)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from uuid import UUID

from sqlmodel import Field, Session, SQLModel, create_engine, select

from tracelens.models import Trace


class TraceRow(SQLModel, table=True):
    id: str = Field(primary_key=True)
    timestamp: datetime = Field(index=True)
    model: str = Field(index=True)
    function: str | None = None
    latency_ms: float
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None
    cost_usd: float | None = None
    prompt: str | None = None
    completion: str | None = None
    error: str | None = None
    metadata_json: str = Field(default="{}")


class SQLAlchemyStorage:
    def __init__(self, database_url: str) -> None:
        self._url = database_url
        self._engine = create_engine(
            database_url,
            echo=False,
            connect_args={"check_same_thread": False}
            if database_url.startswith("sqlite")
            else {},
        )

    def init(self) -> None:
        SQLModel.metadata.create_all(self._engine)

    def insert_trace(self, trace: Trace) -> None:
        with Session(self._engine) as s:
            s.add(_trace_to_row(trace))
            s.commit()

    def get_trace(self, trace_id: UUID) -> Trace | None:
        with Session(self._engine) as s:
            row = s.get(TraceRow, str(trace_id))
            return _row_to_trace(row) if row else None

    def list_traces(
        self,
        *,
        since: datetime,
        model: str | None,
        only_errors: bool,
        limit: int,
    ) -> list[Trace]:
        with Session(self._engine) as s:
            stmt = select(TraceRow).where(TraceRow.timestamp >= since)
            if model:
                stmt = stmt.where(TraceRow.model == model)
            if only_errors:
                stmt = stmt.where(TraceRow.error.is_not(None))  # type: ignore[attr-defined]
            stmt = stmt.order_by(TraceRow.timestamp.desc()).limit(limit)
            rows = s.exec(stmt).all()
            return [_row_to_trace(r) for r in rows]

    def query_window(
        self,
        *,
        since: datetime,
        model: str | None,
    ) -> list[Trace]:
        with Session(self._engine) as s:
            stmt = select(TraceRow).where(TraceRow.timestamp >= since)
            if model:
                stmt = stmt.where(TraceRow.model == model)
            rows = s.exec(stmt).all()
            return [_row_to_trace(r) for r in rows]

    def describe(self) -> str:
        return self._url.split("@")[-1]


def _trace_to_row(t: Trace) -> TraceRow:
    return TraceRow(
        id=str(t.id),
        timestamp=t.timestamp,
        model=t.model,
        function=t.function,
        latency_ms=t.latency_ms,
        prompt_tokens=t.prompt_tokens,
        completion_tokens=t.completion_tokens,
        total_tokens=t.total_tokens,
        cost_usd=t.cost_usd,
        prompt=t.prompt,
        completion=t.completion,
        error=t.error,
        metadata_json=json.dumps(t.metadata),
    )


def _row_to_trace(r: TraceRow) -> Trace:
    return Trace(
        id=UUID(r.id),
        timestamp=r.timestamp.replace(tzinfo=timezone.utc) if r.timestamp.tzinfo is None else r.timestamp,
        model=r.model,
        function=r.function,
        latency_ms=r.latency_ms,
        prompt_tokens=r.prompt_tokens,
        completion_tokens=r.completion_tokens,
        total_tokens=r.total_tokens,
        cost_usd=r.cost_usd,
        prompt=r.prompt,
        completion=r.completion,
        error=r.error,
        metadata=json.loads(r.metadata_json),
    )
