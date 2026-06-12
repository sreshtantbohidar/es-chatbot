"""
ES Intelligence Chatbot — Flask Server
======================================
Simple multi-page web UI + REST API with Swagger docs.

Pages:
  GET  /           Setup page (pick category, model, date range)
  POST /fetch      Fetch data from ES, redirect to chat
  GET  /chat       Chat page (ask questions, see answers)
  GET  /docs       Swagger API documentation

API:
  GET  /api/health, /api/models, /api/categories
  POST /api/session/create, /api/session/fetch, /api/session/ask, /api/ask
"""
import os, json, urllib.request
from datetime import datetime
from flask import Flask, request, jsonify, redirect, url_for
from flasgger import Swagger, swag_from
from dotenv import load_dotenv
from engine import ChatEngine, ChatRequest, ChatSession, EsConfig, FetchRequest, LlmConfig, make_es_client
from categories import CATEGORY_LIST

load_dotenv()

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

es_client = make_es_client(ES_CONFIG)
app = Flask(__name__)
Swagger(app)

# ── Session store ─────────────────────────────────────────────────
_sessions: dict[str, ChatEngine] = {}

def get_session(sid, max_turns=10, model=None):
    if not model:
        models = get_models()
        model = models[0]["name"] if models else None
    if sid not in _sessions:
        cfg = LlmConfig(base_url=LLM_CONFIG.base_url, api_key=LLM_CONFIG.api_key,
                        model=model, timeout=LLM_CONFIG.timeout)
        _sessions[sid] = ChatEngine(es_client, cfg, session=ChatSession(max_turns=max_turns))
    elif model:
        _sessions[sid].model = model
    return _sessions[sid]

def get_models():
    try:
        base = LLM_CONFIG.base_url.replace("/v1", "")
        req = urllib.request.Request(f"{base}/api/tags")
        resp = urllib.request.urlopen(req, timeout=10)
        data = json.loads(resp.read().decode())
        return [{"name": m["name"], "size_gb": round(m.get("size", 0)/1e9, 1)} for m in data.get("models", [])]
    except:
        return []

