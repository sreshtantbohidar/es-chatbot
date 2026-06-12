"""Full e2e test after all fixes."""
import urllib.request, json, time

BASE = "http://localhost:8000"

def call(method, path, data=None, timeout=300):
    url = BASE + path
    body = json.dumps(data).encode() if data else None
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"}, method=method)
    try:
        resp = urllib.request.urlopen(req, timeout=timeout)
        return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        return {"http_error": e.code, "detail": json.loads(e.read().decode())}

print("=" * 60)
print("POST-FIX END-TO-END TEST")
print("=" * 60)

# Health
r = call("GET", "/health")
print(f"\nHealth: {r['status']} | ES: {r.get('es_cluster')} | LLM: {r['llm_model']}")

# Create session
print("\n1. Creating session (phi4-mini)...")
r = call("POST", "/session/create", {"session_id": "fix-test", "llm_model": "phi4-mini-reasoning:3.8b-fp16", "llm_timeout": 180, "max_turns": 10})
print(f"   Session: {r.get('session_id')} | Model: {r.get('llm_model')}")

# Fetch
print("\n2. Fetching Overall Deployment...")
t0 = time.time()
r = call("POST", "/session/fetch?session_id=fix-test", {"mode": "category", "category": "Overall Deployment"})
if "error" in r:
    print(f"   ❌ {r}")
else:
    print(f"   ✅ {r['total_hits']:,} docs → {r['documents_stored']:,} unique ({time.time()-t0:.1f}s)")

# Questions
questions = [
    ("How many unique locations are mentioned in the data?", "agg-COUNT"),
    ("What are the top 5 activity types by document count?", "agg-TOP_N"),
    ("What infrastructure types exist in the data?", "agg-LIST_UNIQUE"),
    ("List the top 10 locations by document count.", "agg-TOP_N"),
]

for i, (q, expected_mode) in enumerate(questions, 1):
    print(f"\n3.{i} {q}")
    t0 = time.time()
    r = call("POST", "/session/ask?session_id=fix-test", {"question": q, "debug": True, "mediate": False})
    elapsed = time.time() - t0
    mode = r.get("debug", {}).get("mode", "?") if r.get("debug") else "?"
    sources = r.get("sources_used", 0)
    answer = r.get("answer", "")[:500]
    match = "✅" if mode == expected_mode or expected_mode in mode else f"⚠ (expected {expected_mode})"
    print(f"   {match} mode={mode} | sources={sources} | {elapsed:.1f}s")
    for line in answer.split("\n")[:12]:
        print(f"   {line}")
    if answer.count("\n") > 12:
        print(f"   ...")

# Session status
r = call("GET", "/session/status?session_id=fix-test")
print(f"\n4. Session: {r['turns_used']}/{r['max_turns']} turns | {r['history']} entries")

# Cleanup
call("DELETE", "/session?session_id=fix-test")
print("\n✅ Done")
