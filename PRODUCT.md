# Product — tracelens

## Target user

**Persona:** Solo founder / 2–5 person team running an LLM app in production. Spending $200–$5K/month on LLM APIs. Operates on shoestring infrastructure budget.

**Job they're trying to do:** Know what their LLM app is doing in production — latency, cost, error patterns, which prompts blow up token budgets.

**Current workflow:** Scattered `print()` statements, manual OpenAI dashboard refreshes, a spreadsheet of last-month cost.

## The pain

1. **Cost spikes are invisible until the bill arrives.** No real-time per-user cost visibility.
2. **p99 latency is a guess.** Slow queries hurt UX but they have no histograms.
3. **Hallucination patterns hide.** Bad outputs go straight to users with no flag.
4. **LangSmith / Helicone / Datadog don't fit.** Either LangChain-only, $$, or both.

## Existing alternatives — and why they fall short

| Alternative | Why it doesn't fit |
|---|---|
| **Datadog / Honeycomb** | Heavyweight, paid, designed for distributed services — overkill for one LLM endpoint |
| **LangSmith** | LangChain-only; vendor lock-in if you're not on that stack |
| **Helicone** | Reasonable but cloud-only paid tier; closed source |
| **DIY logs + Grafana** | Multi-week build, no LLM-specific dashboards |

## Our wedge

1. **Drop-in Python SDK.** One decorator on your LLM call function.
2. **LLM-specific dashboards out of the box.** Token usage, cost per model, hallucination flagging — pre-built, not generic time-series.
3. **Free + self-hostable.** SQLite local, ClickHouse Cloud free tier, Cloudflare Pages dashboard.
4. **Composable with evalstack.** Trace → eval pipeline in one workflow.

## MVP scope

**Must-have:**
- Python SDK with `@traced` decorator capturing latency, model, prompt, completion, token counts
- FastAPI collector with `POST /traces` and `GET /traces` (filtering by model/time/cost)
- ClickHouse (or SQLite locally) for time-series storage
- Next.js dashboard: latency p50/p95/p99, cost over time, model breakdown
- Working sample app

**Out of scope for MVP** (see [ROADMAP.md](./ROADMAP.md)):
- Multi-language SDKs (TS, Go)
- Slack alerts
- Cost forecasting
- Anomaly detection

## Success metric

- Live demo at `tracelens.kartikaneja.com` showing real (or replayed) traffic
- < 2ms SDK overhead per traced call
- Dashboard loads in < 1s on 100K traces

## Non-goals

- Compete with Datadog enterprise features (SSO, audit, SOC2)
- Distributed tracing across services — single-service LLM apps only for now
- Sampling — capture every trace; LLM call volume is low enough
