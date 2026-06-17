"""tracelens collector — FastAPI ingest + read API + static dashboard.

Endpoints:
  POST /traces          — accept a Trace from the SDK
  GET  /traces          — list recent traces (model + window filters)
  GET  /traces/{id}     — single trace detail
  GET  /stats           — rolled-up p50/p95/p99/cost/error-rate, with per-model breakdown
  GET  /                — static HTML dashboard
"""

from __future__ import annotations

import json
import math
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from uuid import UUID

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlmodel import Field, Session, SQLModel, create_engine, select

# Make `sdk` importable for shared models.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "sdk"))
from tracelens.models import ModelBreakdown, Trace, TraceStats  # noqa: E402


DATABASE_URL = os.environ.get("TRACELENS_DB_URL", "sqlite:///./tracelens.db")
engine = create_engine(
    DATABASE_URL,
    echo=False,
    connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {},
)


# ---- DB row ---------------------------------------------------------------


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


# ---- App ------------------------------------------------------------------


app = FastAPI(
    title="tracelens",
    version="0.1.0",
    description="Drop-in LLM observability collector",
)

_cors_origins = os.environ.get("TRACELENS_CORS_ORIGINS", "*").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def _startup() -> None:
    SQLModel.metadata.create_all(engine)


@app.get("/health")
def health() -> dict[str, Any]:
    return {"ok": True, "db_url": DATABASE_URL.split("@")[-1]}


# ---- Helpers --------------------------------------------------------------


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


def _percentile(values: list[float], p: float) -> float:
    """Linear-interpolation percentile. p in [0, 100]."""
    if not values:
        return 0.0
    sorted_vals = sorted(values)
    k = (len(sorted_vals) - 1) * (p / 100.0)
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return sorted_vals[int(k)]
    return sorted_vals[f] + (sorted_vals[c] - sorted_vals[f]) * (k - f)


# ---- Ingest ---------------------------------------------------------------


@app.post("/traces", response_model=Trace)
def ingest_trace(trace: Trace) -> Trace:
    with Session(engine) as s:
        s.add(_trace_to_row(trace))
        s.commit()
    return trace


# ---- Read -----------------------------------------------------------------


@app.get("/traces", response_model=list[Trace])
def list_traces(
    model: str | None = Query(default=None),
    window_minutes: int = Query(default=60, le=10080),
    limit: int = Query(default=200, le=2000),
    only_errors: bool = Query(default=False),
) -> list[Trace]:
    since = datetime.now(timezone.utc) - timedelta(minutes=window_minutes)
    with Session(engine) as s:
        stmt = select(TraceRow).where(TraceRow.timestamp >= since)
        if model:
            stmt = stmt.where(TraceRow.model == model)
        if only_errors:
            stmt = stmt.where(TraceRow.error.is_not(None))  # type: ignore[attr-defined]
        stmt = stmt.order_by(TraceRow.timestamp.desc()).limit(limit)
        rows = s.exec(stmt).all()
        return [_row_to_trace(r) for r in rows]


@app.get("/traces/{trace_id}", response_model=Trace)
def get_trace(trace_id: UUID) -> Trace:
    with Session(engine) as s:
        row = s.get(TraceRow, str(trace_id))
        if row is None:
            raise HTTPException(404, "Trace not found")
        return _row_to_trace(row)


@app.get("/stats", response_model=TraceStats)
def stats(
    model: str | None = Query(default=None),
    window_minutes: int = Query(default=60, le=10080),
) -> TraceStats:
    since = datetime.now(timezone.utc) - timedelta(minutes=window_minutes)
    with Session(engine) as s:
        stmt = select(TraceRow).where(TraceRow.timestamp >= since)
        if model:
            stmt = stmt.where(TraceRow.model == model)
        rows = s.exec(stmt).all()

    latencies = [r.latency_ms for r in rows]
    total_tokens = sum(r.total_tokens or 0 for r in rows)
    total_cost = round(sum(r.cost_usd or 0.0 for r in rows), 6)
    error_rate = (sum(1 for r in rows if r.error) / len(rows)) if rows else 0.0

    by_model: dict[str, list[TraceRow]] = {}
    for r in rows:
        by_model.setdefault(r.model, []).append(r)
    breakdowns: list[ModelBreakdown] = []
    for m, batch in sorted(by_model.items(), key=lambda kv: -len(kv[1])):
        bl = [b.latency_ms for b in batch]
        breakdowns.append(
            ModelBreakdown(
                model=m,
                count=len(batch),
                mean_ms=round(sum(bl) / len(bl), 2) if bl else 0.0,
                total_tokens=sum(b.total_tokens or 0 for b in batch),
                total_cost_usd=round(sum(b.cost_usd or 0.0 for b in batch), 6),
                error_rate=round(sum(1 for b in batch if b.error) / len(batch), 4),
            )
        )

    return TraceStats(
        count=len(rows),
        p50_ms=round(_percentile(latencies, 50), 2),
        p95_ms=round(_percentile(latencies, 95), 2),
        p99_ms=round(_percentile(latencies, 99), 2),
        mean_ms=round(sum(latencies) / len(latencies), 2) if latencies else 0.0,
        total_tokens=total_tokens,
        total_cost_usd=total_cost,
        error_rate=round(error_rate, 4),
        by_model=breakdowns,
    )


# ---- Static dashboard ----------------------------------------------------


_STATIC_DIR = Path(__file__).resolve().parent / "static"
if _STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")

    @app.get("/", include_in_schema=False)
    def home() -> FileResponse:
        return FileResponse(str(_STATIC_DIR / "index.html"))

else:

    @app.get("/")
    def root() -> dict[str, str]:
        return {
            "service": "tracelens",
            "version": "0.1.0",
            "docs": "/docs",
            "github": "https://github.com/anejakartik/tracelens",
        }
