"""
Test aggregation intent classification + ES agg answers.
Uses remote Ollama llama3:8b-instruct-q8_0.
"""
import sys, time

import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from engine import ChatEngine, FetchRequest, ChatRequest, EsConfig, LlmConfig, make_es_client

es = make_es_client(EsConfig(
    hosts="http://192.168.1.16:9200",
    username="elastic",
    password="uHMkl_b8DuAskF2E1h5x",
))

eng = ChatEngine(es, LlmConfig(
    base_url="http://192.168.1.125:11434/v1",
    api_key="ollama",
    model="llama3:8b-instruct-q8_0",
    timeout=180,
))

# ── Fetch ─────────────────────────────────────────────────────────
print("=" * 80, flush=True)
print("FETCHING DATA", flush=True)
print("=" * 80, flush=True)
t0 = time.time()
result = eng.fetch_data(FetchRequest(
    mode="category",
    category="Overall Deployment",
))
print(f"Fetched {result.total_hits} docs in {time.time()-t0:.1f}s", flush=True)
if result.warnings:
    for w in result.warnings:
        print(f"  [WARN] {w}", flush=True)
print(f"Stored: {len(eng.store.documents)} docs (after dedup)", flush=True)

# ── Test intent classification ────────────────────────────────────
print("\n" + "=" * 80, flush=True)
print("INTENT CLASSIFICATION TESTS", flush=True)
print("=" * 80, flush=True)

intent_tests = [
    "How many unique locations are mentioned in the data?",
    "What are all the unique locations mentioned?",
    "List all unique disposition statuses.",
    "What are the top 5 enemy formations by document count?",
    "Group the documents by infrastructure type.",
    "How many documents mention Tsona?",
    "What is the total count of documents?",
    "List all infrastructure types mentioned.",
    "What communication infrastructure is described in the data?",
    "Which formation has the most documents?",
]

for q in intent_tests:
    intent_type, field, top_n = eng._classify_intent(q)
    print(f"  [{intent_type:12s}] field={str(field):35s} top_n={top_n}  |  {q[:60]}", flush=True)

# ── Ask aggregation questions ─────────────────────────────────────
print("\n" + "=" * 80, flush=True)
print("AGGREGATION QUESTIONS (ES-powered, no LLM)", flush=True)
print("=" * 80, flush=True)

agg_questions = [
    "How many unique locations are mentioned in the data?",
    "List all unique disposition statuses.",
    "What are the top 5 enemy formations by document count?",
    "Group the documents by infrastructure type.",
    "How many total documents are there?",
    "List all unique locations mentioned.",
]

for i, q in enumerate(agg_questions, 1):
    print(f"\nQ{i}: {q}", flush=True)
    t0 = time.time()
    resp = eng.ask(ChatRequest(question=q), debug=True)
    elapsed = time.time() - t0
    print(f"ANSWER ({elapsed:.1f}s) [mode={resp.debug.get('mode','?') if resp.debug else '?'}]:", flush=True)
    print(resp.answer, flush=True)
    print(f"[Sources: {resp.sources_used}]", flush=True)

# ── Ask detail questions (still use LLM) ─────────────────────────
print("\n" + "=" * 80, flush=True)
print("DETAIL QUESTIONS (LLM-powered)", flush=True)
print("=" * 80, flush=True)

detail_questions = [
    "What infrastructure development is described at Tsona?",
    "Describe any bridge construction mentioned in the data.",
]

for i, q in enumerate(detail_questions, 1):
    print(f"\nDQ{i}: {q}", flush=True)
    t0 = time.time()
    resp = eng.ask(ChatRequest(question=q), debug=True)
    elapsed = time.time() - t0
    print(f"\nANSWER ({elapsed:.1f}s) [mode={resp.debug.get('mode','?') if resp.debug else '?'}]:", flush=True)
    print(resp.answer[:500], flush=True)
    print(f"[Sources: {resp.sources_used}]", flush=True)

print(f"\n\nDONE — all tests complete", flush=True)
