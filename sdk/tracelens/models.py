"""Shared data models for the SDK + server."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Trace(BaseModel):
    """One observed LLM call."""

    id: UUID = Field(default_factory=uuid4)
    timestamp: datetime = Field(default_factory=utc_now)
    model: str
    function: str | None = None
    latency_ms: float
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None
    cost_usd: float | None = None
    prompt: str | None = None
    completion: str | None = None
    error: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class TraceStats(BaseModel):
    """Aggregated rollup over a window of traces."""

    count: int
    p50_ms: float
    p95_ms: float
    p99_ms: float
    mean_ms: float
    total_tokens: int
    total_cost_usd: float
    error_rate: float
    by_model: list["ModelBreakdown"] = Field(default_factory=list)


class ModelBreakdown(BaseModel):
    model: str
    count: int
    mean_ms: float
    total_tokens: int
    total_cost_usd: float
    error_rate: float


TraceStats.model_rebuild()
