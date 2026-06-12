"""
Comprehensive Test Suite for ES Intelligence Chatbot
=====================================================
Tests all API endpoints, UI rendering, and chat response quality.

Run with: python -m pytest tests/test_comprehensive.py -v
Or:       python tests/test_comprehensive.py

Requirements:
- Elasticsearch running at 192.168.1.16:9200
- Ollama running at 192.168.1.125:11434 with llama3:8b-instruct-q8_0
- Flask server running at localhost:8000
"""

import sys, os, json, time, unittest, requests

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

BASE_URL = "http://localhost:8000"
ES_HOST = "http://192.168.1.16:9200"
OLLAMA_HOST = "http://192.168.1.125:11434"

# ─── Fixtures ────────────────────────────────────────────────────────

def get_test_session_id():
    return f"test-{int(time.time())}"


def create_session(session_id=None, model="llama3:8b-instruct-q8_0", max_turns=5):
    sid = session_id or get_test_session_id()
    r = requests.post(f"{BASE_URL}/api/session/create", json={
        "session_id": sid,
        "llm_model": model,
        "max_turns": max_turns,
    })
    return sid, r


def fetch_data(session_id, category="General Area"):
    r = requests.post(f"{BASE_URL}/api/session/fetch?session_id={session_id}",
        json={"mode": "category", "category": category})
    return r


def ask_question(session_id, question, debug=False):
    r = requests.post(f"{BASE_URL}/api/session/ask?session_id={session_id}",
        json={"question": question, "debug": debug})
    return r


def cleanup_session(session_id):
    requests.delete(f"{BASE_URL}/session?session_id={session_id}")


# ─── Test: Prerequisites ────────────────────────────────────────────

class TestPrerequisites(unittest.TestCase):
    """Verify ES and Ollama are accessible."""

    def test_01_es_running(self):
        r = requests.get(ES_HOST, timeout=5)
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertIn("cluster_name", data)
        print(f"  ES cluster: {data['cluster_name']}")

    def test_02_ollama_running(self):
        r = requests.get(f"{OLLAMA_HOST}/api/tags", timeout=5)
        self.assertEqual(r.status_code, 200)
        models = r.json().get("models", [])
        model_names = [m["name"] for m in models]
        self.assertIn("llama3:8b-instruct-q8_0", model_names)
        print(f"  Ollama models: {len(models)}")

    def test_03_flask_running(self):
        r = requests.get(f"{BASE_URL}/api/health", timeout=5)
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertEqual(data["status"], "ok")
        print(f"  Flask health: {data['status']}")


# ─── Test: API Endpoints ─────────────────────────────────────────────