# ── HTML base ─────────────────────────────────────────────────────
BASE = """<!DOCTYPE html>
<html><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>ES Chatbot</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:-apple-system,BlinkMacSystemFont,sans-serif;background:#0f1117;color:#e4e6f0;min-height:100vh}
.hd{background:#161822;border-bottom:1px solid #2a2d3e;padding:12px 20px;display:flex;align-items:center;gap:12px}
.hd h1{font-size:16px;font-weight:600}
.hd .sub{font-size:11px;color:#5a5e78}
.badge{font-size:10px;padding:3px 8px;border-radius:20px;font-weight:600}
.badge-g{background:rgba(74,222,128,.12);color:#4ade80}
.badge-b{background:rgba(108,140,255,.12);color:#6c8cff}
.c{max-width:800px;margin:30px auto;padding:0 20px}
.card{background:#161822;border:1px solid #2a2d3e;border-radius:12px;padding:24px;margin-bottom:16px}
.card h2{font-size:18px;margin-bottom:4px}
.card .desc{font-size:13px;color:#5a5e78;margin-bottom:16px}
.row{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:12px}
label{font-size:11px;font-weight:600;color:#9498b0;text-transform:uppercase;letter-spacing:.5px;display:block;margin-bottom:4px}
select,input[type=text],input[type=number],input[type=date]{width:100%;background:#1c1f2e;border:1px solid #2a2d3e;color:#e4e6f0;padding:8px 10px;border-radius:8px;font-size:13px;outline:none}
select:focus,input:focus{border-color:#6c8cff}
.btn{background:linear-gradient(135deg,#4a6cf7,#7c3aed);color:#fff;border:none;padding:10px 24px;border-radius:8px;font-size:14px;font-weight:600;cursor:pointer;width:100%}
.btn:hover{opacity:.9}
.btn:disabled{opacity:.4;cursor:not-allowed}
.chips{display:flex;flex-wrap:wrap;gap:6px;margin-top:6px}
.chip{font-size:11px;padding:3px 8px;border-radius:16px;background:#1c1f2e;border:1px solid #2a2d3e;cursor:pointer;color:#9498b0}
.chip:hover{border-color:#6c8cff;color:#6c8cff}
.chip.on{background:rgba(108,140,255,.15);border-color:#6c8cff;color:#6c8cff}
.notice{padding:10px 16px;border-radius:8px;margin-bottom:12px;font-size:13px}
.notice.err{background:rgba(248,113,113,.1);color:#f87171;border:1px solid rgba(248,113,113,.2)}
.notice.ok{background:rgba(74,222,128,.1);color:#4ade80;border:1px solid rgba(74,222,128,.2)}
.notice.info{background:rgba(108,140,255,.08);color:#6c8cff;border:1px solid rgba(108,140,255,.15)}
/* Chat */
.chat-wrap{max-width:900px;margin:20px auto;padding:0 20px;display:flex;flex-direction:column;height:calc(100vh - 80px)}
.chat{flex:1;overflow-y:auto;padding:10px 0}
.msg{display:flex;gap:10px;margin-bottom:12px;max-width:85%}
.msg.u{align-self:flex-end;flex-direction:row-reverse}
.av{width:28px;height:28px;border-radius:6px;display:flex;align-items:center;justify-content:center;font-size:13px;flex-shrink:0}
.msg.u .av{background:linear-gradient(135deg,#6366f1,#8b5cf6)}
.msg.b .av{background:linear-gradient(135deg,#0ea5e9,#06b6d4)}
.bubble{padding:10px 14px;border-radius:10px;font-size:13px;line-height:1.5;word-wrap:break-word;white-space:pre-wrap}
.msg.u .bubble{background:linear-gradient(135deg,#4f46e5,#6366f1);color:#fff}
.msg.b .bubble{background:#1c1f2e;border:1px solid #2a2d3e}
.bubble strong{font-weight:600;color:#6c8cff}
.src{font-size:10px;color:#5a5e78;margin-top:4px}
.input-row{display:flex;gap:8px;padding-top:10px;border-top:1px solid #2a2d3e}
textarea{flex:1;background:#1c1f2e;border:1px solid #2a2d3e;color:#e4e6f0;padding:10px;border-radius:8px;resize:none;min-height:40px;max-height:100px;font-size:13px;outline:none}
textarea:focus{border-color:#6c8cff}
.send{width:40px;height:40px;border-radius:8px;border:none;background:linear-gradient(135deg,#4a6cf7,#7c3aed);color:#fff;cursor:pointer;font-size:16px}
.send:disabled{opacity:.3}
</style></head><body>
<div class="hd">
  <h1>🔍 ES Intelligence Chatbot</h1>
  <div class="sub">{{ llm_model }} · {{ es_status }}</div>
  <span class="badge badge-g">● Connected</span>
</div>
{{ content }}
</body></html>"""

def render(content, notice=None, notice_type="info"):
    html = BASE.replace("{{ content }}", (f'<div class="c"><div class="notice {notice_type}">{notice}</div></div>' if notice else "") + content)
    html = html.replace("{{ llm_model }}", LLM_CONFIG.model or "—")
    try:
        info = es_client.info()
        es_status = f'{info.get("cluster_name","?")} v{info.get("version",{}).get("number","?")}'
    except:
        es_status = "ES unreachable"
    html = html.replace("{{ es_status }}", es_status)
    return html

# ── Pages ─────────────────────────────────────────────────────────

