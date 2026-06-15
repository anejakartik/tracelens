# Copilot instructions for tracelens

> Same intent as [../AGENTS.md](../AGENTS.md), Copilot-format.

## Product context

This repo is **tracelens** — LLM observability for indie devs. See [PRODUCT.md](../PRODUCT.md).

- **Target user:** Solo founder / 2–5 person team running LLM apps
- **Their pain:** No visibility into latency / cost / hallucination patterns
- **Our wedge:** Drop-in Python SDK, LLM-specific dashboards, free + self-host, composes with evalstack

## Code style

- Python: type hints, ruff, pytest
- TypeScript: strict, eslint, vitest
- Small focused changes
- No LangChain in the SDK — intentional non-goal

## Repo layout

```
tracelens/
├── README.md, PRODUCT.md, ROADMAP.md, AGENTS.md, DEMO.md
├── .github/
├── docs/architecture.md
├── sdk/        # Python (light deps)
├── collector/  # FastAPI (runs on 512MB VM)
├── dashboard/  # Next.js (Cloudflare Pages)
└── examples/
```

## Hard constraints

- SDK overhead < 2ms per traced call
- SDK fails soft (no exceptions if collector unreachable)
- Collector runs on 512MB RAM
- Free-tier hosting only — flag PRs that move us to paid tier
