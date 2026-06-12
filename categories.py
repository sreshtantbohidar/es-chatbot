"""
Elasticsearch Chatbot - Index Registry & Category Query Templates
"""
from dataclasses import dataclass, field

INDEX_PATTERN = "fatboy_data*"

# ── Category Query Templates ──────────────────────────────────────
# Each category maps to a base ES query. The chatbot uses these as
# starting points, then applies additional user filters on top.

CATEGORY_QUERIES: dict[str, dict] = {
    "Force Disposition": {
        "description": "Enemy force deployment, disposition, and formation data with location info",
        "query": {
            "bool": {
                "must": [
                    {"exists": {"field": "enemy_formation_name"}},
                    {"exists": {"field": "location_name"}},
                    {"terms": {"activity_type.keyword": ["deployment", "disposition", "movement"]}}
                ],
                "must_not": [{"term": {"form_status": 5}}],
                "filter": []
            }
        },
        "sort": [{"@timestamp": {"order": "desc"}}],
        "size": 10000,
    },
    "Training Areas": {
        "description": "Military training locations, types, and exercise data",
        "query": {
            "bool": {
                "must": [
                    {"exists": {"field": "training_type"}},
                    {"term": {"form_type.keyword": "training"}},
                    {"exists": {"field": "location_name"}}
                ],
                "must_not": [{"term": {"form_status": 5}}],
                "filter": []
            }
        },
        "sort": [{"@timestamp": {"order": "desc"}}],
        "size": 10000,
    },
    "Infra Development": {
        "description": "Infrastructure development projects, types, and status",
        "query": {
            "bool": {
                "must": [
                    {"term": {"activity_type": "infra"}},
                    {"exists": {"field": "infra_type"}},
                    {"exists": {"field": "location_name"}}
                ],
                "must_not": [{"term": {"form_status": 5}}],
                "filter": []
            }
        },
        "sort": [{"@timestamp": {"order": "desc"}}],
        "size": 10000,
    },
    "PLA Sitrep": {
        "description": "PLA patrolling and situation reports",
        "query": {
            "bool": {
                "must": [
                    {"terms": {"form_type.keyword": ["patrolling", "sitrep"]}}
                ],
                "must_not": [{"term": {"form_status": 5}}],
                "filter": []
            }
        },
        "sort": [{"@timestamp": {"order": "desc"}}],
        "size": 10000,
    },
    "General Area": {
        "description": "General geographic area data with location names",
        "query": {
            "bool": {
                "must": [
                    {"exists": {"field": "location_name"}}
                ],
                "filter": []
            }
        },
        "sort": [{"@timestamp": {"order": "desc"}}],
        "size": 10000,
    },
    "Movement": {
        "description": "Force movement tracking with formation and location data",
        "query": {
            "bool": {
                "must": [
                    {"exists": {"field": "location_name"}},
                    {"exists": {"field": "enemy_formation_name"}},
                    {"term": {"activity_type": "movement"}}
                ],
                "must_not": [{"term": {"form_status": 5}}],
                "filter": []
            }
        },
        "sort": [{"@timestamp": {"order": "desc"}}],
        "size": 10000,
    },
    "AIR Aspects": {
        "description": "Airfield and air-related infrastructure and deployment data",
        "query": {
            "bool": {
                "must": [
                    {"exists": {"field": "location_name"}},
                    {"term": {"injester_name": "airfield_injester"}}
                ],
                "must_not": [{"term": {"form_status": 5}}],
                "filter": []
            }
        },
        "sort": [{"@timestamp": {"order": "desc"}}],
        "size": 10000,
    },
    "SAM Deployment": {
        "description": "Surface-to-Air Missile deployment and locations",
        "query": {
            "bool": {
                "must": [
                    {"exists": {"field": "location_name"}},
                    {"term": {"injester_name": "sam_injester"}}
                ],
                "must_not": [{"term": {"form_status": 5}}],
                "filter": []
            }
        },
        "sort": [{"@timestamp": {"order": "desc"}}],
        "size": 10000,
    },
    "Mobile Interception": {
        "description": "Mobile interception and relevant intelligence data",
        "query": {
            "bool": {
                "must": [
                    {"term": {"injester_name": "relevant_injester"}}
                ],
                "must_not": [{"term": {"form_status": 5}}],
                "filter": []
            }
        },
        "sort": [{"form_id": {"order": "desc"}}],
        "size": 10000,
        "track_total_hits": True,
    },
    "Overall Deployment": {
        "description": "Combined view of infrastructure development and force deployment",
        "query": {
            "bool": {
                "must": [],
                "should": [
                    {
                        "bool": {
                            "must": [
                                {"term": {"activity_type": "infra"}},
                                {"exists": {"field": "infra_type"}},
                                {"exists": {"field": "location_name"}}
                            ]
                        }
                    },
                    {
                        "bool": {
                            "must": [
                                {"exists": {"field": "enemy_formation_name"}},
                                {"exists": {"field": "location_name"}},
                                {"exists": {"field": "disposition_status"}},
                                {"term": {"activity_type": "deployment"}}
                            ]
                        }
                    }
                ],
                "minimum_should_match": 1,
                "must_not": [{"term": {"form_status": 5}}],
                "filter": []
            }
        },
        "size": 10000,
    },
}

CATEGORY_LIST = list(CATEGORY_QUERIES.keys())


def get_category_summary() -> str:
    """Return human-readable category descriptions for the LLM router."""
    lines = ["# Available Data Categories\n"]
    for name, cfg in CATEGORY_QUERIES.items():
        lines.append(f"## {name}")
        lines.append(f"  {cfg['description']}")
        lines.append("")
    return "\n".join(lines)
