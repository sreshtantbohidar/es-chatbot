"""
Elasticsearch RAG Chatbot - Index Registry
Auto-built from cluster exploration on 2026-06-08
"""
from dataclasses import dataclass, field

@dataclass
class IndexInfo:
    name: str
    description: str
    category: str  # "primary" | "reference" | "geo" | "logs"
    text_fields: list[str] = field(default_factory=list)
    filter_fields: list[str] = field(default_factory=list)
    date_fields: list[str] = field(default_factory=list)
    geo_field: str | None = None
    doc_count: int = 0


INDEX_REGISTRY: list[IndexInfo] = [
    # === PRIMARY DATA INDICES ===
    IndexInfo(
        name="fatboy_data_v27",
        description="Main military intelligence dataset with deployment, equipment, infrastructure, "
                    "activity, training, and formation data. Rich schema with coordinates, dates, "
                    "equipment details, and country information. Largest active dataset.",
        category="primary",
        text_fields=[
            "description", "name", "activity_name", "equipment_name",
            "enemy_formation_name", "formation_name", "location_name",
            "general_area", "country_name", "infra_name", "army_name",
            "remarks", "comments", "training_name", "form_title",
            "form_data_search", "activity_type", "equipment_type",
        ],
        filter_fields=[
            "country_name", "activity_type", "equipment_type", "infra_type",
            "formation_type", "training_type", "verify_status", "disposition_status",
            "relevance", "form_type", "source_type",
        ],
        date_fields=["start_date", "end_date", "activity_date", "created_date", "@timestamp"],
        geo_field="coordinates",
        doc_count=10432,
    ),
    IndexInfo(
        name="fatboy_data_v26",
        description="Military intelligence dataset (version 26) - similar schema to v27 but earlier snapshot. "
                    "Contains equipment, infrastructure, deployment, and formation data.",
        category="primary",
        text_fields=[
            "description", "name", "activity_name", "equipment_name",
            "enemy_formation_name", "location_name", "general_area",
            "country_name", "infra_name", "remarks", "comments",
        ],
        filter_fields=[
            "country_name", "activity_type", "equipment_type", "verify_status",
        ],
        date_fields=["start_date", "end_date", "activity_date"],
        geo_field="coordinates",
        doc_count=9355,
    ),
    IndexInfo(
        name="new_testing_index",
        description="Large military intelligence index with training, deployment, and equipment data. "
                    "Contains records with location coordinates, formation info, "
                    "infrastructure details, and country/organization data.",
        category="primary",
        text_fields=[
            "description", "name", "activity_name", "equipment_name",
            "location_name", "general_area", "country_name", "infra_name",
            "training_name", "enemy_formation_name", "remarks", "comments",
            "form_title", "form_data_search",
        ],
        filter_fields=[
            "country_name", "activity_type", "equipment_type", "training_type",
            "formation_type", "verify_status", "disposition_status",
        ],
        date_fields=["start_date", "end_date", "activity_date", "@timestamp"],
        geo_field="coordinates",
        doc_count=40385,
    ),

    # === REFERENCE / LOOKUP INDICES ===
    IndexInfo(
        name="equipment_type",
        description="Reference list of equipment types and categories",
        category="reference",
        text_fields=["equipment_type"],
        filter_fields=[],
        date_fields=[],
        doc_count=4538,
    ),
    IndexInfo(
        name="equipment_name",
        description="Reference list of specific equipment names and designations",
        category="reference",
        text_fields=["equipment_name"],
        filter_fields=[],
        date_fields=[],
        doc_count=3961,
    ),
    IndexInfo(
        name="equipment_key",
        description="Equipment lookup by key/identifier",
        category="reference",
        text_fields=["equipment_key"],
        filter_fields=[],
        date_fields=[],
        doc_count=1552,
    ),
    IndexInfo(
        name="infra_type",
        description="Reference list of infrastructure types (buildings, facilities, structures)",
        category="reference",
        text_fields=["infra_type"],
        filter_fields=[],
        date_fields=[],
        doc_count=979,
    ),
    IndexInfo(
        name="infra_name",
        description="Reference list of infrastructure names and designations",
        category="reference",
        text_fields=["infra_name"],
        filter_fields=[],
        date_fields=[],
        doc_count=2171,
    ),
    IndexInfo(
        name="infra_stage",
        description="Infrastructure development stages (planned, under construction, operational, etc.)",
        category="reference",
        text_fields=["infra_stage"],
        filter_fields=[],
        date_fields=[],
        doc_count=95,
    ),
    IndexInfo(
        name="activity_type",
        description="Classification of military activity types (deployment, patrol, exercise, etc.)",
        category="reference",
        text_fields=["activity_type"],
        filter_fields=[],
        date_fields=[],
        doc_count=186,
    ),
    IndexInfo(
        name="activity_name",
        description="Specific named activities and operation names",
        category="reference",
        text_fields=["activity_name"],
        filter_fields=[],
        date_fields=[],
        doc_count=163,
    ),
    IndexInfo(
        name="sub_activity_type",
        description="Sub-categories of military activities",
        category="reference",
        text_fields=["sub_activity_type"],
        filter_fields=[],
        date_fields=[],
        doc_count=17,
    ),
    IndexInfo(
        name="training_type",
        description="Types of military training (combat, tactical, technical, etc.)",
        category="reference",
        text_fields=["training_type"],
        filter_fields=[],
        date_fields=[],
        doc_count=181,
    ),
    IndexInfo(
        name="training_name",
        description="Specific named training programs and exercises",
        category="reference",
        text_fields=["training_name"],
        filter_fields=[],
        date_fields=[],
        doc_count=343,
    ),
    IndexInfo(
        name="enemy_formation_name",
        description="Names and designations of enemy/adversary military formations",
        category="reference",
        text_fields=["enemy_formation_name"],
        filter_fields=[],
        date_fields=[],
        doc_count=382,
    ),
    IndexInfo(
        name="formation_type",
        description="Military formation types (division, brigade, battalion, regiment, etc.)",
        category="reference",
        text_fields=["formation_type"],
        filter_fields=[],
        date_fields=[],
        doc_count=23,
    ),
    IndexInfo(
        name="transgression_sighting_type",
        description="Types of border transgression sightings and incidents",
        category="reference",
        text_fields=["transgression_sighting_type"],
        filter_fields=[],
        date_fields=[],
        doc_count=42,
    ),
    IndexInfo(
        name="location_name",
        description="Named geographic locations, bases, and areas of interest",
        category="reference",
        text_fields=["location_name"],
        filter_fields=[],
        date_fields=[],
        doc_count=1777,
    ),
    IndexInfo(
        name="general_area",
        description="General geographic areas and regions",
        category="reference",
        text_fields=["general_area"],
        filter_fields=[],
        date_fields=[],
        doc_count=1980,
    ),
    IndexInfo(
        name="pass_name",
        description="Mountain passes and route names",
        category="reference",
        text_fields=["pass_name"],
        filter_fields=[],
        date_fields=[],
        doc_count=1456,
    ),
    IndexInfo(
        name="disposition_status",
        description="Force disposition statuses (active, reserve, deployed, etc.)",
        category="reference",
        text_fields=["disposition_status"],
        filter_fields=[],
        date_fields=[],
        doc_count=9,
    ),
    IndexInfo(
        name="base_location_name",
        description="Military base and installation location names",
        category="reference",
        text_fields=["base_location_name"],
        filter_fields=[],
        date_fields=[],
        doc_count=395,
    ),

    # === GEO INDICES ===
    IndexInfo(
        name="nepal_states1",
        description="Nepal administrative boundaries at state/province level with geometry shapes",
        category="geo",
        text_fields=["DISTRICT", "GaPa_NaPa", "Province", "Type_GN"],
        filter_fields=["Province", "Type_GN"],
        geo_field="geometry",
        doc_count=777,
    ),
    IndexInfo(
        name="world-administrative-boundaries",
        description="World country boundaries and administrative regions with geometry, ISO codes, and regions",
        category="geo",
        text_fields=["name", "continent", "region", "iso3", "status", "french_shor"],
        filter_fields=["continent", "region", "status"],
        geo_field="geometry",
        doc_count=256,
    ),

    # === LOGS ===
    IndexInfo(
        name="large_logs",
        description="Flight logs and e-commerce activity data. Contains flight information (origin, destination, "
                    "carrier, delays), customer data, orders, and web traffic logs with IP addresses.",
        category="logs",
        text_fields=[
            "message", "Carrier", "OriginCityName", "DestCityName",
            "OriginCountry", "DestCountry", "customer_full_name",
            "category", "name", "department", "job",
        ],
        filter_fields=[
            "Carrier", "OriginCountry", "DestCountry", "Cancelled",
            "FlightDelay", "FlightDelayType", "day_of_week", "status",
        ],
        date_fields=["@timestamp", "order_date", "created_at", "utc_time"],
        doc_count=192683,
    ),
    IndexInfo(
        name="testing_new",
        description="Test/dataset index with mixed data including location and activity records",
        category="reference",
        text_fields=["name", "description", "location_name", "general_area"],
        filter_fields=[],
        date_fields=["start_date", "end_date", "activity_date"],
        doc_count=1620,
    ),
]


def get_registry_summary() -> str:
    """Return a human-readable summary of the index registry for the LLM."""
    lines = ["# Available Elasticsearch Indices\n"]
    for info in INDEX_REGISTRY:
        lines.append(f"## {info.name} ({info.doc_count} docs) [{info.category}]")
        lines.append(f"  {info.description}")
        if info.text_fields:
            lines.append(f"  Searchable fields: {', '.join(info.text_fields[:6])}")
        if info.filter_fields:
            lines.append(f"  Filter fields: {', '.join(info.filter_fields[:6])}")
        if info.date_fields:
            lines.append(f"  Date fields: {', '.join(info.date_fields[:3])}")
        if info.geo_field:
            lines.append(f"  Geo field: {info.geo_field}")
        lines.append("")
    return "\n".join(lines)
