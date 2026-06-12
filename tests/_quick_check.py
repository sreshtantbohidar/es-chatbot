"""Quick health check."""
import urllib.request, json
try:
    r = json.loads(urllib.request.urlopen('http://localhost:8000/health', timeout=5).read())
    print(f"Server: {r['status']} | LLM: {r['llm_model']}")
except Exception as e:
    print(f"Server error: {e}")

# Quick GK test directly
try:
    data = json.dumps({"session_id": "quick", "llm_model": "qwen3.5:9b", "llm_timeout": 120, "max_turns": 5}).encode()
    req = urllib.request.Request('http://localhost:8000/session/create', data=data, headers={"Content-Type": "application/json"}, method="POST")
    r = json.loads(urllib.request.urlopen(req, timeout=10).read())
    print(f"Session: {r.get('session_id')}")
except Exception as e:
    print(f"Create error: {e}")
