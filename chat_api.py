"""
ES Intelligence Chatbot — FastAPI Server + Chat UI
===================================================
Full-featured REST API with an integrated web-based chat interface.

API Endpoints:
  GET  /health              Health check + cluster info
  GET  /models              List available Ollama models
  GET  /categories          List available data categories
  GET  /indices             List searchable ES indices
  POST /session/create      Create a new chat session
  POST /session/fetch       Fetch data into a session
  POST /session/ask         Ask a question (non-streaming)
  POST /session/ask/stream  Ask a question (SSE streaming)
  GET  /session/status      Session info + history
  DELETE /session           Clear session data
  POST /session/reset       Reset session
  POST /ask                 One-shot ask (fetch + ask, no session)

UI:
  GET  /                    Chat interface (served as static HTML)
"""
import os
import json
from datetime import datetime
from typing import Optional

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, HTMLResponse
from pydantic import BaseModel, Field

from engine import (
    ChatEngine,
    ChatRequest,
    ChatResponse,
    ChatSession,
    EsConfig,
    FetchRequest,
    LlmConfig,
    ProgressEvent,
    make_es_client,
)
from categories import CATEGORY_LIST, CATEGORY_QUERIES, get_category_summary

load_dotenv()

# ── Configuration ─────────────────────────────────────────────────

ES_CONFIG = EsConfig(
    hosts=os.getenv("ES_HOSTS", "http://192.168.1.16:9200"),
    username=os.getenv("ES_USERNAME", "elastic"),
    password=os.getenv("ES_PASSWORD", ""),
)

LLM_CONFIG = LlmConfig(
    base_url=os.getenv("LLM_BASE_URL", "http://127.0.0.1:11434/v1"),
    api_key=os.getenv("LLM_API_KEY", "ollama"),
    model=os.getenv("LLM_MODEL"),
    timeout=int(os.getenv("LLM_TIMEOUT", "120")),
)

APP_HOST = os.getenv("APP_HOST", "0.0.0.0")
APP_PORT = int(os.getenv("APP_PORT", "8000"))

# ── App ───────────────────────────────────────────────────────────

es_client = make_es_client(ES_CONFIG)

