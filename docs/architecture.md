# Architecture — tracelens

## High-level flow

```mermaid
flowchart LR
  A[Your LLM app] -->|@tracelens.traced| B[SDK]
  B -->|HTTP POST /traces| C[Collector]
  C -->|insert| D[(ClickHouse / SQLite)]
  E[Dashboard] -->|GET /traces| C
  E -->|render| F[User browser]
```

## Components

| Component | Stack | Constraints |
|---|---|---|
| SDK (`sdk/`) | Python, httpx, pydantic | < 2ms overhead per call, fail-soft on collector outage |
| Collector (`collector/`) | FastAPI | Runs on 512MB Fly.io VM |
| Storage | ClickHouse Cloud (hosted) / SQLite (local) | Time-series friendly |
| Dashboard (`dashboard/`) | Next.js + Recharts | < 1s load on 100K traces |

## Data model (planned)

```python
class Trace(BaseModel):
    id: UUID
    timestamp: datetime
    model: str
    prompt: str
    completion: str
    prompt_tokens: int
    completion_tokens: int
    latency_ms: float
    cost_usd: float          # computed from model + tokens
    user_id: str | None
    error: str | None
    metadata: dict[str, Any]
```

## Why ClickHouse for storage

- LLM apps emit 10K–10M traces/day → time-series-shaped data
- Columnar storage gives fast aggregations (p99 latency, cost by model)
- ClickHouse Cloud has a free tier
- SQLite for local dev, swap via env var

## Non-goals

- Distributed tracing across multiple services — single LLM app only
- Sampling — capture every trace; LLM call volume is small enough
- Eval functionality — that's [`evalstack`](https://github.com/anejakartik/evalstack)