@app.get("/")
def setup():
    models = get_models()
    # Filter to only LLM models (exclude embedding models)
    llm_models = [m for m in models if not any(x in m["name"].lower() for x in ["embed", "bge-m3"])]
    default_model = "llama3:8b-instruct-q8_0"
    # Fall back to first available model if llama3 not found
    if not any(m["name"] == default_model for m in llm_models):
        default_model = llm_models[0]["name"] if llm_models else ""
    model_opts = "".join(f'<option value="{m["name"]}"' + (' selected' if m["name"] == default_model else '') + f'>{m["name"]} ({m["size_gb"]} GB)</option>' for m in llm_models)
    cat_opts = "".join(f'<option value="{c}">{c}</option>' for c in CATEGORY_LIST)
    cat_chips = "".join(f'<span class="chip" onclick="setCat(\'{c}\')">{c}</span>' for c in CATEGORY_LIST[:6])
    now = datetime.now().strftime("%H%M%S")
    # Preset queries as Python variables
    preset_infra = '{"query":{"bool":{"must":[{"term":{"activity_type":"infra"}},{"exists":{"field":"infra_type"}},{"exists":{"field":"location_name"}}],"must_not":[{"term":{"form_status":5}}]}}}'
    preset_deployment = '{"query":{"bool":{"must":[{"exists":{"field":"enemy_formation_name"}},{"exists":{"field":"location_name"}},{"terms":{"activity_type.keyword":["deployment","disposition","movement"]}}],"must_not":[{"term":{"form_status":5}}]}}}'
    preset_all = '{"query":{"bool":{"must_not":[{"term":{"form_status":5}}]}}}'
    
    content = '''
    <div class="c">
      <div class="card">
        <h2>⚙️ Session Configuration</h2>
        <div class="desc">Pick a data source and model, then load your data.</div>
        <form method="POST" action="/fetch">
          <div class="row">
            <div>
              <label>Fetch Mode</label>
              <select name="mode" id="mode" onchange="toggleMode()">
                <option value="category">Category (recommended)</option>
                <option value="raw_query">Raw ES Query</option>
              </select>
            </div>
            <div>
              <label>Model</label>
              <select name="model">''' + model_opts + '''</select>
            </div>
          </div>
          <div id="catSection">
            <label>Category</label>
            <select name="category" id="cat">''' + cat_opts + '''</select>
            <div class="chips">''' + cat_chips + '''</div>
            <div style="margin-top:10px">
              <label>Quick Presets</label>
              <div class="chips">
                <span class="chip" onclick="applyPreset('infra')">🏗️ Infra</span>
                <span class="chip" onclick="applyPreset('deployment')">🪖 Deployment</span>
                <span class="chip" onclick="applyPreset('all')">📊 All Data</span>
              </div>
            </div>
          </div>
          <div id="rawSection" style="display:none;margin-top:8px">
            <label>Raw Elasticsearch Query (JSON)</label>
            <textarea name="raw_query" id="rawQuery" rows="6" style="width:100%;background:#1c1f2e;border:1px solid #2a2d3e;color:#4ade80;padding:10px;border-radius:8px;font-family:monospace;font-size:12px;resize:vertical;outline:none" placeholder='{"query":{"match_all":{}}}'></textarea>
          </div>
          <div class="row" style="margin-top:10px">
            <div><label>Date From</label><input type="date" name="date_from"></div>
            <div><label>Date To</label><input type="date" name="date_to"></div>
          </div>
          <div class="row">
            <div><label>Session ID</label><input type="text" name="session_id" value="chat-''' + now + '''"></div>
            <div><label>Max Turns</label><input type="number" name="max_turns" value="10" min="1" max="50"></div>
          </div>
          <button class="btn" type="submit">🚀 Load Data & Start Chat</button>
        </form>
      </div>
    </div>
    <script>
    function toggleMode(){
      var m=document.getElementById('mode').value;
      document.getElementById('catSection').style.display=m==='category'?'':'none';
      document.getElementById('rawSection').style.display=m==='raw_query'?'':'none';
    }
    function setCat(c){document.getElementById('cat').value=c;}
    function applyPreset(type){
      document.getElementById('mode').value='raw_query';
      toggleMode();
      var q={
        infra: ''' + preset_infra + ''',
        deployment: ''' + preset_deployment + ''',
        all: ''' + preset_all + ''',
      };
      document.getElementById('rawQuery').value=q[type]||q.all;
    }
    </script>'''
    return render(content)

