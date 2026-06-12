"""Test general knowledge, meta, and out-of-scope questions."""
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
r = call("POST", "/session/create", {"session_id": "gk-test", "llm_model": "phi4-mini-reasoning:3.8b-fp16", "llm_timeout": 180, "max_turns": 10})
print(f"Session: {r.get('session_id')}")

# Fetch data so session is loaded
r = call("POST", "/session/fetch?session_id=gk-test", {"mode": "category", "category": "Overall Deployment"})
print(f"Fetched: {r['total_hits']:,} docs\n")

# Test questions
questions = [
    "What is the current time, day, and date?",
    "What is the capital of India?",
    "Tell me a joke",
    "Who are you?",
    "What is 2 + 2?",
    "What is the meaning of life?",
    "How many unique locations are in the data?",
]

for i, q in enumerate(questions, 1):
    print(f"{'='*60}")
    print(f"Q{i}: {q}")
    print('='*60)
    t0 = time.time()
    r = call("POST", "/session/ask?session_id=gk-test", {"question": q, "debug": True, "mediate": True})
    elapsed = time.time() - t0
    mode = r.get("debug", {}).get("mode", "?") if r.get("debug") else "?"
    answer = r.get("answer", "")
    print(f"  mode={mode} | {elapsed:.1f}s | {len(answer)} chars")
    print(f"  Answer: {answer[:500]}")
    print()

call("DELETE", "/session?session_id=gk-test")
print("✅ Done")
