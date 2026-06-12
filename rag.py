"""
Elasticsearch RAG Chatbot - Core Pipeline
"""
import json
import re
from dataclasses import dataclass

from elasticsearch import Elasticsearch
from openai import OpenAI

from registry import INDEX_REGISTRY, IndexInfo, get_registry_summary


@dataclass
class QuestionIntent:
    indices: list[str]
    intent_type: str  # LOOKUP | COUNT | LIST | TEMPORAL | GEO | GENERAL
    search_terms: str
    entities: dict[str, str]
    date_range: dict | None


@dataclass
class AskResult:
    answer: str
    indices_used: list[str]
    total_hits: int
    query_used: dict | None = None
    debug: dict | None = None


class ElasticsearchRAG:
    def __init__(self, es: EsConfig, llm: LlmConfig, top_k: int = 10):
        self.es_client = Elasticsearch(
            [es.hosts],
            basic_auth=(es.username, es.password),
            verify_certs=False,
            request_timeout=15,
        )
        self.llm = OpenAI(base_url=llm.base_url, api_key=llm.api_key)
        self.model = llm.model
        self.top_k = top_k

    # ── Step 1: Question Routing ──────────────────────────────────
    def route_question(self, question: str) -> QuestionIntent:
        """Use LLM to understand the question and pick indices."""
        registry_text = get_registry_summary()

        system_prompt = f"""You are an expert routing questions to Elasticsearch indices.
Given a question and the available indices below, respond with ONLY a JSON object:

{{
  "indices": ["index_name1"],
  "intent_type": "LOOKUP|COUNT|LIST|TEMPORAL|GEO|GENERAL",
  "search_terms": "key search terms extracted from the question",
  "entities": {{"field_hint": "extracted_value"}},
  "date_range": null or {{"gte": "YYYY-MM-DD", "lte": "YYYY-MM-DD"}}
}}

Intent types:
- LOOKUP: find specific records matching criteria
- COUNT: how many records match
- LIST: enumerate all values of a type
- TEMPORAL: time-based patterns ("recent", "last year", "in 2024")
- GEO: location/spatial questions ("near", "in province X", "boundary")
- GENERAL: open-ended exploration questions

Rules:
- Pick ONE primary index unless the question clearly spans multiple
- For equipment-related questions, prefer main indices (fatboy_data_v27, new_testing_index) over reference lists
- Use reference indices (equipment_type, infra_name, etc.) only for LIST intent
- ALWAYS provide search_terms even if short
- If question references geographic areas or boundaries, route to geo indices

Available indices:
{registry_text}"""

        resp = self.llm.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": question},
            ],
            response_format={"type": "json_object"},
            max_tokens=500,
        )
        raw = resp.choices[0].message.content
        data = json.loads(raw)
        return QuestionIntent(
            indices=data.get("indices", ["fatboy_data_v27"]),
            intent_type=data.get("intent_type", "GENERAL"),
            search_terms=data.get("search_terms", question),
            entities=data.get("entities", {}),
            date_range=data.get("date_range"),
        )

    # ── Step 2: Query Builder ─────────────────────────────────────
    def build_query(self, intent: QuestionIntent, index_info: IndexInfo) -> dict:
        """Convert intent into Elasticsearch DSL query."""
        should_clauses = []
        filter_clauses = []

        # Full-text search on text fields
        if intent.search_terms and index_info.text_fields:
            should_clauses.append({
                "multi_match": {
                    "query": intent.search_terms,
                    "fields": index_info.text_fields[:10],
                    "type": "best_fields",
                    "fuzziness": "AUTO",
                }
            })

        # Entity values as soft boosts (NOT hard filters to avoid missing results)
        for val in intent.entities.values():
            val = str(val).strip()
            if not val or looks_like_field_name(val, index_info):
                continue
            should_clauses.append({
                "multi_match": {
                    "query": val,
                    "fields": index_info.text_fields[:6],
                    "fuzziness": "AUTO",
                }
            })

        # Date range as hard filter
        if intent.date_range and index_info.date_fields:
            filter_clauses.append({
                "range": {index_info.date_fields[0]: intent.date_range}
            })

        # Build bool query
        if should_clauses:
            bool_query = {
                "should": should_clauses,
                "minimum_should_match": 1,
            }
            if filter_clauses:
                bool_query["filter"] = filter_clauses
            query_body = {"query": {"bool": bool_query}}
        elif filter_clauses:
            query_body = {"query": {"bool": {"filter": filter_clauses}}}
        else:
            query_body = {"query": {"match_all": {}}}

        query_body["size"] = self.top_k
        query_body["track_total_hits"] = True

        # Request highlights on text fields
        if index_info.text_fields:
            query_body["highlight"] = {
                "fields": {f: {} for f in index_info.text_fields[:5]},
                "fragment_size": 200,
            }

        return query_body

    # ── Step 3: Retrieve ──────────────────────────────────────────
    def retrieve(self, intent: QuestionIntent) -> tuple[list[dict], list[str], int]:
        """Execute ES queries across selected indices. Returns (docs, indices_used, total_hits)."""
        all_docs = []
        indices_used = []
        total_hits = 0

        for idx_name in intent.indices:
            index_info = next((i for i in INDEX_REGISTRY if i.name == idx_name), None)
            if not index_info:
                # Try direct index search
                try:
                    body = self.build_query_for_unknown(intent)
                    result = self.es_client.search(index=idx_name, body=body)
                    hits = result["hits"]["hits"]
                    total = result["hits"]["total"]["value"]
                    if total > 0:
                        indices_used.append(idx_name)
                        total_hits += total
                        all_docs.extend(hits)
                except Exception:
                    pass
                continue

            try:
                body = self.build_query(intent, index_info)
                result = self.es_client.search(index=idx_name, body=body)
                hits = result["hits"]["hits"]
                total = result["hits"]["total"]["value"]
                if total > 0:
                    indices_used.append(idx_name)
                    total_hits += total
                    all_docs.extend(hits)
            except Exception as e:
                print(f"  [WARN] Search failed on {idx_name}: {e}")

        # If primary indices returned nothing, try fallback search
        if not all_docs and intent.search_terms:
            fallback_indices = ["fatboy_data_v27", "new_testing_index", "fatboy_data_v26"]
            for fb_idx in fallback_indices:
                if fb_idx in intent.indices:
                    continue
                try:
                    index_info = next((i for i in INDEX_REGISTRY if i.name == fb_idx), None)
                    if index_info:
                        body = self.build_query(intent, index_info)
                        result = self.es_client.search(index=fb_idx, body=body)
                        hits = result["hits"]["hits"]
                        total = result["hits"]["total"]["value"]
                        if total > 0:
                            indices_used.append(f"{fb_idx} (fallback)")
                            total_hits += total
                            all_docs.extend(hits)
                            break
                except Exception:
                    pass

        return all_docs, indices_used, total_hits

    def build_query_for_unknown(self, intent: QuestionIntent) -> dict:
        """Fallback query for indices not in the registry."""
        body = {
            "query": {
                "multi_match": {
                    "query": intent.search_terms,
                    "type": "best_fields",
                    "fuzziness": "AUTO",
                }
            },
            "size": self.top_k,
            "track_total_hits": True,
        }
        return body

    # ── Step 4: Generate Answer ───────────────────────────────────
    def generate_answer(self, question: str, docs: list[dict], indices_used: list[str],
                        total_hits: int, intent: QuestionIntent, debug: bool = False) -> AskResult:
        """Generate grounded answer from retrieved documents."""

        # Format context from docs (truncate to avoid token overflow)
        context_parts = []
        docs_for_context = docs[:8]  # Use top 8 docs max
        for i, doc in enumerate(docs_for_context, 1):
            source = doc.get("_source", {})
            score = doc.get("_score", 0)
            idx = doc.get("_index", "")
            highlights = doc.get("highlight", {})

            # Build compact representation
            flat = flatten_source(source)
            relevant_fields = {
                k: v for k, v in flat.items()
                if k in ("description", "name", "equipment_name", "activity_name",
                         "location_name", "general_area", "country_name", "infra_name",
                         "training_name", "enemy_formation_name", "formation_name",
                         "carrier_type", "equipment_type", "infra_type", "activity_type",
                         "remarks", "comments", "type", "status", "count", "quantity",
                         "start_date", "end_date", "activity_date", "date",
                         "carrier", "origin", "dest", "origin_cityname", "dest_cityname",
                         "customer_full_name", "category", "department")
                and v
            }
            # Also include any fields matching the search terms
            if intent.search_terms:
                search_lower = intent.search_terms.lower()
                for k, v in flat.items():
                    if isinstance(v, str) and search_lower in v.lower() and k not in relevant_fields:
                        relevant_fields[k] = v

            lines = [f"[Doc {i} | score={score:.2f} | index={idx}]"]
            for k, v in list(relevant_fields.items())[:15]:
                if isinstance(v, str) and len(v) > 200:
                    v = v[:200] + "..."
                lines.append(f"  {k}: {v}")

            if highlights:
                lines.append("  Highlights:")
                for field, frags in highlights.items():
                    for frag in frags[:2]:
                        lines.append(f"    {field}: ...{strip_html(frag)}...")

            context_parts.append("\n".join(lines))

        context = "\n\n".join(context_parts)
        if len(context) > 8000:
            context = context[:8000] + "\n... [truncated]"

        indices_str = ", ".join(indices_used) if indices_used else "none"

        system_prompt = f"""You are a precise question-answering assistant backed by Elasticsearch search results.

STRICT RULES:
1. ONLY use facts from the provided search results. NEVER invent or guess.
2. If search results are empty or insufficient, say "No data found in the indexes for this query."
3. Quote specific values (names, numbers, dates) directly from the results.
4. Be concise but informative. Max 300 words.
5. When multiple documents agree, state the fact confidently.
6. When results show varied data, summarize the range.
7. If the question asks for a count, report total_hits and show supporting evidence.

Search performed on: {indices_str}
Total matching documents: {total_hits}
Search terms: {intent.search_terms}"""

        user_content = f"Question: {question}\n\nSearch Results:\n{context}"

        if total_hits == 0:
            return AskResult(
                answer="No data found in the indexes for this query. Try rephrasing or using different search terms.",
                indices_used=indices_used,
                total_hits=0,
                debug={"intent": intent.__dict__} if debug else None,
            )

        resp = self.llm.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            max_tokens=600,
        )
        answer = resp.choices[0].message.content.strip()

        return AskResult(
            answer=answer,
            indices_used=indices_used,
            total_hits=total_hits,
            debug={
                "intent": intent.__dict__,
                "query_used": self.build_query(
                    intent,
                    next((i for i in INDEX_REGISTRY if i.name == intent.indices[0]), INDEX_REGISTRY[0])
                ) if intent.indices else None,
            } if debug else None,
        )

    # ── Main Entry Point ──────────────────────────────────────────
    def ask(self, question: str, debug: bool = False) -> AskResult:
        """Full RAG pipeline: route → retrieve → generate."""
        intent = self.route_question(question)
        docs, indices_used, total_hits = self.retrieve(intent)
        return self.generate_answer(question, docs, indices_used, total_hits, intent, debug)


# ── Helpers ────────────────────────────────────────────────────────

def looks_like_field_name(val: str, index_info: IndexInfo) -> bool:
    """Check if a value looks like a field name rather than a search value."""
    all_fields = set(
        index_info.text_fields + index_info.filter_fields +
        index_info.date_fields + ([index_info.geo_field] if index_info.geo_field else [])
    )
    return val.lower() in {f.lower() for f in all_fields}


def flatten_source(source: dict, prefix: str = "") -> dict:
    """Flatten nested _source dict for display."""
    flat = {}
    for k, v in source.items():
        key = f"{prefix}{k}" if not prefix else f"{prefix}.{k}"
        if isinstance(v, dict):
            flat.update(flatten_source(v, key))
        elif isinstance(v, list) and v and isinstance(v[0], dict):
            flat[key] = str(v[:3])  # Truncate list of objects
        else:
            flat[key] = v
    return flat


def strip_html(text: str) -> str:
    """Remove HTML tags from highlight fragments."""
    return re.sub(r"<[^>]+>", "", text)


# ── Config ─────────────────────────────────────────────────────────
@dataclass
class EsConfig:
    hosts: str
    username: str
    password: str


@dataclass
class LlmConfig:
    base_url: str
    api_key: str
    model: str