@app.post("/fetch")
def fetch_data():
    sid = request.form.get("session_id", "").strip()
    mode = request.form.get("mode", "category")
    category = request.form.get("category")
    model = request.form.get("model")
    date_from = request.form.get("date_from") or None
    date_to = request.form.get("date_to") or None
    max_turns = int(request.form.get("max_turns", 10))
    raw_query_str = request.form.get("raw_query", "").strip()
    if not sid:
        return render("", notice="Session ID is required", notice_type="err")
    try:
        eng = get_session(sid, max_turns=max_turns, model=model)
        if mode == "raw_query" and raw_query_str:
            try:
                raw_query = json.loads(raw_query_str)
            except json.JSONDecodeError as je:
                return render("", notice=f"Invalid JSON in raw query: {je}", notice_type="err")
            result = eng.fetch_data(FetchRequest(mode="raw_query", raw_query=raw_query,
                                  date_from=date_from, date_to=date_to))
        else:
            result = eng.fetch_data(FetchRequest(mode="category", category=category,
                                  date_from=date_from, date_to=date_to))
        return redirect(url_for("chat", session_id=sid))
    except Exception as e:
        return render("", notice=f"Error: {e}", notice_type="err")

@app.get("/chat")
def chat():
    sid = request.args.get("session_id", "")
    eng = _sessions.get(sid)
    if not eng:
        return redirect(url_for("setup"))
    history_html = ""
    if eng.session._history:
        for h in eng.session._history:
            q = h['question'].replace('<','&lt;').replace('>','&gt;')
            a = h['answer'][:500].replace('<','&lt;').replace('>','&gt;')
            history_html += f'<div class="msg u"><div class="av">👤</div><div class="bubble">{q}</div></div>'
            history_html += f'<div class="msg b"><div class="av">🤖</div><div class="bubble">{a}</div></div>'
    info = f'{len(eng.store.documents)} docs · {eng.model} · {eng.session.turns_used}/{eng.session.max_turns} turns'
    content = '''
    <div class="chat-wrap">
      <div style="font-size:11px;color:#5a5e78;padding:4px 0">''' + info + '''</div>
      <div class="chat" id="chat">''' + history_html + '''</div>
      <div class="input-row">
        <textarea id="q" placeholder="Ask a question..." rows="1" onkeydown="if(event.key==='Enter'&&!event.shiftKey){event.preventDefault();ask()}"></textarea>
        <button class="send" onclick="ask()">➤</button>
      </div>
    </div>
    <script>
    async function ask(){
      const q=document.getElementById('q').value.trim();
      if(!q)return;
      document.getElementById('q').value='';
      const c=document.getElementById('chat');
      c.innerHTML+='<div class="msg u"><div class="av">👤</div><div class="bubble">'+q.replace(/</g,'&lt;')+'</div></div>';
      c.innerHTML+='<div class="msg b" id="typing"><div class="av">🤖</div><div class="bubble">●●●</div></div>';
      c.scrollTop=c.scrollHeight;
      try{
        const r=await fetch('/api/session/ask?session_id=''' + sid + '''',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({question:q})});
        const d=await r.json();
        document.getElementById('typing').remove();
        const nl=String.fromCharCode(10);
        const a=(d.answer||'No answer').replace(/</g,'&lt;').replace(new RegExp(nl,'g'),'<br>');
        c.innerHTML+='<div class="msg b"><div class="av">🤖</div><div class="bubble">'+a+'</div><div class="src">📄 '+d.sources_used+' sources</div></div>';
      }catch(e){
        document.getElementById('typing').remove();
        c.innerHTML+='<div class="msg b"><div class="av">🤖</div><div class="bubble" style="color:#f87171">Error: '+e.message+'</div></div>';
      }
      c.scrollTop=c.scrollHeight;
    }
    </script>'''
    return render(content)

