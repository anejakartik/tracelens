"""Storage backend abstraction for tracelens.

Two implementations:
- SQLite (default, via SQLModel) — zero config, single-process
- ClickHouse (via clickhouse-driver) — columnar, scales to hundreds of millions
  of rows; targets the hosted demo.

Pick via TRACELENS_DB_URL:
    sqlite:///./tracelens.db
    clickhouse://default:@clickhouse:9000/tracelens
"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol
from uuid import UUID

from tracelens.models import Trace


class Storage(Protocol):
    """Append-only trace store. Implementations MUST be thread-safe."""

    def init(self) -> None: ...

    def insert_trace(self, trace: Trace) -> None: ...

    def get_trace(self, trace_id: UUID) -> Trace | None: ...

    def list_traces(
        self,
        *,
        since: datetime,
        model: str | None,
        only_errors: bool,
        limit: int,
    ) -> list[Trace]: ...

    def query_window(
        self,
        *,
        since: datetime,
        model: str | None,
    ) -> list[Trace]:
        """Return every trace in the window — used by /stats aggregation."""
        ...

    def describe(self) -> str: ...


def make_storage(database_url: str) -> Storage:
    """Factory — branches on URL scheme."""
    if database_url.startswith(("clickhouse://", "clickhouse+native://")):
        from ._clickhouse import ClickHouseStorage

        return ClickHouseStorage(database_url)
    # Default: SQLAlchemy/SQLModel — covers sqlite://, postgresql://, etc.
    from ._sqlite import SQLAlchemyStorage

    return SQLAlchemyStorage(database_url)
