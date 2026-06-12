# ES Intelligence Chatbot

A full-featured RAG (Retrieval-Augmented Generation) chatbot for Elasticsearch intelligence data. Combines a Flask web UI with a REST API, powered by Ollama LLM models.

## UI Screenshots

See [docs/UI_SCREENSHOTS.md](docs/UI_SCREENSHOTS.md) for UI layout and example interactions.

## Architecture

```
┌─────────────┐     ┌──────────────┐     ┌─────────────────┐
│  Browser UI  │────▶│  Flask Server │────▶│  Elasticsearch   │
│  (chat.html) │◀────│  (server.py)  │◀────│  (192.168.1.16)  │
└─────────────┘     └──────┬───────┘     └─────────────────┘
                           │
                    ┌──────▼───────┐
                    │  Ollama LLM   │
                    │ (192.168.1.125)│
                    └──────────────┘
```

**Key Components:**
- **Flask Server** (`server.py`) — Web UI + REST API + Swagger docs
- **RAG Engine** (`engine.py`) — Full pipeline: intent classification → ES retrieval → LLM synthesis → Mediator
- **Categories** (`categories.py`) — Pre-built ES query templates for different data categories
- **DataStore** — In-memory session store with deduplication
- **Mediator** — LLM-based answer formatter that ensures complete, non-summarized responses

## Prerequisites

- Python 3.11+
- Elasticsearch 8.x running and accessible
- Ollama running with at least one LLM model
- Network access to both ES and Ollama

## Installation

```bash
# Clone the repository
git clone <repo-url>
cd es_chatbot

# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

## Configuration

Create a `.env` file in the project root:

```env
# Elasticsearch Connection
ES_HOSTS=http://192.168.1.16:9200
ES_USERNAME=elastic
ES_PASSWORD=your_password

# LLM Backend (Ollama via OpenAI-compatible API)
LLM_BASE_URL=http://192.168.1.125:11434/v1
LLM_API_KEY=ollama

# App Settings
APP_HOST=0.0.0.0
APP_PORT=8000
```

**Note:** No hardcoded LLM model — model is selected via the UI dropdown at runtime.

## Running the Application

```bash
cd es_chatbot
source .venv/bin/activate
python server.py
```

The server starts at `http://localhost:8000`.

**If port 8000 is in use:**
```bash
kill -9 $(lsof -ti :8000)
python server.py
```

## Web UI Flow

1. **Setup Page** (`GET /`) — Select data category, LLM model, date range, and session parameters
2. **Fetch Data** (`POST /fetch`) — Loads data from Elasticsearch into the session
3. **Chat Page** (`GET /chat?session_id=xxx`) — Ask questions, view answers with source citations
4. **Swagger Docs** (`GET /docs`) — Interactive API documentation

## REST API Reference

### System Endpoints

#### Health Check
```
GET /api/health
```
Returns service status, ES cluster info, and current model.

**Response:**
```json
{
  "status": "ok",
  "es_cluster": "fatboydev",
  "es_version": "8.19.14",
  "llm_model": "llama3:8b-instruct-q8_0"
}
```

#### List Available Models
```
GET /api/models
```
Returns all LLM models available from Ollama (excludes embedding models).

**Response:**
```json
{
  "models": [
    {"name": "llama3:8b-instruct-q8_0", "size_gb": 8.5},
    {"name": "qwen2.5:14b", "size_gb": 9.0}
  ],
  "default": "llama3:8b-instruct-q8_0"
}
```

#### List Categories
```
GET /api/categories
```
Returns available data categories for fetching.

**Response:**
```json
{
  "categories": [
    "Force Disposition",
    "Training Areas",
    "Infra Development",
    "PLA Sitrep",
    "General Area",
    "Movement",
    "AIR Aspects",
    "SAM Deployment",
    "Mobile Interception",
    "Overall Deployment"
  ]
}
```

### Session Lifecycle

#### Create Session
```
POST /api/session/create
Content-Type: application/json

{
  "session_id": "my-session-001",
  "llm_model": "llama3:8b-instruct-q8_0",
  "max_turns": 10
}
```