# ── Docs redirect ─────────────────────────────────────────────────

@app.get("/docs")
def docs_redirect():
    """Redirect to Swagger UI."""
    return redirect("/apidocs/")

# ── API helpers ───────────────────────────────────────────────────

def _json_body():
    """Safely parse JSON body. Returns dict or (error_response, status_code)."""
    try:
        b = request.get_json(force=True)
        if b is None:
            return (jsonify({"error": "Request body must be valid JSON"}), 400)
        return b
    except Exception:
        return (jsonify({"error": "Request body must be valid JSON"}), 400)

# ── API ───────────────────────────────────────────────────────────

@app.get("/api/health")
def api_health():
    """
    Health check
    ---
    tags:
      - System
    responses:
      200:
        description: Service status
        content:
          application/json:
            schema:
              type: object
              properties:
                status:
                  type: string
                  example: ok
                es_cluster:
                  type: string
                  example: fatboydev
                es_version:
                  type: string
                  example: 8.19.14
                llm_model:
                  type: string
                  example: llama3.2:1b
    """
    try:
        info = es_client.info()
        return jsonify({"status":"ok","es_cluster":info.get("cluster_name"),"es_version":info.get("version",{}).get("number"),"llm_model":LLM_CONFIG.model})
    except Exception as e:
        return jsonify({"status":f"degraded:{e}","llm_model":LLM_CONFIG.model})

@app.get("/api/models")
def api_models():
    """
    List available Ollama models
    ---
    tags:
      - System
    responses:
      200:
        description: List of models available in Ollama
        content:
          application/json:
            schema:
              type: object
              properties:
                models:
                  type: array
                  items:
                    type: object
                    properties:
                      name:
                        type: string
                        example: llama3.2:1b
                      size_gb:
                        type: number
                        example: 1.3
                default:
                  type: string
                  example: llama3.2:1b
    """
    return jsonify({"models":get_models(),"default":LLM_CONFIG.model})

@app.get("/api/categories")
def api_categories():
    """
    List available data categories
    ---
    tags:
      - System
    responses:
      200:
        description: List of category names for data fetching
        content:
          application/json:
            schema:
              type: object
              properties:
                categories:
                  type: array
                  items:
                    type: string
    """
    return jsonify({"categories":CATEGORY_LIST})

@app.post("/api/session/create")
def api_create():
    """
    Create a new chat session
    ---
    tags:
      - Session
    requestBody:
      required: true
      content:
        application/json:
          schema:
            type: object
            required:
              - session_id
            properties:
              session_id:
                type: string
                example: my-session-001
              llm_model:
                type: string
                example: llama3.2:1b
              llm_timeout:
                type: integer
                example: 120
              max_turns:
                type: integer
                example: 10
    responses:
      200:
        description: Session created
        content:
          application/json:
            schema:
              type: object
              properties:
                session_id:
                  type: string
                created_at:
                  type: string
                  format: date-time
      400:
        description: session_id is required
      409:
        description: Session already exists
    """
    b = _json_body()
    if isinstance(b, tuple):
        return b
    sid = b.get("session_id")
    if not sid: return jsonify({"error":"session_id required"}),400
    if sid in _sessions: return jsonify({"error":"exists"}),409
    get_session(sid, max_turns=b.get("max_turns",10), model=b.get("llm_model"))
    return jsonify({"session_id":sid,"created_at":datetime.now().isoformat()})

