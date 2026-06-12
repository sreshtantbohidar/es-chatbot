"""
Elasticsearch Chatbot - Core Engine

Flow:
  1. User picks a category + time frame (or provides raw ES query)
  2. System fetches ALL matching data from ES using scroll API (no size cap)
  3. User chats — for each question:
     a. Re-retrieve the most relevant subset via ES
     b. If small enough → feed directly to LLM
     c. If large → chunk the docs, summarize each chunk (map), then combine (reduce)

Optimizations for slow LLM backends:
  - No LLM calls during fetch (no pre-summarization)
  - Hard timeout on every LLM call (configurable)
  - If LLM times out → fallback to returning raw doc snippets
  - Chunk summarization only happens during ask(), not during fetch()
"""
from __future__ import annotations

from datetime import datetime, timedelta
import json
import re
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Optional

from elasticsearch import Elasticsearch
from openai import OpenAI


# ── Chat Session ────────────────────────────────────────────────────

@dataclass
class ChatSession:
    """
    Manages a conversation session with memory.

    Stores up to `max_turns` complete question+answer pairs.
    Older turns are automatically evicted when the limit is reached.
    Provides conversation history context to the mediator so it can
    reference prior exchanges when answering new questions.
    """
    max_turns: int = 10
    created_at: datetime = field(default_factory=datetime.now)
    _history: list[dict] = field(default_factory=list)
    _metadata: dict = field(default_factory=lambda: {"total_questions": 0, "rag_questions": 0, "direct_questions": 0})

    @property
    def turns_used(self) -> int:
        return len(self._history)

    @property
    def turns_remaining(self) -> int:
        return max(0, self.max_turns - self.turns_used)

    @property
    def is_full(self) -> bool:
        return self.turns_used >= self.max_turns

    def add_exchange(self, question: str, answer: str, used_rag: bool = False) -> None:
        """Record a completed Q&A turn."""
        self._history.append({
            "turn": self.turns_used + 1,
            "question": question,
            "answer": answer,
            "used_rag": used_rag,
            "timestamp": datetime.now().isoformat(),
        })
        self._metadata["total_questions"] += 1
        if used_rag:
            self._metadata["rag_questions"] += 1
        else:
            self._metadata["direct_questions"] += 1

    def get_history_for_mediator(self, last_n: int = 5) -> str:
        """
        Return recent conversation history as a formatted string
        for the mediator to use as context.
        """
        if not self._history:
            return ""

        recent = self._history[-last_n:]
        lines = ["# Recent Conversation History (for context):"]
        for entry in recent:
            lines.append(f"\n[Turn {entry['turn']}]")
            lines.append(f"User: {entry['question']}")
            lines.append(f"Assistant: {entry['answer'][:300]}")
            if len(entry['answer']) > 300:
                lines.append("  ... (truncated)")

        return "\n".join(lines)

    def summarize_session(self) -> str:
        """A brief summary of what was discussed in this session."""
        topics = []
        for entry in self._history:
            q = entry['question']
            # Extract key topics (simple heuristic)
            for keyword in ["formation", "equipment", "infrastructure", "location", "activity", "deployment", "tsona", "radar", "tank", "brigade", "battalion"]:
                if keyword in q.lower() and keyword not in topics:
                    topics.append(keyword)
        if topics:
            return f"Topics covered: {', '.join(topics[:8])}. Total Q&A: {self.turns_used}."
        return f"Total Q&A: {self.turns_used} across this session."

    def reset(self) -> None:
        """Clear history and start fresh."""
        self._history.clear()
        self._metadata = {"total_questions": 0, "rag_questions": 0, "direct_questions": 0}
        self.created_at = datetime.now()


# ── Data Models ───────────────────────────────────────────────────

from categories import (
    CATEGORY_QUERIES,
    CATEGORY_LIST,
    INDEX_PATTERN,
    get_category_summary,
)


@dataclass
class ProgressEvent:
    """A progress update yielded during ask_stream()."""
    type: str           # status | retrieving | chunk | mediator | answer | error
    message: str        # Human-readable status message
    step: int = 0       # Current step number
    total_steps: int = 0  # Total steps
    data: dict = field(default_factory=dict)  # Extra data (counts, timings, etc.)

    def __str__(self):
        prefix = f"[{self.step}/{self.total_steps}]" if self.total_steps > 0 else ""
        return f"{prefix} {self.message}"


# ── Data Models ───────────────────────────────────────────────────

@dataclass
class FetchRequest:
    mode: str = "category"         # "category" or "raw_query"
    category: str | None = None
    raw_query: dict | None = None
    date_from: str | None = None
    date_to: str | None = None
    date_field: str = "@timestamp"


@dataclass
class FetchResult:
    total_hits: int
    documents: list[dict]
    query_used: dict
    category: str | None
    date_range: dict | None
    warnings: list[str] = field(default_factory=list)


@dataclass
class ChatRequest:
    question: str


@dataclass
class ChatResponse:
    answer: str
    sources_used: int
    debug: dict | None = None


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
    timeout: int = 60  # seconds per LLM call


FIELDS_OF_INTEREST = {
    "description", "name", "enemy_formation_name", "location_name",
    "general_area", "country_name", "infra_name", "infra_type",
    "training_name", "training_type", "activity_name", "activity_type",
    "equipment_name", "equipment_type", "formation_name",
    "disposition_status", "remarks", "comments", "relevance",
    "start_date", "end_date", "activity_date", "date", "year",
    "carrier", "status", "type", "count", "quantity",
    "injester_name", "form_type", "form_unique_id", "verify_status",
    "sentiment_lable", "emotion_lable", "orignal_text",
    "military_geography", "orbat_title", "force_type_name",
    "troop_capacity", "army_name", "bde_name", "bn_name",
    "regts_name", "div_name", "corps_name", "command_name",
    "pass_name", "river_name", "province_name", "state_name",
}


# ── ES Client ─────────────────────────────────────────────────────

def make_es_client(cfg: EsConfig) -> Elasticsearch:
    return Elasticsearch(
        [cfg.hosts],
        basic_auth=(cfg.username, cfg.password),
        verify_certs=False,
        request_timeout=60,
    )


# ── Query Builders ────────────────────────────────────────────────

def build_fetch_query(req: FetchRequest) -> dict:
    """Build ES query for fetching all matching docs (no size cap)."""
    if req.mode == "raw_query" and req.raw_query:
        base = deepcopy(req.raw_query)
        base.pop("size", None)
        base.pop("aggs", None)
    elif req.mode == "category" and req.category in CATEGORY_QUERIES:
        cat = CATEGORY_QUERIES[req.category]
        base = {}
        if "query" in cat:
            base["query"] = deepcopy(cat["query"])
        if "sort" in cat:
            base["sort"] = deepcopy(cat["sort"])
        if not base:
            base = {"query": {"match_all": {}}}
    else:
        base = {"query": {"match_all": {}}}

    # Time filter
    if req.date_from or req.date_to:
        df = _date_filter(req.date_from, req.date_to, req.date_field)
        q = base.get("query", {})
        if "bool" in q:
            q["bool"].setdefault("filter", []).append(df)
        else:
            base["query"] = {"bool": {"must": [q], "filter": [df]}}

    base["track_total_hits"] = True
    return base


def build_search_query(question: str, category: str | None,
                       date_from: str | None, date_to: str | None,
                       size: int = 100) -> dict:
    """Focused re-retrieval for a specific question within session scope."""
    # Build a should clause with both phrase and best_fields matching
    # so exact phrases like "J-20" rank higher than generic word matches
    must_clauses: list = [
        {
            "bool": {
                "should": [
                    {
                        "multi_match": {
                            "query": question,
                            "type": "phrase",
                            "boost": 3,
                        }
                    },
                    {
                        "multi_match": {
                            "query": question,
                            "type": "best_fields",
                            "fuzziness": "AUTO",
                        }
                    },
                ],
                "minimum_should_match": 1,
            }
        }
    ]
    filter_clauses: list = []

    if category and category in CATEGORY_QUERIES:
        cat_q = CATEGORY_QUERIES[category]["query"]
        if "bool" in cat_q:
            if "must" in cat_q["bool"]:
                must_clauses.extend(cat_q["bool"]["must"])
            if "must_not" in cat_q["bool"]:
                filter_clauses.append({"bool": {"must_not": cat_q["bool"]["must_not"]}})
            if "filter" in cat_q["bool"]:
                filter_clauses.extend(cat_q["bool"]["filter"])

    if date_from or date_to:
        filter_clauses.append(_date_filter(date_from, date_to, "@timestamp"))

    body: dict = {
        "query": {"bool": {"must": must_clauses}},
        "size": size,
        "track_total_hits": True,
    }
    if filter_clauses:
        body["query"]["bool"]["filter"] = filter_clauses

    return body


def _date_filter(date_from: str | None, date_to: str | None, field: str) -> dict:
    spec = {}
    if date_from:
        spec["gte"] = date_from
    if date_to:
        spec["lte"] = date_to
    return {"range": {field: spec}}


# ── DataStore ─────────────────────────────────────────────────────

class DataStore:
    def __init__(self):
        self.documents: list[dict] = []
        self.total_hits: int = 0
        self.category: str | None = None
        self.date_range: dict | None = None
        self.query_used: dict | None = None
        self.is_loaded: bool = False

    def load(self, docs: list[dict], total: int, category: str | None,
             date_range: dict | None, query: dict):
        self.documents = docs
        self.total_hits = total
        self.category = category
        self.date_range = date_range
        self.query_used = query
        self.is_loaded = True

    def clear(self):
        self.__init__()


# ── Chat Engine ───────────────────────────────────────────────────

DOCS_PER_CHUNK = 25   # docs per LLM chunk during map-reduce
MAX_DIRECT = 50       # if focused retrieval <= this, skip map-reduce


