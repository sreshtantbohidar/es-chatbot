"""Quick test with local Ollama."""
import urllib.request, json, time
from openai import OpenAI

# Test local Ollama directly
print("=== Local Ollama Test ===")
try:
    client = OpenAI(base_url='http://localhost:11434/v1', api_key='ollama', timeout=30)
    t0 = time.time()
    resp = client.chat.completions.create(
        model='llama3.2:1b-instruct-q4_K_M',
        messages=[
            {'role': 'system', 'content': 'You are a helpful assistant. Answer concisely.'},
            {'role': 'user', 'content': 'What is the capital of India? Answer in one sentence.'}
        ],
        max_tokens=100,
    )
    print("  Answer: {} ({:.1f}s)".format(resp.choices[0].message.content.strip(), time.time()-t0))
except Exception as e:
    print("  Error: {}".format(e))

# Test through API
print("\n=== API Test ===")
BASE = 'http://localhost:8000'

def call(m, p, d=None, t=60):
    body = json.dumps(d).encode() if d else None
    req = urllib.request.Request(BASE+p, data=body, headers={'Content-Type':'application/json'}, method=m)
    try:
        return json.loads(urllib.request.urlopen(req, timeout=t).read().decode())
    except Exception as e:
        return {'error': str(e)}

r = call("POST", "/health")
print("  Health: {} | LLM: {}".format(r['status'], r['llm_model']))

r = call("POST", "/session/create", {"session_id": "local-test", "llm_model": "llama3:8b-instruct-q8_0", "llm_timeout": 60, "max_turns": 5})
print("  Session: {}".format(r.get('session_id')))

r = call("POST", "/session/fetch?session_id=local-test", {"mode": "category", "category": "Overall Deployment"})
print("  Fetched: {:,} docs".format(r['total_hits']))

# GK question
print("\n--- GK: What is the capital of India? ---")
t0 = time.time()
r = call("POST", "/session/ask?session_id=local-test", {"question": "What is the capital of India?", "debug": True})
print("  mode={} | {:.1f}s".format(r.get('debug',{}).get('mode','?'), time.time()-t0))
print("  Answer: {}".format(r.get('answer','')[:200]))

# Data question
print("\n--- DATA: How many unique locations? ---")
t0 = time.time()
r = call("POST", "/session/ask?session_id=local-test", {"question": "How many unique locations are mentioned in the data?", "debug": True})
print("  mode={} | {:.1f}s".format(r.get('debug',{}).get('mode','?'), time.time()-t0))
print("  Answer: {}".format(r.get('answer','')[:200]))

# Joke
print("\n--- GK: Tell me a joke ---")
t0 = time.time()
r = call("POST", "/session/ask?session_id=local-test", {"question": "Tell me a joke", "debug": True})
print("  mode={} | {:.1f}s".format(r.get('debug',{}).get('mode','?'), time.time()-t0))
print("  Answer: {}".format(r.get('answer','')[:200]))

call("DELETE", "/session?session_id=local-test")
print("\n✅ Done")
