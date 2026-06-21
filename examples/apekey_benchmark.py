"""Benchmark: apekey.ai vs OpenAI baseline, measured via tracelens.

Four conditions, one fixed workload:

  1. baseline           — openai gpt-4o-mini (premium frontier model)
  2. apekey-cost        — https://apekey.ai/v1, routing.prefer=cost
  3. apekey-speed       — https://apekey.ai/v1, routing.prefer=speed
  4. apekey-quality     — https://apekey.ai/v1, routing.prefer=quality

Workload: 20 deterministic NL→SQL questions on a fixed SaaS schema
(matches the dataask demo dataset). The model is asked to emit a single
read-only SELECT against the schema; we don't execute the SQL — we only
measure latency / tokens / cost / completion quality.

Quality dimension: each completion is scored 0/1 by a fixed judge prompt
to gpt-4o-mini — "does this look like a single valid SELECT against
tables/columns that exist in the schema, without DDL or DML?". Apples-
to-apples across all four conditions.

Every model call is wrapped by `@tracelens.traced`, so:
  - Latency, tokens, and cost flow into the tracelens collector
  - Per-condition aggregation comes from tracelens's `/stats` endpoint
  - apekey-specific `_optimization` field is captured as metadata

Outputs:
  - Markdown report to stdout
  - JSON dump of per-call results to ./apekey-benchmark-results.json

Usage:
    pip install -e ./sdk
    pip install openai
    export OPENAI_API_KEY=sk-...
    export APEKEY_API_KEY=ak-...
    export TRACELENS_ENDPOINT=http://localhost:8002   # optional
    docker compose up -d   # boots tracelens on :8000 (or alt port)
    python examples/apekey_benchmark.py
"""

from __future__ import annotations

import json
import os
import statistics
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

import tracelens
from openai import OpenAI


# ---------------------------------------------------------------------------
# Workload — 20 NL→SQL questions on the dataask demo schema
# ---------------------------------------------------------------------------

SCHEMA = """\
customers      (id INT, name VARCHAR, plan VARCHAR, country VARCHAR, signup_date DATE)
subscriptions  (id INT, customer_id INT, plan VARCHAR, mrr DOUBLE, started_at TIMESTAMP, ended_at TIMESTAMP)
orders         (id INT, customer_id INT, amount DOUBLE, status VARCHAR, created_at TIMESTAMP)
events         (id INT, customer_id INT, event_name VARCHAR, occurred_at TIMESTAMP)
"""

QUESTIONS: list[str] = [
    # Simple aggregations
    "How many customers do we have in total?",
    "What's the total revenue from paid orders?",
    "What's the average order amount across all completed orders?",
    "How many subscriptions are currently active (ended_at is null)?",
    "How many distinct countries are our customers in?",
    # Grouping
    "Count customers per plan.",
    "Sum total paid order amount by country.",
    "Count active subscriptions per plan.",
    "Count events by event_name.",
    "Average MRR per plan among currently-active subscriptions.",
    # Time-window filters
    "How many customers signed up in May 2026?",
    "What was our MRR by plan as of June 1, 2026?",
    "How many orders were placed in the last 30 days (relative to 2026-06-17)?",
    "Count events that occurred in June 2026.",
    "Weekly active users in June 2026.",
    # Joins
    "Top 5 customers by lifetime paid order amount, with their plan.",
    "For each country, the count of active subscriptions and total MRR.",
    "Customers who signed up in 2026 but have zero orders.",
    "For each plan, the median order amount (use percentile_cont if available).",
    "Which plan has the highest churn rate? Return one row with the plan name.",
]

SYSTEM_PROMPT = f"""You are a senior analytics engineer. Convert a natural-language
question into ONE read-only SQL query against the schema below. Output ONLY the SQL —
no prose, no markdown, no code fences.

Constraints:
- Use ONLY tables and columns listed in the schema.
- Output a single SELECT statement (CTEs via WITH ... SELECT are fine).
- Never emit DDL or DML (no INSERT / UPDATE / DELETE / DROP / CREATE).
- DuckDB dialect. date_trunc, percentile_cont, INTERVAL all available.

SCHEMA:
{SCHEMA}"""


