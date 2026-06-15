"""tracelens — drop-in LLM observability SDK.

Public API (planned, alpha):
    @tracelens.traced       — decorator capturing latency / tokens / cost
    tracelens.log(trace)    — manual trace logging
    tracelens.configure(...) — endpoint, api key

Scaffold only — first working release lands the week of 2026-06-15. See ROADMAP.md.
"""

from __future__ import annotations

import functools
import os
import time
from collections.abc import Callable
from typing import Any


_endpoint: str | None = None


def configure(endpoint: str | None = None, api_key: str | None = None) -> None:
    global _endpoint
    _endpoint = endpoint or os.environ.get("TRACELENS_ENDPOINT") or "http://localhost:8000"


def traced(*, model: str | None = None) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Decorator that captures latency of a wrapped LLM call.

    NOTE: This is a scaffold. Full implementation (token count, cost, error capture,
    fail-soft HTTP ingest) lands in v0.1 — see ROADMAP.md.
    """
    def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            t0 = time.time()
            try:
                result = fn(*args, **kwargs)
                return result
            finally:
                dt_ms = (time.time() - t0) * 1000
                # TODO(v0.1): POST trace to _endpoint
                # For now, print for visibility during development
                if _endpoint:
                    print(f"[tracelens] {fn.__name__} model={model} latency_ms={dt_ms:.1f}")
        return wrapper
    return decorator


__all__ = ["configure", "traced"]
__version__ = "0.1.0-alpha.0"
