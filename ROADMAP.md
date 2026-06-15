# Roadmap — tracelens

## Shipping log (newest on top)

### 2026-06-15 — Scaffold
- [x] Repo + doc set + CI workflow
- [x] Stub SDK with intended API
- Notes: scaffolded alongside evalstack so the two compose.

---

## Short-term — next 4 weeks

- [ ] **P0 / Working `@traced` decorator** — capture latency, model, prompt, completion, tokens *(est. 1 day · drives launch post)*
- [ ] **P0 / FastAPI collector** — `POST /traces` + `GET /traces` with filters
- [ ] **P0 / Storage** — SQLite local; ClickHouse Cloud for hosted demo
- [ ] **P0 / Dashboard MVP** — Next.js, time-series chart (latency p99), model breakdown
- [ ] **P0 / Deploy to Fly.io + Cloudflare Pages** — live `tracelens.kartikaneja.com`
- [ ] **P1 / Cost calculation** — per-model token-to-cost ledger (lookup from OpenAI/Anthropic pricing)
- [ ] **P1 / OpenTelemetry compatibility** — accept OTel-format LLM spans
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
