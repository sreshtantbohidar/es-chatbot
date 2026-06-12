#!/usr/bin/env python3
"""
Interactive CLI chat loop with conversation memory.
"""
import sys, time

sys.path.insert(0, "/home/sresht/Documents/es_chatbot")
from engine import ChatEngine, FetchRequest, ChatRequest, EsConfig, LlmConfig, make_es_client, ChatSession

ES_HOST = "http://192.168.1.16:9200"
ES_USER = "elastic"
ES_PASS = os.getenv("ES_PASS", "uHMkl_b8DuAskF2E1h5x")
OLLAMA_URL = os.getenv("LLM_BASE_URL", "http://192.168.1.125:11434/v1")
MODEL = os.getenv("LLM_MODEL")
TIMEOUT = int(os.getenv("LLM_TIMEOUT", "180"))
CATEGORY = "Overall Deployment"
MAX_TURNS = 10

def print_banner():
    print("=" * 60)
    print("  🔍 ES Intelligence Chatbot — Session Mode")
    print(f"  Model: {MODEL}  |  Memory: {MAX_TURNS} turns")
    print("=" * 60)

def fetch_data(eng):
    print("\n📥 Fetching data from Elasticsearch...")
    t0 = time.time()
    result = eng.fetch_data(FetchRequest(mode="category", category=CATEGORY))
    elapsed = time.time() - t0
    print(f"  ✅ Fetched {result.total_hits} docs in {elapsed:.1f}s")
    print(f"  📦 Stored {len(eng.store.documents)} unique docs (after dedup)")
    if result.warnings:
        for w in result.warnings:
            print(f"  ⚠️  {w}")
    print(f"\n  💬 Session started. {MAX_TURNS} exchanges available.")
    print(f"  Commands: 'quit' | 'status' | 'reset'")
    print("-" * 60)

def ask_with_mediator(eng, question):
    """Ask a question — mediator decides RAG vs DIRECT, presents answer."""
    t0 = time.time()
    resp = eng.ask(ChatRequest(question=question), debug=False, mediate=True)
    elapsed = time.time() - t0

    mode = (resp.debug or {}).get("mode", "?")

    # Session full
    if mode == "session-full":
        print(f"\n{resp.answer}")
        return False  # signal to stop

    # Show progress indicator for RAG questions
    if mode in ("direct", "agg-COUNT", "agg-TOP_N", "agg-LIST_UNIQUE", "agg-GROUP_BY"):
        # Fast answer — just show the response
        pass
    else:
        # RAG answer — show brief progress
        pass

    print(f"\n{resp.answer}")
    print(f"  ⏱ {elapsed:.1f}s  |  Turn {eng.session.turns_used}/{eng.session.max_turns}")
    return True

def main():
    print_banner()

    es = make_es_client(EsConfig(hosts=ES_HOST, username=ES_USER, password=ES_PASS))
    session = ChatSession(max_turns=MAX_TURNS)
    eng = ChatEngine(es, LlmConfig(base_url=OLLAMA_URL, api_key="ollama", model=MODEL, timeout=TIMEOUT), session=session)

    fetch_data(eng)

    while True:
        remaining = eng.session.turns_remaining
        try:
            user_input = input(f"\n🤔 You ({remaining} left): ").strip()
        except (EOFError, KeyboardInterrupt):
            print(f"\n👋 Session ended. {eng.session.summarize_session()}")
            break

        if not user_input:
            continue

        lower = user_input.lower()
        if lower in ("quit", "exit", "q"):
            print(f"\n👋 Session ended. {eng.session.summarize_session()}")
            break
        elif lower == "status":
            s = eng.session
            print(f"  Turns used: {s.turns_used}/{s.max_turns}")
            print(f"  Total questions: {s._metadata['total_questions']}")
            print(f"  RAG questions: {s._metadata['rag_questions']}")
            print(f"  Direct questions: {s._metadata['direct_questions']}")
            print(f"  Session started: {s.created_at.strftime('%H:%M:%S')}")
            continue
        elif lower == "reset":
            eng.session.reset()
            print(f"  🔄 Session reset. {MAX_TURNS} turns available.")
            continue

        should_continue = ask_with_mediator(eng, user_input)
        if not should_continue:
            break

if __name__ == "__main__":
    main()