class ChatEngine:
    def __init__(self, es_client: Elasticsearch, llm_cfg: LlmConfig,
                 session: ChatSession | None = None):
        self.es = es_client
        self.llm = OpenAI(
            base_url=llm_cfg.base_url,
            api_key=llm_cfg.api_key,
            timeout=llm_cfg.timeout,
        )
        self.model = llm_cfg.model
        self.llm_timeout = llm_cfg.timeout
        self.store = DataStore()
        self.session = session or ChatSession(max_turns=10)
        self._mediator: MediatorAgent | None = None

    def _get_mediator(self) -> MediatorAgent:
        """Lazy-initialize the mediator agent."""
        if self._mediator is None:
            self._mediator = MediatorAgent(
                llm_client=self.llm,
                model=self.model,
                timeout=max(30, self.llm_timeout // 2),
            )
        return self._mediator

    # ── Fetch ALL data via scroll ─────────────────────────────────

    def fetch_data(self, req: FetchRequest) -> FetchResult:
        """Fetch every matching document from ES. No LLM calls — just raw ES fetch."""
        query = build_fetch_query(req)
        warnings: list[str] = []

        try:
            resp = self.es.search(
                index=INDEX_PATTERN, body=query,
                scroll="5m", size=1000,
            )
        except Exception as e:
            raise RuntimeError(f"Elasticsearch query failed: {e}")

        scroll_id = resp["_scroll_id"]
        total = resp["hits"]["total"]["value"]
        all_docs: list[dict] = list(resp["hits"]["hits"])

        while len(all_docs) < total:
            try:
                page = self.es.scroll(scroll_id=scroll_id, scroll="5m")
                scroll_id = page["_scroll_id"]
                batch = page["hits"]["hits"]
                if not batch:
                    break
                all_docs.extend(batch)
            except Exception as e:
                warnings.append(f"Scroll interrupted after {len(all_docs)} docs: {e}")
                break

        try:
            self.es.clear_scroll(scroll_id=scroll_id)
        except Exception:
            pass

        if total > len(all_docs):
            warnings.append(f"Retrieved {len(all_docs)} of {total} total documents.")

        # Dedup by description_hash — keep highest-scoring / most recent doc per hash
        before_dedup = len(all_docs)
        seen_hashes: dict[str, int] = {}
        deduped_docs: list[dict] = []
        for doc in all_docs:
            src = doc.get("_source", {})
            dh = src.get("description_hash", "")
            if not dh:
                # No hash — always keep (can't dedup what we can't identify)
                deduped_docs.append(doc)
                continue
            dh_str = str(dh)
            if dh_str not in seen_hashes:
                seen_hashes[dh_str] = len(deduped_docs)
                deduped_docs.append(doc)
            # else: duplicate description_hash — skip (already have representative)

        removed = before_dedup - len(deduped_docs)
        if removed > 0:
            warnings.append(f"Deduplicated {removed} docs by description_hash ({before_dedup} → {len(deduped_docs)} unique).")
        all_docs = deduped_docs

        date_range = None
        if req.date_from or req.date_to:
            date_range = {}
            if req.date_from:
                date_range["from"] = req.date_from
            if req.date_to:
                date_range["to"] = req.date_to

        self.store.load(
            docs=all_docs, total=total, category=req.category,
            date_range=date_range, query=query,
        )

        return FetchResult(
            total_hits=total,
            documents=all_docs,
            query_used=query,
            category=req.category,
            date_range=date_range,
            warnings=warnings,
        )

    # ── Re-retrieve relevant docs ─────────────────────────────────

    def re_retrieve(self, question: str, size: int = 100) -> list[dict]:
        """Focused re-retrieval within the current session's scope. Deduped by description_hash."""
        if not self.store.is_loaded:
            return []
        body = build_search_query(
            question=question,
            category=self.store.category,
            date_from=self.store.date_range.get("from") if self.store.date_range else None,
            date_to=self.store.date_range.get("to") if self.store.date_range else None,
            size=size,
        )
        # Inject parsed temporal filter from the question (overrides session date range)
        date_range = self._parse_date_range(question)
        if date_range:
            # Add activity_date range filter alongside existing filters
            date_filter = {"range": {"activity_date": date_range}}
            body["query"]["bool"].setdefault("filter", []).append(date_filter)
        try:
            resp = self.es.search(index=INDEX_PATTERN, body=body)
            hits = resp["hits"]["hits"]
            # Dedup by description_hash — keep first (highest-scoring) per hash
            seen: set[str] = set()
            deduped: list[dict] = []
            for doc in hits:
                dh = str(doc.get("_source", {}).get("description_hash", ""))
                if not dh:
                    deduped.append(doc)
                elif dh not in seen:
                    seen.add(dh)
                    deduped.append(doc)
            return deduped
        except Exception:
            return self.store.documents[:size]

    # ── Intent Classification ───────────────────────────────────────

    # Keyword patterns that signal aggregation intent (no LLM needed)
    _COUNT_KEYWORDS = [
        "how many", "count", "total number", "total count", "number of",
        "how much", "what is the count", "how many unique",
    ]
    _LIST_UNIQUE_KEYWORDS = [
        "list all", "list of all", "what are the", "list the", "list every",
        "list each", "list unique", "list the unique", "all the unique",
        "all unique", "enumerate", "all of the", "all the different",
        "unique values of", "unique names of",
        "what types of", "what kinds of", "what categories of",
        "what type of", "what kind of",
        "show me all", "show all", "give me all", "give me a list",
        "give me list", "provide a list", "provide list",
    ]
    # Regex patterns for more complex matching (checked with re.search)
    _LIST_UNIQUE_REGEX = [
        r"what\s+(?:\w+\s+){0,3}(?:exist|are\s+there|are\s+found|are\s+present|can\s+be\s+found|do\s+we\s+have|are\s+listed|are\s+recorded|are\s+mentioned)",
        r"what\s+(?:different|various|kinds?\s+of|types?\s+of|categories?\s+of)",
    ]
    _TOP_N_KEYWORDS = [
        "top ", "top 5", "top 10", "top 20", "most frequent",
        "most common", "by document count", "by number of documents",
        "most mentioned", "highest count",
        "has the most", "have the most", "most documents",
        "most records", "most entries", "highest number",
        "which formation has", "which location has", "which status has",
        "which type has", "which infra", "which equipment",
        "most of the", "majority of",
    ]
    _GROUP_BY_KEYWORDS = [
        "group by", "grouped by", "group them", "breakdown by",
        "break down", "breakdown of", "categorized by", "group the",
    ]

    # ── Out-of-scope detection ───────────────────────────────────────
    # Questions that are completely unrelated to the military intelligence
    # data should be rejected immediately without hitting ES or LLM.

    _OOS_KEYWORDS = [
        # Time/date questions about the real world (not data timestamps)
        "current time", "what time is it", "what's the time",
        "current date", "what's the date", "what day is it",
        "today's date", "yesterday's date", "tomorrow's date",
        # Personal/metadata questions
        "your name", "who are you", "what are you",
        "how old are you", "where do you live",
        "tell me a joke", "sing me a song", "write a poem",
        # General knowledge not in the data
        "weather forecast", "stock price", "sports score",
        "news today", "who won", "recipe for", "how to cook",
        # System/meta questions about the bot itself
        "what model", "which llm", "what language model",
        "how many parameters", "what's your provider",
    ]

    _OOS_PHRASES_EXACT = [
        "current time", "current date", "what time is it",
        "what's the date", "what day is it", "today's date",
        "what is the time", "what is the date",
        "which day is today", "what day is today",
        "what's today's date", "tell me the time",
        "tell me the date", "what time is it now",
    ]

    @staticmethod
    def _is_out_of_scope(question: str) -> str | None:
        """
        Check if the question is out of scope for the loaded data.
        Returns a response string if out-of-scope, None if in-scope.
        """
        ql = question.lower().strip()

        # Check exact phrases first
        for phrase in ChatEngine._OOS_PHRASES_EXACT:
            if phrase in ql:
                return (
                    f"I don't have access to that information. My knowledge is limited to "
                    f"the military intelligence data currently loaded in Elasticsearch. "
                    f"I can't answer questions about {phrase.replace('what ', '').replace('is the ', '')} "
                    f"or other topics outside that dataset. Try asking about formations, "
                    f"equipment, infrastructure, locations, or activities in the data."
                )

        # Check keyword list
        for kw in ChatEngine._OOS_KEYWORDS:
            if kw in ql:
                return (
                    f"That question is outside the scope of the loaded data. "
                    f"I can only answer questions about the military intelligence records "
                    f"currently in Elasticsearch — things like formations, equipment types, "
                    f"infrastructure development, locations, activities, and dispositions. "
                    f"Please rephrase your question to relate to the available data."
                )

        return None

    # Field name mapping: keyword in question → ES field to aggregate on
    _AGG_FIELD_MAP = [
        # (search terms, es_field)
        (["location", "locations", "places", "areas", "where"], "location_name.keyword"),
        (["formation", "formations", "enemy formation", "enemy formations"], "enemy_formation_name.keyword"),
        (["status", "disposition", "disposition status"], "disposition_status.keyword"),
        (["infra", "infrastructure", "infra type", "infrastructure type"], "infra_type.keyword"),
        (["equipment type", "equipment types"], "equipment_type.keyword"),
        (["equipment", "equipment name"], "equipment_name.keyword"),
        (["activity type", "activity types", "activities"], "activity_type.keyword"),
        (["activity", "activities"], "activity_type.keyword"),
        (["training type"], "training_type.keyword"),
        (["training"], "training_name.keyword"),
        (["general area", "general areas"], "general_area.keyword"),
    ]

    @staticmethod
    def _classify_intent(question: str) -> tuple[str, str | None, int | None]:
        """
        Classify the question intent without LLM.
        Returns: (intent_type, agg_field, top_n)
        """
        ql = question.lower()

        for kw in ChatEngine._TOP_N_KEYWORDS:
            if kw in ql:
                field = ChatEngine._resolve_agg_field(ql)
                top_n = 5
                import re as _re
                m = _re.search(r"top\s+(\d+)", ql)
                if m:
                    top_n = int(m.group(1))
                return ("TOP_N", field, top_n)

        for kw in ChatEngine._COUNT_KEYWORDS:
            if kw in ql:
                field = ChatEngine._resolve_agg_field(ql)
                return ("COUNT", field, None)

        for kw in ChatEngine._GROUP_BY_KEYWORDS:
            if kw in ql:
                field = ChatEngine._resolve_agg_field(ql)
                return ("GROUP_BY", field, None)

        for kw in ChatEngine._LIST_UNIQUE_KEYWORDS:
            if kw in ql:
                field = ChatEngine._resolve_agg_field(ql)
                return ("LIST_UNIQUE", field, None)

        # Check regex patterns for LIST_UNIQUE
        import re as _re
        for pattern in ChatEngine._LIST_UNIQUE_REGEX:
            if _re.search(pattern, ql):
                field = ChatEngine._resolve_agg_field(ql)
                return ("LIST_UNIQUE", field, None)

        return ("DETAIL", None, None)

    @staticmethod
    def _resolve_agg_field(question_lower: str) -> str | None:
        """Map question keywords to an ES aggregation field."""
        ql = question_lower
        for search_terms, es_field in ChatEngine._AGG_FIELD_MAP:
            if any(term in ql for term in search_terms):
                return es_field
        return None

    # ── Temporal Parser ─────────────────────────────────────────────

    # Month name mapping
    _MONTHS = {
        "january": 1, "jan": 1, "february": 2, "feb": 2, "march": 3, "mar": 3,
        "april": 4, "apr": 4, "may": 5, "june": 6, "jun": 6,
        "july": 7, "jl": 7, "jul": 7, "august": 8, "aug": 8,
        "september": 9, "sep": 9, "sept": 9, "october": 10, "oct": 10,
        "november": 11, "nov": 11, "december": 12, "dec": 12,
    }

    _WORD_NUMS = {
        "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
        "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
        "eleven": 11, "twelve": 12, "couple": 2, "few": 3,
        "several": 5, "many": 10, "half": 0.5,
    }

    _ORDINAL_RE = re.compile(r"(\d{1,2})(?:st|nd|rd|th)")

    @staticmethod
    def _parse_num(val: str) -> float | None:
        """Parse a number from digit string or word."""
        try:
            return float(val)
        except ValueError:
            return ChatEngine._WORD_NUMS.get(val.lower())

    @staticmethod
    def _parse_date_range(question: str) -> dict | None:
        """
        Extract date range from natural language question.
        Returns {"gte": "YYYY-MM-DD", "lte": "YYYY-MM-DD"} or None.
        """
        ql = question.lower().strip()
        now = datetime.now()

        # Helper: resolve a month+year to first/last day
        def month_range(month_str, year=None):
            m = ChatEngine._MONTHS.get(month_str.lower())
            if not m:
                return None, None
            y = year if year else now.year
            from calendar import monthrange
            last_day = monthrange(y, m)[1]
            return f"{y:04d}-{m:02d}-01", f"{y:04d}-{m:02d}-{last_day:02d}"

        def year_range(year_str):
            y = int(year_str)
            return f"{y:04d}-01-01", f"{y:04d}-12-31"

        # ── Absolute date patterns ──

        # "from DD MMM YYYY to DD MMM YYYY" / "from 12 Aug 2024 to 18 Sep 2024"
        # Also: "from 12th of Aug 2024 to 18th of September 2024"
        m = re.search(
            r"(?:from|between)\s+(\d{1,2})(?:st|nd|rd|th)?\s+(?:of\s+)?([a-z]+)\s+(\d{4})\s+(?:to|and|through|-)\s+(\d{1,2})(?:st|nd|rd|th)?\s+(?:of\s+)?([a-z]+)\s+(\d{4})",
            ql)
        if m:
            d1, m1, y1, d2, m2, y2 = m.group(1), m.group(2), int(m.group(3)), m.group(4), m.group(5), int(m.group(6))
            try:
                dt1 = datetime(y1, ChatEngine._MONTHS[m1.lower()], int(d1))
                dt2 = datetime(y2, ChatEngine._MONTHS[m2.lower()], int(d2))
                return {"gte": dt1.strftime("%Y-%m-%d"), "lte": dt2.strftime("%Y-%m-%d")}
            except (ValueError, KeyError):
                pass

        # "from DD MMM to DD MMM" (no year, assume current) / "from 12th of Aug to 18th of September"
        m = re.search(
            r"(?:from|between)\s+(\d{1,2})(?:st|nd|rd|th)?\s+(?:of\s+)?([a-z]+)\s+(?:to|and|through|-)\s+(\d{1,2})(?:st|nd|rd|th)?\s+(?:of\s+)?([a-z]+)(?:\s+(\d{4}))?",
            ql)
        if m:
            d1, m1, d2, m2 = int(m.group(1)), m.group(2), int(m.group(3)), m.group(4)
            year_str = m.group(5)
            try:
                mon1 = ChatEngine._MONTHS[m1.lower()]
                mon2 = ChatEngine._MONTHS[m2.lower()]
                y = int(year_str) if year_str else now.year
                dt1 = datetime(y, mon1, d1)
                dt2 = datetime(y, mon2, d2)
                return {"gte": dt1.strftime("%Y-%m-%d"), "lte": dt2.strftime("%Y-%m-%d")}
            except (ValueError, KeyError):
                pass

        # "from DD-MMM-YYYY to DD-MMM-YYYY" / "from 01-03-2024 to 15-04-2024"
        m = re.search(r"(?:from|between)\s+(\d{1,2})[/-](\d{1,2}|[a-z]+)[/-](\d{4})\s+(?:to|and|through|-)\s+(\d{1,2})[/-](\d{1,2}|[a-z]+)[/-](\d{4})", ql)
        if m:
            try:
                parts = [m.group(i) for i in range(1, 7)]
                # Try to parse as DD-MM-YYYY or DD-mon-YYYY
                d1_str, m1_str, y1_str, d2_str, m2_str, y2_str = parts
                y1, y2 = int(y1_str), int(y2_str)
                # Month could be numeric or name
                try:
                    m1 = int(m1_str)
                except ValueError:
                    m1 = ChatEngine._MONTHS.get(m.lower(), 1)
                try:
                    m2 = int(m2_str)
                except ValueError:
                    m2 = ChatEngine._MONTHS.get(m2.lower(), 1)
                dt1 = datetime(y1, m1, int(d1_str))
                dt2 = datetime(y2, m2, int(d2_str))
                return {"gte": dt1.strftime("%Y-%m-%d"), "lte": dt2.strftime("%Y-%m-%d")}
            except (ValueError, KeyError):
                pass

        # "from MMM YYYY to MMM YYYY" / "from March 2024 to May 2024"
        m = re.search(r"(?:from|between)\s+([a-z]+)\s+(\d{4})\s+(?:to|and|through|-)\s+([a-z]+)\s+(\d{4})", ql)
        if m:
            m1_str, y1_str, m2_str, y2_str = m.group(1), m.group(2), m.group(3), m.group(4)
            try:
                m1 = ChatEngine._MONTHS[m1_str.lower()]
                m2 = ChatEngine._MONTHS[m2_str.lower()]
                y1, y2 = int(y1_str), int(y2_str)
                return {"gte": f"{y1:04d}-{m1:02d}-01", "lte": f"{y2:04d}-{m2:02d}-28"}
            except KeyError:
                pass

        # "from MMM to MMM" (assume current year) / "from June to August"
        m = re.search(r"(?:from|between)\s+([a-z]+)\s+(?:to|and|through|-)\s+([a-z]+)(?:\s+(\d{4}))?", ql)
        if m:
            m1_str, m2_str = m.group(1), m.group(2)
            year_str = m.group(3)
            try:
                m1 = ChatEngine._MONTHS[m1_str.lower()]
                m2 = ChatEngine._MONTHS[m2_str.lower()]
                y = int(year_str) if year_str else now.year
                return {"gte": f"{y:04d}-{m1:02d}-01", "lte": f"{y:04d}-{m2:02d}-28"}
            except KeyError:
                pass

        # "YYYY-YYYY" / "2019-2022" / "between 2021 and 2023"
        m = re.search(r"(?:from|between)\s+(\d{4})\s+(?:to|and|through|-)\s+(\d{4})", ql)
        if m:
            y1, y2 = int(m.group(1)), int(m.group(2))
            return {"gte": f"{y1:04d}-01-01", "lte": f"{y2:04d}-12-31"}

        # "in YYYY" / "during YYYY" / "only YYYY"
        m = re.search(r"(?:in|during|only|for|year)\s+(\d{4})\b", ql)
        if m:
            y = int(m.group(1))
            return {"gte": f"{y:04d}-01-01", "lte": f"{y:04d}-12-31"}

        # "on DD MMM YYYY" / "on 12th of Aug 2025" / "on 16th January"
        m = re.search(r"(?:on|dated)\s+(?:the\s+)?(\d{1,2})(?:st|nd|rd|th)?\s+(?:of\s+)?([a-z]+)(?:\s+(\d{4}))?", ql)
        if m:
            d = int(m.group(1))
            mon_str = m.group(2)
            y_str = m.group(3)
            try:
                mon = ChatEngine._MONTHS[mon_str.lower()]
                y = int(y_str) if y_str else now.year
                return {"gte": f"{y:04d}-{mon:02d}-{d:02d}", "lte": f"{y:04d}-{mon:02d}-{d:02d}"}
            except KeyError:
                pass

        # "since DD MMM YYYY" / "since 12 Aug 2024"
        m = re.search(r"since\s+(?:the\s+)?(\d{1,2})(?:st|nd|rd|th)?\s+(?:of\s+)?([a-z]+)(?:\s+(\d{4}))?", ql)
        if m:
            d = int(m.group(1))
            mon_str = m.group(2)
            y_str = m.group(3)
            try:
                mon = ChatEngine._MONTHS[mon_str.lower()]
                y = int(y_str) if y_str else now.year
                return {"gte": f"{y:04d}-{mon:02d}-{d:02d}", "lte": "now"}
            except KeyError:
                pass

        # ── Quarter patterns ──
        # "Qn YYYY" / "quarter N of YYYY" / "Nth quarter YYYY" / "3rd quarter 2023"
        m = re.search(r"(?:q|quarter)\s*([1-4])\s*(?:of\s+)?(\d{4})", ql)
        if m:
            q, y = int(m.group(1)), int(m.group(2))
            q_start = {1: "01-01", 2: "04-01", 3: "07-01", 4: "10-01"}[q]
            q_end = {1: "03-31", 2: "06-30", 3: "09-30", 4: "12-31"}[q]
            return {"gte": f"{y:04d}-{q_start}", "lte": f"{y:04d}-{q_end}"}

        # "Nth quarter YYYY" / "3rd quarter 2023" (ordinal before quarter)
        m = re.search(r"(\d+)(?:st|nd|rd|th)\s+quarter\s+(?:of\s+)?(\d{4})", ql)
        if m:
            q, y = int(m.group(1)), int(m.group(2))
            if 1 <= q <= 4:
                q_start = {1: "01-01", 2: "04-01", 3: "07-01", 4: "10-01"}[q]
                q_end = {1: "03-31", 2: "06-30", 3: "09-30", 4: "12-31"}[q]
                return {"gte": f"{y:04d}-{q_start}", "lte": f"{y:04d}-{q_end}"}

        if "this quarter" in ql:
            q = (now.month - 1) // 3 + 1
            y = now.year
            q_start = {1: "01-01", 2: "04-01", 3: "07-01", 4: "10-01"}[q]
            q_end = {1: "03-31", 2: "06-30", 3: "09-30", 4: "12-31"}[q]
            return {"gte": f"{y:04d}-{q_start}", "lte": f"{y:04d}-{q_end}"}

        if "last quarter" in ql:
            q = (now.month - 1) // 3
            y = now.year
            if q == 0:
                q = 4
                y -= 1
            q_start = {1: "01-01", 2: "04-01", 3: "07-01", 4: "10-01"}[q]
            q_end = {1: "03-31", 2: "06-30", 3: "09-30", 4: "12-31"}[q]
            return {"gte": f"{y:04d}-{q_start}", "lte": f"{y:04d}-{q_end}"}

        # ── Relative date patterns ──

        # "since last X days/weeks/months/years" — supports word numbers like "six"
        m = re.search(r"since\s+(?:last|past|previous|prior)\s+(\d+|[a-z]+)?\s*(day|days|week|weeks|month|months|year|years|fortnight|half\s+year)", ql)
        if m:
            num = ChatEngine._parse_num(m.group(1)) if m.group(1) else 1
            if num is not None:
                unit = m.group(2).replace(" ", "")
                delta = {
                    "day": timedelta(days=num), "days": timedelta(days=num),
                    "week": timedelta(weeks=num), "weeks": timedelta(weeks=num),
                    "fortnight": timedelta(weeks=2 * num),
                    "month": timedelta(days=30 * num), "months": timedelta(days=30 * num),
                    "halfyear": timedelta(days=180 * num),
                    "year": timedelta(days=365 * num), "years": timedelta(days=365 * num),
                }.get(unit, timedelta(days=30 * num))
                gte = (now - delta).strftime("%Y-%m-%d")
                return {"gte": gte, "lte": "now"}

        # "last X days/weeks/months/years" (without "since") — supports word numbers
        m = re.search(r"(?:last|past|previous|prior)\s+(\d+|[a-z]+)?\s*(day|days|week|weeks|month|months|year|years|fortnight|half\s+year|quarter|quarters|couple\s+(?:of\s+)?(?:weeks|months|days))", ql)
        if m:
            num = ChatEngine._parse_num(m.group(1)) if m.group(1) else 1
            if num is None:
                num = 1
            unit = m.group(2).replace(" ", "")
            if "couple" in unit:
                num = 2
                unit = unit.replace("coupleof", "").replace("couple", "")
            delta = {
                "day": timedelta(days=num), "days": timedelta(days=num),
                "week": timedelta(weeks=num), "weeks": timedelta(weeks=num),
                "fortnight": timedelta(weeks=2 * num),
                "month": timedelta(days=30 * num), "months": timedelta(days=30 * num),
                "halfyear": timedelta(days=180 * num),
                "year": timedelta(days=365 * num), "years": timedelta(days=365 * num),
                "quarter": timedelta(days=90 * num), "quarters": timedelta(days=90 * num),
            }.get(unit, timedelta(days=30 * num))
            gte = (now - delta).strftime("%Y-%m-%d")
            return {"gte": gte, "lte": "now"}

        # "past X days/weeks/months/years" — supports word numbers
        m = re.search(r"past\s+(\d+|[a-z]+)?\s*(day|days|week|weeks|month|months|year|years)", ql)
        if m:
            num = ChatEngine._parse_num(m.group(1)) if m.group(1) else 1
            if num is None:
                num = 1
            unit = m.group(2)
            delta = {
                "day": timedelta(days=num), "days": timedelta(days=num),
                "week": timedelta(weeks=num), "weeks": timedelta(weeks=num),
                "month": timedelta(days=30 * num), "months": timedelta(days=30 * num),
                "year": timedelta(days=365 * num), "years": timedelta(days=365 * num),
            }.get(unit, timedelta(days=30 * num))
            gte = (now - delta).strftime("%Y-%m-%d")
            return {"gte": gte, "lte": "now"}

        # "next X days/weeks/months/years" / "coming X days" / "upcoming X weeks" — supports word numbers
        m = re.search(r"(?:next|coming|upcoming)\s+(\d+|[a-z]+)?\s*(day|days|week|weeks|month|months|year|years|couple\s+(?:of\s+)?(?:weeks|months|days))", ql)
        if m:
            num = ChatEngine._parse_num(m.group(1)) if m.group(1) else 1
            if num is None:
                num = 1
            unit = m.group(2).replace(" ", "")
            if "couple" in unit:
                num = 2
                unit = unit.replace("coupleof", "").replace("couple", "")
            delta = {
                "day": timedelta(days=num), "days": timedelta(days=num),
                "week": timedelta(weeks=num), "weeks": timedelta(weeks=num),
                "month": timedelta(days=30 * num), "months": timedelta(days=30 * num),
                "year": timedelta(days=365 * num), "years": timedelta(days=365 * num),
            }.get(unit, timedelta(days=30 * num))
            gte = now.strftime("%Y-%m-%d")
            lte = (now + delta).strftime("%Y-%m-%d")
            return {"gte": gte, "lte": lte}

        # "today"
        if re.search(r"\btoday\b", ql):
            return {"gte": now.strftime("%Y-%m-%d"), "lte": now.strftime("%Y-%m-%d")}

        # "yesterday"
        if re.search(r"\byesterday\b", ql):
            yest = now - timedelta(days=1)
            return {"gte": yest.strftime("%Y-%m-%d"), "lte": yest.strftime("%Y-%m-%d")}

        # "this month" / "this year" / "this week"
        if "this month" in ql:
            return {"gte": f"{now.year:04d}-{now.month:02d}-01", "lte": "now"}
        if "this year" in ql or "ytd" in ql:
            return {"gte": f"{now.year:04d}-01-01", "lte": "now"}
        if "this week" in ql or "wtd" in ql:
            monday = now - timedelta(days=now.weekday())
            return {"gte": monday.strftime("%Y-%m-%d"), "lte": "now"}
        if "mtd" in ql:
            return {"gte": f"{now.year:04d}-{now.month:02d}-01", "lte": "now"}
        if "qtd" in ql:
            q = (now.month - 1) // 3 + 1
            q_start = {1: "01-01", 2: "04-01", 3: "07-01", 4: "10-01"}[q]
            return {"gte": f"{now.year:04d}-{q_start}", "lte": "now"}

        # "last month" / "last year" / "last week"
        if "last month" in ql:
            first_of_month = now.replace(day=1)
            last_month_end = first_of_month - timedelta(days=1)
            last_month_start = last_month_end.replace(day=1)
            return {"gte": last_month_start.strftime("%Y-%m-%d"), "lte": last_month_end.strftime("%Y-%m-%d")}
        if "last year" in ql:
            return {"gte": f"{now.year - 1:04d}-01-01", "lte": f"{now.year - 1:04d}-12-31"}
        if "last week" in ql:
            monday = now - timedelta(days=now.weekday() + 7)
            sunday = monday + timedelta(days=6)
            return {"gte": monday.strftime("%Y-%m-%d"), "lte": sunday.strftime("%Y-%m-%d")}

        # "next month" / "next year" / "next week"
        if "next month" in ql:
            if now.month == 12:
                nm = now.replace(year=now.year + 1, month=1, day=1)
            else:
                nm = now.replace(month=now.month + 1, day=1)
            from calendar import monthrange
            last = monthrange(nm.year, nm.month)[1]
            return {"gte": nm.strftime("%Y-%m-%d"), "lte": f"{nm.year:04d}-{nm.month:02d}-{last:02d}"}
        if "next year" in ql:
            return {"gte": f"{now.year + 1:04d}-01-01", "lte": f"{now.year + 1:04d}-12-31"}
        if "next week" in ql:
            monday = now - timedelta(days=now.weekday() - 7)
            sunday = monday + timedelta(days=6)
            return {"gte": monday.strftime("%Y-%m-%d"), "lte": sunday.strftime("%Y-%m-%d")}

        # "this weekend" / "last weekend" / "next weekend"
        if "this weekend" in ql:
            saturday = now + timedelta(days=(5 - now.weekday()) % 7)
            return {"gte": saturday.strftime("%Y-%m-%d"), "lte": (saturday + timedelta(days=1)).strftime("%Y-%m-%d")}
        if "last weekend" in ql:
            saturday = now - timedelta(days=now.weekday() + 2)
            return {"gte": saturday.strftime("%Y-%m-%d"), "lte": (saturday + timedelta(days=1)).strftime("%Y-%m-%d")}
        if "next weekend" in ql:
            saturday = now + timedelta(days=(5 - now.weekday()) % 7 + 7)
            return {"gte": saturday.strftime("%Y-%m-%d"), "lte": (saturday + timedelta(days=1)).strftime("%Y-%m-%d")}

        # "since Monday" / "since Tuesday" etc.
        m = re.search(r"since\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday)", ql)
        if m:
            day_name = m.group(1)
            days = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
            target_day = days.index(day_name)
            days_since = (now.weekday() - target_day) % 7
            if days_since == 0:
                days_since = 7  # last occurrence
            gte = (now - timedelta(days=days_since)).strftime("%Y-%m-%d")
            return {"gte": gte, "lte": "now"}

        # "MMM YYYY" standalone / "march 2025" / "apr 2026"
        m = re.search(r"\b([a-z]{3,})\s+(\d{4})\b", ql)
        if m:
            mon_str, y_str = m.group(1), m.group(2)
            mon = ChatEngine._MONTHS.get(mon_str.lower())
            if mon:
                y = int(y_str)
                from calendar import monthrange
                last_day = monthrange(y, mon)[1]
                return {"gte": f"{y:04d}-{mon:02d}-01", "lte": f"{y:04d}-{mon:02d}-{last_day:02d}"}

        # "till now" / "till date" / "to date" / "until now"
        m = re.search(r"(?:till\s+now|till\s+date|to\s+date|until\s+now)(?:\s+for\s+([a-z]+)\s+(\d{4}))?", ql)
        if m:
            if m.group(1):
                mon = ChatEngine._MONTHS.get(m.group(1).lower())
                y = int(m.group(2))
                if mon:
                    return {"gte": f"{y:04d}-{mon:02d}-01", "lte": "now"}
            return {"gte": "2020-01-01", "lte": "now"}

        # "monday to friday" / "tuesday through thursday"
        m = re.search(r"(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\s+(?:to|through)\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday)", ql)
        if m:
            days = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
            d1, d2 = days.index(m.group(1)), days.index(m.group(2))
            # Find most recent occurrence
            today = now.weekday()
            if d1 <= today:
                start = now - timedelta(days=today - d1)
            else:
                start = now - timedelta(days=today + 7 - d1)
            end = start + timedelta(days=(d2 - d1) % 7)
            return {"gte": start.strftime("%Y-%m-%d"), "lte": end.strftime("%Y-%m-%d")}

        # "tomorrow"
        if re.search(r"\btomorrow\b", ql):
            tmr = now + timedelta(days=1)
            return {"gte": tmr.strftime("%Y-%m-%d"), "lte": tmr.strftime("%Y-%m-%d")}

        # "next quarter"
        if "next quarter" in ql:
            q = (now.month - 1) // 3 + 2
            y = now.year
            if q > 4:
                q -= 4
                y += 1
            q_start = {1: "01-01", 2: "04-01", 3: "07-01", 4: "10-01"}[q]
            q_end = {1: "03-31", 2: "06-30", 3: "09-30", 4: "12-31"}[q]
            return {"gte": f"{y:04d}-{q_start}", "lte": f"{y:04d}-{q_end}"}

        # "since MMM" (month name only, assume current year)
        m = re.search(r"since\s+([a-z]+)(?:\s+(\d{4}))?", ql)
        if m:
            mon = ChatEngine._MONTHS.get(m.group(1).lower())
            if mon:
                y = int(m.group(2)) if m.group(2) else now.year
                return {"gte": f"{y:04d}-{mon:02d}-01", "lte": "now"}

        # "YYYY-YYYY" bare year range (no from/between)
        m = re.search(r"\b(\d{4})\s*-\s*(\d{4})\b", ql)
        if m:
            y1, y2 = int(m.group(1)), int(m.group(2))
            return {"gte": f"{y1:04d}-01-01", "lte": f"{y2:04d}-12-31"}

        # "between DD.MM.YYYY and DD.MM.YYYY" / dotted date format
        m = re.search(r"(?:from|between)\s+(\d{1,2})\.(\d{1,2})\.(\d{4})\s+(?:to|and|-)\s+(\d{1,2})\.(\d{1,2})\.(\d{4})", ql)
        if m:
            try:
                dt1 = datetime(int(m.group(3)), int(m.group(2)), int(m.group(1)))
                dt2 = datetime(int(m.group(6)), int(m.group(5)), int(m.group(4)))
                return {"gte": dt1.strftime("%Y-%m-%d"), "lte": dt2.strftime("%Y-%m-%d")}
            except ValueError:
                pass

        # "dated YYYY-MM-DD" / ISO date
        m = re.search(r"(?:dated|on|from)\s+(\d{4})-(\d{2})-(\d{2})", ql)
        if m:
            try:
                dt = datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)))
                return {"gte": dt.strftime("%Y-%m-%d"), "lte": dt.strftime("%Y-%m-%d")}
            except ValueError:
                pass

        # "MMM to MMM" (bare month range, no year — assume current year)
        m = re.search(r"\b([a-z]{3,})\s+to\s+([a-z]{3,})\b", ql)
        if m:
            m1 = ChatEngine._MONTHS.get(m.group(1).lower())
            m2 = ChatEngine._MONTHS.get(m.group(2).lower())
            if m1 and m2:
                return {"gte": f"{now.year:04d}-{m1:02d}-01", "lte": f"{now.year:04d}-{m2:02d}-28"}

        return None

    # ── Spatial Parser ───────────────────────────────────────────────

    _DISTANCE_RE = re.compile(
        r"(?:within|inside|radius|buffer|near|around|scan|search|look|check|detect|identify|plot|draw|connect|enable|avoid|plan|find|list|note|show)\s+(?:a\s+)?(?:~(\s+)?)?(\d+(?:\.\d+)?)\s*(km|kilomet(?:er|re)s?|m|met(?:er|re)s?|mi|miles?)\b",
        re.IGNORECASE,
    )
    _BETWEEN_RE = re.compile(
        r"(?:between|from|connect(?:ing)?|route|path|corridor|track|directions?)\s+(.+?)\s+(?:and|to|through)\s+(.+?)(?:\s+within\s+(\d+(?:\.\d+)?)\s*(km|kilomet(?:er|re)s?|m|met(?:er|re)s?|mi|miles?))?",
        re.IGNORECASE,
    )
    _NEAR_RE = re.compile(
        r"(?:near|around|close\s+to|in\s+the\s+(?:general\s+)?area\s+of|opposite|gen(?:eral)?\s+area)\s+(.+?)(?:\s+within\s+(\d+(?:\.\d+)?)\s*(km|kilomet(?:er|re)s?|m|met(?:er|re)s?|mi|miles?))?",
        re.IGNORECASE,
    )

    @staticmethod
    def _parse_spatial(question: str) -> dict | None:
        """
        Extract spatial constraints from question.
        Returns a dict with spatial params or None.
        """
        ql = question.lower().strip()
        result = {}

        # Distance/radius patterns: "within 5 km", "radius 2km", "15 km near X"
        m = ChatEngine._DISTANCE_RE.search(ql)
        if m:
            dist_val = float(m.group(2))
            unit = m.group(3).lower()
            if unit in ("km", "kilometer", "kilometre", "kilometers", "kilometres"):
                result["distance_km"] = dist_val
            elif unit in ("m", "meter", "metre", "meters", "metres"):
                result["distance_km"] = dist_val / 1000
            elif unit in ("mi", "mile", "miles"):
                result["distance_km"] = dist_val * 1.60934

        # Between A and B patterns
        m = ChatEngine._BETWEEN_RE.search(ql)
        if m:
            result["between"] = {
                "point_a": m.group(1).strip(),
                "point_b": m.group(2).strip(),
            }
            if m.group(3):
                dist_val = float(m.group(3))
                unit = m.group(4).lower() if m.group(4) else "km"
                if unit in ("m", "meter", "metre"):
                    dist_val /= 1000
                elif unit in ("mi", "mile", "miles"):
                    dist_val *= 1.60934
                result["between"]["distance_km"] = dist_val

        # Near X patterns
        m = ChatEngine._NEAR_RE.search(ql)
        if m:
            result["near"] = {"location": m.group(1).strip()}
            if m.group(2):
                dist_val = float(m.group(2))
                unit = m.group(3).lower() if m.group(3) else "km"
                if unit in ("m", "meter", "metre"):
                    dist_val /= 1000
                result["near"]["distance_km"] = dist_val

        return result if result else None

    # ── Formation / Equipment keyword detection ─────────────────────

    _FORMATION_KEYWORDS = [
        "formation", "formations", "brigade", "bde", "regiment", "reg",
        "battalion", "bn", "division", "div", "corps", "command", "comd",
        "cab", "cc", "cad", "armd", "inf", "armd bde", "inf bde",
        "armored", "armoured", "artillery", "arty", "aviation", "avn",
        "signal", "engineer", "supply", "medical", "med",
        "lt car", "hy cab", "lt cab", "heavy cab", "light car",
        "combined arms", "cbt", "sof", "tmd",
    ]

    _EQUIPMENT_KEYWORDS = [
        "equipment", "equipments", "eqpt", "eqpts", "weapon", "weapons",
        "radar", "drone", "uav", "tank", "tanks", "aircraft", "helicopter",
        "helo", "missile", "sam", "howitzer", "gun", "guns",
        "vehicle", "vehicles", "apc", "ifv", "mlrs", "rocket",
        "communication tower", "surveillance", "camera", "sensor",
        "bridge", "helipad", "airfield", "airbase", "runway",
        "dugout", "trench", "bunker", "shelter", "barricade",
        "power plant", "dam", "canal", "pipeline", "pipeline",
        "nuclear", "gas field", "oil field", "mine", "ammunition", "amn",
        "ammo dump", "storage", "depot", "garrison", "camp", "base",
        "hq", "headquarters", "post", "outpost", "checkpoint",
    ]

    @staticmethod
    def _detect_formation_intent(question: str) -> bool:
        """Check if question is about military formations/units."""
        ql = question.lower()
        return any(kw in ql for kw in ChatEngine._FORMATION_KEYWORDS)

    @staticmethod
    def _detect_equipment_intent(question: str) -> bool:
        """Check if question is about equipment/infrastructure."""
        ql = question.lower()
        return any(kw in ql for kw in ChatEngine._EQUIPMENT_KEYWORDS)

    def _build_base_query(self) -> dict:
        """Build the full base query (category + date) from the current session.
        Returns the complete query dict that mimics what was used during fetch."""
        query: dict = {"bool": {"must": [], "filter": [], "must_not": [], "should": []}}

        if self.store.category and self.store.category in CATEGORY_QUERIES:
            cat_q = CATEGORY_QUERIES[self.store.category]["query"]
            if "bool" in cat_q:
                b = cat_q["bool"]
                if b.get("must"):
                    query["bool"]["must"].extend(deepcopy(b["must"]))
                if b.get("must_not"):
                    query["bool"]["must_not"].extend(deepcopy(b["must_not"]))
                if b.get("filter"):
                    query["bool"]["filter"].extend(deepcopy(b["filter"]))
                if b.get("should"):
                    query["bool"]["should"].extend(deepcopy(b["should"]))
                if b.get("minimum_should_match"):
                    query["bool"]["minimum_should_match"] = b["minimum_should_match"]
        if self.store.date_range:
            dr = self.store.date_range
            spec = {}
            if dr.get("from"):
                spec["gte"] = dr["from"]
            if dr.get("to"):
                spec["lte"] = dr["to"]
            if spec:
                query["bool"]["filter"].append({"range": {"@timestamp": spec}})

        # Clean up empty keys
        for key in ["must", "filter", "must_not", "should"]:
            if not query["bool"][key]:
                del query["bool"][key]
        if not query["bool"]:
            query = {"match_all": {}}

        return query

    def _build_base_filters(self) -> list[dict]:
        """Legacy: build filter list from session. Use _build_base_query() instead."""
        filters: list[dict] = []
        if self.store.category and self.store.category in CATEGORY_QUERIES:
            cat_q = CATEGORY_QUERIES[self.store.category]["query"]
            if "bool" in cat_q:
                if "must_not" in cat_q["bool"]:
                    filters.append({"bool": {"must_not": cat_q["bool"]["must_not"]}})
                if "filter" in cat_q["bool"]:
                    filters.extend(cat_q["bool"]["filter"])
                for clause in cat_q["bool"].get("must", []):
                    if "exists" in clause or "terms" in clause:
                        filters.append(clause)
        if self.store.date_range:
            dr = self.store.date_range
            spec = {}
            if dr.get("from"):
                spec["gte"] = dr["from"]
            if dr.get("to"):
                spec["lte"] = dr["to"]
            if spec:
                filters.append({"range": {"@timestamp": spec}})
        return filters

    def _build_agg_query(
        self,
        question: str,
        agg_field: str | None,
        intent_type: str,
        top_n: int | None = None,
        max_buckets: int = 200,
    ) -> dict:
        """Build an ES aggregation query scoped to the session's loaded data."""
        # Build the category filter using the original category query structure
        # but wrapped in filter context for better performance (no scoring)
        filter_clauses: list[dict] = []

        if self.store.category and self.store.category in CATEGORY_QUERIES:
            cat_q = CATEGORY_QUERIES[self.store.category]["query"]
            if "bool" in cat_q:
                b = cat_q["bool"]
                # Reconstruct the full bool query inside filter context
                inner: dict = {}
                if b.get("must"):
                    inner["must"] = deepcopy(b["must"])
                if b.get("must_not"):
                    inner["must_not"] = deepcopy(b["must_not"])
                if b.get("filter"):
                    inner["filter"] = deepcopy(b["filter"])
                if b.get("should"):
                    inner["should"] = deepcopy(b["should"])
                if b.get("minimum_should_match") is not None:
                    inner["minimum_should_match"] = b["minimum_should_match"]
                if inner:
                    filter_clauses.append({"bool": inner})

        if self.store.date_range:
            dr = self.store.date_range
            spec = {}
            if dr.get("from"):
                spec["gte"] = dr["from"]
            if dr.get("to"):
                spec["lte"] = dr["to"]
            if spec:
                filter_clauses.append({"range": {"@timestamp": spec}})

        # Temporal filter from question text
        date_range = self._parse_date_range(question)
        if date_range:
            filter_clauses.append({"range": {"activity_date": date_range}})

        body: dict = {
            "size": 0,
            "track_total_hits": True,
            "query": {"bool": {"filter": filter_clauses}} if filter_clauses else {"match_all": {}},
            "timeout": "15s",
        }

        if intent_type == "COUNT":
            if agg_field:
                body["aggs"] = {
                    "unique_count": {"cardinality": {"field": agg_field, "precision_threshold": 10000}}
                }
        elif intent_type in ("LIST_UNIQUE", "TOP_N"):
            if agg_field:
                size = top_n if intent_type == "TOP_N" and top_n else max_buckets
                body["aggs"] = {
                    "unique_values": {
                        "terms": {"field": agg_field, "size": size, "order": {"_count": "desc"}},
                    }
                }
            else:
                body["aggs"] = {
                    "unique_values": {
                        "terms": {"field": "description_hash.keyword", "size": max_buckets},
                    }
                }
        elif intent_type == "GROUP_BY":
            if agg_field:
                body["aggs"] = {
                    "by_field": {
                        "terms": {"field": agg_field, "size": max_buckets, "order": {"_count": "desc"}},
                        "aggs": {
                            "sample_docs": {
                                "top_hits": {"size": 3, "_source": ["description", "location_name", "general_area"]}
                            }
                        },
                    }
                }

        return body

    def _format_agg_answer(
        self,
        question: str,
        intent_type: str,
        agg_field: str | None,
        total_hits: int,
        es_result: dict,
        top_n: int | None = None,
    ) -> str:
        """Format aggregation results directly into an answer — no LLM needed."""
        # Clean up field name for display
        field_display = agg_field.replace(".keyword", "").replace("_name", "").replace("_", " ") if agg_field else "value"

        if intent_type == "COUNT":
            aggs = es_result.get("aggregations", {})
            if "unique_count" in aggs:
                count = aggs["unique_count"]["value"]
                return f"There are **{count} unique {field_display}s** across {total_hits} total documents."
            else:
                return f"There are **{total_hits} total documents** matching the query."

        elif intent_type in ("LIST_UNIQUE", "TOP_N"):
            aggs = es_result.get("aggregations", {})
            buckets = aggs.get("unique_values", {}).get("buckets", [])
            if not buckets:
                return f"No {field_display} values found in the data."

            # Filter out null-like values for location fields
            if agg_field and "location" in agg_field.lower():
                buckets = [b for b in buckets if not _is_null_location(b.get("key", ""))]
                if not buckets:
                    return f"No meaningful {field_display} values found (all were null/empty)."

            label = f"Top {len(buckets)} {field_display}s" if intent_type == "TOP_N" else f"Unique {field_display}s ({len(buckets)} total)"
            lines = [f"**{label}** (out of {total_hits} documents):\n"]
            for b in buckets:
                key = b.get("key", b.get("key_as_string", "?"))
                cnt = b.get("doc_count", 0)
                lines.append(f"  • {key} ({cnt} docs)")
            return "\n".join(lines)

        elif intent_type == "GROUP_BY":
            aggs = es_result.get("aggregations", {})
            buckets = aggs.get("by_field", {}).get("buckets", [])
            if not buckets:
                return f"No {field_display} values found in the data."

            lines = [f"**Documents grouped by {field_display}** ({total_hits} total):\n"]
            for b in buckets:
                key = b.get("key", b.get("key_as_string", "?"))
                cnt = b.get("doc_count", 0)
                # Include a sample description if available
                sample = b.get("sample_docs", {}).get("hits", {}).get("hits", [])
                sample_desc = ""
                if sample:
                    desc = sample[0].get("_source", {}).get("description", "")
                    if desc:
                        sample_desc = f' — e.g., "{desc[:100]}..."' if len(desc) > 100 else f' — e.g., "{desc}"'
                lines.append(f"  • **{key}**: {cnt} docs{sample_desc}")
            return "\n".join(lines)

        return str(es_result.get("aggregations", {}))

    # ── Ask ───────────────────────────────────────────────────────

    def ask(self, req: ChatRequest, debug: bool = False, mediate: bool = True) -> ChatResponse:
        # ── Session limit check ──
        if self.session.is_full:
            return ChatResponse(
                answer=(
                    f"📋 This chat session has reached its limit of {self.session.max_turns} exchanges.\n\n"
                    f"Session summary: {self.session.summarize_session()}\n\n"
                    "Please start a new chat session to continue. Your previous conversation "
                    "history will be cleared."
                ),
                sources_used=0,
                debug={"mode": "session-full"},
            )

        if not self.store.is_loaded:
            return ChatResponse(answer="No data loaded yet. Fetch data first.", sources_used=0)

        total = self.store.total_hits
        if total == 0:
            return ChatResponse(answer="No data was found for the specified query.", sources_used=0)

        # ── Step 1: Classify intent + parse temporal ──
        intent_type, agg_field, top_n = self._classify_intent(req.question)
        parsed_date_range = self._parse_date_range(req.question)

        if debug:
            print(f"[DEBUG] Intent: {intent_type} | field: {agg_field} | top_n: {top_n} | date_range: {parsed_date_range} | mediate: {mediate} | session: {self.session.turns_used}/{self.session.max_turns}")

        # ── Step 2: Aggregation intent → ES aggs (fast, mediator presents) ──
        if intent_type != "DETAIL" and agg_field:
            resp = self._ask_aggregate(req.question, intent_type, agg_field, top_n, debug)
            if mediate:
                # Pass raw bucket data to mediator so it can format the full list
                raw_aggs = (resp.debug or {}).get("_raw_aggs", {})
                buckets = raw_aggs.get("unique_values", {}).get("buckets", [])
                total_hits = (resp.debug or {}).get("total", 0)
                # Build a compact but complete representation for the mediator
                bucket_lines = [f"{b['key']} ({b['doc_count']} docs)" for b in buckets]
                bucket_text = "\n".join(bucket_lines)
                agg_doc = {
                    "_source": {
                        "description": f"Found {len(buckets)} unique {agg_field.replace('.keyword','').replace('_',' ')}s from {total_hits} documents:\n{bucket_text}",
                        "agg_field": agg_field,
                        "total_hits": total_hits,
                        "buckets": len(buckets),
                    }
                }
                resp = self._apply_mediator(req.question, resp, [agg_doc], debug)
            self.session.add_exchange(req.question, resp.answer, used_rag=False)
            return resp

        # ── Step 3: Mediator decides RAG vs DIRECT ──
        if mediate:
            mediator = self._get_mediator()
            needs_rag = mediator.should_use_rag(req.question, debug=debug)

            if not needs_rag:
                # Build history context for direct answers too
                history_str = self.session.get_history_for_mediator(last_n=5)
                raw_ctx = f"Previous conversation:\n{history_str}" if history_str else None
                answer, meta = mediator.respond(
                    question=req.question,
                    raw_answer=raw_ctx,
                    source_docs=[],
                    debug=debug,
                )
                self.session.add_exchange(req.question, answer, used_rag=False)
                return ChatResponse(
                    answer=answer, sources_used=0,
                    debug={"mode": "direct", "mediator": meta},
                )

        # ── Step 4: RAG pipeline ──
        focused = self.re_retrieve(req.question, size=100)
        if not focused:
            focused = self.store.documents[:50]

        if len(focused) <= MAX_DIRECT:
            resp = self._ask_direct(req.question, focused, total, debug)
        else:
            resp = self._ask_mapreduce(req.question, focused, total, debug)

        # ── Step 5: Mediator presents ──
        if mediate:
            resp = self._apply_mediator(req.question, resp, focused, debug)

        self.session.add_exchange(req.question, resp.answer, used_rag=len(focused) > 0)
        return resp

    def _apply_mediator(
        self,
        question: str,
        resp: ChatResponse,
        source_docs: list[dict],
        debug: bool,
    ) -> ChatResponse:
        """Pass the answer through the mediator agent for final presentation."""
        mediator = self._get_mediator()

        # For aggregation queries with many buckets, chunk the data to avoid
        # context length limits and LLM summarization
        if resp.debug and resp.debug.get("mode", "").startswith("agg-"):
            raw_aggs = (resp.debug or {}).get("_raw_aggs", {})
            buckets = raw_aggs.get("unique_values", {}).get("buckets", [])
            total_hits = (resp.debug or {}).get("total", 0)
            agg_field = (resp.debug or {}).get("field", "")

            if len(buckets) > 50:
                # Chunk the buckets into groups and process each through mediator
                return self._apply_mediator_chunked(
                    question, resp, mediator, buckets, total_hits, agg_field, debug
                )
            # Small enough — return formatted answer directly
            return resp

        # Build conversation history context (last 5 turns)
        history_str = self.session.get_history_for_mediator(last_n=5)

        # Prepend history to the raw answer so mediator has context
        raw_with_context = resp.answer
        if history_str:
            raw_with_context = f"{history_str}\n\n--- Current Question & Pipeline Answer ---\nPipeline answer: {resp.answer}"

        # For RAG queries with retrieved docs, pass them to LLM with explicit
        # instructions to use ONLY the provided data (no hallucination)
        if source_docs and len(source_docs) > 0:
            relevant_text = self._format_docs_for_answer(source_docs[:20])
            if relevant_text:
                # Build a focused prompt that forces LLM to use the data
                data_msg = (
                    f"User question: {question}\n\n"
                    f"CRITICAL: Answer using ONLY the following retrieved documents. "
                    f"Do NOT use your own knowledge. Do NOT say 'no data found'. "
                    f"Extract ALL relevant details: names, locations, dates, numbers, analysis.\n\n"
                    f"RETRIEVED DOCUMENTS:\n{relevant_text}\n\n"
                    f"Provide a thorough, detailed answer based solely on these documents."
                )
                try:
                    llm_resp = mediator.llm.chat.completions.create(
                        model=mediator.model,
                        messages=[
                            {"role": "system", "content": mediator._ANSWER_SYSTEM},
                            {"role": "user", "content": data_msg},
                        ],
                        max_tokens=8000,
                        timeout=mediator.timeout,
                    )
                    final_answer = llm_resp.choices[0].message.content.strip()
                    # Strip artifacts
                    import re as _re
                    final_answer = _re.sub(r"<think>[\s\S]*?</think>", "", final_answer)
                    final_answer = _re.sub(r"</?think>", "", final_answer)
                    final_answer = final_answer.strip()
                    if final_answer:
                        new_debug = resp.debug or {}
                        new_debug["mediator"] = {"mediator": "active", "source": "llm_with_docs"}
                        return ChatResponse(
                            answer=final_answer,
                            sources_used=resp.sources_used,
                            debug=new_debug,
                        )
                except Exception as e:
                    if debug:
                        print(f"[MEDIATOR] LLM failed: {e}")
                    # Fallback to direct doc formatting

                # Fallback: return formatted docs directly
                new_debug = resp.debug or {}
                new_debug["mediator"] = {"mediator": "active", "source": "direct_from_docs_fallback"}
                return ChatResponse(
                    answer=relevant_text,
                    sources_used=resp.sources_used,
                    debug=new_debug,
                )

        # For direct/conversational questions without retrieved docs, use LLM
        final_answer, meta = mediator.respond(
            question=question,
            raw_answer=raw_with_context,
            source_docs=source_docs,
            debug=debug,
        )
        new_debug = resp.debug or {}
        new_debug["mediator"] = meta
        return ChatResponse(
            answer=final_answer,
            sources_used=resp.sources_used,
            debug=new_debug,
        )

    def _apply_mediator_chunked(
        self,
        question: str,
        resp: ChatResponse,
        mediator,
        buckets: list[dict],
        total_hits: int,
        agg_field: str,
        debug: bool,
    ) -> ChatResponse:
        """Process large aggregation results in chunks through the mediator."""
        import re as _re
        from datetime import datetime as _dt

        _now = _dt.now()
        time_str = _now.strftime("%H:%M:%S")
        date_str = _now.strftime("%B %d, %Y")
        field_display = agg_field.replace(".keyword", "").replace("_", " ")

        # Split buckets into chunks of ~50
        chunk_size = 50
        chunks = [buckets[i:i + chunk_size] for i in range(0, len(buckets), chunk_size)]
        total_chunks = len(chunks)

        if debug:
            print(f"[MEDIATOR] Chunking {len(buckets)} buckets into {total_chunks} chunks")

        all_answer_parts = []

        for chunk_idx, chunk_buckets in enumerate(chunks, 1):
            bucket_lines = [f"{b['key']} ({b['doc_count']} docs)" for b in chunk_buckets]
            bucket_text = "\n".join(bucket_lines)

            if total_chunks == 1:
                header = f"Found {len(buckets)} unique {field_display}s from {total_hits} documents:\n"
            else:
                header = f"Unique {field_display}s (part {chunk_idx}/{total_chunks}, {len(chunk_buckets)} of {len(buckets)} total) from {total_hits} documents:\n"

            context_str = header + bucket_text

            msg_parts = [
                f"User question: {question}\n",
                f"Current time: {time_str}, Date: {date_str}\n",
                f"Database contains relevant information.\n",
                f"Database context:\n{context_str}\n",
            ]

            if total_chunks == 1:
                msg_parts.append("Output the complete list from the database context above. Do NOT summarize or truncate — include ALL items.")
            else:
                msg_parts.append(f"Output the complete list from part {chunk_idx} above. Do NOT summarize or truncate — include ALL items from this chunk.")

            user_msg = "\n".join(msg_parts)

            try:
                llm_resp = mediator.llm.chat.completions.create(
                    model=mediator.model,
                    messages=[
                        {"role": "system", "content": mediator._ANSWER_SYSTEM},
                        {"role": "user", "content": user_msg},
                    ],
                    max_tokens=8000,
                    timeout=mediator.timeout,
                )
                chunk_answer = llm_resp.choices[0].message.content.strip()
                # Strip technical artifacts
                chunk_answer = _re.sub(r"<think>[\s\S]*?</think>", "", chunk_answer)
                chunk_answer = _re.sub(r"</?think>", "", chunk_answer)
                chunk_answer = _re.sub(
                    r"(?im)^\s*(DATABASE CONTEXT|Current time|No relevant database|User question:|Database contains)\s*:.*", "", chunk_answer
                )
                chunk_answer = chunk_answer.strip()
                all_answer_parts.append(chunk_answer)
            except Exception as e:
                if debug:
                    print(f"[MEDIATOR] Chunk {chunk_idx} failed: {e}")
                # Fallback: use raw bucket text for this chunk
                all_answer_parts.append(context_str)

        # Combine all chunk answers
        if total_chunks == 1:
            final_answer = all_answer_parts[0]
        else:
            final_answer = "\n\n".join(all_answer_parts)

        new_debug = resp.debug or {}
        new_debug["mediator"] = {"mediator": "active", "chunked": True, "chunks": total_chunks}
        return ChatResponse(
            answer=final_answer,
            sources_used=resp.sources_used,
            debug=new_debug,
        )

    # ── Streaming Ask (progress events) ──────────────────────────────

    def ask_stream(self, req: ChatRequest, debug: bool = False, mediate: bool = True):
        """
        Streaming version of ask() that yields ProgressEvent updates
        as the pipeline executes. Finally yields the ChatResponse.

        Usage:
            for event in eng.ask_stream(ChatRequest(question="...")):
                if isinstance(event, ProgressEvent):
                    print(f"  → {event}")
                elif isinstance(event, ChatResponse):
                    print(f"ANSWER: {event.answer}")
        """
        total_steps = 5 if mediate else 4
        step = 0

        # ── Step 1: Setup & Intent Classification ──
        step += 1
        if not self.store.is_loaded:
            yield ProgressEvent("error", "No data loaded yet. Fetch data first.", step, total_steps)
            return
        total = self.store.total_hits
        if total == 0:
            yield ProgressEvent("error", "No data was found for the specified query.", step, total_steps)
            return

        # ── Step 0.5: Always run pipeline — mediator will decide answerability ──
        # No hardcoded OOS filtering. The mediator is smart enough to figure out
        # whether the question is answerable from data, general knowledge, or out-of-scope.

        intent_type, agg_field, top_n = self._classify_intent(req.question)
        parsed_date_range = self._parse_date_range(req.question)

        intent_labels = {
            "COUNT": "counting",
            "LIST_UNIQUE": "listing unique values",
            "TOP_N": "finding top results",
            "GROUP_BY": "grouping data",
            "DETAIL": "searching for details",
        }
        action = intent_labels.get(intent_type, "analyzing")
        time_hint = ""
        if parsed_date_range:
            gte = parsed_date_range.get("gte", "")
            lte = parsed_date_range.get("lte", "")
            if gte and lte:
                time_hint = f" for period {gte} to {lte}"
            elif gte:
                time_hint = f" from {gte} onwards"

        yield ProgressEvent(
            "status",
            f"🤔 {action.capitalize()} your question...{time_hint}",
            step, total_steps,
            {"intent": intent_type, "field": agg_field},
        )

        # ── Step 2: Aggregation path (ES only, instant) ──
        if intent_type != "DETAIL" and agg_field:
            step += 1
            field_display = agg_field.replace(".keyword", "").replace("_", " ")
            yield ProgressEvent(
                "status",
                f"📊 Querying Elasticsearch for {intent_type.lower().replace('_', ' ')} ({field_display})...",
                step, total_steps,
            )
            resp = self._ask_aggregate(req.question, intent_type, agg_field, top_n, debug)
            yield ProgressEvent(
                "status",
                f"✅ Found {resp.sources_used} results from {(resp.debug or {}).get('total', 0)} documents",
                step, total_steps,
                resp.debug or {},
            )
            yield resp
            return

        # ── Step 2 (alt): Document retrieval ──
        step += 1
        yield ProgressEvent(
            "status",
            f"🔍 Retrieving relevant documents from Elasticsearch...",
            step, total_steps,
        )

        focused = self.re_retrieve(req.question, size=100)

        if not focused:
            yield ProgressEvent("status", "⚠️ No relevant documents found. Trying broader search...", step, total_steps)
            focused = self.store.documents[:50]

        doc_count = len(focused)
        if doc_count == 0:
            yield ProgressEvent("error", "No documents found to answer this question.", step, total_steps)
            return

        # ── Step 3: LLM Answer Generation ──
        if doc_count <= MAX_DIRECT:
            step += 1
            yield ProgressEvent(
                "retrieving",
                f"💭 Generating answer from {doc_count} documents (direct mode)...",
                step, total_steps,
                {"docs": doc_count, "mode": "direct"},
            )
            resp = self._ask_direct(req.question, focused, total, debug)
        else:
            step += 1
            chunks = [focused[i:i + DOCS_PER_CHUNK] for i in range(0, focused, DOCS_PER_CHUNK)]
            total_chunks = len(chunks)
            yield ProgressEvent(
                "status",
                f"💭 Analyzing {doc_count} documents in {total_chunks} chunks (map-reduce)...",
                step, total_steps,
                {"docs": doc_count, "chunks": total_chunks, "mode": "map-reduce"},
            )
            # For map-reduce, stream chunk progress via _ask_mapreduce_streaming_gen
            # which yields ProgressEvents and finally yields the ChatResponse.
            resp = None
            for event in self._ask_mapreduce_streaming_gen(req.question, focused, total, debug, step, total_steps):
                if isinstance(event, ProgressEvent):
                    yield event
                elif isinstance(event, ChatResponse):
                    resp = event
            if resp is None:
                resp = ChatResponse(answer="Map-reduce analysis failed.", sources_used=0)

        # ── Step 4: Mediator (optional) ──
        if mediate and resp.sources_used > 0:
            step += 1
            yield ProgressEvent(
                "mediator",
                f"✨ Refining answer quality ({len(resp.answer)} chars)...",
                step, total_steps,
            )
            resp = self._apply_mediator(req.question, resp, focused, debug)
            yield ProgressEvent(
                "status",
                f"✅ Refinement complete ({(resp.debug or {}).get('mediator', {}).get('mediator', 'done')})",
                step, total_steps,
            )

        # ── Final: yield the answer ──
        step += 1
        yield ProgressEvent(
            "answer",
            f"📝 Answer ready ({len(resp.answer)} chars, {resp.sources_used} sources)",
            step, total_steps,
            resp.debug or {},
        )
        yield resp
    def _ask_mapreduce_streaming_gen(self, question, docs, total, debug, step, total_steps):
        """
        Generator that yields ProgressEvents during map-reduce
        and finally yields the ChatResponse.
        """
        from engine import ProgressEvent  # avoid circular import

        chunks = [docs[i:i + DOCS_PER_CHUNK] for i in range(0, docs, DOCS_PER_CHUNK)]
        total_chunks = len(chunks)

        insights = []
        for i, chunk in enumerate(chunks):
            ctx = self._format_docs(chunk)
            yield ProgressEvent(
                "chunk",
                f"  📄 Analyzing chunk {i+1}/{total_chunks} ({len(chunk)} docs)...",
                step, total_steps,
                {"chunk": i + 1, "total_chunks": total_chunks, "chunk_size": len(chunk)},
            )
            try:
                llm_resp = self.llm.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": (
                            "Analyze this subset of military intelligence records. "
                            "Extract facts relevant to the question: names, locations, dates, "
                            "numbers, activities, equipment. Use bullet points. Be thorough."
                        )},
                        {"role": "user", "content": (
                            f"Question: {question}\n\n"
                            f"Document subset {i+1}/{len(chunks)}:\n\n{ctx}"
                        )},
                    ],
                    max_tokens=4000,
                    timeout=self.llm_timeout,
                )
                insights.append(llm_resp.choices[0].message.content.strip())
                yield ProgressEvent(
                    "chunk",
                    f"  ✅ Chunk {i+1}/{total_chunks} done ({len(insights)} insights so far)",
                    step, total_steps,
                    {"completed": i + 1, "total": total_chunks},
                )
            except Exception as e:
                insights.append(f"[Analysis timed out for subset {i+1}: {e}]")
                yield ProgressEvent(
                    "chunk",
                    f"  ⚠️ Chunk {i+1}/{total_chunks} timed out",
                    step, total_steps,
                    {"completed": i + 1, "total": total_chunks, "error": str(e)},
                )

        # Reduce phase
        yield ProgressEvent(
            "status",
            f"🔄 Combining {len(insights)} chunk analyses into final answer...",
            step, total_steps,
        )

        combined = "\n\n".join(
            f"--- Subset {i+1}/{len(chunks)} ---\n{ins}"
            for i, ins in enumerate(insights)
        )

        system_reduce = (
            "You are a military intelligence analyst. "
            "Answer the question using ONLY the provided analyses from document subsets. "
            "Combine insights from all subsets. Use bullet points. "
            "Cite specific names, numbers, locations, dates. Up to 500 words.\n\n"
            f"Session: {self._session_info()}"
        )

        try:
            llm_resp = self.llm.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_reduce},
                    {"role": "user", "content": (
                        f"Question: {question}\n\n"
                        f"Analyses from {len(insights)} subsets "
                        f"(search matched {total} total docs):\n\n{combined}"
                    )},
                ],
                max_tokens=4000,
                timeout=self.llm_timeout,
            )
            answer = _strip_llm_artifacts(llm_resp.choices[0].message.content.strip())
        except Exception as e:
            answer = (
                f"Combined analysis from {len(insights)} subsets "
                f"(search matched {total} total docs):\n\n{combined}"
                f"\n\n[Final synthesis timed out: {e}]"
            )

        yield ChatResponse(
            answer=answer, sources_used=len(docs),
            debug={
                "mode": "map-reduce",
                "total": total,
                "focused": len(docs),
                "chunks": len(insights),
            },
        )

    def _ask_aggregate(
        self,
        question: str,
        intent_type: str,
        agg_field: str,
        top_n: int | None,
        debug: bool,
    ) -> ChatResponse:
        """Answer aggregation questions directly from ES — no LLM needed."""
        query = self._build_agg_query(question, agg_field, intent_type, top_n)
        if debug:
            print(f"[DEBUG] Agg query: {json.dumps(query, indent=2)[:800]}")

        try:
            result = self.es.search(index=INDEX_PATTERN, body=query)
        except Exception as e:
            return ChatResponse(
                answer=f"Aggregation query failed: {e}. Falling back to document retrieval.",
                sources_used=0,
                debug={"mode": "agg-error", "error": str(e)} if debug else None,
            )

        total_hits = result.get("hits", {}).get("total", {}).get("value", 0)
        answer = self._format_agg_answer(question, intent_type, agg_field, total_hits, result, top_n)

        # Bucket count as "sources"
        aggs = result.get("aggregations", {})
        bucket_key = "by_field" if intent_type == "GROUP_BY" else "unique_values"
        bucket_count = len(aggs.get(bucket_key, {}).get("buckets", []))
        if not bucket_count and intent_type == "COUNT":
            bucket_count = 0

        return ChatResponse(
            answer=answer,
            sources_used=bucket_count,
            debug={
                "mode": f"agg-{intent_type}",
                "total": total_hits,
                "field": agg_field,
                "buckets": bucket_count,
                "_raw_aggs": aggs,
            },
        )

    def _ask_direct(self, question: str, docs: list[dict],
                    total: int, debug: bool) -> ChatResponse:
        context = self._format_docs(docs)
        system = self._system_prompt(total)
        try:
            resp = self.llm.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": f"Question: {question}\n\nDocuments:\n{context}"},
                ],
                max_tokens=4000,
            )
            answer = _strip_llm_artifacts(resp.choices[0].message.content.strip())
        except Exception as e:
            # Fallback: return raw snippets
            answer = self._fallback_snippets(docs, question, str(e))

        return ChatResponse(
            answer=answer, sources_used=len(docs),
            debug={"mode": "direct", "total": total} if debug else None,
        )

    def _ask_mapreduce(self, question: str, docs: list[dict],
                       total: int, debug: bool) -> ChatResponse:
        """Map: summarize each chunk. Reduce: combine into final answer."""
        chunks = [docs[i:i + DOCS_PER_CHUNK] for i in range(0, len(docs), DOCS_PER_CHUNK)]

        # Map phase
        insights: list[str] = []
        for i, chunk in enumerate(chunks):
            ctx = self._format_docs(chunk)
            try:
                resp = self.llm.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": (
                            "Analyze this subset of military intelligence records. "
                            "Extract facts relevant to the question: names, locations, dates, "
                            "numbers, activities, equipment. Use bullet points. Be thorough."
                        )},
                        {"role": "user", "content": (
                            f"Question: {question}\n\n"
                            f"Document subset {i+1}/{len(chunks)}:\n\n{ctx}"
                        )},
                    ],
                    max_tokens=4000,
                )
                insights.append(resp.choices[0].message.content.strip())
            except Exception as e:
                insights.append(f"[Analysis timed out for subset {i+1}: {e}]")

        # Reduce phase
        combined = "\n\n".join(
            f"--- Subset {i+1}/{len(chunks)} ---\n{ins}"
            for i, ins in enumerate(insights)
        )

        system_reduce = (
            "You are a military intelligence analyst. "
            "Answer the question using ONLY the provided analyses from document subsets. "
            "Combine insights from all subsets. Use bullet points. "
            "Cite specific names, numbers, locations, dates. Up to 500 words.\n\n"
            f"Session: {self._session_info()}"
        )

        try:
            resp = self.llm.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_reduce},
                    {"role": "user", "content": (
                        f"Question: {question}\n\n"
                        f"Analyses from {len(insights)} subsets "
                        f"(search matched {total} total docs):\n\n{combined}"
                    )},
                ],
                max_tokens=4000,
            )
            answer = _strip_llm_artifacts(resp.choices[0].message.content.strip())
        except Exception as e:
            answer = (
                f"Combined analysis from {len(insights)} subsets "
                f"(search matched {total} total docs):\n\n{combined}"
                f"\n\n[Final synthesis timed out: {e}]"
            )

        return ChatResponse(
            answer=answer, sources_used=len(docs),
            debug={
                "mode": "map-reduce",
                "total": total,
                "focused": len(docs),
                "chunks": len(insights),
            } if debug else None,
        )

    # ── Fallback when LLM times out ───────────────────────────────

    def _fallback_snippets(self, docs: list[dict], question: str, error: str) -> str:
        """Return formatted doc snippets when LLM is unavailable."""
        snippets = []
        for i, doc in enumerate(docs[:15], 1):
            src = doc.get("_source", {})
            flat = _flatten_source(src)
            relevant = {k: v for k, v in flat.items()
                        if k.lower() in FIELDS_OF_INTEREST and v is not None}
            lines = [f"[Doc {i}]"]
            for k, v in list(relevant.items())[:15]:
                if isinstance(v, str) and len(v) > 200:
                    v = v[:200] + "..."
                lines.append(f"  {k}: {v}")
            snippets.append("\n".join(lines))
        return (
            f"[LLM synthesis timed out ({error}). Showing top document snippets:]\n\n"
            + "\n\n".join(snippets)
        )

    # ── Helpers ───────────────────────────────────────────────────

    def _system_prompt(self, total: int) -> str:
        return (
            "You are a military intelligence analyst assistant. "
            "Answer based ONLY on the provided documents. "
            "Quote specific names, numbers, locations, dates. "
            "Use bullet points for lists. Be thorough and complete. "
            "Do NOT summarize or truncate — include ALL relevant details from the documents.\n\n"
            f"Session: {self._session_info()}\n"
            f"Total matching documents: {total}"
        )

    def _session_info(self) -> str:
        lines = []
        if self.store.category:
            desc = CATEGORY_QUERIES.get(self.store.category, {}).get("description", "")
            lines.append(f"Category: {self.store.category} — {desc}")
        if self.store.date_range:
            dr = self.store.date_range
            lines.append(f"Time range: {dr.get('from', 'start')} to {dr.get('to', 'end')}")
        lines.append(f"Total matching docs: {self.store.total_hits}")
        return "\n".join(lines)

    def _format_docs(self, docs: list[dict]) -> str:
        parts = []
        for i, doc in enumerate(docs, 1):
            src = doc.get("_source", {})
            idx = doc.get("_index", "")
            score = doc.get("_score") or 0.0

            flat = _flatten_source(src)
            relevant: dict = {}
            for k, v in flat.items():
                if k.lower() in FIELDS_OF_INTEREST and v is not None:
                    relevant[k] = v
            for k, v in flat.items():
                if k not in relevant and isinstance(v, str) and v.strip():
                    if any(h in k.lower() for h in ("name", "type", "status", "date", "location", "count", "remark")):
                        relevant[k] = v

            lines = [f"[Doc {i} | score={score:.2f} | index={idx}]"]
            for k, v in list(relevant.items())[:25]:
                if isinstance(v, str) and len(v) > 400:
                    v = v[:400] + "..."
                lines.append(f"  {k}: {v}")
            parts.append("\n".join(lines))

        ctx = "\n\n".join(parts)
        if len(ctx) > 5000:
            ctx = ctx[:5000] + "\n... [truncated within chunk]"
        return ctx

    def _format_docs_for_answer(self, docs: list[dict]) -> str:
        """Format retrieved docs into a clean, readable answer (no LLM needed)."""
        if not docs:
            return ""
        parts = []
        for i, doc in enumerate(docs, 1):
            src = doc.get("_source", {})
            flat = _flatten_source(src)
            # Extract key fields
            priority = [
                "description", "location_name", "equipment_name", "equipment_type",
                "enemy_formation_name", "infra_name", "infra_type", "activity_type",
                "activity_date", "date", "general_area", "disposition_status",
            ]
            lines = [f"[Doc {i}]"]
            for k in priority:
                v = flat.get(k)
                if v and str(v).strip():
                    val = str(v).strip()
                    if len(val) > 300:
                        val = val[:300] + "..."
                    lines.append(f"  {k}: {v}")
            # Add any other interesting fields
            for k, v in flat.items():
                if k not in priority and isinstance(v, str) and v.strip():
                    if any(h in k.lower() for h in ("name", "type", "status", "date", "location", "count")):
                        val = str(v).strip()
                        if len(val) > 200:
                            val = val[:200] + "..."
                        lines.append(f"  {k}: {v}")
            parts.append("\n".join(lines))
        result = "\n\n".join(parts)
        # Allow up to 16000 chars for the answer
        if len(result) > 16000:
            result = result[:16000] + "\n... [additional docs truncated]"
        return result


