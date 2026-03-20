# agentops_app.py — AstroAgentTrace v1.1
# Python/FastAPI reference implementation matching the live Replit API.
# Live demo: https://python-tool--kawokawok98.replit.app
#
# Run locally:  uvicorn agentops_app:app --reload
# Auth:         Set AGENTOPS_API_KEY env var to enable X-API-Key enforcement.
#               Leave unset for open dev mode.

from fastapi import FastAPI, HTTPException, Depends, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from fastapi.security import APIKeyHeader
from pydantic import BaseModel
import sqlite3, json, uuid, os
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List

app = FastAPI(title="AstroAgentTrace", version="1.1")

app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]
)

API_KEY = os.getenv("AGENTOPS_API_KEY", "")
DB = os.getenv("AGENTOPS_DB", "agenttrace.db")


def init_db():
    conn = sqlite3.connect(DB)
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS agents (
            id TEXT PRIMARY KEY, name TEXT, tags TEXT, created_at TEXT
        );
        CREATE TABLE IF NOT EXISTS runs (
            id TEXT PRIMARY KEY, agent_id TEXT, status TEXT,
            input TEXT, output TEXT, error TEXT,
            latency_ms INTEGER, prompt_tokens INTEGER, completion_tokens INTEGER,
            started_at TEXT, ended_at TEXT
        );
    """)
    conn.commit()
    conn.close()


init_db()

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def verify_key(key: Optional[str] = Depends(api_key_header)):
    if API_KEY and key != API_KEY:
        raise HTTPException(401, "Unauthorized — provide a valid X-API-Key header")


class AgentCreate(BaseModel):
    name: str
    tags: List[str] = []
    description: Optional[str] = None
    model: Optional[str] = None


class RunCreate(BaseModel):
    status: str = "running"
    input: Optional[Dict[str, Any]] = None
    output: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    latencyMs: Optional[int] = None
    promptTokens: Optional[int] = None
    completionTokens: Optional[int] = None


class RunUpdate(BaseModel):
    status: Optional[str] = None
    output: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    latencyMs: Optional[int] = None
    promptTokens: Optional[int] = None
    completionTokens: Optional[int] = None


def _row_to_run(r):
    pt, ct = r[7] or 0, r[8] or 0
    return {
        "id": r[0], "agentId": r[1], "status": r[2],
        "input": json.loads(r[3]) if r[3] else None,
        "output": json.loads(r[4]) if r[4] else None,
        "error": r[5],
        "latencyMs": r[6], "promptTokens": pt, "completionTokens": ct,
        "totalTokens": pt + ct if pt + ct > 0 else None,
        "startedAt": r[9], "endedAt": r[10],
    }


@app.post("/api/agents", status_code=201)
def create_agent(agent: AgentCreate, _=Depends(verify_key)):
    aid = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    conn = sqlite3.connect(DB)
    conn.execute("INSERT INTO agents VALUES (?, ?, ?, ?)",
                 (aid, agent.name, json.dumps(agent.tags), now))
    conn.commit(); conn.close()
    return {"id": aid, "name": agent.name, "tags": agent.tags, "createdAt": now}


@app.get("/api/agents")
def list_agents(tag: Optional[str] = None, _=Depends(verify_key)):
    conn = sqlite3.connect(DB)
    rows = conn.execute("SELECT id, name, tags, created_at FROM agents").fetchall()
    conn.close()
    result = [{"id": r[0], "name": r[1], "tags": json.loads(r[2]), "createdAt": r[3]} for r in rows]
    return [a for a in result if tag in a["tags"]] if tag else result


@app.get("/api/agents/{agent_id}")
def get_agent(agent_id: str, _=Depends(verify_key)):
    conn = sqlite3.connect(DB)
    row = conn.execute("SELECT id, name, tags, created_at FROM agents WHERE id = ?", (agent_id,)).fetchone()
    conn.close()
    if not row: raise HTTPException(404, "Agent not found")
    return {"id": row[0], "name": row[1], "tags": json.loads(row[2]), "createdAt": row[3]}


@app.delete("/api/agents/{agent_id}", status_code=204)
def delete_agent(agent_id: str, _=Depends(verify_key)):
    conn = sqlite3.connect(DB)
    conn.execute("DELETE FROM runs WHERE agent_id = ?", (agent_id,))
    conn.execute("DELETE FROM agents WHERE id = ?", (agent_id,))
    conn.commit(); conn.close()


@app.post("/api/agents/{agent_id}/runs", status_code=201)
def create_run(agent_id: str, run: RunCreate, _=Depends(verify_key)):
    conn = sqlite3.connect(DB)
    if not conn.execute("SELECT 1 FROM agents WHERE id = ?", (agent_id,)).fetchone():
        conn.close(); raise HTTPException(404, "Agent not found")
    rid = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    pt, ct = run.promptTokens or 0, run.completionTokens or 0
    ended = now if run.status in ("success", "error", "timeout") else None
    conn.execute("INSERT INTO runs VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                 (rid, agent_id, run.status, json.dumps(run.input), json.dumps(run.output),
                  run.error, run.latencyMs, pt, ct, now, ended))
    conn.commit(); conn.close()
    return {"id": rid, "agentId": agent_id, "status": run.status, "startedAt": now,
            "totalTokens": pt + ct if pt + ct > 0 else None}


@app.get("/api/agents/{agent_id}/runs")
def list_agent_runs(agent_id: str, status: Optional[str] = None,
                    limit: int = 100, offset: int = 0, _=Depends(verify_key)):
    conn = sqlite3.connect(DB)
    rows = conn.execute(
        "SELECT * FROM runs WHERE agent_id = ? ORDER BY started_at DESC LIMIT ? OFFSET ?",
        (agent_id, limit, offset)).fetchall()
    conn.close()
    result = [_row_to_run(r) for r in rows]
    return [r for r in result if r["status"] == status] if status else result


@app.get("/api/runs")
def list_runs(agent_id: Optional[str] = None, status: Optional[str] = None,
              limit: int = 100, offset: int = 0, _=Depends(verify_key)):
    conn = sqlite3.connect(DB)
    rows = conn.execute("SELECT * FROM runs ORDER BY started_at DESC LIMIT ? OFFSET ?",
                        (limit, offset)).fetchall()
    conn.close()
    result = [_row_to_run(r) for r in rows]
    if agent_id: result = [r for r in result if r["agentId"] == agent_id]
    if status: result = [r for r in result if r["status"] == status]
    return result


@app.get("/api/runs/{run_id}")
def get_run(run_id: str, _=Depends(verify_key)):
    conn = sqlite3.connect(DB)
    row = conn.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
    conn.close()
    if not row: raise HTTPException(404, "Run not found")
    return _row_to_run(row)


@app.patch("/api/runs/{run_id}")
def update_run(run_id: str, update: RunUpdate, _=Depends(verify_key)):
    conn = sqlite3.connect(DB)
    row = conn.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
    if not row: conn.close(); raise HTTPException(404, "Run not found")
    existing = _row_to_run(row)
    pt = update.promptTokens if update.promptTokens is not None else existing.get("promptTokens") or 0
    ct = update.completionTokens if update.completionTokens is not None else existing.get("completionTokens") or 0
    status = update.status or existing["status"]
    ended = datetime.now(timezone.utc).isoformat() if status in ("success", "error", "timeout") else existing.get("endedAt")
    out = json.dumps(update.output) if update.output is not None else row[4]
    conn.execute(
        "UPDATE runs SET status=?, output=?, error=?, latency_ms=?, prompt_tokens=?, completion_tokens=?, ended_at=? WHERE id=?",
        (status, out, update.error, update.latencyMs or row[6], pt, ct, ended, run_id))
    conn.commit(); conn.close()
    return {"id": run_id, "agentId": existing["agentId"], "status": status,
            "latencyMs": update.latencyMs or existing.get("latencyMs"),
            "totalTokens": pt + ct if pt + ct > 0 else None, "endedAt": ended}


@app.get("/api/agents/{agent_id}/metrics")
def get_metrics(agent_id: str, _=Depends(verify_key)):
    conn = sqlite3.connect(DB)
    rows = conn.execute(
        "SELECT status, latency_ms, prompt_tokens, completion_tokens FROM runs WHERE agent_id = ?",
        (agent_id,)).fetchall()
    conn.close()
    total = len(rows)
    success = sum(1 for r in rows if r[0] == "success")
    latencies = [r[1] for r in rows if r[1] is not None]
    tokens = [(r[2] or 0) + (r[3] or 0) for r in rows]
    p95 = sorted(latencies)[int(len(latencies) * 0.95)] if latencies else None
    return {
        "agentId": agent_id, "totalRuns": total,
        "successCount": success,
        "errorCount": sum(1 for r in rows if r[0] == "error"),
        "runningCount": sum(1 for r in rows if r[0] == "running"),
        "timeoutCount": sum(1 for r in rows if r[0] == "timeout"),
        "successRate": round(success / total, 3) if total else 0,
        "avgLatencyMs": round(sum(latencies) / len(latencies)) if latencies else None,
        "p95LatencyMs": p95,
        "totalTokens": sum(tokens),
        "avgTokensPerRun": round(sum(tokens) / len(tokens)) if tokens else None,
    }


@app.get("/api/stats")
def stats(_=Depends(verify_key)):
    conn = sqlite3.connect(DB)
    total_agents = conn.execute("SELECT COUNT(*) FROM agents").fetchone()[0]
    rows = conn.execute("SELECT status, latency_ms, prompt_tokens, completion_tokens FROM runs").fetchall()
    conn.close()
    total = len(rows)
    success = sum(1 for r in rows if r[0] == "success")
    latencies = [r[1] for r in rows if r[1] is not None]
    tokens = sum((r[2] or 0) + (r[3] or 0) for r in rows)
    return {
        "totalAgents": total_agents, "totalRuns": total,
        "successCount": success,
        "successRate": round(success / total, 3) if total else 0,
        "avgLatencyMs": round(sum(latencies) / len(latencies)) if latencies else None,
        "totalTokens": tokens,
    }


@app.get("/api/prometheus")
def prometheus():
    conn = sqlite3.connect(DB)
    total_agents = conn.execute("SELECT COUNT(*) FROM agents").fetchone()[0]
    rows = conn.execute("SELECT status, latency_ms, prompt_tokens, completion_tokens FROM runs").fetchall()
    conn.close()
    total = len(rows)
    success = sum(1 for r in rows if r[0] == "success")
    latencies = [r[1] for r in rows if r[1] is not None]
    tokens = sum((r[2] or 0) + (r[3] or 0) for r in rows)
    return PlainTextResponse("\n".join([
        "# HELP agenttrace_agents_total Total registered agents",
        "# TYPE agenttrace_agents_total gauge",
        f"agenttrace_agents_total {total_agents}",
        "# HELP agenttrace_runs_total Total runs logged",
        "# TYPE agenttrace_runs_total counter",
        f"agenttrace_runs_total {total}",
        "# HELP agenttrace_success_rate Global success rate",
        "# TYPE agenttrace_success_rate gauge",
        f"agenttrace_success_rate {round(success/total,3) if total else 0}",
        "# HELP agenttrace_avg_latency_ms Average run latency in ms",
        "# TYPE agenttrace_avg_latency_ms gauge",
        f"agenttrace_avg_latency_ms {round(sum(latencies)/len(latencies)) if latencies else 0}",
        "# HELP agenttrace_total_tokens_consumed Cumulative tokens",
        "# TYPE agenttrace_total_tokens_consumed counter",
        f"agenttrace_total_tokens_consumed {tokens}",
    ]))


@app.get("/api/healthz")
def health():
    return {"status": "ok", "version": "1.1"}


@app.get("/api/version")
def version():
    return {"name": "AstroAgentTrace", "version": "1.1.0", "authEnabled": bool(API_KEY)}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)
