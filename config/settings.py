"""
es_chatbot - Elasticsearch RAG Chatbot
Converts natural language questions to ES queries and generates grounded answers.
"""

import os
from dataclasses import dataclass, field

# ============================================================
# Configuration
# ============================================================

ES_HOST = os.getenv("ES_HOST", "https://192.168.1.125:9200")
ES_USER = os.getenv("ES_USER", "elastic")
ES_PASS = os.getenv("ES_PASS", "30oIsFcjJa8Zao+iq5*e")

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://192.168.1.125:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", os.getenv("LLM_MODEL"))
EMBED_MODEL = os.getenv("EMBED_MODEL", "bge-m3:latest")

# Retrieval settings
DEFAULT_TOP_K = 10
MAX_CONTEXT_DOCS = 5
MAX_CONTEXT_CHARS = 4000


@dataclass
class IndexInfo:
    """Metadata about an Elasticsearch index for routing and query building."""
    name: str
    description: str
    category: str
    key_fields: list[str]
    text_fields: list[str]       # fields for full-text search
    filter_fields: list[str]     # fields for exact filter/term queries
    date_fields: list[field]     # fields usable as date ranges
    geo_field: str | None = None # geo_point field if any
    doc_count: int = 0


# ============================================================
# Index Registry — describes every searchable index
# ============================================================

