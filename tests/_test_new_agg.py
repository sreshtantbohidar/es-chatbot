"""Test the new agg query performance and accuracy."""
from elasticsearch import Elasticsearch
import json, time

es = Elasticsearch(['http://192.168.1.16:9200'], basic_auth=('elastic','uHMkl_b8DuAskF2E1h5x'), verify_certs=False, request_timeout=30)
INDEX = 'fatboy_data*'

# Build the new-style agg query for Overall Deployment + infra_type
query = {
    "size": 0,
    "track_total_hits": True,
    "query": {
        "bool": {
            "filter": [
                {"term": {"form_status": 5}},  # must_not becomes filter
                {"terms": {"activity_type.keyword": ["deployment", "infra"]}},
                {"exists": {"field": "infra_type"}},
                {"exists": {"field": "location_name"}},
                {"exists": {"field": "enemy_formation_name"}},
                {"exists": {"field": "disposition_status"}},
            ]
        }
    },
    "timeout": "10s",
    "aggs": {
        "unique_values": {
            "terms": {"field": "infra_type.keyword", "size": 10, "order": {"_count": "desc"}}
        }
    }
}

print("Testing new agg query...")
t0 = time.time()
r = es.search(index=INDEX, body=query)
elapsed = time.time() - t0
print(f"  Time: {elapsed:.2f}s")
print(f"  Total hits: {r['hits']['total']['value']:,}")
print(f"  Top infra types:")
for b in r['aggregations']['unique_values']['buckets'][:5]:
    print(f"    • {b['key']}: {b['doc_count']:,}")

# Test location query with null filter
query2 = {
    "size": 0, "track_total_hits": True,
    "query": {"bool": {"filter": [
        {"term": {"form_status": 5}},
        {"terms": {"activity_type.keyword": ["deployment", "infra"]}},
        {"exists": {"field": "infra_type"}},
        {"exists": {"field": "location_name"}},
        {"exists": {"field": "enemy_formation_name"}},
        {"exists": {"field": "disposition_status"}},
    ]}},
    "timeout": "10s",
    "aggs": {
        "unique_values": {
            "terms": {"field": "location_name.keyword", "size": 15, "order": {"_count": "desc"}}
        }
    }
}

print(f"\nTop locations (new query):")
t0 = time.time()
r2 = es.search(index=INDEX, body=query2)
elapsed = time.time() - t0
print(f"  Time: {elapsed:.2f}s")
for b in r2['aggregations']['unique_values']['buckets'][:10]:
    print(f"    • {b['key']}: {b['doc_count']}")