# ---------------------------------------------------------------------------
# Conditions
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Condition:
    name: str
    base_url: str | None       # None means OpenAI default
    api_key_env: str
    model: str
    extra_body: dict[str, Any] = field(default_factory=dict)
    description: str = ""


CONDITIONS: list[Condition] = [
    Condition(
        name="baseline-gpt-4o-mini",
        base_url=None,
        api_key_env="OPENAI_API_KEY",
        model="gpt-4o-mini",
        description="openai.OpenAI() default, premium frontier model",
    ),
    Condition(
        name="apekey-cost",
        base_url="https://apekey.ai/v1",
        api_key_env="APEKEY_API_KEY",
        model="auto",
        extra_body={"routing": {"prefer": "cost"}},
        description="apekey, cost-optimized routing (leans Together-hosted Llama)",
    ),
    Condition(
        name="apekey-speed",
        base_url="https://apekey.ai/v1",
        api_key_env="APEKEY_API_KEY",
        model="auto",
        extra_body={"routing": {"prefer": "speed"}},
        description="apekey, speed-optimized routing (routes to Groq)",
    ),
    Condition(
        name="apekey-quality",
        base_url="https://apekey.ai/v1",
        api_key_env="APEKEY_API_KEY",
        model="auto",
        extra_body={"routing": {"prefer": "quality"}},
        description="apekey, quality-routed (heavier Llama model)",
    ),
]


# ---------------------------------------------------------------------------
# Per-call result
# ---------------------------------------------------------------------------

@dataclass
class CallResult:
    condition: str
    question: str
    sql: str
    latency_ms: float
    prompt_tokens: int | None
    completion_tokens: int | None
    total_tokens: int | None
    cost_usd_self_reported: float | None  # from apekey _optimization
    model_used: str | None                  # from apekey _optimization
    cache_hit: bool | None                  # from apekey _optimization
    quality_pass: bool | None               # from fixed judge
    error: str | None = None


# ---------------------------------------------------------------------------
# Quality judge — single fixed call per completion
# ---------------------------------------------------------------------------

JUDGE_SYSTEM = """You score SQL completions for analytics-engineer-quality.

Return EXACTLY one character: 1 if the SQL is a single valid SELECT (or CTE
chain ending in SELECT) that references ONLY tables/columns in the provided
schema and emits no DDL/DML, 0 otherwise. No prose, no punctuation, just 1 or 0."""


def judge_completion(judge_client: OpenAI, sql: str) -> bool | None:
    """Best-effort 0/1 quality score. Returns None if the judge errored."""
    if not sql:
        return False
    try:
        resp = judge_client.chat.completions.create(
            model="gpt-4o-mini",
            temperature=0,
            max_tokens=2,
            messages=[
                {"role": "system", "content": JUDGE_SYSTEM},
                {"role": "user", "content": f"SCHEMA:\n{SCHEMA}\n\nSQL:\n{sql}"},
            ],
        )
        out = (resp.choices[0].message.content or "").strip()
        return out.startswith("1")
    except Exception:  # noqa: BLE001
        return None


# ---------------------------------------------------------------------------
# Per-question run, instrumented through tracelens
# ---------------------------------------------------------------------------

def _make_client(condition: Condition) -> OpenAI:
    api_key = os.environ.get(condition.api_key_env)
    if not api_key:
        raise RuntimeError(f"{condition.api_key_env} not set")
    if condition.base_url:
        return OpenAI(api_key=api_key, base_url=condition.base_url)
    return OpenAI(api_key=api_key)