app = FastAPI(
    title="ES Intelligence Chatbot",
    description="Chat with military intelligence data in Elasticsearch",
    version="2.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Session Store (in-memory) ─────────────────────────────────────

_sessions: dict[str, ChatEngine] = {}


def get_or_create_session(
    session_id: str,
    max_turns: int = 10,
    llm_config: Optional[LlmConfig] = None,
) -> ChatEngine:
    if session_id not in _sessions:
        sess = ChatSession(max_turns=max_turns)
        cfg = llm_config or LLM_CONFIG
        _sessions[session_id] = ChatEngine(es_client, cfg, session=sess)
    return _sessions[session_id]


# ── Request / Response Models ─────────────────────────────────────

class CreateSessionRequest(BaseModel):
    session_id: str = Field(..., description="Unique session identifier")
    max_turns: int = Field(default=10, ge=1, le=50)
    llm_model: Optional[str] = Field(default=None)
    llm_timeout: Optional[int] = Field(default=None, ge=10, le=600)


class CreateSessionResponse(BaseModel):
    session_id: str
    max_turns: int
    llm_model: str
    created_at: str


class FetchPayload(BaseModel):
    mode: str = Field(default="category")
    category: Optional[str] = Field(default=None)
    raw_query: Optional[dict] = Field(default=None)
    date_from: Optional[str] = Field(default=None)
    date_to: Optional[str] = Field(default=None)
    date_field: str = Field(default="@timestamp")


class FetchResponse(BaseModel):
    total_hits: int
    documents_returned: int
    documents_stored: int
    category: Optional[str]
    date_range: Optional[dict]
    warnings: list[str]


class AskPayload(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)
    debug: bool = Field(default=False)
    mediate: bool = Field(default=True)


class AskResponse(BaseModel):
    answer: str
    sources_used: int
    total_hits: int
    session_turns_used: int
    session_turns_remaining: int
    debug: Optional[dict] = None


class AskWithFetchPayload(BaseModel):
    question: str
    fetch: FetchPayload
    debug: bool = Field(default=False)
    mediate: bool = Field(default=True)


class SessionStatusResponse(BaseModel):
    session_id: str
    is_loaded: bool
    total_hits: int
    documents_stored: int
    category: Optional[str]
    date_range: Optional[dict]
    turns_used: int
    turns_remaining: int
    max_turns: int
    llm_model: str
    history: list[dict]


class HealthResponse(BaseModel):
    status: str
    es_cluster: Optional[str] = None
    es_version: Optional[str] = None
    llm_model: str
    llm_base_url: str
    active_sessions: int


# ── Endpoints ─────────────────────────────────────────────────────

@app.get("/health", response_model=HealthResponse)
def health():
    try:
        info = es_client.info()
        return HealthResponse(
            status="ok",
            es_cluster=info.get("cluster_name"),
            es_version=info.get("version", {}).get("number"),
            llm_model=LLM_CONFIG.model,
            llm_base_url=LLM_CONFIG.base_url,
            active_sessions=len(_sessions),
        )
    except Exception as e:
        return HealthResponse(
            status=f"degraded: {e}",
            llm_model=LLM_CONFIG.model,
            llm_base_url=LLM_CONFIG.base_url,
            active_sessions=len(_sessions),
        )


@app.get("/models")
def list_models():
    """List available Ollama models."""
    import urllib.request
    try:
        req = urllib.request.Request(f"{LLM_CONFIG.base_url.replace('/v1', '')}/api/tags")
        resp = urllib.request.urlopen(req, timeout=10)
        data = json.loads(resp.read().decode())
        models = []
        for m in data.get("models", []):
            models.append({
                "name": m["name"],
                "size_gb": round(m.get("size", 0) / 1e9, 1),
            })
        return {"models": models, "default": LLM_CONFIG.model}
    except Exception as e:
        return {"error": str(e), "default": LLM_CONFIG.model}


@app.get("/categories")
def list_categories():
    return {"categories": CATEGORY_LIST, "details": get_category_summary()}


@app.get("/indices")
def list_indices():
    from categories import INDEX_PATTERN
    try:
        r = es_client.search(index=INDEX_PATTERN, size=0, track_total_hits=True)
        total = r["hits"]["total"]["value"]
        r2 = es_client.search(
            index=INDEX_PATTERN, size=0,
            aggs={"by_index": {"terms": {"field": "_index", "size": 50}}},
        )
        indices = [{"name": b["key"], "doc_count": b["doc_count"]}
                   for b in r2["aggregations"]["by_index"]["buckets"]]
        return {"pattern": INDEX_PATTERN, "total_docs": total, "indices": indices}
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"ES error: {e}")


@app.post("/session/create", response_model=CreateSessionResponse)
def create_session(req: CreateSessionRequest):
    if req.session_id in _sessions:
        raise HTTPException(status_code=409, detail=f"Session '{req.session_id}' already exists")
    cfg = LlmConfig(
        base_url=LLM_CONFIG.base_url,
        api_key=LLM_CONFIG.api_key,
        model=req.llm_model or LLM_CONFIG.model,
        timeout=req.llm_timeout or LLM_CONFIG.timeout,
    )
    get_or_create_session(req.session_id, max_turns=req.max_turns, llm_config=cfg)
    return CreateSessionResponse(
        session_id=req.session_id,
        max_turns=req.max_turns,
        llm_model=cfg.model,
        created_at=datetime.now().isoformat(),
    )


