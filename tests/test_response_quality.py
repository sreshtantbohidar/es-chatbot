"""
Response Quality Test Suite
=============================
Tests chat response quality across different query types:
- Aggregation queries (list all, count, top N)
- Detail queries (specific equipment, locations)
- Analysis queries (patterns, comparisons, reasoning)
- Edge cases (empty, long, out-of-scope)
- Common sense / general knowledge
- Time/date queries

Run: python -m pytest tests/test_response_quality.py -v
"""

import sys, os, json, time, unittest, requests

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

BASE_URL = "http://localhost:8000"


def get_sid():
    return f"quality-test-{int(time.time())}"


def create_and_fetch(category="General Area"):
    sid = get_sid()
    requests.post(f"{BASE_URL}/api/session/create",
        json={"session_id": sid, "max_turns": 10})
    requests.post(f"{BASE_URL}/api/session/fetch?session_id={sid}",
        json={"mode": "category", "category": category})
    return sid


def ask(sid, q):
    r = requests.post(f"{BASE_URL}/api/session/ask?session_id={sid}",
        json={"question": q, "debug": True})
    return r.json()


def cleanup(sid):
    requests.delete(f"{BASE_URL}/session?session_id={sid}")


# ─── Test Prompts by Category ────────────────────────────────────────

AGGREGATION_PROMPTS = [
    {
        "prompt": "show me all locations",
        "must_contain": ["burang", "karachi", "lhasa"],
        "must_not_contain": ["no data", "no specific", "cannot provide"],
        "min_length": 500,
        "description": "List all locations - should return 197+ unique locations"
    },
    {
        "prompt": "list of all equipment types",
        "must_contain": [],
        "must_not_contain": ["no data", "no specific", "cannot provide"],
        "min_length": 200,
        "description": "List all equipment types"
    },
    {
        "prompt": "what are the top 5 locations by document count",
        "must_contain": ["burang"],
        "must_not_contain": ["no data", "no specific"],
        "min_length": 200,
        "description": "Top 5 locations by count"
    },
    {
        "prompt": "how many unique locations are there",
        "must_contain": [],
        "must_not_contain": ["no data", "cannot count"],
        "min_length": 50,
        "description": "Count of unique locations"
    },
    {
        "prompt": "show me all categories of activity",
        "must_contain": [],
        "must_not_contain": ["no data", "no specific"],
        "min_length": 200,
        "description": "List all activity types"
    },
]

DETAIL_PROMPTS = [
    {
        "prompt": "need a detailed report on equipment J-20",
        "must_contain": ["j-20"],
        "must_not_contain": ["no specific mention", "no direct reference",
                            "not available", "cannot provide"],
        "min_length": 200,
        "description": "J-20 equipment report - 772 docs exist in ES"
    },
    {
        "prompt": "give me details on location Lhasa",
        "must_contain": ["lhasa"],
        "must_not_contain": ["no data", "no specific"],
        "min_length": 100,
        "description": "Lhasa location details"
    },
    {
        "prompt": "what is the infrastructure status at Urumqi",
        "must_contain": ["urumqi"],
        "must_not_contain": ["no data", "no specific"],
        "min_length": 100,
        "description": "Urumqi infrastructure status"
    },
    {
        "prompt": "tell me about training activities",
        "must_contain": [],
        "must_not_contain": ["no data", "no specific", "cannot provide"],
        "min_length": 100,
        "description": "Training activities"
    },
    {
        "prompt": "what deployments happened in 2025",
        "must_contain": [],
        "must_not_contain": ["no data", "no specific", "cannot provide"],
        "min_length": 100,
        "description": "2025 deployments"
    },
]

ANALYSIS_PROMPTS = [
    {
        "prompt": "analyze the deployment patterns across locations",
        "must_contain": [],
        "must_not_contain": ["no data", "cannot analyze", "no specific"],
        "min_length": 300,
        "description": "Deployment pattern analysis"
    },
    {
        "prompt": "compare activity levels between Urumqi and Karachi",
        "must_contain": ["urumqi", "karachi"],
        "must_not_contain": ["no data", "cannot compare"],
        "min_length": 200,
        "description": "Compare two locations"
    },
    {
        "prompt": "what are the trends in infrastructure development",
        "must_contain": [],
        "must_not_contain": ["no data", "cannot determine"],
        "min_length": 200,
        "description": "Infrastructure trends"
    },
    {
        "prompt": "connect the dots between training areas and equipment deployment",
        "must_contain": [],
        "must_not_contain": ["no data", "cannot connect"],
        "min_length": 200,
        "description": "Cross-category analysis"
    },
]