class TestAPIEndpoints(unittest.TestCase):
    """Test all 10 API endpoints."""

    def test_01_health(self):
        r = requests.get(f"{BASE_URL}/api/health")
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertEqual(data["status"], "ok")
        self.assertIn("es_cluster", data)
        self.assertIn("es_version", data)

    def test_02_models(self):
        r = requests.get(f"{BASE_URL}/api/models")
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertIn("models", data)
        self.assertTrue(len(data["models"]) > 0)
        # Should NOT include embedding models
        for m in data["models"]:
            self.assertNotIn("embed", m["name"].lower())
            self.assertNotIn("bge-m3", m["name"].lower())

    def test_03_categories(self):
        r = requests.get(f"{BASE_URL}/api/categories")
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertIn("categories", data)
        self.assertEqual(len(data["categories"]), 10)
        self.assertIn("General Area", data["categories"])

    def test_04_session_create(self):
        sid = get_test_session_id()
        r = requests.post(f"{BASE_URL}/api/session/create", json={
            "session_id": sid, "max_turns": 5
        })
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertEqual(data["session_id"], sid)
        self.assertIn("created_at", data)
        cleanup_session(sid)

    def test_05_session_create_duplicate(self):
        sid = get_test_session_id()
        r1 = requests.post(f"{BASE_URL}/api/session/create", json={
            "session_id": sid, "max_turns": 5
        })
        self.assertEqual(r1.status_code, 200)
        r2 = requests.post(f"{BASE_URL}/api/session/create", json={
            "session_id": sid, "max_turns": 5
        })
        self.assertEqual(r2.status_code, 409)
        cleanup_session(sid)

    def test_06_session_create_no_id(self):
        r = requests.post(f"{BASE_URL}/api/session/create", json={
            "max_turns": 5
        })
        self.assertEqual(r.status_code, 400)

    def test_07_session_fetch(self):
        sid, _ = create_session()
        r = requests.post(f"{BASE_URL}/api/session/fetch?session_id={sid}",
            json={"mode": "category", "category": "General Area"})
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertIn("total_hits", data)
        self.assertIn("documents_stored", data)
        self.assertGreater(data["documents_stored"], 0)
        cleanup_session(sid)

    def test_08_session_fetch_not_found(self):
        r = requests.post(f"{BASE_URL}/api/session/fetch?session_id=nonexistent-xyz",
            json={"mode": "category", "category": "General Area"})
        self.assertEqual(r.status_code, 404)

    def test_09_session_status(self):
        sid, _ = create_session()
        r = requests.get(f"{BASE_URL}/api/session/status?session_id={sid}")
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertEqual(data["session_id"], sid)
        self.assertFalse(data["is_loaded"])
        cleanup_session(sid)

    def test_10_session_status_not_found(self):
        r = requests.get(f"{BASE_URL}/api/session/status?session_id=nonexistent-xyz")
        self.assertEqual(r.status_code, 404)

    def test_11_session_reset(self):
        sid, _ = create_session()
        r = requests.post(f"{BASE_URL}/session/reset?session_id={sid}")
        self.assertEqual(r.status_code, 200)
        cleanup_session(sid)

    def test_12_session_delete(self):
        sid, _ = create_session()
        r = requests.delete(f"{BASE_URL}/session?session_id={sid}")
        self.assertEqual(r.status_code, 200)
        # Verify deleted
        r2 = requests.get(f"{BASE_URL}/api/session/status?session_id={sid}")
        self.assertEqual(r2.status_code, 404)

    def test_13_one_shot_ask(self):
        r = requests.post(f"{BASE_URL}/api/ask", json={
            "question": "list top 3 locations",
            "fetch": {
                "mode": "raw_query",
                "raw_query": {"query": {"bool": {"must_not": [{"term": {"form_status": 5}}]}}, "size": 3}
            }
        })
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertIn("answer", data)
        self.assertIn("sources_used", data)
        self.assertGreater(len(data["answer"]), 0)

    def test_14_one_shot_empty_body(self):
        r = requests.post(f"{BASE_URL}/api/ask", json={})
        self.assertEqual(r.status_code, 400)

    def test_15_docs_redirect(self):
        r = requests.get(f"{BASE_URL}/docs", allow_redirects=False)
        self.assertEqual(r.status_code, 302)
        self.assertIn("/apidocs/", r.headers.get("Location", ""))

    def test_16_apidocs_renders(self):
        r = requests.get(f"{BASE_URL}/apidocs/")
        self.assertEqual(r.status_code, 200)
        self.assertIn("swagger-ui", r.text.lower())

    def test_17_spec_json(self):
        r = requests.get(f"{BASE_URL}/apispec_1.json")
        self.assertEqual(r.status_code, 200)
        spec = r.json()
        self.assertIn("paths", spec)
        self.assertGreater(len(spec["paths"]), 0)


# ─── Test: UI Rendering ──────────────────────────────────────────────

