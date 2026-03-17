# astro-agent-trace v1.0
Lightweight self-hostable AI agent tracing
 topics: fastapi  observability  llm  agents  opentelemetry prometheus
# AgentTrace v1.1

**Zero-dep REST API for LLM agent observability.** 
Register → Run → Metrics. No DBs, no SDKs. Prod-ready tracing in minutes.

[![Demo](https://via.placeholder.com/800x400?text=AgentTrace+v1.1)](https://python-tool--kawokawok98.replit.app/)
⭐ **Built solo during IdEs Of MaRcH bEnDeR™**

## Why AgentTrace?
LLM agents need tracing that doesn't suck. Traditional APM misses token variance, multi-step spans, probabilistic outputs. AgentTrace gives you:

- Success rates, p95 latency, token usage — computed inline
- Span tracing for tool calls and reasoning chains
- Pure HTTP/JSON — works in any language
- In-memory store (Redis optional for prod)

## 🚀 Quickstart (60s)

```bash
# Docker or Replit
docker run -p 8080:8080 kawokawok98/agenttrace:v1.1

# 1. Register agent
curl -X POST http://localhost:8080/register -d '{"name":"my-agent"}'

# 2. Create run  
RUN_ID=$(curl -s -X POST http://localhost:8080/runs \
  -d '{"agent_id":1,"input":"2+2?"}' | jq -r '.run_id')

# 3. Log results
curl -X PATCH http://localhost:8080/runs/$RUN_ID \
  -d '{"output":"4","success":true,"latency_ms":250}'

# 4. Metrics!
curl http://localhost:8080/metrics/1 | jq