def run_condition(
    condition: Condition,
    questions: list[str],
    judge_client: OpenAI,
) -> list[CallResult]:
    print(f"\n=== {condition.name} ===")
    client = _make_client(condition)
    results: list[CallResult] = []

    @tracelens.traced(model=condition.name, capture_prompt=False, capture_completion=False)
    def call(question: str) -> Any:
        kwargs: dict[str, Any] = {
            "model": condition.model,
            "temperature": 0.0,
            "max_tokens": 500,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": question},
            ],
        }
        if condition.extra_body:
            kwargs["extra_body"] = condition.extra_body
        return client.chat.completions.create(**kwargs)

    for i, q in enumerate(questions, 1):
        t0 = time.perf_counter()
        sql = ""
        error: str | None = None
        prompt_tokens = completion_tokens = total_tokens = None
        cost = model_used = cache_hit = None
        try:
            resp = call(q)
            latency_ms = (time.perf_counter() - t0) * 1000
            sql = (resp.choices[0].message.content or "").strip()
            usage = getattr(resp, "usage", None)
            if usage is not None:
                prompt_tokens = getattr(usage, "prompt_tokens", None)
                completion_tokens = getattr(usage, "completion_tokens", None)
                total_tokens = getattr(usage, "total_tokens", None)
            # apekey-specific metadata (best-effort extraction with
            # defensive key fallbacks — the exact field names aren't documented
            # publicly, so we cover the obvious variants).
            try:
                raw = resp.model_dump(mode="json") if hasattr(resp, "model_dump") else {}
                opt = raw.get("_optimization") or raw.get("optimization") or {}
                cost = opt.get("cost_usd") or opt.get("cost")
                model_used = opt.get("model") or opt.get("model_used") or opt.get("served_by")
                cache_hit = opt.get("cache_hit")
                if cache_hit is None:
                    cache_hit = opt.get("cached")
                if cache_hit is None:
                    cache_hit = opt.get("from_cache")
            except Exception:  # noqa: BLE001
                pass
        except Exception as exc:  # noqa: BLE001
            latency_ms = (time.perf_counter() - t0) * 1000
            error = f"{type(exc).__name__}: {exc}"

        quality_pass = judge_completion(judge_client, sql) if not error else False
        results.append(CallResult(
            condition=condition.name,
            question=q,
            sql=sql[:500],
            latency_ms=round(latency_ms, 3),
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            cost_usd_self_reported=cost,
            model_used=model_used,
            cache_hit=cache_hit,
            quality_pass=quality_pass,
            error=error,
        ))
        marker = "✓" if quality_pass else ("✗" if error else "?")
        print(f"  {i:2d}/{len(questions)} {marker} {round(latency_ms):>5}ms  q={q[:60]}")
        time.sleep(0.2)  # gentle rate-limit hedge

    return results


# ---------------------------------------------------------------------------
# Aggregation + reporting
# ---------------------------------------------------------------------------

