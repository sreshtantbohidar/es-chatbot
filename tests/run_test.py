import sys, json, time
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from engine import ChatEngine, FetchRequest, ChatRequest, EsConfig, LlmConfig, make_es_client

es = make_es_client(EsConfig(hosts="http://192.168.1.16:9200", username="elastic", password="uHMkl_b8DuAskF2E1h5x"))
eng = ChatEngine(es, LlmConfig(base_url="http://192.168.1.125:11434/v1", api_key="ollama", model="qwen2.5:14b", timeout=120))

print("Fetching...", flush=True)
t0 = time.time()
result = eng.fetch_data(FetchRequest(mode="category", category="Overall Deployment", date_from="2025-05-01", date_to="2025-05-07"))
print(f"Fetched {result.total_hits} docs in {time.time()-t0:.1f}s", flush=True)

questions = [
    "What are all the unique locations mentioned in the data?",
    "What infrastructure types are listed? Group them by type.",
    "Which documents mention Tsona? What activities are described there?",
    "What communication and surveillance infrastructure is mentioned?",
    "List all documents related to dugouts and trenches. Where are they located?",
]

for i, q in enumerate(questions, 1):
    print(f"\n{'='*80}", flush=True)
    print(f"Q{i}: {q}", flush=True)
    print("="*80, flush=True)
    t0 = time.time()
    resp = eng.ask(ChatRequest(question=q), debug=True)
    elapsed = time.time() - t0
    print(f"\nANSWER ({elapsed:.1f}s):\n{resp.answer}", flush=True)
    print(f"\n[Sources: {resp.sources_used} | Debug: {resp.debug}]", flush=True)

print(f"\n\nDONE — all 5 questions answered", flush=True)
