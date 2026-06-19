# tracelens

> Datadog for LLM apps — for indie devs. Drop-in observability with one decorator.

**Live demo:** [tracelens.kartikaneja.com](https://tracelens.kartikaneja.com) *(coming soon)*
**Status:** alpha · last shipped 2026-06-17
**Built by:** [Kartik Aneja](https://kartikaneja.com) — AI/ML Platform Engineer

[![CI](https://github.com/anejakartik/tracelens/actions/workflows/ci.yml/badge.svg)](https://github.com/anejakartik/tracelens/actions/workflows/ci.yml)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](./LICENSE)

---

## Why this exists

Your LLM app got slow yesterday. Or expensive. Or started hallucinating. You have no idea which.

See [PRODUCT.md](./PRODUCT.md) for the full writeup. TL;DR:

- **Who:** Solo founder / small team running an LLM app
- **Pain:** No visibility into latency p99, cost per user, hallucination patterns
- **Why now:** Every LLM app needs this; Datadog/Honeycomb are heavyweight + paid; LangSmith is LangChain-only

## Demo

![tracelens dashboard — p50/p95 latency, total cost, error rate, per-model breakdown, recent traces with status pills](./docs/screenshots/01-dashboard.png)

`examples/quickstart.py` posts 25 synthetic traces across `gpt-4o`, `gpt-4o-mini`, `claude-3-5-sonnet`, and `claude-3-5-haiku`. The dashboard auto-refreshes every 5s and computes p50/p95/p99 latency, total cost from the embedded pricing table, error rate, and per-model breakdown — all without sending a single real LLM call.

## What works today (alpha MVP)

- **`@tracelens.traced` decorator** — captures latency, tokens, cost, errors; fail-soft (collector down → wrapped function still returns)
- **OpenAI + Anthropic auto-detection** — pulls token usage from `response.usage.{prompt,completion,total}_tokens` (OpenAI) or `response.usage.{input,output}_tokens` (Anthropic)
- **Per-model cost calculation** — static pricing table for OpenAI + Anthropic SKUs (gpt-4o, gpt-4o-mini, o1, claude-3.5-sonnet, claude-3.5-haiku, claude-3-opus, …)
- **FastAPI collector** — `POST /traces` ingest, `GET /traces` with model/window/error filters, `GET /traces/{id}`, `GET /stats` with p50/p95/p99 + per-model breakdown
- **Pluggable storage** — SQLite (default, zero-config local) or ClickHouse (columnar, scales to hundreds of millions of traces); choose with `TRACELENS_DB_URL`
- **Static dashboard at `/`** — p50/p95 latency, total cost, error rate, per-model table, recent trace list with status pills
- **No-key quickstart** — `examples/quickstart.py` posts 25 synthetic traces so you can see the dashboard light up without spending tokens

## Try it (60 seconds, local)

```bash
git clone https://github.com/anejakartik/tracelens.git
cd tracelens
pip install -e ./sdk
docker compose up -d
python examples/quickstart.py
open http://localhost:8000
```

Real usage:

```python
import tracelens
import openai

tracelens.configure(endpoint="http://localhost:8000")
client = openai.OpenAI()

@tracelens.traced(model="gpt-4o-mini")
def ask(question: str) -> str:
    return client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": question}],
    ).choices[0].message.content

ask("Summarize the last commit.")  # latency + tokens + cost flow to the collector
```

## Architecture

See [docs/architecture.md](./docs/architecture.md). Stack: Python SDK + FastAPI collector + pluggable storage (SQLite or ClickHouse) + server-rendered HTML dashboard (no Node deps).

### Storage backends

| URL prefix | Backend | Notes |
| --- | --- | --- |
| `sqlite:///...` | SQLAlchemy/SQLModel → SQLite | default; single-process |
| `postgresql://...` | SQLAlchemy/SQLModel → Postgres | requires `psycopg2-binary` |
| `clickhouse://user:pass@host:9000/db` | `clickhouse-driver` (native protocol) | MergeTree engine, partitioned by month, 90-day TTL, `ORDER BY (model, timestamp)` |

Bring up ClickHouse locally:

```bash
TRACELENS_DB_URL=clickhouse://default:@clickhouse:9000/tracelens \
    docker compose --profile clickhouse up -d
```

## What's next

See [ROADMAP.md](./ROADMAP.md). Top items: ClickHouse adapter, public deploy (Fly.io + Cloudflare Pages), OpenTelemetry compatibility, evalstack integration (link traces → eval results), Slack alerts.

## Contributing

PRs welcome. See [AGENTS.md](./AGENTS.md).

## License

MIT — see [LICENSE](./LICENSE).