@app.post("/api/session/fetch")
def api_fetch():
    """
    Fetch data from Elasticsearch into a session
    ---
    tags:
      - Session
    parameters:
      - in: query
        name: session_id
        required: true
        schema:
          type: string
    requestBody:
      required: true
      content:
        application/json:
          schema:
            type: object
            properties:
              mode:
                type: string
                enum: [category, raw_query]
                example: category
              category:
                type: string
                example: Infra Development
              raw_query:
                type: object
                description: Raw ES query JSON (used when mode=raw_query)
              date_from:
                type: string
                example: "2024-01-01"
              date_to:
                type: string
                example: "2024-12-31"
    responses:
      200:
        description: Data fetched successfully
        content:
          application/json:
            schema:
              type: object
              properties:
                total_hits:
                  type: integer
                  example: 1500
                documents_stored:
                  type: integer
                  example: 500
                warnings:
                  type: array
                  items:
                    type: string
      404:
        description: Session not found
      500:
        description: Fetch error
    """
    sid = request.args.get("session_id")
    eng = _sessions.get(sid)
    if not eng: return jsonify({"error":"not found"}),404
    b = _json_body()
    if isinstance(b, tuple):
        return b
    try:
        result = eng.fetch_data(FetchRequest(mode=b.get("mode","category"),category=b.get("category"),
                              raw_query=b.get("raw_query"),date_from=b.get("date_from"),date_to=b.get("date_to")))
        return jsonify({"total_hits":result.total_hits,"documents_stored":len(eng.store.documents),"warnings":result.warnings})
    except Exception as e:
        return jsonify({"error":str(e)}),500

@app.post("/api/session/ask")
def api_ask():
    """
    Ask a question within a session
    ---
    tags:
      - Session
    parameters:
      - in: query
        name: session_id
        required: true
        schema:
          type: string
    requestBody:
      required: true
      content:
        application/json:
          schema:
            type: object
            required:
              - question
            properties:
              question:
                type: string
                example: What deployments happened in January?
              debug:
                type: boolean
                example: false
              mediate:
                type: boolean
                example: true
    responses:
      200:
        description: Answer from the RAG pipeline
        content:
          application/json:
            schema:
              type: object
              properties:
                answer:
                  type: string
                sources_used:
                  type: integer
                  example: 5
                debug:
                  type: object
      400:
        description: No data loaded in session
      404:
        description: Session not found
      500:
        description: Processing error
    """
    sid = request.args.get("session_id")
    eng = _sessions.get(sid)
    if not eng: return jsonify({"error":"not found"}),404
    if not eng.store.is_loaded: return jsonify({"error":"no data loaded"}),400
    b = _json_body()
    if isinstance(b, tuple):
        return b
    question = b.get("question")
    if not question:
        return jsonify({"error": "question is required"}), 400
    try:
        result = eng.ask(ChatRequest(question=question), debug=b.get("debug",False), mediate=b.get("mediate",True))
        return jsonify({"answer":result.answer,"sources_used":result.sources_used,"debug":result.debug})
    except Exception as e:
        return jsonify({"error":str(e)}),500

@app.get("/api/session/status")
def api_status():
    """
    Get session status
    ---
    tags:
      - Session
    parameters:
      - in: query
        name: session_id
        required: true
        schema:
          type: string
    responses:
      200:
        description: Session status including loaded data and turns
        content:
          application/json:
            schema:
              type: object
              properties:
                session_id:
                  type: string
                is_loaded:
                  type: boolean
                total_hits:
                  type: integer
                documents_stored:
                  type: integer
                turns_used:
                  type: integer
                turns_remaining:
                  type: integer
                history:
                  type: array
      404:
        description: Session not found
    """
    sid = request.args.get("session_id")
    eng = _sessions.get(sid)
    if not eng: return jsonify({"error":"not found"}),404
    return jsonify({"session_id":sid,"is_loaded":eng.store.is_loaded,"total_hits":eng.store.total_hits,
                    "documents_stored":len(eng.store.documents),"turns_used":eng.session.turns_used,
                    "turns_remaining":eng.session.turns_remaining,"history":eng.session._history})

