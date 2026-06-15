# tracelens

> Datadog for LLM apps — for indie devs. Drop-in observability with one decorator.

**Live demo:** [tracelens.kartikaneja.com](https://tracelens.kartikaneja.com) *(coming soon)*
**Status:** scaffold · last shipped 2026-06-15
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

## What works today

- *(scaffolding — first feature lands week of 2026-06-15)*
- Repo + doc structure
- CI workflow
- Stub SDK with intended API (`@traced` decorator, `tracelens.log()`)

## Try it (when shipped)

```bash
pip install tracelens
export TRACELENS_ENDPOINT=https://tracelens.kartikaneja.com
```

```python
import tracelens
import openai

tracelens.configure(endpoint="http://localhost:8000")

@tracelens.traced(model="openai/gpt-4o-mini")
def ask(question: str) -> str:
    return openai.chat.completions.create(...).choices[0].message.content
```

Then check `http://localhost:8000/dashboard` for latency / token / cost charts.

## Architecture

See [docs/architecture.md](./docs/architecture.md). Stack: Python SDK · FastAPI collector · ClickHouse Cloud (free tier) · Next.js dashboard · Cloudflare Pages + Fly.io.

## What's next

See [ROADMAP.md](./ROADMAP.md). Top items: working trace decorator, ingest endpoint, time-series dashboard.

## Contributing

PRs welcome. See [AGENTS.md](./AGENTS.md).

## License

MIT — see [LICENSE](./LICENSE).