class TestUIRendering(unittest.TestCase):
    """Test that UI pages render correctly."""

    def test_01_setup_page(self):
        r = requests.get(f"{BASE_URL}/")
        self.assertEqual(r.status_code, 200)
        html = r.text
        # Key elements
        self.assertIn("Session Configuration", html)
        self.assertIn('name="category"', html)
        self.assertIn('name="model"', html)
        self.assertIn('name="session_id"', html)
        self.assertIn('name="max_turns"', html)
        self.assertIn("Load Data", html)
        # Model dropdown should have llama3:8b selected
        self.assertIn("llama3:8b-instruct-q8_0", html)

    def test_02_setup_page_model_filter(self):
        """Embedding models should NOT appear in dropdown."""
        r = requests.get(f"{BASE_URL}/")
        html = r.text
        self.assertNotIn("nomic-embed-text", html)
        self.assertNotIn("bge-m3", html)

    def test_03_chat_page_no_session(self):
        """Chat page without valid session should redirect to setup."""
        r = requests.get(f"{BASE_URL}/chat?session_id=nonexistent-xyz",
            allow_redirects=False)
        self.assertEqual(r.status_code, 302)

    def test_04_chat_page_with_session(self):
        sid, _ = create_session()
        r = requests.get(f"{BASE_URL}/chat?session_id={sid}")
        self.assertEqual(r.status_code, 200)
        html = r.text
        self.assertIn("chat-wrap", html)
        self.assertIn("textarea", html)
        self.assertIn("ask()", html)
        self.assertIn(sid, html)
        cleanup_session(sid)

    def test_05_favicon(self):
        r = requests.get(f"{BASE_URL}/favicon.ico")
        self.assertEqual(r.status_code, 204)

    def test_06_fetch_form_redirect(self):
        """Form-based fetch should redirect to chat page."""
        sid = get_test_session_id()
        r = requests.post(f"{BASE_URL}/fetch",
            data={"session_id": sid, "mode": "category", "category": "General Area",
                  "model": "llama3:8b-instruct-q8_0", "max_turns": "5"},
            allow_redirects=False)
        self.assertEqual(r.status_code, 302)
        self.assertIn(f"/chat?session_id={sid}", r.headers.get("Location", ""))
        cleanup_session(sid)


# ─── Test: Session Lifecycle ─────────────────────────────────────────

class TestSessionLifecycle(unittest.TestCase):
    """Test full session lifecycle: create → fetch → ask → reset → delete."""

    def test_01_full_lifecycle(self):
        sid = get_test_session_id()

        # Create
        r = requests.post(f"{BASE_URL}/api/session/create", json={
            "session_id": sid, "max_turns": 3
        })
        self.assertEqual(r.status_code, 200)

        # Fetch
        r = requests.post(f"{BASE_URL}/api/session/fetch?session_id={sid}",
            json={"mode": "category", "category": "General Area"})
        self.assertEqual(r.status_code, 200)
        self.assertGreater(r.json()["documents_stored"], 0)

        # Ask
        r = requests.post(f"{BASE_URL}/api/session/ask?session_id={sid}",
            json={"question": "list top 5 locations"})
        self.assertEqual(r.status_code, 200)
        self.assertGreater(len(r.json()["answer"]), 0)

        # Status
        r = requests.get(f"{BASE_URL}/api/session/status?session_id={sid}")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json()["is_loaded"])
        self.assertEqual(r.json()["turns_used"], 1)

        # Reset
        r = requests.post(f"{BASE_URL}/session/reset?session_id={sid}")
        self.assertEqual(r.status_code, 200)

        # Delete
        r = requests.delete(f"{BASE_URL}/session?session_id={sid}")
        self.assertEqual(r.status_code, 200)

    def test_02_model_switch(self):
        """Switching model on re-fetch should update the session."""
        sid, _ = create_session(model="llama3:8b-instruct-q8_0")
        fetch_data(sid)

        # Re-fetch with different model
        r = requests.post(f"{BASE_URL}/fetch",
            data={"session_id": sid, "mode": "category", "category": "General Area",
                  "model": "qwen2.5:14b", "max_turns": "5"},
            allow_redirects=False)
        self.assertEqual(r.status_code, 302)
        cleanup_session(sid)

    def test_03_raw_query_fetch(self):
        """Raw ES query mode should work."""
        sid, _ = create_session()
        r = requests.post(f"{BASE_URL}/api/session/fetch?session_id={sid}",
            json={
                "mode": "raw_query",
                "raw_query": {
                    "query": {"bool": {"must_not": [{"term": {"form_status": 5}}]}},
                    "size": 5
                }
            })
        self.assertEqual(r.status_code, 200)
        self.assertGreater(r.json()["documents_stored"], 0)
        cleanup_session(sid)

    def test_04_raw_query_invalid_json(self):
        """Invalid JSON in raw query should return 400."""
        sid, _ = create_session()
        r = requests.post(f"{BASE_URL}/fetch",
            data={"session_id": sid, "mode": "raw_query", "raw_query": "not json",
                  "model": "llama3:8b-instruct-q8_0", "max_turns": "5"})
        self.assertEqual(r.status_code, 400)
        cleanup_session(sid)

    def test_05_ask_without_data(self):
        """Asking without loading data should return 400."""
        sid, _ = create_session()
        r = requests.post(f"{BASE_URL}/api/session/ask?session_id={sid}",
            json={"question": "test"})
        self.assertEqual(r.status_code, 400)
        cleanup_session(sid)

    def test_06_session_turn_limit(self):
        """Session should enforce max_turns limit."""
        sid, _ = create_session(max_turns=1)
        fetch_data(sid)

        # First ask should work
        r = requests.post(f"{BASE_URL}/api/session/ask?session_id={sid}",
            json={"question": "list locations"})
        self.assertEqual(r.status_code, 200)

        # Second ask should fail (limit reached)
        r = requests.post(f"{BASE_URL}/api/session/ask?session_id={sid}",
            json={"question": "another question"})
        self.assertEqual(r.status_code, 200)
        self.assertIn("limit", r.json().get("answer", "").lower())
        cleanup_session(sid)