**Response:**
```json
{
  "session_id": "my-session-001",
  "created_at": "2026-06-12T10:46:17.623436"
}
```

**Errors:**
- `400` — session_id is required
- `409` — session already exists

#### Fetch Data into Session
```
POST /api/session/fetch?session_id=my-session-001
Content-Type: application/json

{
  "mode": "category",
  "category": "General Area"
}
```

**Modes:**
- `category` — Use a predefined category query template
- `raw_query` — Provide a raw Elasticsearch query JSON

**Response:**
```json
{
  "total_hits": 21217,
  "documents_stored": 7668,
  "warnings": ["Deduplicated 13229 docs by description_hash (19830 → 7601 unique)."]
}
```

**Errors:**
- `404` — Session not found
- `500` — Fetch error

#### Ask a Question
```
POST /api/session/ask?session_id=my-session-001
Content-Type: application/json

{
  "question": "What are the main training areas?",
  "debug": false,
  "mediate": true
}
```

**Response:**
```json
{
  "answer": "**Unique locations (197 total)** (out of 28407 documents):\n\n  • burang (715 docs)\n  • karachi (532 docs)...",
  "sources_used": 200,
  "debug": {
    "mode": "agg-LIST_UNIQUE",
    "total": 28407,
    "field": "location_name.keyword",
    "buckets": 200,
    "mediator": {"mediator": "active", "chunked": true, "chunks": 4}
  }
}
```

**Intent Modes:**
- `agg-LIST_UNIQUE` — Aggregation query returning all unique values (e.g., "list all locations")
- `agg-TOP_N` — Top N results by count
- `agg-COUNT` — Count of matching documents
- `agg-GROUP_BY` — Grouped aggregation
- `direct` — Direct LLM answer from retrieved documents
- `map-reduce` — Chunked analysis for large document sets

**Errors:**
- `400` — No data loaded in session
- `404` — Session not found
- `500` — Processing error

#### One-Shot Ask (No Session)
```
POST /api/ask
Content-Type: application/json

{
  "question": "Summarize key locations",
  "fetch": {
    "mode": "raw_query",
    "raw_query": {"query": {"bool": {"must_not": [{"term": {"form_status": 5}}]}}, "size": 3}
  },
  "llm_model": "llama3:8b-instruct-q8_0"
}
```

Fetches data and answers in a single call. No session created.

#### Session Status
```
GET /api/session/status?session_id=my-session-001
```

**Response:**
```json
{
  "session_id": "my-session-001",
  "is_loaded": true,
  "total_hits": 21217,
  "documents_stored": 7668,
  "turns_used": 3,
  "turns_remaining": 7,
  "history": [...]
}
```

#### Reset Session
```
POST /session/reset?session_id=my-session-001
```
Clears history and data, keeps the session.

#### Delete Session
```
DELETE /session?session_id=my-session-001
```
Removes the session entirely.

### UI Form Endpoints

#### Setup Page
```
GET /
```
Returns the HTML setup page with model dropdown, category selector, and configuration form.

#### Fetch Data (Form Submit)
```
POST /fetch
Content-Type: application/x-www-form-urlencoded

session_id=xxx&mode=category&category=General+Area&model=llama3:8b-instruct-q8_0&max_turns=10
```
Fetches data and redirects to `/chat?session_id=xxx`.

#### Chat Page
```
GET /chat?session_id=xxx
```
Returns the chat interface HTML with session context.

### Docs Redirect
```
GET /docs
```
Redirects to `/apidocs/` (Swagger UI).

## Data Categories

Each category maps to a pre-built Elasticsearch query:

