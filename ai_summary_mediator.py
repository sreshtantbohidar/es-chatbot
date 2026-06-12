"""
AI Summary Module — OpenClaw Mediator + Chunking Logic
=======================================================
Replacement for the basic ai_analysis_summary_check LLM call.
Uses the same agentic mediator pattern as the main es_chatbot project.

This module is designed to be imported into the existing ai_summary script
with minimal changes to the rest of the codebase.
"""

import json
import time
import requests
from typing import List, Optional

# ─── Configuration (from existing constants) ─────────────────────────
# These are imported from the parent script's constants:
# LLM_IP, LLM_PORT, LLM_MODEL, OLLAMA_TIMEOUT, MAX_RETRIES

OLLAMA_TIMEOUT = 900   # 15 min max
MAX_RETRIES = 3
CHUNK_MAX_TOKENS = 2200       # per chunk input
CHUNK_RESPONSE_TOKENS = 800   # per chunk output
FINAL_RESPONSE_TOKENS = 1500  # final consolidation output
MAX_CONTEXT_TOKENS = 32000    # max context for mediator


# ─── Token Counting ──────────────────────────────────────────────────

def count_words_and_tokens(text: str):
    word_count = 0
    prev_space = True
    for ch in text:
        is_space = ch.isspace()
        if prev_space and not is_space:
            word_count += 1
        prev_space = is_space
    token_estimate = int(word_count * 1.3)
    return word_count, token_estimate


def count_tokens_approx(text):
    word_count = 0
    prev_space = True
    for ch in text:
        is_space = ch.isspace()
        if prev_space and not is_space:
            word_count += 1
        prev_space = is_space
    return int(word_count * 1.3)


# ─── Chunking ────────────────────────────────────────────────────────

def build_chunks_from_lines(lines, max_tokens=CHUNK_MAX_TOKENS):
    """Split data lines into chunks that fit within token limits."""
    chunks = []
    current_chunk = []
    current_tokens = 0

    for line in lines:
        line_tokens = int(len(line.split()) * 1.3)

        if current_tokens + line_tokens > max_tokens and current_chunk:
            chunks.append("\n\n".join(current_chunk))
            current_chunk = []
            current_tokens = 0

        current_chunk.append(line)
        current_tokens += line_tokens

    if current_chunk:
        chunks.append("\n\n".join(current_chunk))

    return chunks


# ─── LLM Call (compatible with existing get_llm_response) ────────────

def get_llm_response_mediator(query: str, llm_model: str, max_tokens: int = 1200,
                               base_url: str = None) -> str:
    """
    Drop-in replacement for get_llm_response() with mediator-style prompting.
    Uses the same Ollama endpoint but with enhanced instructions.
    """
    if base_url is None:
        base_url = f"http://{LLM_IP}:{LLM_PORT}/api/generate"

    prompt = query.replace("\n", " ").strip()

    payload = {
        "model": llm_model,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": 0.1,
            "top_p": 0.9,
            "num_predict": max_tokens
        }
    }

    for attempt in range(MAX_RETRIES):
        try:
            r = requests.post(base_url, json=payload, timeout=OLLAMA_TIMEOUT)
            if r.status_code == 200:
                return r.json().get("response", "")
            print(f"[ERROR] Ollama status {r.status_code}: {r.text}")
        except requests.exceptions.Timeout:
            print(f"[ERROR] Timeout (attempt {attempt+1}/{MAX_RETRIES})")
        except Exception as e:
            print(f"[ERROR] {str(e)}")
        time.sleep(2)

    raise Exception("LLM request failed after retries")


# ─── Mediator System Prompt ──────────────────────────────────────────

_MEDIATOR_SYSTEM_PROMPT = """You are a military intelligence analyst assistant.

RULES:
- Answer based ONLY on the provided documents.
- Quote specific names, numbers, locations, dates.
- Use bullet points for lists.
- Be thorough and complete. Do NOT summarize or truncate.
- When listing items, include ALL items from the data.
- If the data directly answers the question, output it fully.
- NEVER say "no data found" when data is provided.
- Output should be in HTML format: h2 for titles, p for paragraphs, ul/li for lists."""


# ─── Main Replacement Function ───────────────────────────────────────