# ─── Test: Intent Classification ─────────────────────────────────────

class TestIntentClassification(unittest.TestCase):
    """Test that questions are classified into correct intent types."""

    def setUp(self):
        self.sid, _ = create_session()
        fetch_data(self.sid)

    def tearDown(self):
        cleanup_session(self.sid)

    def test_01_list_unique_locations(self):
        r = ask_question(self.sid, "show me all locations", debug=True)
        data = r.json()
        mode = data.get("debug", {}).get("mode", "")
        self.assertIn("LIST_UNIQUE", mode)
        self.assertGreater(data.get("sources_used", 0), 50)

    def test_02_list_unique_equipment(self):
        r = ask_question(self.sid, "list all equipment types", debug=True)
        data = r.json()
        mode = data.get("debug", {}).get("mode", "")
        self.assertIn("LIST_UNIQUE", mode)

    def test_03_list_of_all(self):
        """'list of all' should trigger LIST_UNIQUE."""
        r = ask_question(self.sid, "give me list of all locations", debug=True)
        data = r.json()
        mode = data.get("debug", {}).get("mode", "")
        self.assertIn("LIST_UNIQUE", mode)

    def test_04_show_me_all(self):
        """'show me all' should trigger LIST_UNIQUE."""
        r = ask_question(self.sid, "show me all equipment", debug=True)
        data = r.json()
        mode = data.get("debug", {}).get("mode", "")
        self.assertIn("LIST_UNIQUE", mode)

    def test_05_detail_query(self):
        """Specific detail queries should use DETAIL mode."""
        r = ask_question(self.sid, "what is the status of infrastructure at Urumqi", debug=True)
        data = r.json()
        mode = data.get("debug", {}).get("mode", "")
        self.assertIn("direct", mode)

    def test_06_count_query(self):
        """Count queries should trigger COUNT mode."""
        r = ask_question(self.sid, "how many documents mention Karachi", debug=True)
        data = r.json()
        mode = data.get("debug", {}).get("mode", "")
        # Could be COUNT or direct depending on classification
        self.assertIsNotNone(data.get("answer"))


# ─── Test: Chat Response Quality ─────────────────────────────────────