@app.post("/session/fetch", response_model=FetchResponse)
def session_fetch(session_id: str, payload: FetchPayload):
    eng = _sessions.get(session_id)
    if not eng:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found")
    try:
        result = eng.fetch_data(FetchRequest(
            mode=payload.mode, category=payload.category,
            raw_query=payload.raw_query, date_from=payload.date_from,
            date_to=payload.date_to, date_field=payload.date_field,
        ))
        return FetchResponse(
            total_hits=result.total_hits,
            documents_returned=len(result.documents),
            documents_stored=len(eng.store.documents),
            category=result.category, date_range=result.date_range,
            warnings=result.warnings,
        )
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/session/ask", response_model=AskResponse)
def session_ask(session_id: str, payload: AskPayload):
    eng = _sessions.get(session_id)
    if not eng:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found")
    if not eng.store.is_loaded:
        raise HTTPException(status_code=400, detail="No data loaded. Fetch first.")
    try:
        result = eng.ask(ChatRequest(question=payload.question),
                         debug=payload.debug, mediate=payload.mediate)
        return AskResponse(
            answer=result.answer, sources_used=result.sources_used,
            total_hits=eng.store.total_hits,
            session_turns_used=eng.session.turns_used,
            session_turns_remaining=eng.session.turns_remaining,
            debug=result.debug,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/session/ask/stream")
def session_ask_stream(session_id: str, payload: AskPayload):
    eng = _sessions.get(session_id)
    if not eng:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found")
    if not eng.store.is_loaded:
        raise HTTPException(status_code=400, detail="No data loaded. Fetch first.")

    def event_generator():
        try:
            for event in eng.ask_stream(
                ChatRequest(question=payload.question),
                debug=payload.debug, mediate=payload.mediate,
            ):
                if isinstance(event, ProgressEvent):
                    yield f"event: progress\ndata: {json.dumps({'type': event.type, 'message': event.message, 'step': event.step, 'total_steps': event.total_steps, 'data': event.data})}\n\n"
                elif isinstance(event, ChatResponse):
                    yield f"event: answer\ndata: {json.dumps({'type': 'answer', 'answer': event.answer, 'sources_used': event.sources_used, 'debug': event.debug})}\n\n"
        except Exception as e:
            yield f"event: error\ndata: {json.dumps({'error': str(e)})}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"})


@app.get("/session/status", response_model=SessionStatusResponse)
def session_status(session_id: str):
    eng = _sessions.get(session_id)
    if not eng:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found")
    return SessionStatusResponse(
        session_id=session_id, is_loaded=eng.store.is_loaded,
        total_hits=eng.store.total_hits, documents_stored=len(eng.store.documents),
        category=eng.store.category, date_range=eng.store.date_range,
        turns_used=eng.session.turns_used, turns_remaining=eng.session.turns_remaining,
        max_turns=eng.session.max_turns, llm_model=eng.model,
        history=eng.session._history,
    )


@app.delete("/session")
def delete_session(session_id: str):
    if session_id not in _sessions:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found")
    del _sessions[session_id]
    return {"status": "deleted", "session_id": session_id}


@app.post("/session/reset")
def reset_session(session_id: str):
    eng = _sessions.get(session_id)
    if not eng:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found")
    eng.session.reset()
    eng.store.clear()
    return {"status": "reset", "session_id": session_id}


@app.post("/ask", response_model=AskResponse)
def one_shot_ask(payload: AskWithFetchPayload):
    try:
        eng = ChatEngine(es_client, LLM_CONFIG)
        eng.fetch_data(FetchRequest(
            mode=payload.fetch.mode, category=payload.fetch.category,
            raw_query=payload.fetch.raw_query, date_from=payload.fetch.date_from,
            date_to=payload.fetch.date_to, date_field=payload.fetch.date_field,
        ))
        result = eng.ask(ChatRequest(question=payload.question),
                         debug=payload.debug, mediate=payload.mediate)
        return AskResponse(
            answer=result.answer, sources_used=result.sources_used,
            total_hits=eng.store.total_hits,
            session_turns_used=0, session_turns_remaining=0, debug=result.debug,
        )
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Chat UI ───────────────────────────────────────────────────────

# Read HTML from the separate file at startup
import os as _os
_CHAT_UI_PATH = _os.path.join(_os.path.dirname(__file__), "_chat_ui_html.py")
if _os.path.exists(_CHAT_UI_PATH):
    with open(_CHAT_UI_PATH) as _f:
        _raw = _f.read()
    # Extract the triple-quoted string value
    _start = _raw.index('CHAT_HTML = r"""') + len('CHAT_HTML = r"""')
    _end = _raw.index('"""', _start)
    CHAT_HTML = _raw[_start:_end]
else:
    # Fallback: inline definition
    CHAT_HTML = "<html><body><h1>Chat UI not found</h1><p>Please ensure _chat_ui_html.py exists.</p></body></html>"


@app.get("/", response_class=HTMLResponse)
def chat_ui():
    return CHAT_HTML


# ── Main ─────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    print(f"Starting ES Intelligence Chatbot on {APP_HOST}:{APP_PORT}")
    print(f"  ES: {ES_CONFIG.hosts}  |  Index: fatboy_data*")
    print(f"  LLM: {LLM_CONFIG.model} @ {LLM_CONFIG.base_url}")
    print(f"  UI:  http://localhost:{APP_PORT}")
    uvicorn.run(app, host=APP_HOST, port=APP_PORT)
