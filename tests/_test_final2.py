"""Quick test of the fixed intent classification + agg scoping."""
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

# Create session
r = call("POST", "/session/create", {"session_id": "final", "llm_model": "phi4-mini-reasoning:3.8b-fp16", "llm_timeout": 180, "max_turns": 10})
print(f"Session: {r.get('session_id')} | Model: {r.get('llm_model')}")

# Fetch
r = call("POST", "/session/fetch?session_id=final", {"mode": "category", "category": "Overall Deployment"})
print(f"Fetched: {r['total_hits']:,} docs → {r['documents_stored']:,} unique")

# Test the key questions
questions = [
    "How many unique locations are mentioned in the data?",
    "What infrastructure types exist in the data?",
    "List the top 10 locations by document count.",
]

for i, q in enumerate(questions, 1):
    print(f"\nQ{i}: {q}")
    t0 = time.time()
    r = call("POST", "/session/ask?session_id=final", {"question": q, "debug": True, "mediate": False})
    elapsed = time.time() - t0
    mode = r.get("debug", {}).get("mode", "?") if r.get("debug") else "?"
    print(f"  mode={mode} | {elapsed:.1f}s")
    for line in r.get("answer", "").split("\n")[:15]:
        print(f"  {line}")

call("DELETE", "/session?session_id=final")
print("\n✅ Done")