COMMON_SENSE_PROMPTS = [
    {
        "prompt": "what is the capital of France",
        "must_contain": ["paris"],
        "must_not_contain": [],
        "min_length": 20,
        "description": "Common sense: capital of France"
    },
    {
        "prompt": "what time is it right now",
        "must_contain": [],
        "must_not_contain": [],
        "min_length": 20,
        "description": "Current time query"
    },
    {
        "prompt": "what day of the week is it today",
        "must_contain": [],
        "must_not_contain": [],
        "min_length": 20,
        "description": "Current day query"
    },
    {
        "prompt": "how many days are in a week",
        "must_contain": ["7", "seven"],
        "must_not_contain": [],
        "min_length": 10,
        "description": "Common sense: days in week"
    },
]

TIME_DATE_PROMPTS = [
    {
        "prompt": "what activities happened in January 2025",
        "must_contain": [],
        "must_not_contain": ["no data", "cannot provide"],
        "min_length": 100,
        "description": "Time-filtered query: January 2025"
    },
    {
        "prompt": "show me recent activity from the last 3 months",
        "must_contain": [],
        "must_not_contain": ["no data", "cannot provide"],
        "min_length": 100,
        "description": "Recent activity query"
    },
    {
        "prompt": "what happened in 2024",
        "must_contain": [],
        "must_not_contain": ["no data", "cannot provide"],
        "min_length": 100,
        "description": "Year-based query: 2024"
    },
]

EDGE_CASE_PROMPTS = [
    {
        "prompt": "",
        "must_contain": [],
        "must_not_contain": [],
        "min_length": 0,
        "description": "Empty question - should handle gracefully",
        "expect_error": True
    },
    {
        "prompt": "a" * 1000,
        "must_contain": [],
        "must_not_contain": [],
        "min_length": 50,
        "description": "Very long question (1000 chars)"
    },
    {
        "prompt": "what is the meaning of life",
        "must_contain": [],
        "must_not_contain": [],
        "min_length": 20,
        "description": "Philosophical question"
    },
    {
        "prompt": "tell me a joke",
        "must_contain": [],
        "must_not_contain": [],
        "min_length": 20,
        "description": "Joke request"
    },
    {
        "prompt": "what is 2 + 2",
        "must_contain": ["4", "four"],
        "must_not_contain": [],
        "min_length": 10,
        "description": "Simple math"
    },
    {
        "prompt": "who is the president of the United States",
        "must_contain": [],
        "must_not_contain": [],
        "min_length": 20,
        "description": "Current affairs (general knowledge)"
    },
    {
        "prompt": "what is the weather like today",
        "must_contain": [],
        "must_not_contain": [],
        "min_length": 20,
        "description": "Weather (out of scope for intelligence data)"
    },
    {
        "prompt": "show me data about Mars",
        "must_contain": [],
        "must_not_contain": [],
        "min_length": 20,
        "description": "Out of scope: Mars data"
    },
]


class TestResponseQuality(unittest.TestCase):
    """Test response quality across all prompt categories."""

    @classmethod
    def setUpClass(cls):
        """Create a session once for all tests."""
        cls.sid = create_and_fetch("General Area")
        time.sleep(2)  # Let fetch complete

    @classmethod
    def tearDownClass(cls):
        cleanup(cls.sid)

    def _test_prompt(self, prompt_info):
        """Helper to test a single prompt."""
        prompt = prompt_info["prompt"]
        must_contain = prompt_info.get("must_contain", [])
        must_not_contain = prompt_info.get("must_not_contain", [])
        min_length = prompt_info.get("min_length", 100)
        desc = prompt_info.get("description", prompt)
        expect_error = prompt_info.get("expect_error", False)

        with self.subTest(prompt=prompt[:50]):
            result = ask(self.sid, prompt)
            answer = result.get("answer", "")
            status = result.get("_status_code", 200)

            if expect_error:
                # Empty questions might return 400 or short answer
                return

            # Check minimum length
            if min_length > 0:
                self.assertGreater(len(answer), min_length,
                    f"[{desc}] Answer too short ({len(answer)} chars): {answer[:200]}")

            # Check must_contain terms
            answer_lower = answer.lower()
            for term in must_contain:
                self.assertIn(term.lower(), answer_lower,
                    f"[{desc}] Missing '{term}' in answer: {answer[:200]}")

            # Check must_not_contain terms
            for term in must_not_contain:
                self.assertNotIn(term.lower(), answer_lower,
                    f"[{desc}] Should not contain '{term}': {answer[:200]}")

    # ── Aggregation ──

    def test_aggregation_prompts(self):
        for p in AGGREGATION_PROMPTS:
            self._test_prompt(p)

    # ── Detail ──

    def test_detail_prompts(self):
        for p in DETAIL_PROMPTS:
            self._test_prompt(p)

    # ── Analysis ──

    def test_analysis_prompts(self):
        for p in ANALYSIS_PROMPTS:
            self._test_prompt(p)

    # ── Common Sense ──

    def test_common_sense_prompts(self):
        for p in COMMON_SENSE_PROMPTS:
            self._test_prompt(p)

    # ── Time/Date ──

    def test_time_date_prompts(self):
        for p in TIME_DATE_PROMPTS:
            self._test_prompt(p)

    # ── Edge Cases ──

    def test_edge_case_prompts(self):
        for p in EDGE_CASE_PROMPTS:
            self._test_prompt(p)