@app.delete("/session")
def api_delete():
    """
    Delete a session
    ---
    tags:
      - Session
    parameters:
      - in: query
        name: session_id
        required: true
        schema:
          type: string
    responses:
      200:
        description: Session deleted
        content:
          application/json:
            schema:
              type: object
              properties:
                status:
                  type: string
                  example: deleted
    """
    sid = request.args.get("session_id")
    if sid in _sessions: del _sessions[sid]
    return jsonify({"status":"deleted"})

@app.post("/session/reset")
def api_reset():
    """
    Reset a session (clear history and data)
    ---
    tags:
      - Session
    parameters:
      - in: query
        name: session_id
        required: true
        schema:
          type: string
    responses:
      200:
        description: Session reset
        content:
          application/json:
            schema:
              type: object
              properties:
                status:
                  type: string
                  example: reset
      404:
        description: Session not found
    """
    sid = request.args.get("session_id")
    eng = _sessions.get(sid)
    if not eng: return jsonify({"error":"not found"}),404
    eng.session.reset(); eng.store.clear()
    return jsonify({"status":"reset"})

@app.post("/api/ask")
def api_one_shot_ask():
    """
    One-shot ask (fetch + ask without a session)
    ---
    tags:
      - One-shot
    description: Fetch data and ask a question in a single call. No session is created.
    requestBody:
      required: true
      content:
        application/json:
          schema:
            type: object
            required:
              - question
            properties:
              question:
                type: string
                example: Summarize the latest deployments
              llm_model:
                type: string
                example: llama3.2:1b
              debug:
                type: boolean
                example: false
              mediate:
                type: boolean
                example: true
              fetch:
                type: object
                properties:
                  mode:
                    type: string
                    enum: [category, raw_query]
                    example: category
                  category:
                    type: string
                    example: Deployment
                  raw_query:
                    type: object
                  date_from:
                    type: string
                    example: "2024-01-01"
                  date_to:
                    type: string
                    example: "2024-12-31"
    responses:
      200:
        description: Answer with sources
        content:
          application/json:
            schema:
              type: object
              properties:
                answer:
                  type: string
                sources_used:
                  type: integer
                total_hits:
                  type: integer
                debug:
                  type: object
      500:
        description: Processing error
    """
    b = _json_body()
    if isinstance(b, tuple):
        return b
    fetch_body = b.get("fetch", {})
    model = b.get("llm_model") or LLM_CONFIG.model
    cfg = LlmConfig(base_url=LLM_CONFIG.base_url, api_key=LLM_CONFIG.api_key,
                    model=model, timeout=LLM_CONFIG.timeout)
    try:
        eng = ChatEngine(es_client, cfg)
        eng.fetch_data(FetchRequest(
            mode=fetch_body.get("mode", "category"),
            category=fetch_body.get("category"),
            raw_query=fetch_body.get("raw_query"),
            date_from=fetch_body.get("date_from"),
            date_to=fetch_body.get("date_to"),
        ))
        question = b.get("question")
        if not question:
            return jsonify({"error": "question is required"}), 400
        result = eng.ask(ChatRequest(question=question),
                         debug=b.get("debug", False), mediate=b.get("mediate", True))
        return jsonify({"answer": result.answer, "sources_used": result.sources_used,
                        "total_hits": eng.store.total_hits, "debug": result.debug})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ── Main ──────────────────────────────────────────────────────────

@app.get("/favicon.ico")
def favicon():
    return "", 204

if __name__ == "__main__":
    print(f"ES Chatbot — http://localhost:{APP_PORT}")
    print(f"  ES: {ES_CONFIG.hosts}  LLM: {LLM_CONFIG.model} @ {LLM_CONFIG.base_url}")
    app.run(host=APP_HOST, port=APP_PORT)
