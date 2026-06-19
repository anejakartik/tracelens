# Roadmap — tracelens

## Shipping log (newest on top)

### 2026-06-19 — ClickHouse storage adapter
- [x] Storage protocol introduced (`server/storage/__init__.py`) with two implementations
- [x] SQLAlchemy/SQLModel backend (default) handles `sqlite://` + `postgresql://` URLs
- [x] ClickHouse backend (`clickhouse-driver`) handles `clickhouse://user:pass@host:9000/db` URLs — MergeTree engine, monthly partitioning, `ORDER BY (model, timestamp)`, 90-day TTL
- [x] Auto-detect at startup via TRACELENS_DB_URL; factory picks the right impl
- [x] Optional `clickhouse` Compose profile spins up a CH server with HTTP (8123) + native (9000) ports exposed
- [x] Both backends verified end-to-end via quickstart.py (25 synthetic traces → identical /stats output)

### 2026-06-17 — Alpha MVP: SDK + collector + dashboard
- [x] Working `@tracelens.traced` decorator — captures latency, function name, tokens, cost, errors; fail-soft async POST to collector
- [x] OpenAI + Anthropic token usage auto-detected from response shape
- [x] Per-model cost calculation via static pricing table (OpenAI + Anthropic SKUs)
- [x] FastAPI collector — `POST /traces`, `GET /traces` with model + window + only_errors filters, `GET /traces/{id}`, `GET /stats` with p50/p95/p99 + per-model breakdown
- [x] SQLite storage by default; pluggable via `TRACELENS_DB_URL`
- [x] Static dashboard at `/` — p50/p95 latency, total cost, error rate, model breakdown table, recent traces with status pills, window switcher, 5s auto-refresh
- [x] `examples/quickstart.py` posts 25 synthetic traces without a real LLM call
- Notes: dashboard is server-rendered HTML (no Node build step) for fast iteration; can swap to Next.js when needed.

### 2026-06-15 — Scaffold
- [x] Repo + doc set + CI workflow
- [x] Stub SDK with intended API
- Notes: scaffolded alongside evalstack so the two compose.

---

## Short-term — next 4 weeks

- [ ] **P0 / ClickHouse-specific aggregations** — push the /stats query down into ClickHouse SQL (currently still pulls rows to Python); needed to hit the "scales to 100M traces" claim
- [ ] **P0 / Deploy to Fly.io + Cloudflare Pages** — live `tracelens.kartikaneja.com`
- [ ] **P0 / Time-series chart** — replace the summary stat tile with an inline sparkline for p95 latency
- [ ] **P1 / OpenTelemetry compatibility** — accept OTel-format LLM spans
- [ ] **P1 / evalstack integration** — link a trace → its judge results
- [ ] **P2 / Sample replay** — public dashboard with synthetic + replayed real traffic

## Medium-term — months 2–3

- [ ] **Slack / Discord alerts** — DM on cost spike / p99 regression
- [ ] **TypeScript SDK**
- [ ] **Go SDK**
- [ ] **Anomaly detection** — auto-flag cost spikes, latency regressions, hallucinations
- [ ] **Per-tenant cost dashboards** — for SaaS LLM apps
- [ ] **evalstack integration** — link traces → eval results

## Long-term — 6+ months

- [ ] Cost forecasting (linear regression on per-user trends)
- [ ] Self-host Helm chart (under `tracelens-chart/`)
- [ ] Managed cloud offering (only if self-host adoption is real)

## Content posts derived from this roadmap

| Feature | Posted? |
|---|---|
| Launch post (alpha) | _pending_ |
| Cost-tracking deep-dive | _pending_ |
| Why we picked ClickHouse | _pending_ |