# ── OpenClaw Mediator Agent ────────────────────────────────────────

class MediatorAgent:
    """
    Intelligent mediator — the single point of contact between user and pipeline.

    For every question:
    1. should_use_rag() — decides if RAG is needed or can answer directly
    2. respond() — generates the final natural-language answer

    The user never sees raw pipeline output — everything goes through the mediator.
    """

    _DECISION_SYSTEM = """You are a military intelligence assistant with a database of
military intelligence records (formations, equipment, infrastructure, locations, activities).

For each user question, decide if it needs database lookup or can be answered directly.

Reply with ONLY one word:
- RAG — if the question is about specific data in the military records
- DIRECT — if it's general knowledge, current time/date, or unrelated to the records"""

    _ANSWER_SYSTEM = """You are a helpful military intelligence assistant chatting with a user.

RULES:
- If the message contains a CONVERSATION HISTORY section, use it to understand what was
  previously discussed. Reference prior topics naturally when relevant.
- If DATABASE CONTEXT is provided, you MUST use it as the primary source of your answer.
  Extract and include ALL relevant details: names, locations, coordinates, dates, numbers.
  Do NOT ignore the database context or fall back to general knowledge.
- If the database context directly answers the question, quote it fully without summarizing.
- For time/date questions, use the CURRENT real-world time/date provided in the message.
- If completely outside your scope, redirect warmly.
- NEVER mention "DATABASE CONTEXT", "CONVERSATION HISTORY", "RAG", "DIRECT", or any
  technical terms. Just answer naturally.
- Provide complete, detailed answers. Do NOT summarize or truncate.
- When listing items (locations, formations, equipment, etc.), include ALL items from the data.
- Use bullet points for lists. Be thorough and specific with names, numbers, dates.
- If you need more context to answer fully, say so explicitly rather than guessing."""

    def __init__(self, llm_client: OpenAI, model: str, timeout: int = 120):
        self.llm = llm_client
        self.model = model
        self.timeout = timeout

    def should_use_rag(self, question: str, debug: bool = False) -> bool:
        """Quick decision: does this question need the RAG pipeline or not?"""
        from datetime import datetime as _dt
        _now = _dt.now()
        time_str = _now.strftime("%H:%M")
        date_str = _now.strftime("%B %d, %Y")

        prompt = (
            f"Current time: {time_str}, Date: {date_str}\n"
            f"Database contains: military intelligence records (formations, equipment, "
            f"infrastructure, locations, activities)\n"
            f"User question: {question}\n"
            f"Reply RAG if it needs database lookup, DIRECT if it can be answered without the database."
        )
        try:
            resp = self.llm.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": self._DECISION_SYSTEM},
                    {"role": "user", "content": prompt},
                ],
                max_tokens=10,
                timeout=min(15, self.timeout),
            )
            decision = resp.choices[0].message.content.strip().upper()
            needs_rag = "RAG" in decision
            if debug:
                print(f"[MEDIATOR] Decision: {'RAG' if needs_rag else 'DIRECT'} ({decision})")
            return needs_rag
        except Exception:
            return True  # default to RAG on error

    def respond(
        self,
        question: str,
        raw_answer: str | None,
        source_docs: list[dict],
        debug: bool = False,
    ) -> tuple[str, dict]:
        """Generate the final user-facing answer."""
        import re as _re
        from datetime import datetime as _dt

        _now = _dt.now()
        time_str = _now.strftime("%H:%M:%S")
        date_str = _now.strftime("%B %d, %Y")
        day_str = _now.strftime("%A")

        # Build compact context from source docs
        context_str = ""
        if source_docs:
            parts = []
            for i, doc in enumerate(source_docs[:50], 1):
                src = doc.get("_source", {})
                flat = _flatten_source(src)
                priority = [
                    "description", "location_name", "general_area",
                    "enemy_formation_name", "equipment_name", "equipment_type",
                    "infra_type", "disposition_status", "activity_type", "date",
                ]
                lines = [f"[Doc {i}]"]
                for k in priority:
                    v = flat.get(k)
                    if v and str(v).strip():
                        lines.append(f"  {k}: {str(v)[:200]}")
                parts.append("\n".join(lines))
            context_str = "\n\n".join(parts)
            if len(context_str) > 32000:
                context_str = context_str[:32000] + "\n... [truncated]"

        # Build the message
        msg_parts = [f"User question: {question}\n"]
        msg_parts.append(f"Current time: {time_str}, Date: {day_str}, {date_str}\n")

        if raw_answer and source_docs:
            msg_parts.append(f"Database contains relevant information.\\n")
            msg_parts.append(f"Database context:\\n{context_str}\\n")
        else:
            msg_parts.append("No relevant database records found for this question.\\n")

        # If context contains a pre-formatted aggregation list, output it directly
        # without re-summarizing — the list is already complete and formatted
        if context_str and ("unique " in context_str.lower() or "list of" in context_str.lower()) and ("docs)" in context_str or "documents)" in context_str):
            msg_parts.append("Output the complete list from the database context above. Do NOT summarize or truncate — include ALL items.")
        else:
            msg_parts.append("Answer the user naturally based on the available information.")
        user_msg = "\n".join(msg_parts)

        try:
            resp = self.llm.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": self._ANSWER_SYSTEM},
                    {"role": "user", "content": user_msg},
                ],
                max_tokens=8000,
                timeout=self.timeout,
            )
            answer = resp.choices[0].message.content.strip()
        except Exception as e:
            if raw_answer:
                return raw_answer, {"mediator": "failed", "error": str(e)}
            return "I'm having trouble responding right now. Please try again.", {
                "mediator": "failed",
                "error": str(e),
            }

        # Strip any leaked technical text and reasoning blocks
        answer = _re.sub(r"<think>[\s\S]*?</think>", "", answer)
        answer = _re.sub(r"</?think>", "", answer)
        answer = _re.sub(
            r"(?im)^\s*(DATABASE CONTEXT|Current time|No relevant database|User question:|Database contains)\s*:.*", "", answer
        )
        answer = answer.strip()

        return answer, {
            "mediator": "active",
            "used_rag": raw_answer is not None and len(source_docs) > 0,
        }


    # ── Utility ───────────────────────────────────────────────────────

