"""Final test: GK + data with llama3.2:1b, mediator always on."""
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
print("Health: {} | LLM: {}\n".format(r['status'], r['llm_model']))

r = call("POST", "/session/create", {"session_id": "final", "llm_model": "llama3:8b-instruct-q8_0", "llm_timeout": 60, "max_turns": 10})
print("Session: {} | Model: {}".format(r.get('session_id'), r.get('llm_model')))

r = call("POST", "/session/fetch?session_id=final", {"mode": "category", "category": "Overall Deployment"})
print("Fetched: {:,} docs → {:,} unique\n".format(r['total_hits'], r['documents_stored']))

questions = [
    ("What is the current time, day, and date?", "GK"),
    ("What is the capital of India?", "GK"),
    ("Tell me a joke", "GK"),
    ("Who are you?", "GK"),
    ("How many unique locations are mentioned in the data?", "DATA"),
    ("What infrastructure types exist in the data?", "DATA"),
    ("List the top 5 locations by document count.", "DATA"),
]

for i, (q, qtype) in enumerate(questions, 1):
    print("Q{} [{}]: {}".format(i, qtype, q))
    t0 = time.time()
    r = call("POST", "/session/ask?session_id=final", {"question": q, "debug": True})
    elapsed = time.time() - t0
    mode = r.get("debug", {}).get("mode", "?") if r.get("debug") else "?"
    answer = r.get("answer", "")
    if "error" in r or "http_error" in r:
        err = r.get("error") or r.get("detail", {}).get("detail", "?")
        print("  ❌ {}".format(str(err)[:120]))
    else:
        print("  mode={} | {:.1f}s".format(mode, elapsed))
        for line in answer.split("\n")[:6]:
            print("  {}".format(line))
    print()

call("DELETE", "/session?session_id=final")
print("✅ Done")
