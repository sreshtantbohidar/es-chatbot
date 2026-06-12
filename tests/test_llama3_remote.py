"""
Test the ES chatbot with remote Ollama llama3:8b-instruct-q8_0
"""
import sys, json, time

import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from engine import ChatEngine, FetchRequest, ChatRequest, EsConfig, LlmConfig, make_es_client

# ES config
es = make_es_client(EsConfig(
    hosts="http://192.168.1.16:9200",
    username="elastic",
    password="uHMkl_b8DuAskF2E1h5x",
))

# Remote Ollama with llama3:8b-instruct-q8_0
eng = ChatEngine(es, LlmConfig(
    base_url="http://192.168.1.125:11434/v1",
    api_key="ollama",
    model="llama3:8b-instruct-q8_0",
    timeout=180,
))

print("=" * 80)
print("ES Chatbot Test — Remote Ollama llama3:8b-instruct-q8_0")
print("=" * 80)

# ── Step 1: Fetch data ──────────────────────────────────────────────
print("\n[1/2] Fetching data from ES (Overall Deployment, 2025-05-01 to 2025-05-07)...")
t0 = time.time()
result = eng.fetch_data(FetchRequest(
    mode="category",
    category="Overall Deployment",
    date_from="2025-05-01",
    date_to="2025-05-07",
))
print(f"  => Fetched {result.total_hits} docs in {time.time()-t0:.1f}s")

if result.warnings:
    for w in result.warnings:
        print(f"  [WARN] {w}")

if result.total_hits == 0:
    print("\nNo data found. Trying without date filter...")
    t0 = time.time()
    result = eng.fetch_data(FetchRequest(
        mode="category",
        category="Overall Deployment",
    ))
    print(f"  => Fetched {result.total_hits} docs in {time.time()-t0:.1f}s")

# ── Step 2: Ask questions ──────────────────────────────────────────
questions = [
    "What are all the unique locations mentioned in the data?",
    "What infrastructure types are listed? Group them by type.",
    "Which documents mention Tsona? What activities are described there?",
    "What communication and surveillance infrastructure is mentioned?",
    "List all documents related to dugouts and trenches. Where are they located?",
]

for i, q in enumerate(questions, 1):
    print(f"\n{'='*80}")
    print(f"Q{i}: {q}")
    print("=" * 80)
    t0 = time.time()
    resp = eng.ask(ChatRequest(question=q), debug=True)
    elapsed = time.time() - t0
    print(f"\nANSWER ({elapsed:.1f}s):\n{resp.answer}")
    print(f"\n[Sources: {resp.sources_used} | Debug: {resp.debug}]")

print(f"\n\nDONE — all {len(questions)} questions answered with llama3:8b-instruct-q8_0")
