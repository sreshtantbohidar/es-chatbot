"""
Patch file: How to integrate ai_summary_mediator.py into the existing ai_summary script
======================================================================================

This file shows the EXACT changes needed in the original ai_summary script
to replace the basic LLM chunking with the OpenClaw mediator + chunking logic.

STEP 1: Copy ai_summary_mediator.py to the same directory as your ai_summary script.

STEP 2: Add this import at the top of your ai_summary script (with the other imports):
    from ai_summary_mediator import ai_analysis_summary_check_replacement

STEP 3: Replace the LLM chunking section in ai_analysis_summary_check().

Find this block (around line 300-340 in the original script):

    # OLD CODE — Replace this entire block:
    # ──────────────────────────────────────────────────────────────────
    words, total_tokens = count_words_and_tokens(llm_prompt)
    print("[INFO] Words:", words)
    print("[INFO] Approx Tokens:", total_tokens)

    if total_tokens < 3000:
        temp_llm_response = get_llm_response(full_prompt, model_name)
    else:
        print("[INFO] Large input detected → Using hierarchical chunking")
        chunks = build_chunks_from_lines(data_lines, max_tokens=2200)
        print(f"[INFO] Processing {len(chunks)} chunks...")
        chunk_summaries = []
        chunk_times = []
        chunk_loop_start = time.time()
        for idx, chunk in enumerate(tqdm(chunks, desc="LLM Chunk Processing", unit="chunk")):
            single_chunk_start = time.time()
            chunk_prompt = chunk + "\\n\\n" + base_prompt + extra_prompt
            summary = get_llm_response(chunk_prompt, model_name, max_tokens=800)
            chunk_summaries.append(summary)
            chunk_time = time.time() - single_chunk_start
            chunk_times.append(chunk_time)
            avg_time = sum(chunk_times) / len(chunk_times)
            remaining = len(chunks) - (idx + 1)
            eta = avg_time * remaining
            print(f"[CHUNK {idx+1}/{len(chunks)}] Time: {chunk_time:.2f}s | Avg: {avg_time:.2f}s | ETA: {eta/60:.2f}m")
        total_chunk_time = time.time() - chunk_loop_start
        print(f"[INFO] All chunks completed in {total_chunk_time/60:.2f} minutes")
        combined_text = "\\n\\n".join(chunk_summaries)
        final_prompt = combined_text + "\\n\\n" + base_prompt + extra_prompt
        temp_llm_response = get_llm_response(final_prompt, model_name, max_tokens=1500)
    temp_llm_response = f"<div>{temp_llm_response}</div><br>"
    llm_response += temp_llm_response
    # ──────────────────────────────────────────────────────────────────

REPLACE WITH:

    # NEW CODE — OpenClaw Mediator + Chunking
    # ──────────────────────────────────────────────────────────────────
    from ai_summary_mediator import ai_analysis_summary_check_replacement

    extra_prompt = "\\n\\n(PLEASE NOTE: The response you will give should be in html(hyper text markup language). Any title in the response should be in h2 tag and paragraph should be in p tag.)"

    llm_response += ai_analysis_summary_check_replacement(
        data_lines=data_lines,
        base_prompt=base_prompt,
        model_name=model_name,
        search_form_type=search_form_type
    )
    # ──────────────────────────────────────────────────────────────────

That's it! The rest of the script (trends, change detection, tabbed HTML, DB updates)
remains completely unchanged.

WHAT CHANGES:
- The LLM now receives a mediator system prompt that instructs it to:
  - Use ONLY the provided documents (no hallucination)
  - Include ALL items (no summarization/truncation)
  - Output in HTML format
- Large inputs are chunked with proper mediator instructions per chunk
- Final consolidation also goes through the mediator
- If the final prompt is too large, it does a second-level consolidation

WHAT DOESN'T CHANGE:
- get_llm_response() function — still used internally
- build_chunks_from_lines() — still used internally
- count_words_and_tokens() — still used internally
- ai_trends, ai_change detection — completely untouched
- tabbed HTML generation — completely untouched
- DB update functions — completely untouched
- Main loop (run_ai_analysis_summary_loop) — completely untouched
- All other functions — completely untouched
