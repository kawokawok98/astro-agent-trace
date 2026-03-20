# AstroAgentTrace

A simple, single-file observability tool for AI agents.

Lightweight REST API • Span/trace support • Zero dependencies.

### Live Demo
https://python-tool--kawokawok98.replit.app

### Quick start

```bash
git clone https://github.com/kawokawok98/astro-agent-trace.git
cd astro-agent-trace

docker build -t astro-trace .
docker run -p 8000:8000 -v $(pwd)/data:/app astro-trace
Test it:
Bashcurl -X POST http://localhost:8000/run \
  -H "X-API-Key: demo-key-for-github" \
  -H "Content-Type: application/json" \
  -d '{"input": {"message": "hello"}}'
Check data at:
http://localhost:8000/traces
http://localhost:8000/stats
http://localhost:8000/metrics
Features

Agent run logging
Trace + span hierarchy
Token usage and basic cost tracking
Prometheus metrics endpoint
API key auth + CORS
Basic LangChain callback support

 MIT licensed.
Thanks for checking it out - tmk
Enterprise commercial license & support available — DM @kawokawok98 on X
