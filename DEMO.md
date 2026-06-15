# Demo — tracelens

## Live demo

**URL:** [tracelens.kartikaneja.com](https://tracelens.kartikaneja.com) *(coming soon)*

**Hosting plan:**
- Collector: Fly.io free tier
- Dashboard: Cloudflare Pages
- Storage: ClickHouse Cloud free tier (or SQLite for local)

## Local fallback (once shipped)

```bash
git clone https://github.com/anejakartik/tracelens.git
cd tracelens
pip install -e ./sdk
export OPENAI_API_KEY=sk-...
docker compose up -d
python examples/sample_app.py        # generates sample traces
open http://localhost:3000/dashboard
```

## Quick port-forward demo

```bash
cloudflared tunnel --url http://localhost:8000   # collector
cloudflared tunnel --url http://localhost:3000   # dashboard
```
