"""Full test: data + GK + out-of-scope with llama3.2, mediator always on."""
import urllib.request, json, time

BASE = "http://localhost:8000"

def call(method, path, data=None, timeout=60):
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

r = call("GET", "/health")
print(f"Health: {r['status']} | LLM: {r['llm_model']}\n")

r = call("POST", "/session/create", {"session_id": "final", "llm_model": "llama3.2:1b-instruct-q4_K_M", "llm_timeout": 60, "max_turns": 10})
print(f"Session: {r.get('session_id')} | Model: {r.get('llm_model')}")

r = call("POST", "/session/fetch?session_id=final", {"mode": "category", "category": "Overall Deployment"})
print(f"Fetched: {r['total_hits']:,} docs → {r['documents_stored']:,} unique\n")

questions = [
    # GK / out-of-scope — should be fast, no DB hit
    ("What is the current time, day, and date?", "GK"),
    ("What is the capital of India?", "GK"),
    ("Tell me a joke", "GK"),
    ("Who are you?", "GK"),
    # Data questions — should use RAG/agg
    ("How many unique locations are mentioned in the data?", "DATA"),
    ("What infrastructure types exist in the data?", "DATA"),
    ("List the top 5 locations by document count.", "DATA"),
]

for i, (q, qtype) in enumerate(questions, 1):
    print(f"Q{i} [{qtype}]: {q}")
    t0 = time.time()
    r = call("POST", "/session/ask?session_id=final", {"question": q, "debug": True})
    elapsed = time.time() - t0
    mode = r.get("debug", {}).get("mode", "?") if r.get("debug") else "?"
    answer = r.get("answer", "")
    if "error" in r or "http_error" in r:
        err = r.get("error") or r.get("detail", {}).get("detail", "?")
        print(f"  ❌ {str(err)[:120]}")
    else:
        print(f"  mode={mode} | {elapsed:.1f}s")
        for line in answer.split("\n")[:6]:
            print(f"  {line}")
    print()

call("DELETE", "/session?session_id=final")
print("✅ Done")