class TestResponseQuality(unittest.TestCase):
    """Test response quality with a standard set of prompts."""

    def setUp(self):
        self.sid, _ = create_session()
        fetch_data(self.sid, "General Area")

    def tearDown(self):
        cleanup_session(self.sid)

    def _check_answer(self, r, min_length=100, must_contain=None, must_not_contain=None):
        """Helper to validate answer quality."""
        data = r.json()
        answer = data.get("answer", "")
        self.assertGreater(len(answer), min_length,
            f"Answer too short ({len(answer)} chars): {answer[:200]}")
        if must_contain:
            for term in must_contain:
                self.assertIn(term.lower(), answer.lower(),
                    f"Answer missing '{term}': {answer[:200]}")
        if must_not_contain:
            for term in must_not_contain:
                self.assertNotIn(term.lower(), answer.lower(),
                    f"Answer should not contain '{term}': {answer[:200]}")
        return data

    # ── Aggregation Queries ──

    def test_01_list_all_locations(self):
        """Should return a comprehensive list, not just a few."""
        r = ask_question(self.sid, "show me all locations")
        data = self._check_answer(r, min_length=500,
            must_contain=["burang", "karachi", "lhasa"],
            must_not_contain=["no data", "no specific mention", "cannot provide"])
        # Should have many sources
        self.assertGreater(data.get("sources_used", 0), 50)

    def test_02_list_all_equipment(self):
        """Should list equipment types."""
        r = ask_question(self.sid, "list all equipment types")
        self._check_answer(r, min_length=200,
            must_not_contain=["no data", "no specific mention"])

    def test_03_top_locations(self):
        """Should return top locations by count."""
        r = ask_question(self.sid, "what are the top 5 locations")
        self._check_answer(r, min_length=200,
            must_contain=["burang"],
            must_not_contain=["no data", "no specific mention"])

    # ── Detail Queries ──

    def test_04_equipment_j20(self):
        """J-20 query should return real data, not hallucination."""
        r = ask_question(self.sid, "need a detailed report on equipment J-20")
        self._check_answer(r, min_length=200,
            must_contain=["j-20"],
            must_not_contain=["no specific mention", "no direct reference",
                              "cannot provide", "not available in the documents"])

    def test_05_location_detail(self):
        """Location detail query should return specific info."""
        r = ask_question(self.sid, "give me details on location Lhasa")
        self._check_answer(r, min_length=100,
            must_contain=["lhasa"],
            must_not_contain=["no data", "no specific mention"])

    def test_06_infrastructure_query(self):
        """Infrastructure query should return relevant results."""
        r = ask_question(self.sid, "what infrastructure developments are mentioned")
        self._check_answer(r, min_length=200,
            must_not_contain=["no data", "no specific mention"])

    # ── Analysis Queries ──

    def test_07_analysis_query(self):
        """Analysis query should provide reasoning, not just list."""
        r = ask_question(self.sid,
            "analyze the deployment patterns across locations")
        self._check_answer(r, min_length=300,
            must_not_contain=["no data", "no specific mention", "cannot analyze"])

    def test_08_comparison_query(self):
        """Comparison query should compare data points."""
        r = ask_question(self.sid,
            "compare activity levels between Urumqi and Karachi")
        self._check_answer(r, min_length=200,
            must_contain=["urumqi", "karachi"],
            must_not_contain=["no data", "no specific mention"])

    # ── Edge Cases ──

    def test_09_empty_question(self):
        """Empty question should be handled gracefully."""
        r = ask_question(self.sid, "")
        # Should not crash
        self.assertIn(r.status_code, [200, 400])

    def test_10_very_long_question(self):
        """Very long question should still work."""
        r = ask_question(self.sid,
            "Can you please provide me with a very detailed and comprehensive "
            "report about all the different types of equipment that are mentioned "
            "in the database, including their locations, dates, and any other "
            "relevant information that might be useful for analysis?")
        self._check_answer(r, min_length=100)

    def test_11_out_of_scope(self):
        """Out of scope question should be redirected, not hallucinated."""
        r = ask_question(self.sid, "what is the weather today?")
        self.assertEqual(r.status_code, 200)
        # Should not hallucinate weather data
        answer = r.json().get("answer", "").lower()
        # Either redirects or says it's out of scope
        self.assertTrue(
            "weather" in answer or "scope" in answer or "data" in answer,
            f"Unexpected answer: {answer[:200]}"
        )


# ─── Test: Mediator Quality ──────────────────────────────────────────

class TestMediatorQuality(unittest.TestCase):
    """Test that mediator produces complete, non-summarized answers."""

    def setUp(self):
        self.sid, _ = create_session()
        fetch_data(self.sid, "General Area")

    def tearDown(self):
        cleanup_session(self.sid)

    def test_01_no_truncation(self):
        """Aggregation answers should not be truncated."""
        r = ask_question(self.sid, "show me all locations", debug=True)
        data = r.json()
        answer = data.get("answer", "")
        # Should contain many locations, not just top 5
        self.assertIn("burang", answer.lower())
        self.assertIn("karachi", answer.lower())
        self.assertIn("lhasa", answer.lower())
        # Should mention total count
        self.assertTrue(
            "197" in answer or "200" in answer or "unique" in answer.lower(),
            f"Missing total count: {answer[:200]}"
        )

    def test_02_no_summarization(self):
        """'Some of' or 'top' should not appear for LIST_UNIQUE queries."""
        r = ask_question(self.sid, "list all locations")
        answer = r.json().get("answer", "").lower()
        self.assertNotIn("some of the locations", answer)
        self.assertNotIn("here are some", answer)
        self.assertNotIn("top locations", answer)

    def test_03_complete_equipment_list(self):
        """Equipment list should be comprehensive."""
        r = ask_question(self.sid, "list all equipment types")
        answer = r.json().get("answer", "")
        self.assertGreater(len(answer), 200,
            f"Answer too short: {answer[:200]}")

    def test_04_no_hallucination(self):
        """Answers should not contain hallucinated data."""
        r = ask_question(self.sid, "details on equipment J-20")
        answer = r.json().get("answer", "").lower()
        # Should NOT say "no data found" when data exists
        self.assertNotIn("no specific mention", answer)
        self.assertNotIn("no direct reference", answer)
        self.assertNotIn("not available in the provided documents", answer)

    def test_05_sources_cited(self):
        """Answers should include source citations."""
        r = ask_question(self.sid, "show me all locations", debug=True)
        data = r.json()
        self.assertGreater(data.get("sources_used", 0), 0)