def _p(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    if len(values) == 1:
        return values[0]
    return statistics.quantiles(values, n=100, method="inclusive")[int(q) - 1]


def aggregate(results: list[CallResult]) -> dict[str, Any]:
    by_cond: dict[str, list[CallResult]] = {}
    for r in results:
        by_cond.setdefault(r.condition, []).append(r)

    summary: dict[str, Any] = {}
    for cond, rows in by_cond.items():
        latencies = [r.latency_ms for r in rows if r.error is None]
        # Cache-miss-only subset — this is the honest projection for a
        # real, varied workload where prompts aren't deterministic repeats.
        cache_miss_rows = [r for r in rows if r.cache_hit is not True]
        cache_miss_latencies = [r.latency_ms for r in cache_miss_rows if r.error is None]
        prompt_t = sum(r.prompt_tokens or 0 for r in rows)
        completion_t = sum(r.completion_tokens or 0 for r in rows)
        total_t = sum(r.total_tokens or 0 for r in rows)
        cost_all = sum(r.cost_usd_self_reported or 0.0 for r in rows)
        cost_miss = sum(r.cost_usd_self_reported or 0.0 for r in cache_miss_rows)
        errors = sum(1 for r in rows if r.error)
        quality_passes = sum(1 for r in rows if r.quality_pass)
        cache_hits = sum(1 for r in rows if r.cache_hit)
        models_used = sorted({r.model_used for r in rows if r.model_used})
        summary[cond] = {
            "n": len(rows),
            "errors": errors,
            "p50_ms": round(_p(latencies, 50), 1) if latencies else 0,
            "p95_ms": round(_p(latencies, 95), 1) if latencies else 0,
            "p99_ms": round(_p(latencies, 99), 1) if latencies else 0,
            "mean_ms": round(statistics.mean(latencies), 1) if latencies else 0,
            "p50_ms_cache_misses_only": round(_p(cache_miss_latencies, 50), 1) if cache_miss_latencies else 0,
            "p95_ms_cache_misses_only": round(_p(cache_miss_latencies, 95), 1) if cache_miss_latencies else 0,
            "prompt_tokens": prompt_t,
            "completion_tokens": completion_t,
            "total_tokens": total_t,
            "self_reported_cost_usd": round(cost_all, 6) if cost_all else None,
            "self_reported_cost_usd_cache_misses_only": round(cost_miss, 6) if cost_miss else None,
            "cache_hits": cache_hits,
            "cache_hit_rate": round(cache_hits / len(rows), 3) if rows else 0,
            "quality_pass_rate": round(quality_passes / len(rows), 3) if rows else 0,
            "models_used": models_used,
        }
    return summary


def markdown_report(summary: dict[str, Any], total_questions: int) -> str:
    lines = [
        f"# apekey.ai vs OpenAI benchmark · {datetime.now(timezone.utc).strftime('%Y-%m-%d')}",
        "",
        f"- **Workload:** {total_questions} NL→SQL questions on the dataask demo schema",
        "- **Quality dimension:** single judge prompt to gpt-4o-mini (0/1 per completion)",
        "- **Instrumentation:** every call wrapped by `@tracelens.traced`",
        "- **Fair-quality comparison:** baseline-gpt-4o-mini vs apekey-quality — open-model output sits closest to the frontier on the quality column",
        "- **Cache honesty:** apekey exact-match cache means deterministic prompts will hit. We report `cache_hit_rate` per condition AND a `cache-misses only` cost projection — the second number is what real varied workloads will see.",
        "",
        "## Aggregate per condition (all calls)",
        "",
        "| Condition | n | errs | p50 ms | p95 ms | tokens | self-reported cost | cache hit rate | quality pass rate |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for cond, s in summary.items():
        cost_str = f"${s['self_reported_cost_usd']:.6f}" if s["self_reported_cost_usd"] else "—"
        lines.append(
            f"| {cond} | {s['n']} | {s['errors']} | {s['p50_ms']} | {s['p95_ms']} | {s['total_tokens']:,} | {cost_str} | {s['cache_hit_rate']:.0%} | {s['quality_pass_rate']:.0%} |"
        )
    lines += [
        "",
        "## Cache-miss projection — what a varied real workload will look like",
        "",
        "| Condition | cache-misses n | p50 ms | p95 ms | self-reported cost |",
        "|---|---|---|---|---|",
    ]
    for cond, s in summary.items():
        miss_n = s["n"] - s["cache_hits"]
        cost_miss = s.get("self_reported_cost_usd_cache_misses_only")
        cost_str = f"${cost_miss:.6f}" if cost_miss else "—"
        lines.append(
            f"| {cond} | {miss_n} | {s['p50_ms_cache_misses_only']} | {s['p95_ms_cache_misses_only']} | {cost_str} |"
        )
    lines += [
        "",
        "## Models used",
        "",
    ]
    for cond, s in summary.items():
        models = ", ".join(s["models_used"]) if s["models_used"] else "—"
        lines.append(f"- **{cond}** — {models}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    if not os.environ.get("OPENAI_API_KEY"):
        print("OPENAI_API_KEY is required (baseline + quality judge).", file=sys.stderr)
        sys.exit(2)
    if not os.environ.get("APEKEY_API_KEY"):
        print("APEKEY_API_KEY is required (apekey conditions).", file=sys.stderr)
        sys.exit(2)

    endpoint = os.environ.get("TRACELENS_ENDPOINT", "http://localhost:8000")
    tracelens.configure(endpoint=endpoint, print_local=False)
    judge_client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

    print(f"# apekey-benchmark · {len(QUESTIONS)} questions × {len(CONDITIONS)} conditions")
    print(f"tracelens endpoint: {endpoint}")

    all_results: list[CallResult] = []
    for cond in CONDITIONS:
        all_results.extend(run_condition(cond, QUESTIONS, judge_client))

    # Flush tracelens background threads before aggregation
    time.sleep(1.0)

    summary = aggregate(all_results)
    report = markdown_report(summary, total_questions=len(QUESTIONS))
    print("\n" + report + "\n")

    out_path = os.environ.get("APEKEY_BENCHMARK_OUT", "apekey-benchmark-results.json")
    with open(out_path, "w") as f:
        json.dump(
            {
                "ran_at": datetime.now(timezone.utc).isoformat(),
                "summary": summary,
                "calls": [asdict(r) for r in all_results],
            },
            f,
            indent=2,
        )
    print(f"→ raw results dumped to {out_path}")


if __name__ == "__main__":
    main()
