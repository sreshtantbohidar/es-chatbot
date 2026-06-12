"""
Comprehensive test: RAG answers WITH and WITHOUT mediator.
Shows question, raw answer, refined answer, and verification.
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

# ── Fetch data ───────────────────────────────────────────────────
print("=" * 80)
print("FETCHING DATA")
print("=" * 80)
t0 = time.time()
result = eng.fetch_data(FetchRequest(mode="category", category="Overall Deployment"))
print(f"Fetched {result.total_hits} docs in {time.time()-t0:.1f}s")
if result.warnings:
    for w in result.warnings:
        print(f"  [WARN] {w}")
print(f"Stored: {len(eng.store.documents)} docs (after dedup)\n")

# ── Ground truth from ES ─────────────────────────────────────────
print("=" * 80)
print("GROUND TRUTH (from ES)")
print("=" * 80)

from categories import CATEGORY_QUERIES
cat = CATEGORY_QUERIES["Overall Deployment"]
base = {"query": cat["query"], "size": 0, "track_total_hits": True}

# Formations
r = es.search(index="fatboy_data*", body={**base, "aggs": {"f": {"terms": {"field": "enemy_formation_name.keyword", "size": 5}}}})
gt_forms = [(b["key"], b["doc_count"]) for b in r["aggregations"]["f"]["buckets"]]
print(f"\nTop 5 formations: {gt_forms}")

# Infra types
r = es.search(index="fatboy_data*", body={**base, "aggs": {"i": {"terms": {"field": "infra_type.keyword", "size": 5}}}})
gt_infra = [(b["key"], b["doc_count"]) for b in r["aggregations"]["i"]["buckets"]]
print(f"Top 5 infra types: {gt_infra}")

# Disposition statuses
r = es.search(index="fatboy_data*", body={**base, "aggs": {"d": {"terms": {"field": "disposition_status.keyword", "size": 10}}}})
gt_disp = [(b["key"], b["doc_count"]) for b in r["aggregations"]["d"]["buckets"]]
print(f"All disposition statuses: {gt_disp}")

# Tsona count
r = es.search(index="fatboy_data*", body={"query": {"bool": {"must": [{"match": {"location_name": "tsona"}}]}}, "size": 0, "track_total_hits": True})
print(f"Tsona doc count: {r['hits']['total']['value']}")

print()

# ── Questions to test ────────────────────────────────────────────
questions = [
    "What are the top 5 enemy formations by document count?",
    "What infrastructure types are mentioned in the data?",
    "What are the disposition statuses of forces in the data?",
    "How many unique locations are in the data?",
    "What infrastructure development is described at Tsona?",
    "Describe any new construction activity near Tsona.",
]

print("=" * 80)
print("TESTING: raw answer vs mediator-refined answer")
print("=" * 80)

for i, q in enumerate(questions, 1):
    print(f"\n{'='*70}")
    print(f"Q{i}: {q}")
    print("="*70)

    # Without mediator
    t0 = time.time()
    resp_raw = eng.ask(ChatRequest(question=q), debug=True, mediate=False)
    t_raw = time.time() - t0
    raw_answer = resp_raw.answer
    print(f"\n[RAW ANSWER] ({t_raw:.1f}s, {len(raw_answer)} chars, mode={resp_raw.debug.get('mode','?') if resp_raw.debug else '?'}):")
    print(raw_answer[:600])
    if len(raw_answer) > 600:
        print(f"  ... [{len(raw_answer)-600} more chars]")

    # With mediator
    t0 = time.time()
    resp_med = eng.ask(ChatRequest(question=q), debug=True, mediate=True)
    t_med = time.time() - t0
    med_answer = resp_med.answer
    med_meta = (resp_med.debug or {}).get("mediator", {})
    print(f"\n[MEDIATOR ANSWER] ({t_med:.1f}s, {len(med_answer)} chars, mediator={med_meta.get('mediator','?')}):")
    print(med_answer[:600])
    if len(med_answer) > 600:
        print(f"  ... [{len(med_answer)-600} more chars]")

    # Quick verification hints
    print(f"\n--- Verification hints ---")
    if "formation" in q.lower():
        found = sum(1 for name, _ in gt_forms if name.lower() in med_answer.lower())
        print(f"  Formations mentioned: {found}/{len(gt_forms)}")
    if "infra" in q.lower():
        found = sum(1 for name, _ in gt_infra if name.lower() in med_answer.lower())
        print(f"  Infra types mentioned: {found}/{len(gt_infra)}")
    if "disposition" in q.lower():
        found = sum(1 for name, _ in gt_disp if name.lower() in med_answer.lower())
        print(f"  Disposition statuses mentioned: {found}/{len(gt_disp)}")
    if "tsona" in q.lower():
        has_coords = "27.44" in med_answer or "27.40" in med_answer
        print(f"  Tsona coordinates present: {has_coords}")

print(f"\n\n{'='*80}")
print("DONE — all questions tested")
print("="*80)
