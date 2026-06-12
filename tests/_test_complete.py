"""Full test: data questions + general knowledge + out-of-scope."""
import urllib.request, json, time

BASE = "http://localhost:8000"

def call(method, path, data=None, timeout=120):
    url = BASE + path
    body = json.dumps(data).encode() if data else None
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"}, method=method)
    try:
        resp = urllib.request.urlopen(req, timeout=timeout)
        return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        return {"http_error": e.code, "detail": json.loads(e.read().decode())}
    except Exception as e:
        return {"error": str(e)}

# Health
r = call("GET", "/health")
print(f"Health: {r['status']} | ES: {r.get('es_cluster')} | LLM: {r['llm_model']}\n")

# Create session
r = call("POST", "/session/create", {"session_id": "full-test", "llm_model": "qwen3.5:9b", "llm_timeout": 120, "max_turns": 10})
print(f"Session: {r.get('session_id')} | Model: {r.get('llm_model')}")

# Fetch
r = call("POST", "/session/fetch?session_id=full-test", {"mode": "category", "category": "Overall Deployment"})
print(f"Fetched: {r['total_hits']:,} docs → {r['documents_stored']:,} unique\n")

# ── Data Questions ──
print("=" * 60)
print("DATA QUESTIONS")
print("=" * 60)

data_questions = [
    "How many unique locations are mentioned in the data?",
    "What infrastructure types exist in the data?",
    "List the top 10 locations by document count.",
]

for i, q in enumerate(data_questions, 1):
    print(f"\nQ{i}: {q}")
    t0 = time.time()
    r = call("POST", "/session/ask?session_id=full-test", {"question": q, "debug": True})
    elapsed = time.time() - t0
    mode = r.get("debug", {}).get("mode", "?") if r.get("debug") else "?"
    answer = r.get("answer", "")
    print(f"  mode={mode} | {elapsed:.1f}s | sources={r.get('sources_used')}")
    for line in answer.split("\n")[:12]:
        print(f"  {line}")
    if answer.count("\n") > 12:
        print(f"  ...")

# ── General Knowledge Questions ──
print(f"\n{'='*60}")
print("GENERAL KNOWLEDGE QUESTIONS")
print("=" * 60)

gk_questions = [
    "What is the current time, day, and date?",
    "What is the capital of India?",
    "Tell me a joke",
    "Who are you and what can you do?",
]

for i, q in enumerate(gk_questions, 1):
    print(f"\nGQ{i}: {q}")
    t0 = time.time()
    r = call("POST", "/session/ask?session_id=full-test", {"question": q, "debug": True})
    elapsed = time.time() - t0
    mode = r.get("debug", {}).get("mode", "?") if r.get("debug") else "?"
    answer = r.get("answer", "")
    print(f"  mode={mode} | {elapsed:.1f}s")
    for line in answer.split("\n")[:8]:
        print(f"  {line}")

# ── Mixed: data question after GK ──
print(f"\n{'='*60}")
print("MIXED: Data question after GK")
print("=" * 60)

q = "How many unique locations are in the data?"
print(f"\nQ: {q}")
r = call("POST", "/session/ask?session_id=full-test", {"question": q, "debug": True})
mode = r.get("debug", {}).get("mode", "?") if r.get("debug") else "?"
print(f"  mode={mode} | sources={r.get('sources_used')}")
for line in r.get("answer","").split("\n")[:5]:
    print(f"  {line}")

# Cleanup
call("DELETE", "/session?session_id=full-test")
print(f"\n✅ All tests complete")
