"""Full test after all fixes."""
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
r = call("POST", "/session/create", {"session_id": "final", "llm_model": "qwen3.5:9b", "llm_timeout": 120, "max_turns": 10})
print(f"Session: {r.get('session_id')} | Model: {r.get('llm_model')}")

# Fetch
r = call("POST", "/session/fetch?session_id=final", {"mode": "category", "category": "Overall Deployment"})
print(f"Fetched: {r['total_hits']:,} docs → {r['documents_stored']:,} unique\n")

all_questions = [
    ("How many unique locations are mentioned in the data?", "DATA"),
    ("What infrastructure types exist in the data?", "DATA"),
    ("List the top 10 locations by document count.", "DATA"),
    ("What is the current time, day, and date?", "GK"),
    ("What is the capital of India?", "GK"),
    ("Tell me a joke", "GK"),
    ("Who are you and what can you do?", "GK"),
    ("How many unique locations are in the data?", "DATA"),
]

for i, (q, qtype) in enumerate(all_questions, 1):
    print(f"{'='*60}")
    print(f"Q{i} [{qtype}]: {q}")
    print('='*60)
    t0 = time.time()
    r = call("POST", "/session/ask?session_id=final", {"question": q, "debug": True})
    elapsed = time.time() - t0
    mode = r.get("debug", {}).get("mode", "?") if r.get("debug") else "?"
    answer = r.get("answer", "")
    if "error" in r:
        print(f"  ❌ ERROR: {r}")
    elif "http_error" in r:
        print(f"  ❌ HTTP {r['http_error']}: {r.get('detail',{}).get('detail','?')}")
    else:
        print(f"  mode={mode} | {elapsed:.1f}s | sources={r.get('sources_used')}")
        for line in answer.split("\n")[:10]:
            print(f"  {line}")
        if answer.count("\n") > 10:
            print(f"  ...")
    print()

# Cleanup
call("DELETE", "/session?session_id=final")
print("✅ All tests complete")
