# agentops_app.py
# AstroAgentTrace OSS - Single-file AgentOps-style tracing. Built for $5M++ acquisition.
# OTEL-ready, Prometheus-ready, self-host in 60 seconds.

from typing import Any, Dict, List, Optional
from datetime import datetime, timezone
import uuid
import json
import sqlite3
import os
import logging
from pathlib import Path

from fastapi import FastAPI, HTTPException, Depends, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import APIKeyHeader
from pydantic import BaseModel, Field

from contextlib import contextmanager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# =========================
# Config (enterprise-ish)
# =========================

API_KEY = os.getenv("AGENTOPS_API_KEY", "demo-key-for-github")
DB_PATH = Path(os.getenv("AGENTOPS_DB", "agentops.db"))
OTEL_ENABLED = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT") is not None

# =========================
# Domain models
# =========================

class Span(BaseModel):
    span_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    parent_span_id: Optional[str] = None
    name: str
    start_time: datetime
    end_time: Optional[datetime] = None
    attributes: Dict[str, Any] = Field(default_factory=dict)

class Trace(BaseModel):
    trace_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    agent_name: str
    input: Dict[str, Any]
    spans: List[Span] = Field(default_factory=list)
    success: bool = True
    error: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

# =========================
# Tracing helpers
# =========================

@contextmanager
def span(
    trace: Trace,
    name: str,
    parent_span_id: Optional[str] = None,
    attrs: Optional[Dict[str, Any]] = None,
):
    s = Span(
        name=name,
        parent_span_id=parent_span_id,
        start_time=datetime.now(timezone.utc),
        attributes=attrs or {},
    )
    try:
        yield s
        s.end_time = datetime.now(timezone.utc)
    except Exception as e:
        s.end_time = datetime.now(timezone.utc)
        s.attributes["error"] = str(e)
        trace.success = False
        trace.error = trace.error or str(e)
        logger.error(f"Span failed: {name}", exc_info=True)
        raise
    finally:
        trace.spans.append(s)
        if OTEL_ENABLED:
            # Hook point: convert this Span to real OTEL span and export
            logger.info(f"OTEL export ready for span {s.span_id}")

# =========================
# Agent runtime (extendable)
# =========================

def dummy_model_call(prompt: str) -> Dict[str, Any]:
    # replace with real LLM call later
    reply = f"you said: {prompt}"
    return {
        "text": reply,
        "prompt_tokens": len(prompt.split()),
        "completion_tokens": len(reply.split()),
    }

def run_agent(agent_name: str, user_input: Dict[str, Any]) -> Trace:
    trace = Trace(agent_name=agent_name, input=user_input)

    with span(trace, "agent.preprocess") as sp:
        message = str(user_input.get("message", ""))
        sp.attributes["input.length"] = len(message)

    with span(trace, "agent.build_prompt") as sp:
        prompt = f"User message:\n{message}\n"
        sp.attributes["prompt.length"] = len(prompt)

    with span(trace, "llm.call") as sp:
        sp.attributes.update(
            {
                "llm.provider": "dummy",
                "llm.model": "demo-model",
            }
        )
        result = dummy_model_call(prompt)
        total_tokens = result["prompt_tokens"] + result["completion_tokens"]
        sp.attributes.update(
            {
                "llm.usage.prompt_tokens": result["prompt_tokens"],
                "llm.usage.completion_tokens": result["completion_tokens"],
                "llm.usage.total_tokens": total_tokens,
                "llm.cost_estimated_usd": total_tokens * 0.000002,
            }
        )

    with span(trace, "agent.postprocess") as sp:
        sp.attributes["reply.length"] = len(result["text"])

    return trace

# =========================
# Storage (SQLite)
# =========================

