"""Debug: compare old vs new query results."""
from elasticsearch import Elasticsearch
import json, time

es = Elasticsearch(['http://192.168.1.16:9200'], basic_auth=('elastic','uHMkl_b8DuAskF2E1h5x'), verify_certs=False, request_timeout=30)
INDEX = 'fatboy_data*'

# Original Overall Deployment query (from categories.py)
old_query = {
    "query": {
        "bool": {
            "must": [],
            "should": [
                {"bool": {"must": [
                    {"term": {"activity_type": "infra"}},
                    {"exists": {"field": "infra_type"}},
                    {"exists": {"field": "location_name"}}
                ]}},
                {"bool": {"must": [
                    {"exists": {"field": "enemy_formation_name"}},
                    {"exists": {"field": "location_name"}},
                    {"exists": {"field": "disposition_status"}},
                    {"term": {"activity_type": "deployment"}}
                ]}}
            ],
            "minimum_should_match": 1,
            "must_not": [{"term": {"form_status": 5}}]
        }
    },
    "size": 0,
    "track_total_hits": True
}

print("OLD query (should-based):")
t0 = time.time()
r = es.search(index=INDEX, body=old_query)
print(f"  {r['hits']['total']['value']:,} hits in {time.time()-t0:.2f}s")

# The issue: my new filter requires ALL should clauses to match (AND logic)
# But the original uses OR logic (minimum_should_match=1)
# The correct approach: use the should clauses as separate bool/should in filter context

new_query_fixed = {
    "size": 0,
    "track_total_hits": True,
    "query": {
        "bool": {
            "filter": [
                {"bool": {"must_not": [{"term": {"form_status": 5}}]}},
                {"bool": {
                    "should": [
                        {"bool": {"must": [
                            {"term": {"activity_type": "infra"}},
                            {"exists": {"field": "infra_type"}},
                            {"exists": {"field": "location_name"}}
                        ]}},
                        {"bool": {"must": [
                            {"exists": {"field": "enemy_formation_name"}},
                            {"exists": {"field": "location_name"}},
                            {"exists": {"field": "disposition_status"}},
                            {"term": {"activity_type": "deployment"}}
                        ]}}
                    ],
                    "minimum_should_match": 1
                }}
            ]
        }
    },
    "timeout": "10s"
}

print("\nNEW query (should in filter context):")
t0 = time.time()
r = es.search(index=INDEX, body=new_query_fixed)
print(f"  {r['hits']['total']['value']:,} hits in {time.time()-t0:.2f}s")

# Even simpler: just use the original query structure but with timeout
simple_query = {
    "size": 0,
    "track_total_hits": True,
    "query": old_query["query"],
    "timeout": "10s"
}

print("\nSIMPLE (original + timeout):")
t0 = time.time()
r = es.search(index=INDEX, body=simple_query)
print(f"  {r['hits']['total']['value']:,} hits in {time.time()-t0:.2f}s")
