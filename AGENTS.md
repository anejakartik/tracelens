# AGENTS.md — instructions for AI coding agents

## Before you touch code

1. Read [PRODUCT.md](./PRODUCT.md) — who this is for + the wedge
2. Read the top of [ROADMAP.md](./ROADMAP.md) — what's prioritized
3. Check open issues + PRs to avoid duplication

## Coding conventions

- **Python:** type hints, ruff, pytest
- **TypeScript:** strict mode, eslint, vitest
- Small focused PRs
- Match existing patterns; no speculative abstractions

## Repo-specific guardrails

- SDK overhead **< 2ms per traced call** — this is a hard requirement
- SDK must work without a running collector (fail soft)
- Collector must run on 512MB Fly.io VM
- Dashboard must load in < 1s with 100K traces
- Do not add LangChain to the SDK — it's a non-goal

## Commits & PRs

- Imperative-mood commit messages focused on *why*
- PR description: problem (1–2 lines) + change (2–3 lines) + test plan
- Squash on merge

## Deployment

- CI: `.github/workflows/ci.yml`
- Deploy: Fly.io for collector, Cloudflare Pages for dashboard
- Live: `tracelens.kartikaneja.com` *(coming)*
- Free tier only

## Companion doc

[.github/copilot-instructions.md](./.github/copilot-instructions.md) — Copilot-format variant.