def ai_summary_with_mediator(data_lines: List[str], base_prompt: str,
                              model_name: str, extra_prompt: str = "") -> str:
    """
    Process data lines through the OpenClaw mediator with chunking.
    
    This replaces the simple get_llm_response() call in ai_analysis_summary_check.
    
    Args:
        data_lines: List of formatted data strings (one per document)
        base_prompt: The analysis prompt from the database
        model_name: Ollama model name to use
        extra_prompt: Additional instructions (e.g., HTML formatting note)
    
    Returns:
        Complete HTML-formatted analysis string
    """
    if not data_lines:
        return ""

    data_string = "\n\n".join(data_lines)
    full_prompt = data_string + "\n\n" + base_prompt + extra_prompt

    words, total_tokens = count_words_and_tokens(full_prompt)
    print(f"[INFO] Words: {words}, Approx Tokens: {total_tokens}")

    # ── Case 1: Safe size — single LLM call ──
    if total_tokens < 3000:
        print("[INFO] Safe size → single LLM call")
        return get_llm_response_mediator(full_prompt, model_name, max_tokens=1200)

    # ── Case 2: Large input → chunked processing with mediator ──
    print("[INFO] Large input detected → Using hierarchical chunking with mediator")

    chunks = build_chunks_from_lines(data_lines, max_tokens=CHUNK_MAX_TOKENS)
    print(f"[INFO] Processing {len(chunks)} chunks...")

    chunk_summaries = []
    chunk_times = []

    for idx, chunk in enumerate(chunks):
        chunk_start = time.time()

        # Each chunk gets the base prompt + mediator instructions
        chunk_prompt = (
            f"{_MEDIATOR_SYSTEM_PROMPT}\n\n"
            f"Data (part {idx+1}/{len(chunks)}):\n{chunk}\n\n"
            f"Instructions:\n{base_prompt}\n{extra_prompt}\n\n"
            f"Provide a thorough analysis of this data chunk. "
            f"Include ALL relevant details. Do NOT summarize."
        )

        summary = get_llm_response_mediator(
            chunk_prompt, model_name, max_tokens=CHUNK_RESPONSE_TOKENS
        )
        chunk_summaries.append(summary)

        chunk_time = time.time() - chunk_start
        chunk_times.append(chunk_time)
        avg_time = sum(chunk_times) / len(chunk_times)
        remaining = len(chunks) - (idx + 1)
        eta = avg_time * remaining

        print(
            f"[CHUNK {idx+1}/{len(chunks)}] "
            f"Time: {chunk_time:.2f}s | Avg: {avg_time:.2f}s | ETA: {eta/60:.2f}m"
        )

    total_chunk_time = time.time() - (time.time() - sum(chunk_times))
    print(f"[INFO] All chunks completed in {total_chunk_time/60:.2f} minutes")

    # ── Final consolidation through mediator ──
    combined_text = "\n\n".join(chunk_summaries)

    final_prompt = (
        f"{_MEDIATOR_SYSTEM_PROMPT}\n\n"
        f"Combined analysis from {len(chunks)} data chunks:\n\n"
        f"{combined_text}\n\n"
        f"Original instructions:\n{base_prompt}\n{extra_prompt}\n\n"
        f"Provide a comprehensive, consolidated intelligence report. "
        f"Include ALL findings from all chunks. Connect dots across data. "
        f"Be thorough with names, locations, dates, and analysis."
    )

    # Check if final prompt itself needs chunking
    _, final_tokens = count_words_and_tokens(final_prompt)
    if final_tokens > 3000:
        print(f"[INFO] Final prompt also large ({final_tokens} tokens) → splitting final call")
        # Split chunk summaries into groups and do a second-level consolidation
        mid = len(chunk_summaries) // 2
        first_half = ai_summary_with_mediator(
            chunk_summaries[:mid], base_prompt, model_name, extra_prompt
        )
        second_half = ai_summary_with_mediator(
            chunk_summaries[mid:], base_prompt, model_name, extra_prompt
        )
        return first_half + "\n\n" + second_half

    return get_llm_response_mediator(final_prompt, model_name, max_tokens=FINAL_RESPONSE_TOKENS)


# ─── Drop-in Replacement for ai_analysis_summary_check ──────────────

def ai_analysis_summary_check_replacement(
    data_lines: List[str],
    base_prompt: str,
    model_name: str,
    search_form_type: str = ""
) -> str:
    """
    Drop-in replacement for the LLM call section of ai_analysis_summary_check.
    
    Usage in the existing script (replace the chunking/LLM section):
    
    OLD CODE:
        words, total_tokens = count_words_and_tokens(llm_prompt)
        if total_tokens < 3000:
            temp_llm_response = get_llm_response(full_prompt, model_name)
        else:
            chunks = build_chunks_from_lines(data_lines, max_tokens=2200)
            # ... chunk processing ...
            temp_llm_response = get_llm_response(final_prompt, model_name, max_tokens=1500)
        temp_llm_response = f"<div>{temp_llm_response}</div><br>"
        llm_response += temp_llm_response
    
    NEW CODE:
        from ai_summary_mediator import ai_analysis_summary_check_replacement
        extra_prompt = "\\n\\n(PLEASE NOTE: The response you will give should be in html...)"
        llm_response += ai_analysis_summary_check_replacement(
            data_lines, base_prompt, model_name, search_form_type
        )
    """
    extra_prompt = (
        "\n\n(PLEASE NOTE: The response you will give should be in html"
        "(hyper text markup language). Any title in the response should be "
        "in h2 tag and paragraph should be in p tag.)"
    )

    result = ai_summary_with_mediator(
        data_lines=data_lines,
        base_prompt=base_prompt,
        model_name=model_name,
        extra_prompt=extra_prompt
    )

    return f"<div>{result}</div><br>"
