"""tracelens — drop-in LLM observability SDK.

Public API:
    tracelens.configure(endpoint=..., api_key=...)
    @tracelens.traced(model="gpt-4o-mini")
    tracelens.log(Trace(...))

Design contracts:
- Decorator MUST be fail-soft. If the collector is down, the wrapped function
  still returns normally. Observability never breaks the host app.
- Token + cost extraction from OpenAI / Anthropic response shapes is best-effort.
  Callers can also supply `metadata={"prompt_tokens": ..., ...}` for manual override.
"""

from __future__ import annotations

import functools
import logging
import os
import threading
import time
from collections.abc import Callable
from typing import Any
from uuid import UUID, uuid4

import httpx

from .models import ModelBreakdown, Trace, TraceStats
from .pricing import compute_cost

log = logging.getLogger("tracelens")


_endpoint: str = "http://localhost:8000"
_api_key: str | None = None
_async_post_threads: list[threading.Thread] = []
_print_local: bool = False


def configure(
    endpoint: str | None = None,
    api_key: str | None = None,
    print_local: bool | None = None,
) -> None:
    """Set the collector endpoint and optional API key.

    `endpoint` defaults to TRACELENS_ENDPOINT env var, then http://localhost:8000.
    `print_local=True` is a dev convenience — also emit each trace to stdout.
    """
    global _endpoint, _api_key, _print_local
    _endpoint = endpoint or os.environ.get("TRACELENS_ENDPOINT") or "http://localhost:8000"
    _api_key = api_key or os.environ.get("TRACELENS_API_KEY")
    if print_local is not None:
        _print_local = print_local


def traced(
    *,
    model: str | None = None,
    capture_prompt: bool = False,
    capture_completion: bool = False,
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Wrap a callable. Captures latency / tokens / cost / error and posts a Trace.

    `capture_prompt` and `capture_completion` opt into storing the actual text;
    default-off because prompts and outputs are often sensitive.
    """

    def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            t0 = time.perf_counter()
            error: str | None = None
            result: Any = None
            try:
                result = fn(*args, **kwargs)
                return result
            except Exception as exc:  # noqa: BLE001
                error = f"{type(exc).__name__}: {exc}"
                raise
            finally:
                latency_ms = (time.perf_counter() - t0) * 1000.0
                trace = _build_trace(
                    fn=fn,
                    model=model,
                    args=args,
                    kwargs=kwargs,
                    result=result,
                    latency_ms=latency_ms,
                    error=error,
                    capture_prompt=capture_prompt,
                    capture_completion=capture_completion,
                )
                _emit(trace)

        return wrapper

    return decorator


def log_trace(trace: Trace) -> None:
    """Send a manually-constructed Trace."""
    _emit(trace)


def _build_trace(
    *,
    fn: Callable[..., Any],
    model: str | None,
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
    result: Any,
    latency_ms: float,
    error: str | None,
    capture_prompt: bool,
    capture_completion: bool,
) -> Trace:
    prompt_text = _maybe_extract_prompt(args, kwargs) if capture_prompt else None
    completion_text = _maybe_extract_completion(result) if capture_completion else None
    tokens = _extract_token_usage(result)
    resolved_model = model or _maybe_extract_model(result) or "unknown"
    prompt_tokens = tokens.get("prompt_tokens")
    completion_tokens = tokens.get("completion_tokens")
    total_tokens = tokens.get("total_tokens")
    if total_tokens is None and (prompt_tokens or completion_tokens):
        total_tokens = (prompt_tokens or 0) + (completion_tokens or 0)
    cost = compute_cost(resolved_model, prompt_tokens, completion_tokens)
    return Trace(
        model=resolved_model,
        function=getattr(fn, "__qualname__", getattr(fn, "__name__", None)),
        latency_ms=round(latency_ms, 3),
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens,
        cost_usd=cost,
        prompt=prompt_text,
        completion=completion_text,
        error=error,
    )


def _maybe_extract_prompt(args: tuple[Any, ...], kwargs: dict[str, Any]) -> str | None:
    """Best-effort: look for common kwargs (prompt=, messages=, question=)."""
    for key in ("prompt", "question", "input", "user_message"):
        if key in kwargs and isinstance(kwargs[key], str):
            return kwargs[key]
    if "messages" in kwargs and isinstance(kwargs["messages"], list):
        # OpenAI-style: take last user message
        for m in reversed(kwargs["messages"]):
            if isinstance(m, dict) and m.get("role") == "user":
                content = m.get("content")
                if isinstance(content, str):
                    return content
    if args and isinstance(args[0], str):
        return args[0]
    return None


def _maybe_extract_completion(result: Any) -> str | None:
    """Best-effort: handle OpenAI / Anthropic / plain-string return values."""
    if result is None:
        return None
    if isinstance(result, str):
        return result
    # OpenAI chat completion: result.choices[0].message.content
    try:
        choices = getattr(result, "choices", None)
        if choices:
            message = getattr(choices[0], "message", None)
            content = getattr(message, "content", None)
            if isinstance(content, str):
                return content
    except Exception:  # noqa: BLE001
        pass
    # Anthropic messages: result.content[0].text
    try:
        content = getattr(result, "content", None)
        if isinstance(content, list) and content:
            text = getattr(content[0], "text", None)
            if isinstance(text, str):
                return text
    except Exception:  # noqa: BLE001
        pass
    return None


def _extract_token_usage(result: Any) -> dict[str, int]:
    """Pull prompt/completion/total token counts from common LLM response shapes."""
    out: dict[str, int] = {}
    if result is None:
        return out
    usage = getattr(result, "usage", None)
    if usage is None:
        return out
    # OpenAI: prompt_tokens, completion_tokens, total_tokens
    for src_key, dest_key in (
        ("prompt_tokens", "prompt_tokens"),
        ("completion_tokens", "completion_tokens"),
        ("total_tokens", "total_tokens"),
        # Anthropic: input_tokens, output_tokens
        ("input_tokens", "prompt_tokens"),
        ("output_tokens", "completion_tokens"),
    ):
        try:
            value = getattr(usage, src_key, None)
            if value is None and isinstance(usage, dict):
                value = usage.get(src_key)
            if isinstance(value, int):
                out[dest_key] = value
        except Exception:  # noqa: BLE001
            continue
    return out


def _maybe_extract_model(result: Any) -> str | None:
    if result is None:
        return None
    model = getattr(result, "model", None)
    if isinstance(model, str):
        return model
    return None


def _emit(trace: Trace) -> None:
    """Post the trace in a background thread; never raise."""
    if _print_local:
        log.info(
            "trace model=%s function=%s latency_ms=%s tokens=%s cost=%s",
            trace.model,
            trace.function,
            trace.latency_ms,
            trace.total_tokens,
            trace.cost_usd,
        )

    def _send() -> None:
        try:
            headers = {"Content-Type": "application/json"}
            if _api_key:
                headers["Authorization"] = f"Bearer {_api_key}"
            httpx.post(
                f"{_endpoint.rstrip('/')}/traces",
                json=trace.model_dump(mode="json"),
                headers=headers,
                timeout=2.0,
            )
        except Exception as exc:  # noqa: BLE001
            log.debug("tracelens: trace POST failed (fail-soft): %s", exc)

    th = threading.Thread(target=_send, daemon=True, name="tracelens-emit")
    th.start()
    _async_post_threads.append(th)


# Public re-exports.
__all__ = [
    "configure",
    "traced",
    "log_trace",
    "Trace",
    "TraceStats",
    "ModelBreakdown",
    "compute_cost",
]
__version__ = "0.1.0a1"