class TestResponseQualityPerCategory(unittest.TestCase):
    """Test response quality with category-specific data."""

    def _test_category(self, category, prompts):
        sid = create_and_fetch(category)
        time.sleep(2)
        try:
            for p in prompts:
                result = ask(sid, p["prompt"])
                answer = result.get("answer", "")
                min_len = p.get("min_length", 100)
                if min_len > 0:
                    self.assertGreater(len(answer), min_len,
                        f"[{category}/{p.get('description', '')}] Too short: {answer[:100]}")
        finally:
            cleanup(sid)

    def test_general_area(self):
        self._test_category("General Area", [
            {"prompt": "list all locations", "min_length": 500},
            {"prompt": "show me equipment J-20", "min_length": 200},
        ])

    def test_infra_development(self):
        self._test_category("Infra Development", [
            {"prompt": "list all infrastructure types", "min_length": 200},
            {"prompt": "what is the status of development projects", "min_length": 200},
        ])

    def test_training_areas(self):
        self._test_category("Training Areas", [
            {"prompt": "list all training locations", "min_length": 200},
            {"prompt": "what training activities are mentioned", "min_length": 200},
        ])

    def test_force_disposition(self):
        self._test_category("Force Disposition", [
            {"prompt": "list all force dispositions", "min_length": 200},
            {"prompt": "what formations are mentioned", "min_length": 200},
        ])


class TestNoHallucination(unittest.TestCase):
    """Verify LLM does not hallucinate when data exists."""

    @classmethod
    def setUpClass(cls):
        cls.sid = create_and_fetch("General Area")
        time.sleep(2)

    @classmethod
    def tearDownClass(cls):
        cleanup(cls.sid)

    def test_j20_not_hallucinated(self):
        """J-20 has 772 docs in ES. Answer must NOT say 'no data'."""
        result = ask(self.sid, "equipment J-20")
        answer = result.get("answer", "").lower()
        bad_phrases = [
            "no specific mention", "no direct reference",
            "not available in the provided documents",
            "cannot provide", "no data found",
            "i don't have information",
        ]
        for phrase in bad_phrases:
            self.assertNotIn(phrase, answer,
                f"LLM hallucinated: '{phrase}' in answer")

    def test_locations_not_truncated(self):
        """'show me all locations' should return many, not just top 5."""
        result = ask(self.sid, "show me all locations")
        answer = result.get("answer", "")
        # Should contain at least 10 different location names
        locations = ["burang", "karachi", "lhasa", "tholing", "kashgar",
                     "manza", "chitral", "chepzi", "quetta", "sargodha"]
        found = sum(1 for loc in locations if loc in answer.lower())
        self.assertGreater(found, 5,
            f"Only {found}/10 expected locations in answer")

    def test_answer_uses_retrieved_data(self):
        """Answer should reference actual data from documents."""
        result = ask(self.sid, "what equipment is at Urumqi")
        answer = result.get("answer", "").lower()
        # Should mention specific equipment or activities
        self.assertTrue(
            "urumqi" in answer and len(answer) > 100,
            f"Answer doesn't use retrieved data: {answer[:200]}"
        )


if __name__ == "__main__":
    print("=" * 70)
    print("Response Quality Test Suite")
    print("=" * 70)
    print(f"Aggregation prompts: {len(AGGREGATION_PROMPTS)}")
    print(f"Detail prompts:      {len(DETAIL_PROMPTS)}")
    print(f"Analysis prompts:    {len(ANALYSIS_PROMPTS)}")
    print(f"Common sense:        {len(COMMON_SENSE_PROMPTS)}")
    print(f"Time/Date prompts:   {len(TIME_DATE_PROMPTS)}")
    print(f"Edge case prompts:   {len(EDGE_CASE_PROMPTS)}")
    print("=" * 70)
    unittest.main(verbosity=2)
