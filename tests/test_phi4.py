"""
Test + verify chatbot with phi4-mini-reasoning:3.8b-fp16
Remote Ollama
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
    model="phi4-mini-reasoning:3.8b-fp16",
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
elapsed = time.time() - t0
print(f"Fetched {result.total_hits} docs in {elapsed:.1f}s", flush=True)
if result.warnings:
    for w in result.warnings:
        print(f"  [WARN] {w}", flush=True)
stored = len(eng.store.documents)
print(f"Stored in engine: {stored} docs (after dedup)", flush=True)

# ── Ground truth from ES ─────────────────────────────────────────
print("\n" + "=" * 80, flush=True)
print("GROUND TRUTH (from ES aggregations)", flush=True)
print("=" * 80, flush=True)

# Unique locations
body_loc = {
    "query": {"bool": {"must": [{"exists": {"field": "location_name"}}]}},
    "size": 0,
    "aggs": {"locations": {"terms": {"field": "location_name.keyword", "size": 100}}}
}
gt_loc = es.search(index="fatboy_data*", body=body_loc)
locs = [b["key"] for b in gt_loc["aggregations"]["locations"]["buckets"]]
print(f"\n[Locations] {len(locs)} unique:", flush=True)
print(f"  {', '.join(locs[:20])}...", flush=True)

# Disposition statuses
body_disp = {
    "query": {"bool": {"must": [{"exists": {"field": "disposition_status"}}]}},
    "size": 0,
    "aggs": {"statuses": {"terms": {"field": "disposition_status.keyword", "size": 20}}}
}
gt_disp = es.search(index="fatboy_data*", body=body_disp)
disps = [b["key"] for b in gt_disp["aggregations"]["statuses"]["buckets"]]
print(f"\n[Disposition statuses] {len(disps)}: {', '.join(disps)}", flush=True)

# Top formations
body_form = {
    "query": {"bool": {"must": [{"exists": {"field": "enemy_formation_name"}}]}},
    "size": 0,
    "aggs": {"formations": {"terms": {"field": "enemy_formation_name.keyword", "size": 10}}}
}
gt_form = es.search(index="fatboy_data*", body=body_form)
forms = [(b["key"], b["doc_count"]) for b in gt_form["aggregations"]["formations"]["buckets"]]
print(f"\n[Top formations]:", flush=True)
for name, cnt in forms:
    print(f"  {name}: {cnt}", flush=True)

# Infrastructure types
body_infra = {
    "query": {"bool": {"must": [{"exists": {"field": "infra_type"}}]}},
    "size": 0,
    "aggs": {"types": {"terms": {"field": "infra_type.keyword", "size": 30}}}
}
gt_infra = es.search(index="fatboy_data*", body=body_infra)
infra_types = [b["key"] for b in gt_infra["aggregations"]["types"]["buckets"]]
print(f"\n[Infrastructure types] {len(infra_types)}: {', '.join(infra_types[:15])}...", flush=True)

# ── Ask questions ─────────────────────────────────────────────────
print("\n" + "=" * 80, flush=True)
print("CHATBOT Q&A — phi4-mini-reasoning:3.8b-fp16", flush=True)
print("=" * 80, flush=True)

questions = [
    ("How many unique locations are mentioned? List all of them.", len(locs), locs),
    ("What are the disposition statuses of enemy forces?", len(disps), disps),
    ("List the top 5 enemy formations by number of documents.", len(forms), [f[0] for f in forms]),
    ("What infrastructure types are mentioned? Group them.", len(infra_types), infra_types),
]

all_results = []
for i, (q, gt_count, gt_items) in enumerate(questions, 1):
    print(f"\n{'='*60}", flush=True)
    print(f"Q{i}: {q}", flush=True)
    print("=" * 60, flush=True)
    t0 = time.time()
    resp = eng.ask(ChatRequest(question=q), debug=True)
    elapsed = time.time() - t0
    answer = resp.answer
    print(f"\nANSWER ({elapsed:.1f}s):\n{answer}", flush=True)
    print(f"\n[Sources: {resp.sources_used} | Mode: {resp.debug.get('mode','?') if resp.debug else '?'}]", flush=True)
    all_results.append((i, q, answer, elapsed, gt_count, gt_items))

# ── Verification ──────────────────────────────────────────────────
print("\n" + "=" * 80, flush=True)
print("VERIFICATION REPORT", flush=True)
print("=" * 80, flush=True)

for i, q, answer, elapsed, gt_count, gt_items in all_results:
    print(f"\n--- Q{i}: {q[:60]}... ---", flush=True)
    print(f"  Ground truth: {gt_count} items", flush=True)
    if isinstance(gt_items, list) and len(gt_items) <= 10:
        print(f"  GT items: {', '.join(str(x) for x in gt_items)}", flush=True)
    elif isinstance(gt_items, list):
        print(f"  GT items (first 10): {', '.join(str(x) for x in gt_items[:10])}", flush=True)

    items_found = sum(1 for item in gt_items if str(item).lower() in answer.lower())
    pct = (items_found / gt_count * 100) if gt_count > 0 else 0
    status = "PASS" if pct >= 70 else ("PARTIAL" if pct >= 40 else "FAIL")
    print(f"  Found: {items_found}/{gt_count} ({pct:.0f}%)  [{status}]", flush=True)
    print(f"  Time: {elapsed:.1f}s", flush=True)

print(f"\n\nDONE — phi4-mini-reasoning:3.8b-fp16 test complete", flush=True)
