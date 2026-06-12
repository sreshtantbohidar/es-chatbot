"""Verify the fix: agg queries should now use session's base query."""
from elasticsearch import Elasticsearch
from copy import deepcopy

es = Elasticsearch(['http://192.168.1.16:9200'], basic_auth=('elastic','uHMkl_b8DuAskF2E1h5x'), verify_certs=False, request_timeout=15)
INDEX = 'fatboy_data*'

# Build the Overall Deployment query + activity_type agg (what the fixed code does)
cat_q = {
    "bool": {
        "must": [],
        "should": [
            {"bool": {"must": [{"term": {"activity_type": "infra"}}, {"exists": {"field": "infra_type"}}, {"exists": {"field": "location_name"}}]}},
            {"bool": {"must": [{"exists": {"field": "enemy_formation_name"}}, {"exists": {"field": "location_name"}}, {"exists": {"field": "disposition_status"}}, {"term": {"activity_type": "deployment"}}]}}
        ],
        "minimum_should_match": 1,
        "must_not": [{"term": {"form_status": 5}}]
    }
}

r = es.search(index=INDEX, size=0, track_total_hits=True, query=deepcopy(cat_q), aggs={
    "types": {"terms": {"field": "activity_type.keyword", "size": 10, "order": {"_count": "desc"}}}
})
total = r['hits']['total']['value']
top5 = [(b['key'], b['doc_count']) for b in r['aggregations']['types']['buckets'][:5]]
print(f"Overall Deployment scope: {total:,} docs")
print("Top 5 activity types:")
for name, cnt in top5:
    print(f"  • {name}: {cnt:,} docs")

# Now test location filter
r2 = es.search(index=INDEX, size=0, track_total_hits=True, query=deepcopy(cat_q), aggs={
    "locs": {"terms": {"field": "location_name.keyword", "size": 15, "order": {"_count": "desc"}}}
})
top15 = [(b['key'], b['doc_count']) for b in r2['aggregations']['locs']['buckets']]
print(f"\nTop 15 locations (raw):")
for name, cnt in top15:
    print(f"  • {name}: {cnt}")

# Filter nulls
null_vals = {"unknown", "location not known", "n/a", "na", "none", "null", "", "not known", "not available", "tbd", "to be determined"}
filtered = [(n, c) for n, c in top15 if n.strip().lower() not in null_vals and len(n.strip()) >= 2]
print(f"\nTop 10 locations (filtered nulls):")
for name, cnt in filtered[:10]:
    print(f"  • {name}: {cnt}")

# Test infra_type
r3 = es.search(index=INDEX, size=0, track_total_hits=True, query=deepcopy(cat_q), aggs={
    "infra": {"terms": {"field": "infra_type.keyword", "size": 10, "order": {"_count": "desc"}}}
})
infra5 = [(b['key'], b['doc_count']) for b in r3['aggregations']['infra']['buckets'][:5]]
print(f"\nTop 5 infra types:")
for name, cnt in infra5:
    print(f"  • {name}: {cnt}")

# Test cardinality
r4 = es.search(index=INDEX, size=0, track_total_hits=True, query=deepcopy(cat_q), aggs={
    "unique_locs": {"cardinality": {"field": "location_name.keyword", "precision_threshold": 10000}}
})
print(f"\nUnique locations: {r4['aggregations']['unique_locs']['value']:,}")
