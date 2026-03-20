# AstroAgentTrace

A simple, single-file observability tool for AI agents. 

Lightweight REST API • Span/trace support • Zero dependencies. **For CrewAI • LangChain • AutoGPT • MetaGPT • Custom agents** — Complete visibility into agent decisions, errors, token usage, and costs.

Scale notes: SQLite handles 10k–500k agents comfortably. Postgres migration script included for larger fleets.

Step-by-step span logging: every agent action (preprocess → llm.call → postprocess) visible in one click for debugging & audit.

perfect bolt-on for Datadog / Snowflake observability stacks. Enterprise commercial license & pricing available — DM @kawokawok98 on X

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

