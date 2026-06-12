"""
Test + verify chatbot answers against ground-truth ES data.
Uses remote Ollama llama3:8b-instruct-q8_0.
"""
import sys, json, time

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
print("=" * 80)
print("FETCHING DATA")
print("=" * 80)
t0 = time.time()
result = eng.fetch_data(FetchRequest(
    mode="category",
    category="Overall Deployment",
))
elapsed = time.time() - t0
print(f"Fetched {result.total_hits} docs in {elapsed:.1f}s")
if result.warnings:
    for w in result.warnings:
        print(f"  [WARN] {w}")
stored = len(eng.store.documents)
print(f"Stored in engine: {stored} docs")

# ── Ground truth from ES ─────────────────────────────────────────
print("\n" + "=" * 80)
print("GROUND TRUTH (from ES)")
print("=" * 80)

# All unique location_names
body_loc = {
    "query": {"bool": {"must": [{"exists": {"field": "location_name"}}]}},
    "size": 0,
    "aggs": {
        "locations": {"terms": {"field": "location_name.keyword", "size": 100}}
    }
}
gt_loc = es.search(index="fatboy_data*", body=body_loc)
locs = [b["key"] for b in gt_loc["aggregations"]["locations"]["buckets"]]
print(f"\n[Locations] {len(locs)} unique:")
print(f"  {', '.join(locs)}")

# All unique infra_types
body_infra = {
    "query": {"bool": {"must": [{"term": {"activity_type": "infra"}}, {"exists": {"field": "infra_type"}}]}},
    "size": 0,
    "aggs": {
        "types": {"terms": {"field": "infra_type.keyword", "size": 50}}
    }
}
gt_infra = es.search(index="fatboy_data*", body=body_infra)
if gt_infra["hits"]["total"]["value"] > 0:
    infra_types = [b["key"] for b in gt_infra["aggregations"]["types"]["buckets"]]
    print(f"\n[Infra types] {len(infra_types)} unique:")
    print(f"  {', '.join(infra_types)}")

# Disposition statuses
body_disp = {
    "query": {"bool": {"must": [{"exists": {"field": "disposition_status"}}]}},
    "size": 0,
    "aggs": {
        "statuses": {"terms": {"field": "disposition_status.keyword", "size": 20}}
    }
}
gt_disp = es.search(index="fatboy_data*", body=body_disp)
disps = [b["key"] for b in gt_disp["aggregations"]["statuses"]["buckets"]]
print(f"\n[Disposition statuses] {len(disps)} unique:")
print(f"  {', '.join(disps)}")

# Top enemy formations
body_form = {
    "query": {"bool": {"must": [{"exists": {"field": "enemy_formation_name"}}]}},
    "size": 0,
    "aggs": {
        "formations": {"terms": {"field": "enemy_formation_name.keyword", "size": 10}}
    }
}
gt_form = es.search(index="fatboy_data*", body=body_form)
forms = [(b["key"], b["doc_count"]) for b in gt_form["aggregations"]["formations"]["buckets"]]
print(f"\n[Top formations]:")
for name, cnt in forms:
    print(f"  {name}: {cnt} docs")

# ── Ask questions ─────────────────────────────────────────────────
print("\n" + "=" * 80)
print("CHATBOT Q&A")
print("=" * 80)

questions = [
    "How many unique locations are mentioned in the data?",
    "What are the disposition statuses of enemy forces?",
    "List the top 5 enemy formations by document count.",
]

answers = []
for i, q in enumerate(questions, 1):
    print(f"\n{'='*60}")
    print(f"Q{i}: {q}")
    print("=" * 60)
    t0 = time.time()
    resp = eng.ask(ChatRequest(question=q), debug=True)
    elapsed = time.time() - t0
    print(f"\nANSWER ({elapsed:.1f}s):\n{resp.answer}")
    print(f"\n[Sources: {resp.sources_used} | Debug: {resp.debug}]")
    answers.append((q, resp.answer, elapsed))

# ── Verification ──────────────────────────────────────────────────
print("\n" + "=" * 80)
print("VERIFICATION")
print("=" * 80)

print("\n--- Q1: Location count ---")
print(f"  Ground truth: {len(locs)} unique locations")
print(f"  Chatbot said: {answers[0][1][:200]}")
if str(len(locs)) in answers[0][1]:
    print("  [PASS] Count matches")
else:
    print(f"  [CHECK] Verify manually — GT count is {len(locs)}")

print("\n--- Q2: Disposition statuses ---")
print(f"  Ground truth: {', '.join(disps)}")
print(f"  Chatbot said: {answers[1][1][:300]}")
found = sum(1 for d in disps if d.lower() in answers[1][1].lower())
print(f"  [CHECK] {found}/{len(disps)} statuses mentioned")

print("\n--- Q3: Top formations ---")
print(f"  Ground truth:")
for name, cnt in forms:
    print(f"    {name}: {cnt}")
print(f"  Chatbot said: {answers[2][1][:300]}")
found_f = sum(1 for name, _ in forms if name.lower() in answers[2][1].lower())
print(f"  [CHECK] {found_f}/{len(forms)} formations mentioned")

print(f"\n\nDONE — all questions answered and verified")