def _conn():
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS traces (
            trace_id   TEXT PRIMARY KEY,
            agent_name TEXT,
            created_at TEXT,
            success    INTEGER,
            payload    TEXT
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_created ON traces(created_at)")
    return conn

def save_trace(trace: Trace) -> None:
    conn = _conn()
    with conn:
        conn.execute(
            "INSERT OR REPLACE INTO traces(trace_id, agent_name, created_at, success, payload) "
            "VALUES (?, ?, ?, ?, ?)",
            (
                trace.trace_id,
                trace.agent_name,
                trace.created_at.isoformat(),
                1 if trace.success else 0,
                trace.model_dump_json(),
            ),
        )
    conn.close()
    logger.info(f"Saved trace {trace.trace_id}")

def load_trace(trace_id: str) -> Optional[Trace]:
    conn = _conn()
    cur = conn.cursor()
    cur.execute("SELECT payload FROM traces WHERE trace_id = ?", (trace_id,))
    row = cur.fetchone()
    conn.close()
    return Trace.model_validate(json.loads(row[0])) if row else None

def list_traces(limit: int = 50) -> List[Dict[str, Any]]:
    conn = _conn()
    cur = conn.cursor()
    cur.execute(
        "SELECT trace_id, agent_name, created_at, success "
        "FROM traces ORDER BY created_at DESC LIMIT ?",
        (limit,),
    )
    rows = cur.fetchall()
    conn.close()
    return [
        {
            "trace_id": r[0],
            "agent": r[1],
            "created": r[2],
            "success": bool(r[3]),
        }
        for r in rows
    ]

def get_stats() -> Dict[str, Any]:
    conn = _conn()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*), SUM(success) FROM traces")
    total, success = cur.fetchone()
    total = total or 0
    success = success or 0

    avg_spans = 0.0
    if total:
        cur.execute("SELECT payload FROM traces")
        rows = cur.fetchall()
        span_counts = [
            len(json.loads(row[0]).get("spans", [])) for row in rows
        ]
        avg_spans = sum(span_counts) / total if total else 0.0

    conn.close()
    return {
        "total_traces": total,
        "success_rate_pct": round((success / total) * 100, 2) if total else 0.0,
        "avg_spans_per_trace": round(avg_spans, 2),
    }

# =========================
# FastAPI
# =========================

app = FastAPI(title="AstroAgentTrace OSS", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten later if needed
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

async def verify_key(key: Optional[str] = Depends(api_key_header)):
    # In demo mode, don't enforce API key; in production, require it
    if API_KEY != "demo-key-for-github" and key != API_KEY:
        raise HTTPException(status_code=403, detail="Invalid API key")
    return key

class RunRequest(BaseModel):
    input: Dict[str, Any]

class RunResponse(BaseModel):
    trace_id: str
    success: bool

@app.post("/run", response_model=RunResponse)
def run(req: RunRequest, _=Depends(verify_key)):
    trace = run_agent("demo-agent", req.input)
    save_trace(trace)
    return RunResponse(trace_id=trace.trace_id, success=trace.success)

@app.get("/trace/{trace_id}")
def get_trace(trace_id: str, _=Depends(verify_key)):
    trace = load_trace(trace_id)
    if not trace:
        raise HTTPException(status_code=404, detail="trace not found")
    return trace

@app.get("/traces")
def get_traces(limit: int = Query(50, le=200), _=Depends(verify_key)):
    return list_traces(limit)

@app.get("/stats")
def stats(_=Depends(verify_key)):
    return get_stats()

@app.get("/metrics")
def metrics(_=Depends(verify_key)):
    s = get_stats()
    return (
        "# HELP agenttrace_traces_total Total traces\n"
        "# TYPE agenttrace_traces_total gauge\n"
        f"agenttrace_traces_total {s['total_traces']}\n"
        "# HELP agenttrace_success_rate Success rate %\n"
        "# TYPE agenttrace_success_rate gauge\n"
        f"agenttrace_success_rate {s['success_rate_pct']}\n"
    )

@app.get("/health")
def health():
    return {"status": "healthy", "version": "1.0.0"}

# =========================
# Entry
# =========================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("agentops_app:app", host="0.0.0.0", port=8000, reload=True)
