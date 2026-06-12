"""
Elasticsearch Chatbot — FastAPI Application

Endpoints:
  POST /fetch          Load data by category + time range (uses scroll, gets ALL docs)
  POST /ask            Ask a question about the loaded data
  POST /ask-with-fetch  One-shot: fetch + ask in one call
  GET  /health         Health check
  GET  /categories     List available categories
  DELETE /session      Clear loaded data
"""
import os

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from engine import (
    ChatEngine,
    ChatRequest,
    ChatResponse,
    EsConfig,
    FetchRequest,
    FetchResult,
    LlmConfig,
    make_es_client,
)
from categories import CATEGORY_LIST, get_category_summary

load_dotenv()

# ── Config from env ───────────────────────────────────────────────

ES_CONFIG = EsConfig(
    hosts=os.getenv("ES_HOSTS", "http://192.168.1.16:9200"),
    username=os.getenv("ES_USERNAME", "elastic"),
    password=os.getenv("ES_PASSWORD", ""),
)

LLM_CONFIG = LlmConfig(
    base_url=os.getenv("LLM_BASE_URL", "http://192.168.1.125:11434/v1"),
    api_key=os.getenv("LLM_API_KEY", "ollama"),
    model=os.getenv("LLM_MODEL"),
    timeout=int(os.getenv("LLM_TIMEOUT", "120")),
)

APP_HOST = os.getenv("APP_HOST", "0.0.0.0")
APP_PORT = int(os.getenv("APP_PORT", "8000"))

# ── App + Engine ──────────────────────────────────────────────────

es_client = make_es_client(ES_CONFIG)
engine = ChatEngine(es_client, LLM_CONFIG)

app = FastAPI(
    title="Elasticsearch Chatbot",
    description="Chat with Elasticsearch fatboy_data* records by category and time range",
    version="1.0.0",
)


# ── Request/Response Models ───────────────────────────────────────

class FetchPayload(BaseModel):
    """Fetch data from ES."""
    mode: str = Field(default="category", description="'category' or 'raw_query'")
    category: str | None = Field(default=None, description="Category name (if mode=category)")
    raw_query: dict | None = Field(default=None, description="Full ES query body (if mode=raw_query)")
    date_from: str | None = Field(default=None, description="Start date (ISO format: 2025-01-01)")
    date_to: str | None = Field(default=None, description="End date (ISO format: 2025-12-31)")
    date_field: str = Field(default="@timestamp", description="Date field to filter on")


class AskPayload(BaseModel):
    question: str
    debug: bool = False


class AskWithFetchPayload(BaseModel):
    question: str
    fetch: FetchPayload
    debug: bool = False


class FetchResponse(BaseModel):
    total_hits: int
    documents_returned: int
    category: str | None
    date_range: dict | None
    chunks_total: int
    warnings: list[str]


class AskResponse(BaseModel):
    answer: str
    sources_used: int
    total_hits: int
    debug: dict | None = None


# ── Endpoints ─────────────────────────────────────────────────────

@app.get("/health")
def health():
    try:
        info = es_client.info()
        return {
            "status": "ok",
            "es_cluster": info.get("cluster_name"),
            "es_version": info.get("version", {}).get("number"),
            "llm_model": LLM_CONFIG.model,
            "llm_base_url": LLM_CONFIG.base_url,
        }
    except Exception as e:
        return {"status": "degraded", "error": str(e)}


@app.get("/categories")
def list_categories():
    return {
        "categories": CATEGORY_LIST,
        "details": get_category_summary(),
    }


@app.post("/fetch", response_model=FetchResponse)
def fetch_data(payload: FetchPayload):
    """Load ALL matching data into the chat session."""
    try:
        req = FetchRequest(
            mode=payload.mode,
            category=payload.category,
            raw_query=payload.raw_query,
            date_from=payload.date_from,
            date_to=payload.date_to,
            date_field=payload.date_field,
        )
        result = engine.fetch_data(req)
        return FetchResponse(
            total_hits=result.total_hits,
            documents_returned=len(result.documents),
            category=result.category,
            date_range=result.date_range,
            chunks_total=result.chunks_total,
            warnings=result.warnings,
        )
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal error: {e}")


@app.post("/ask", response_model=AskResponse)
def ask_question(payload: AskPayload):
    """Ask a question about the currently loaded data."""
    if not engine.store.is_loaded:
        raise HTTPException(
            status_code=400,
            detail="No data loaded. Call /fetch first with a category and time range.",
        )
    try:
        result = engine.ask(ChatRequest(question=payload.question), debug=payload.debug)
        return AskResponse(
            answer=result.answer,
            sources_used=result.sources_used,
            total_hits=engine.store.total_hits,
            debug=result.debug,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generating answer: {e}")


@app.post("/ask-with-fetch", response_model=AskResponse)
def ask_with_fetch(payload: AskWithFetchPayload):
    """One-shot: fetch data then ask a question."""
    try:
        fetch_req = FetchRequest(
            mode=payload.fetch.mode,
            category=payload.fetch.category,
            raw_query=payload.fetch.raw_query,
            date_from=payload.fetch.date_from,
            date_to=payload.fetch.date_to,
            date_field=payload.fetch.date_field,
        )
        engine.fetch_data(fetch_req)
        result = engine.ask(ChatRequest(question=payload.question), debug=payload.debug)
        return AskResponse(
            answer=result.answer,
            sources_used=result.sources_used,
            total_hits=engine.store.total_hits,
            debug=result.debug,
        )
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {e}")


@app.delete("/session")
def clear_session():
    """Clear the current chat session data."""
    engine.store.clear()
    return {"status": "session cleared"}


# ── Main ──────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    print(f"Starting ES Chatbot on {APP_HOST}:{APP_PORT}")
    print(f"  ES: {ES_CONFIG.hosts}")
    print(f"  Index: fatboy_data*")
    print(f"  LLM: {LLM_CONFIG.model} @ {LLM_CONFIG.base_url}")
    uvicorn.run(app, host=APP_HOST, port=APP_PORT)