INDEX_REGISTRY: dict[str, IndexInfo] = {
    # ---- Main data indices ----
    "fatboy_data": IndexInfo(
        name="fatboy_data",
        description=(
            "Primary military intelligence dataset. Contains records about enemy formations, "
            "equipment, activities, personnel, infrastructure, transgressions, ORBAT data, "
 "locations, coordinates, appointments, training, patrols,communications (calls, SIM), "
            "and procurement. This is the richest and most comprehensive index."
        ),
        category="intelligence",
        key_fields=[
            "activity_type", "activity_name", "equipment_name", "equipment_type",
            "equipment_key", "enemy_formation_name", "location_name", "coordinates",
            "date", "description", "keywords"
        ],
        text_fields=[
            "activity_type", "activity_name", "activity_obs", "equipment_name",
            "equipment_type", "equipment_key", "enemy_formation_name", "location_name",
            "location_area_name", "base_location_name", "description", "description_dup",
            "keywords", "matched_keyword", "form_title", "form_type",
            "formation_type", "person_name", "designation", "rank",
            "force_type_name", "army_name", "bde_name", "remarks", "remark",
            "general_area", "army_name", "infra_name", "infra_type",
            "training_name", "training_type", "transgression_sighting_type",
            "disposition_status", "form_data_search", "agency_name",
        ],
        filter_fields=[
            "activity_type", "equipment_type", "equipment_key",
            "enemy_formation_name", "location_name", "force_type_name",
            "disposition_status", "formation_type", "infra_type",
            "training_type", "transgression_sighting_type", "army_name",
            "country_name", "relevance", "verify_status", "form_status",
            "gender", "category", "group", "rank",
        ],
        date_fields=["date", "activity_date", "created_date", "@timestamp",
                      "appointment_date", "start_date", "end_date",
                      "date_of_birth", "date_of_commission", "date_of_retirement",
                      "transgression_date", "en_ptl_date", "own_ptl_date",
                      "report_date", "called_date", "simactivation_date"],
        geo_field="coordinates",
        doc_count=32831,
    ),

    "ifc_prod_alias_for_dv": IndexInfo(
        name="ifc_prod_alias_for_dv",
        description=(
            "Production intelligence data — similar schema to fatboy_data. "
            "Contains enemy ORBAT, formation, equipment, and activity records."
        ),
        category="intelligence",
        key_fields=[
            "activity_type", "equipment_name", "equipment_type",
            "enemy_formation_name", "orbat_title", "date", "keywords"
        ],
        text_fields=[
            "activity_type", "equipment_name", "equipment_type",
            "enemy_formation_name", "orbat_title", "keywords",
            "formation_type", "army_name", "force_type_name",
            "bde_name", "mil_dist_name", "theatre_comd_name",
            "form_title", "form_type", "form_data_search",
        ],
        filter_fields=[
            "activity_type", "equipment_type", "formation_type",
            "army_name", "force_type_name", "relevance",
            "verify_status", "form_status",
        ],
        date_fields=["date", "activity_date", "created_date", "@timestamp"],
        doc_count=4,
    ),

    # ---- Reference / Lookup indices ----
    "activity_name": IndexInfo(
        name="activity_name",
        description="Reference list of activity names (e.g., appointment, patrol, exercise).",
        category="reference",
        key_fields=["activity_name"],
        text_fields=["activity_name"],
        filter_fields=["activity_name"],
        date_fields=[],
        doc_count=19,
    ),
    "activity_type": IndexInfo(
        name="activity_type",
        description="Reference list of activity types (e.g., equipment, movement, training).",
        category="reference",
        key_fields=["activity_type"],
        text_fields=["activity_type"],
        filter_fields=["activity_type"],
        date_fields=[],
        doc_count=53,
    ),
    "airfield_type": IndexInfo(
        name="airfield_type",
        description="Reference list of airfield types.",
        category="reference",
        key_fields=["airfield_type"],
        text_fields=["airfield_type"],
        filter_fields=["airfield_type"],
        date_fields=[],
        doc_count=2,
    ),
    "base_location_name": IndexInfo(
        name="base_location_name",
        description="Reference list of base/location names (e.g., Mumbai, Delhi).",
        category="reference",
        key_fields=["base_location_name"],
        text_fields=["base_location_name"],
        filter_fields=["base_location_name"],
        date_fields=[],
        doc_count=150,
    ),
    "base_coordinates": IndexInfo(
        name="base_coordinates",
        description="Reference list of base coordinates.",
        category="reference",
        key_fields=["base_coordinates"],
        text_fields=[],
        filter_fields=[],
        date_fields=[],
        doc_count=128,
    ),
    "coordinates": IndexInfo(
        name="coordinates",
        description="Reference list of general coordinates.",
        category="reference",
        key_fields=["coordinates"],
        text_fields=[],
        filter_fields=[],
        date_fields=[],
        doc_count=214,
    ),
    "disposition_status": IndexInfo(
        name="disposition_status",
        description="Reference list of disposition statuses (e.g., Forward_deployment).",
        category="reference",
        key_fields=["disposition_status"],
        text_fields=["disposition_status"],
        filter_fields=["disposition_status"],
        date_fields=[],
        doc_count=7,
    ),
    "enemy_formation_name": IndexInfo(
        name="enemy_formation_name",
        description="Reference list of enemy formation names (e.g., 733 FS Sec, 12 Artillery Brigade).",
        category="reference",
        key_fields=["enemy_formation_name"],
        text_fields=["enemy_formation_name"],
        filter_fields=["enemy_formation_name"],
        date_fields=[],
        doc_count=139,
    ),
    "equipment_key": IndexInfo(
        name="equipment_key",
        description="Reference list of equipment keys (e.g., unknown(attack helicopter)).",
        category="reference",
        key_fields=["equipment_key"],
        text_fields=["equipment_key"],
        filter_fields=["equipment_key"],
        date_fields=[],
        doc_count=162,
    ),
    "equipment_name": IndexInfo(
        name="equipment_name",
        description="Reference list of equipment names (e.g., Missile-20202).",
        category="reference",
        key_fields=["equipment_name"],
        text_fields=["equipment_name"],
        filter_fields=["equipment_name"],
        date_fields=[],
        doc_count=128,
    ),
    "equipment_type": IndexInfo(
        name="equipment_type",
        description="Reference list of equipment types (e.g., vehicles, aircraft, vessels).",
        category="reference",
        key_fields=["equipment_type"],
        text_fields=["equipment_type"],
        filter_fields=["equipment_type"],
        date_fields=[],
        doc_count=86,
    ),
    "formation_type": IndexInfo(
        name="formation_type",
        description="Reference list of formation types (e.g., bde, bn, corps).",
        category="reference",
        key_fields=["formation_type"],
        text_fields=["formation_type"],
        filter_fields=["formation_type"],
        date_fields=[],
        doc_count=49,
    ),
    "general_area": IndexInfo(
        name="general_area",
        description="Reference list of general area names (e.g., burang).",
        category="reference",
        key_fields=["general_area"],
        text_fields=["general_area"],
        filter_fields=["general_area"],
        date_fields=[],
        doc_count=52,
    ),
    "infra_name": IndexInfo(
        name="infra_name",
        description="Reference list of infrastructure names (e.g., Camp_202).",
        category="reference",
        key_fields=["infra_name"],
        text_fields=["infra_name"],
        filter_fields=["infra_name"],
        date_fields=[],
        doc_count=55,
    ),
    "infra_stage": IndexInfo(
        name="infra_stage",
        description="Reference list of infrastructure stages (e.g., Progress, Completed).",
        category="reference",
        key_fields=["infra_stage"],
        text_fields=["infra_stage"],
        filter_fields=["infra_stage"],
        date_fields=[],
        doc_count=18,
    ),
    "infra_type": IndexInfo(
        name="infra_type",
        description="Reference list of infrastructure types (e.g., Military Camp, Bridge).",
        category="reference",
        key_fields=["infra_type"],
        text_fields=["infra_type"],
        filter_fields=["infra_type"],
        date_fields=[],
        doc_count=43,
    ),
    "location_name": IndexInfo(
        name="location_name",
        description="Reference list of location names (e.g., zhangjiakou, urumqi).",
        category="reference",
        key_fields=["location_name"],
        text_fields=["location_name"],
        filter_fields=["location_name"],
        date_fields=[],
        doc_count=219,
    ),
    "patrol_by": IndexInfo(
        name="patrol_by",
        description="Reference list of patrol by values (e.g., enemy, own).",
        category="reference",
        key_fields=["patrol_by"],
        text_fields=["patrol_by"],
        filter_fields=["patrol_by"],
        date_fields=[],
        doc_count=2,
    ),
    "sub_activity_type": IndexInfo(
        name="sub_activity_type",
        description="Reference list of sub-activity types (e.g., miscellaneous).",
        category="reference",
        key_fields=["sub_activity_type"],
        text_fields=["sub_activity_type"],
        filter_fields=["sub_activity_type"],
        date_fields=[],
        doc_count=6,
    ),
    "training_name": IndexInfo(
        name="training_name",
        description="Reference list of training names (e.g., Operation Desert Strike).",
        category="reference",
        key_fields=["training_name"],
        text_fields=["training_name"],
        filter_fields=["training_name"],
        date_fields=[],
        doc_count=10,
    ),
    "training_type": IndexInfo(
        name="training_type",
        description="Reference list of training types (e.g., Firing, Exercise).",
        category="reference",
        key_fields=["training_type"],
        text_fields=["training_type"],
        filter_fields=["training_type"],
        date_fields=[],
        doc_count=10,
    ),
    "transgression_sighting_type": IndexInfo(
        name="transgression_sighting_type",
        description="Reference list of transgression/sighting types (e.g., Chance mtg).",
        category="reference",
        key_fields=["transgression_sighting_type"],
        text_fields=["transgression_sighting_type"],
        filter_fields=["transgression_sighting_type"],
        date_fields=[],
        doc_count=8,
    ),

    # ---- Geo / Spatial indices ----
    "csv_locations": IndexInfo(
        name="csv_locations",
        description="CSV-imported locations with geo-coordinates (e.g., New York).",
        category="geo",
        key_fields=["location_n", "lat", "long", "geometry"],
        text_fields=["location_n"],
        filter_fields=["location_n"],
        date_fields=[],
        geo_field="location",
        doc_count=5,
    ),
    "gis_osm_roads_07_1": IndexInfo(
        name="gis_osm_roads_07_1",
        description="OpenStreetMap road network data with geometries.",
        category="geo",
        key_fields=["geometry", "latitude", "longitude"],
        text_fields=[],
        filter_fields=[],
        date_fields=[],
        geo_field="location",
        doc_count=62236,
    ),
    "gis_osm_traffic_a_07_1": IndexInfo(
        name="gis_osm_traffic_a_07_1",
        description="OpenStreetMap traffic data (parking areas, etc.) with geometries and names.",
        category="geo",
        key_fields=["name", "fclass", "geometry"],
        text_fields=["name", "fclass"],
        filter_fields=["fclass"],
        date_fields=["lastchange"],
        geo_field="location",
        doc_count=2325,
    ),
    "ind_roads": IndexInfo(
        name="ind_roads",
        description="India road network data with road type descriptions.",
        category="geo",
        key_fields=["f_code_des", "med_descri", "rtt_descri", "geometry"],
        text_fields=["f_code_des", "med_descri", "rtt_descri"],
        filter_fields=["f_code_des", "rtt_descri"],
        date_fields=[],
        geo_field="location",
        doc_count=19148,
    ),
    "national_highway": IndexInfo(
        name="national_highway",
        description="National highway data with names, routes, and geometries.",
        category="geo",
        key_fields=["name", "type", "from", "to", "geometry"],
        text_fields=["name", "type", "from", "to"],
        filter_fields=["type"],
        date_fields=[],
        geo_field="location",
        doc_count=31,
    ),
    "g695_highway": IndexInfo(
        name="g695_highway",
        description="G695 highway geometry data.",
        category="geo",
        key_fields=["geometry"],
        text_fields=[],
        filter_fields=[],
        date_fields=[],
        geo_field="location",
        doc_count=1,
    ),
    "india_sample_area": IndexInfo(
        name="india_sample_area",
        description="Sample area zones within India with polygon geometries.",
        category="geo",
        key_fields=["name", "geometry"],
        text_fields=["name"],
        filter_fields=["name"],
        date_fields=[],
        geo_field="location",
        doc_count=1,
    ),
    "polygon5": IndexInfo(
        name="polygon5",
        description="Polygon boundary data (geofences/areas of interest).",
        category="geo",
        key_fields=["geometry"],
        text_fields=[],
        filter_fields=[],
        date_fields=[],
        geo_field="location",
        doc_count=1,
    ),
    "polygon6": IndexInfo(
        name="polygon6",
        description="Polygon boundary data (geofences/areas of interest).",
        category="geo",
        key_fields=["geometry"],
        text_fields=[],
        filter_fields=[],
        date_fields=[],
        geo_field="location",
        doc_count=1,
    ),
    "polyline": IndexInfo(
        name="polyline",
        description="Polyline data (routes/boundaries as line geometries).",
        category="geo",
        key_fields=["geometry"],
        text_fields=[],
        filter_fields=[],
        date_fields=[],
        geo_field="location",
        doc_count=1,
    ),
    "polyline5": IndexInfo(
        name="polyline5",
        description="Polyline data (routes/boundaries as line geometries).",
        category="geo",
        key_fields=["geometry"],
        text_fields=[],
        filter_fields=[],
        date_fields=[],
        geo_field="location",
        doc_count=1,
    ),
}


def get_registry_summary() -> str:
    """Return a compact summary of the index registry for the LLM."""
    lines = []
    for name, info in sorted(INDEX_REGISTRY.items()):
        lines.append(
            f"Index: {name}\n"
            f"  Category: {info.category}\n"
            f"  Description: {info.description}\n"
            f"  Docs: {info.doc_count}\n"
            f"  Searchable fields: {', '.join(info.text_fields[:10])}"
            f"{'...' if len(info.text_fields) > 10 else ''}\n"
            f"  Filter fields: {', '.join(info.filter_fields[:8])}"
            f"{'...' if len(info.filter_fields) > 8 else ''}\n"
            f"  Date fields: {', '.join(info.date_fields[:5]) if info.date_fields else 'none'}\n"
            f"  Geo field: {info.geo_field or 'none'}"
        )
    return "\n".join(lines)