# Known null-like values to exclude from aggregation results
_NULL_LOCATION_VALUES = {
    "unknown", "location not known", "n/a", "na", "none", "null", "",
    "not known", "not available", "tbd", "to be determined",
}

def _strip_llm_artifacts(text: str) -> str:
    """Strip reasoning blocks and leaked technical text from LLM output."""
    import re as _re
    text = _re.sub(r"<think>[\s\S]*?</think>", "", text)
    text = _re.sub(r"</?think>", "", text)
    text = _re.sub(
        r"(?im)^\s*(DATABASE CONTEXT|Current time|No relevant database|"
        r"User question:|Database contains|Previous conversation)\s*:.*", "", text
    )
    return text.strip()

def _is_null_location(value: str) -> bool:
    """Check if a location value is effectively null/empty."""
    if not value:
        return True
    v = value.strip().lower()
    return v in _NULL_LOCATION_VALUES or len(v) < 2

def _flatten_source(source: dict, prefix: str = "") -> dict:
    flat = {}
    for k, v in source.items():
        key = f"{prefix}.{k}" if prefix else k
        if isinstance(v, dict):
            flat.update(_flatten_source(v, key))
        elif isinstance(v, list) and v and isinstance(v[0], (dict, list)):
            flat[key] = str(v[:3])
        else:
            flat[key] = v
    return flat