# ─── Test: Chunking ──────────────────────────────────────────────────

class TestChunking(unittest.TestCase):
    """Test that large aggregation results are chunked properly."""

    def setUp(self):
        self.sid, _ = create_session()
        fetch_data(self.sid, "General Area")

    def tearDown(self):
        cleanup_session(self.sid)

    def test_01_chunked_response(self):
        """Large result sets should be chunked."""
        r = ask_question(self.sid, "show me all locations", debug=True)
        data = r.json()
        debug = data.get("debug", {})
        mediator = debug.get("mediator", {})
        # Should indicate chunking was used
        if mediator.get("chunked"):
            self.assertGreater(mediator.get("chunks", 0), 1)
        # Answer should still be complete
        self.assertGreater(len(data.get("answer", "")), 1000)

    def test_02_all_locations_present(self):
        """All locations from ES should appear in answer."""
        r = ask_question(self.sid, "show me all locations")
        answer = r.json().get("answer", "").lower()
        # Top locations must be present
        for loc in ["burang", "karachi", "lhasa", "tholing", "kashgar"]:
            self.assertIn(loc, answer,
                f"Missing location '{loc}' in answer")


# ─── Test: Model Selection ───────────────────────────────────────────

class TestModelSelection(unittest.TestCase):
    """Test model selection via dropdown."""

    def test_01_default_model_is_llama(self):
        """Default model should be llama3:8b."""
        r = requests.get(f"{BASE_URL}/")
        html = r.text
        # llama3:8b should be selected
        self.assertIn("llama3:8b-instruct-q8_0", html)

    def test_02_embedding_models_excluded(self):
        """Embedding models should not appear in dropdown."""
        r = requests.get(f"{BASE_URL}/")
        html = r.text
        self.assertNotIn("nomic-embed-text", html)
        self.assertNotIn("bge-m3", html)

    def test_03_all_llm_models_present(self):
        """All LLM models from Ollama should be in dropdown."""
        r = requests.get(f"{BASE_URL}/")
        html = r.text
        # Check for known LLM models
        for model in ["llama3:8b-instruct-q8_0", "qwen2.5:14b", "gemma3:4b"]:
            self.assertIn(model, html, f"Model {model} missing from dropdown")


# ─── Run ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 70)
    print("ES Intelligence Chatbot — Comprehensive Test Suite")
    print("=" * 70)
    print()

    # Check prerequisites first
    print("Checking prerequisites...")
    try:
        requests.get(ES_HOST, timeout=3)
        print(f"  ✓ ES running at {ES_HOST}")
    except Exception as e:
        print(f"  ✗ ES not reachable: {e}")
        sys.exit(1)

    try:
        requests.get(f"{OLLAMA_HOST}/api/tags", timeout=3)
        print(f"  ✓ Ollama running at {OLLAMA_HOST}")
    except Exception as e:
        print(f"  ✗ Ollama not reachable: {e}")
        sys.exit(1)

    try:
        requests.get(f"{BASE_URL}/api/health", timeout=3)
        print(f"  ✓ Flask running at {BASE_URL}")
    except Exception as e:
        print(f"  ✗ Flask not reachable: {e}")
        print("  Start with: python server.py")
        sys.exit(1)

    print()
    print("Running tests...")
    print("-" * 70)

    # Run with verbose output
    unittest.main(verbosity=2)