| Category | Description | ES Query Focus |
|----------|-------------|----------------|
| Force Disposition | Enemy force deployment, disposition, formation data | `enemy_formation_name`, `location_name`, `activity_type: [deployment, disposition, movement]` |
| Training Areas | Military training locations, exercises | `training_type`, `form_type: training` |
| Infra Development | Infrastructure projects, types, status | `activity_type: infra`, `infra_type` |
| PLA Sitrep | PLA patrolling and situation reports | `form_type: [patrolling, sitrep]` |
| General Area | General geographic data with location names | `location_name` exists |
| Movement | Force tracking with formation and location | `activity_type: movement` |
| AIR Aspects | Air-related activities | `activity_type: air` |
| SAM Deployment | SAM deployment data | `activity_type: sam` |
| Mobile Interception | Mobile interception data | `activity_type: interception` |
| Overall Deployment | All deployment data | `activity_type: deployment` |

## RAG Pipeline Details

### 1. Intent Classification
Questions are classified into intent types:
- **LIST_UNIQUE** — "list all X", "show me all X", "what are the X" → ES aggregation
- **TOP_N** — "top 5 X", "most common X" → ES aggregation with size limit
- **COUNT** — "how many X" → ES count aggregation
- **GROUP_BY** — "group by X" → ES terms aggregation
- **DETAIL** — Everything else → Document retrieval + LLM synthesis

### 2. Retrieval
- Uses `multi_match` with phrase boosting (3x) + best_fields with fuzziness
- Searches across all `fatboy_data_*` indices
- Deduplicates by `description_hash`
- Returns up to 100 documents

### 3. LLM Synthesis
- **Direct mode** — ≤50 docs passed directly to LLM
- **Map-reduce mode** — >50 docs split into chunks of 25, analyzed separately, then combined
- All LLM calls use `max_tokens=4000`

### 4. Mediator
- Always active (never bypassed)
- Receives formatted documents + question
- For aggregation queries with >50 buckets: chunked processing (50 per chunk, max_tokens=8000 per chunk)
- Context limit: 32000 chars
- Timeout: 120 seconds
- Explicitly instructed to NOT summarize or truncate

## Available Ollama Models

The dropdown dynamically loads from Ollama `/api/tags`. Recommended models:

| Model | Size | Best For |
|-------|------|----------|
| `llama3:8b-instruct-q8_0` | 8.5 GB | General purpose, fast |
| `qwen2.5:14b` | 9.0 GB | Detailed analysis, reasoning |
| `qwen3:14b` | 9.3 GB | Latest, best quality |
| `deepseek-r1:14b` | 9.0 GB | Deep reasoning |
| `gemma3:12b-it-q8_0` | 13.4 GB | Alternative |

Embedding models (`nomic-embed-text`, `bge-m3`) are automatically filtered out.

## Troubleshooting

### Port 8000 in use
```bash
kill -9 $(lsof -ti :8000)
```

### LLM model not found
- Check Ollama is running: `curl http://192.168.1.125:11434/api/tags`
- Verify model name matches exactly (e.g., `llama3:8b-instruct-q8_0`)
- Model must be pulled: `ollama pull llama3:8b-instruct-q8_0`

### No data loaded
- Fetch data first via `POST /api/session/fetch` or the UI setup form
- Check ES connection: `curl http://192.168.1.16:9200`

### LLM hallucinating / ignoring data
- The mediator is configured to always use retrieved data
- If issues persist, try a different model (qwen2.5:14b works well)
- Check `debug.mediator.source` in response to see if it's using docs directly

### Stale server processes
Hermes background process tracking can be unreliable. Always kill before restarting:
```bash
kill -9 $(lsof -ti :8000)
python -B server.py
```

## Project Structure

```
es_chatbot/
├── server.py           # Flask app: UI + REST API + Swagger
├── engine.py           # RAG engine: intent, retrieval, LLM, mediator
├── categories.py       # Category query templates
├── config/
│   ├── settings.py     # Index registry
│   └── ...
├── core/
│   ├── rag.py          # Alternative RAG pipeline (unused)
│   └── time_parser.py  # Date parser
├── templates/
│   └── chat.html       # UI template (inline in server.py)
├── tests/              # Test files (25 files)
├── .env                # Configuration (not in git)
├── .gitignore
├── requirements.txt
└── README.md           # This file
```

## License

Proprietary — All rights reserved.
