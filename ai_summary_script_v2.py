"""
AI Analysis Summary — Main Script
===================================
Polls PostgreSQL for pending AI analysis jobs and processes them.

Features:
- --ai_summary: LLM-based summary generation with OpenClaw mediator + chunking
- --ai_trends: Trend analysis per category
- --ai_change: Change detection analysis

Usage:
    python ai_summary_script.py --ai_summary
    python ai_summary_script.py --ai_summary --ai_trends --ai_change
"""

import argparse
import json
import time
import base64
import traceback
from datetime import datetime
import multiprocessing
import pandas as pd
import psycopg2
import requests
import sys
from elasticsearch import Elasticsearch
import importlib.util
import os
import re
from tqdm import tqdm
from typing import List

# ─── Load Constants ──────────────────────────────────────────────────
file_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'constants.py'))
spec = importlib.util.spec_from_file_location("constants", file_path)
constants = importlib.util.module_from_spec(spec)
spec.loader.exec_module(constants)

PG_DB_NAME = constants.PG_DB_NAME
DJANGO_HOST = constants.DJANGO_HOST
CUREENT_INDEX_NAME = constants.CUREENT_INDEX_NAME
ELASTIC_HOST = constants.ELASTIC_HOST
ELASTIC_PORT = constants.ELASTIC_PORT
PG_USER = constants.PG_USER
PG_PORT = constants.PG_PORT
PG_PASSWORD = constants.PG_PASSWORD
LLM_IP = constants.LLM_IP
LLM_PORT = constants.LLM_PORT
LLM_MODEL = constants.LLM_MODEL

OLLAMA_TIMEOUT = 900
MAX_RETRIES = 3

# ─── Mediator Configuration ──────────────────────────────────────────
CHUNK_MAX_TOKENS = 2200       # per chunk input
CHUNK_RESPONSE_TOKENS = 800   # per chunk output
FINAL_RESPONSE_TOKENS = 1500  # final consolidation output

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

# ─── Imports from project modules ────────────────────────────────────
# These are imported at runtime to avoid circular imports
_sitrep_main = None
_infra_main = None
_trends_sam_main = None
_trends_airfield_main = None
_training_main = None
_force_disposition_main = None
_run_change_detection = None

def _lazy_import():
    """Lazy import project modules to avoid circular dependencies."""
    global _sitrep_main, _infra_main, _trends_sam_main
    global _trends_airfield_main, _training_main, _force_disposition_main
    global _run_change_detection
    if _sitrep_main is None:
        from test_sitrep_trends import sitrep_main as _sitrep_main
        from test_infra_trends import infra_main as _infra_main
        from test_sam_trends import trends_sam_main as _trends_sam_main
        from test_airinspect_trends import trends_airfield_main as _trends_airfield_main
        from test_training_trends import training_main as _training_main
        from test_force_disposition_trends import force_disposition_main as _force_disposition_main
        from change_detect_v2 import run_change_detection as _run_change_detection

# ─── Elasticsearch ───────────────────────────────────────────────────
es = Elasticsearch([{"host": ELASTIC_HOST, "port": ELASTIC_PORT, "scheme": "http"}])

# ─── PostgreSQL ──────────────────────────────────────────────────────

def postgres_connection():
    return psycopg2.connect(
        database=PG_DB_NAME, host=DJANGO_HOST, user=PG_USER,
        password=PG_PASSWORD, port=PG_PORT,
    )

# ─── HTML Helpers ────────────────────────────────────────────────────

def _strip_wrappers(html: str) -> str:
    html = re.sub(r'</?html[^>]*>', '', html, flags=re.I)
    html = re.sub(r'<head[^>]*>.*?</head>', '', html, flags=re.I | re.S)
    html = re.sub(r'</?body[^>]*>', '', html, flags=re.I)
    return html.strip()


def build_tabbed_html(html_strings: List[str]) -> str:
    labels = ["AI Summary", "AI Trends", "AI Change Detection"]
    sections = []
    for i, (label, content) in enumerate(zip(labels, html_strings)):
        if content:
            section_content = _strip_wrappers(content) if content else "<p>No data available</p>"
            sections.append(f'''
            <section class="report-section">
                <div class="section-header" id="section-{i}">
                    <h2>{label}</h2>
                </div>
                <div class="section-content">
                    {section_content}
                </div>
            </section>''')

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>AI Reports – Summary | Trends | Change</title>
  <style>
    body {{ margin:0; font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;
           background:#f3f5f7; color:#212529; line-height:1.6; }}
    header {{ background:#004085; color:#fff; padding:20px 40px; }}
    .report-container {{ max-width:1200px; margin:0 auto; padding:20px; }}
    .section-header {{ background:#fff; padding:15px 25px; border-left:4px solid #004085;
                      margin:20px 0 10px 0; box-shadow:0 1px 3px rgba(0,0,0,0.1); }}
    .section-header h2 {{ margin:0; color:#004085; font-size:1.5em; }}
    .section-content {{ background:#fff; padding:25px; border-radius:4px;
                      box-shadow:0 1px 3px rgba(0,0,0,0.1); margin-bottom:30px; }}
    footer {{ padding:15px 40px; background:#e9ecef; font-size:.8em; color:#6c757d; text-align:center; }}
  </style>
</head>
<body>
  <header><h1>AI Intelligence Report</h1><p>Generated on: {now}</p></header>
  <div class="report-container">{''.join(sections)}</div>
  <footer>Report automatically generated by AI Analysis System</footer>
</body>
</html>"""

# ─── Token Counting ──────────────────────────────────────────────────

def count_words_and_tokens(text: str):
    word_count = 0
    prev_space = True
    for ch in text:
        is_space = ch.isspace()
        if prev_space and not is_space:
            word_count += 1
        prev_space = is_space
    return word_count, int(word_count * 1.3)


def count_tokens_approx(text):
    return int(len(text.split()) * 1.3)


# ─── Chunking ────────────────────────────────────────────────────────

def build_chunks_from_lines(lines, max_tokens=CHUNK_MAX_TOKENS):
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

# ─── LLM Call ───────────────────────────────────────────────────────

def get_llm_response(query, llm_model, max_tokens=1200):
    ollama_url = f"http://{LLM_IP}:{LLM_PORT}/api/generate"
    payload = {
        "model": llm_model,
        "prompt": query.replace("\n", " ").strip(),
        "stream": False,
        "options": {"temperature": 0.1, "top_p": 0.9, "num_predict": max_tokens}
    }
    for attempt in range(MAX_RETRIES):
        try:
            r = requests.post(ollama_url, json=payload, timeout=OLLAMA_TIMEOUT)
            if r.status_code == 200:
                return r.json().get("response", "")
            print(f"[ERROR] Ollama status {r.status_code}: {r.text}")
        except requests.exceptions.Timeout:
            print(f"[ERROR] Timeout (attempt {attempt+1}/{MAX_RETRIES})")
        except Exception as e:
            print(f"[ERROR] {str(e)}")
        time.sleep(2)
    raise Exception("LLM request failed after retries")

# ─── OpenClaw Mediator + Chunking ────────────────────────────────────

def ai_summary_with_mediator(data_lines: List[str], base_prompt: str,
                              model_name: str, extra_prompt: str = "") -> str:
    """
    Process data lines through the OpenClaw mediator with chunking.
    Replaces the basic LLM chunking in the original ai_analysis_summary_check.
    """
    if not data_lines:
        return ""

    data_string = "\n\n".join(data_lines)
    full_prompt = data_string + "\n\n" + base_prompt + extra_prompt
    words, total_tokens = count_words_and_tokens(full_prompt)
    print(f"[INFO] Words: {words}, Approx Tokens: {total_tokens}")

    # Case 1: Safe size — single LLM call with mediator prompt
    if total_tokens < 3000:
        print("[INFO] Safe size → single LLM call with mediator")
        mediator_prompt = (
            f"{_MEDIATOR_SYSTEM_PROMPT}\n\n"
            f"Data:\n{data_string}\n\n"
            f"Instructions:\n{base_prompt}\n{extra_prompt}\n\n"
            f"Provide a thorough analysis. Include ALL relevant details. Do NOT summarize."
        )
        return get_llm_response(mediator_prompt, model_name, max_tokens=1200)

    # Case 2: Large input → chunked processing with mediator
    print("[INFO] Large input detected → Using hierarchical chunking with mediator")
    chunks = build_chunks_from_lines(data_lines, max_tokens=CHUNK_MAX_TOKENS)
    print(f"[INFO] Processing {len(chunks)} chunks...")

    chunk_summaries = []
    chunk_times = []

    for idx, chunk in enumerate(tqdm(chunks, desc="LLM Chunk Processing", unit="chunk")):
        chunk_start = time.time()
        chunk_prompt = (
            f"{_MEDIATOR_SYSTEM_PROMPT}\n\n"
            f"Data (part {idx+1}/{len(chunks)}):\n{chunk}\n\n"
            f"Instructions:\n{base_prompt}\n{extra_prompt}\n\n"
            f"Provide a thorough analysis of this data chunk. "
            f"Include ALL relevant details. Do NOT summarize."
        )
        summary = get_llm_response(chunk_prompt, model_name, max_tokens=CHUNK_RESPONSE_TOKENS)
        chunk_summaries.append(summary)
        chunk_time = time.time() - chunk_start
        chunk_times.append(chunk_time)
        avg_time = sum(chunk_times) / len(chunk_times)
        remaining = len(chunks) - (idx + 1)
        eta = avg_time * remaining
        print(f"[CHUNK {idx+1}/{len(chunks)}] Time: {chunk_time:.2f}s | Avg: {avg_time:.2f}s | ETA: {eta/60:.2f}m")

    # Final consolidation through mediator
    combined_text = "\n\n".join(chunk_summaries)
    _, final_tokens = count_words_and_tokens(combined_text + base_prompt)

    if final_tokens > 3000:
        print(f"[INFO] Final prompt also large ({final_tokens} tokens) → second-level consolidation")
        mid = len(chunk_summaries) // 2
        first = ai_summary_with_mediator(chunk_summaries[:mid], base_prompt, model_name, extra_prompt)
        second = ai_summary_with_mediator(chunk_summaries[mid:], base_prompt, model_name, extra_prompt)
        return first + "\n\n" + second

    final_prompt = (
        f"{_MEDIATOR_SYSTEM_PROMPT}\n\n"
        f"Combined analysis from {len(chunks)} data chunks:\n\n"
        f"{combined_text}\n\n"
        f"Original instructions:\n{base_prompt}\n{extra_prompt}\n\n"
        f"Provide a comprehensive, consolidated intelligence report. "
        f"Include ALL findings from all chunks. Connect dots across data."
    )
    return get_llm_response(final_prompt, model_name, max_tokens=FINAL_RESPONSE_TOKENS)

# ─── JSON Correction ─────────────────────────────────────────────────

def correct_json_format(json_str):
    open_curly_count = 0
    open_square_count = 0
    result = []
    prev_b = []
    prev_inverted = 0
    prev_inverted_array = []
    json_str = (json_str.replace(", ", ",").replace("\n", "").replace("\r", "")
                .replace(" }", "}").replace("} ", "}").replace("{ ", "{")
                .replace(" {", "{").replace(" [", "[").replace("[ ", "[")
                .replace(" ]", "]").replace("] ", "]").strip())
    for char in json_str:
        if char == '"':
            if prev_inverted == 0:
                prev_inverted = 1
                prev_inverted_array.append('"')
            else:
                prev_inverted = 0
                prev_inverted_array.pop()
        if char == "{":
            open_curly_count += 1
            prev_b.append(char)
            result.append(char)
        elif char == "[":
            open_square_count += 1
            prev_b.append(char)
            result.append(char)
        elif char == "}":
            if prev_inverted == 1:
                result.append('"')
                prev_inverted = 0
                prev_inverted_array.pop()
            if prev_b[-1] == "[":
                result.append("]")
            prev_b.pop()
            result.append(char)
        elif char == "]":
            if prev_inverted == 1:
                result.append('"')
                prev_inverted = 0
                prev_inverted_array.pop()
            if prev_b[-1] == "{":
                result.append("}")
            prev_b.pop()
            result.append(char)
        else:
            result.append(char)
    for p_b in prev_b[::-1]:
        if p_b == "{":
            result.append("}")
        if p_b == "[":
            result.append("]")
    result = "".join(result)
    result = result.replace(",}", "}").replace(",]", "]").strip()
    try:
        return json.loads(result)
    except Exception as e:
        traceback.print_exc()
        print("[!]json load failed:", e)
        return {"summary": result}

# ─── DB Update Functions ─────────────────────────────────────────────

def update_imint_ai_analysis(cursor, imint_ai_analysis_id, ai_analysis_text):
    q = """UPDATE public.imint_ai_analysis SET status=%d,ai_analysis_text='%s' WHERE imint_ai_analysis_id=%d;"""
    cursor.execute(q % (1, ai_analysis_text, imint_ai_analysis_id))


def update_ai_analysis_summary_query_text(cursor, ai_analysis_summary_id, query_text):
    q = """UPDATE public.ai_analysis_summary SET query_status=%d,query_text='%s' WHERE ai_analysis_summary_id=%d;"""
    cursor.execute(q % (1, query_text, ai_analysis_summary_id))

# ─── Elasticsearch ───────────────────────────────────────────────────

def get_data_from_elastic(elastic_query):
    try:
        return es.search(index=CUREENT_INDEX_NAME, body=elastic_query)
    except Exception as e:
        print(f"[error] ES query failed: {e}")
        return None

# ─── Profile Analysis Prompt ─────────────────────────────────────────

def create_llm_prompt_for_profile(complete_summary_dict_list, search_form_type, person_names, organization_names):
    summary_question = {'profile analysis': '''"%s"\n\n"%s"'''}
    activity_question = summary_question[search_form_type]
    query_string = ""
    if person_names and organization_names:
        query_string = "Create the summary of person" + ", ".join(person_names) + " and organization " + ", ".join(organization_names) + " in mentioned list of dictionary and create relation and summary of each other with refrence of date and file paths."
    elif person_names:
        query_string = '''Deep dive and create a analysis of " ''' + ", ".join(person_names) + '''" from below json data description, the analysis should have all the personal details, involvement in any activity and his relations with other people, mention the relationship names with other people and create html table also mention the reference of file name along with your analysis". The output should be in html format. Title should be h2 with font-size:20px and paragraph should be in p tag with font-size:15px'''
    elif organization_names:
        query_string = "Create the summary of organization in above list of dictionary and create a summary of " + ", ".join(organization_names)
    if query_string:
        return activity_question % (str(query_string), str(complete_summary_dict_list))

# ─── Type Mapping (unchanged) ────────────────────────────────────────

type_mapping = {
    "infra": {
        "types": ["infra development analysis", "event infra development analysis"],
        "fields": ["infra_type", "location_name", "activity_date", "coordinates", "description"],
        "line_format": "infra_type:{infra_type}, location_name:{location_name}, date: {activity_date}, coordinates: {coordinates}, description:{description}",
    },
    "training": {
        "types": ["training areas analysis", "event training areas analysis"],
        "fields": ["enemy_formation_name", "location_name", "description"],
        "line_format": "enemy_formation_name:{enemy_formation_name}, location_name:{location_name}, description:{description}",
    },
    "general": {
        "types": ["general area analysis", "event general area analysis"],
        "fields": ["location_name", "coordinates", "description"],
        "line_format": "location_name:{location_name}, coordinates:{coordinates}, description:{description}",
    },
    "force": {
        "types": ["force disposition analysis", "event force disposition analysis"],
        "fields": ["location_name", "coordinates", "base_location_name", "base_coordinates", "enemy_formation_name", "orbate_title", "description"],
        "line_format": "location_name:{location_name}, coordinates:{coordinates}, base_location_name:{base_location_name}, base_coordinates:{base_coordinates}, enemy_formation_name:{enemy_formation_name}, orbate_title:{orbate_title}, description:{description}",
    },
    "sitrep": {
        "types": ["pla sitrep analysis", "event pla sitrep analysis"],
        "fields": ["pass_name", "transgression_sighting_type", "sub_activity_type", "description"],
        "line_format": "pass_name:{pass_name},transgression_sighting_type:{transgression_sighting_type}, sub_activity_type:{sub_activity_type}, description:{description}",
    },
    "air_aspects": {
        "types": ["air aspects analysis", "event air aspects analysis"],
        "fields": ["location_name", "coordinates", "infra_name", "infra_type", "equipment_name", "equipement_type", "count", "airfield_type"],
        "line_format": "location_name:{location_name}, coordinates:{coordinates}, infra_name:{infra_name}, infra_type:{infra_type}, equipment_name:{equipment_name}, equipment_name:{equipment_name}, count:{count}, airfield_type:{airfield_type}"
    },
    "sam_deployment_analysis": {
        "types": ["sam deployment analysis", "event sam deployment analysis"],
        "fields": ["location_name", "coordinates", "infra_name", "infra_type", "equipment_name", "equipment_type", "count"],
        "line_format": "location_name:{location_name}, coordinates:{coordinates}, infra_name:{infra_name}, infra_type:{infra_type}, equipment_name:{equipment_name}, equipment_type:{equipment_type}, count:{count}"
    },
    "mobile_interception": {
        "types": ["mobile interception analysis", "Mobile Interception Analysis"],
        "fields": ["start_location_name", "end_location_name", "opposite_to", "mobile_no", "description"],
        "line_format": "start_location_name:{start_location_name}, end_location_name:{end_location_name}, opposite_to:{opposite_to}, mobile_no:{mobile_no}, description:{description}"
    },
    "internal_security": {
        "types": ["internal security analysis", "Internal Security Analysis"],
        "fields": ["coordinates", "terrorist_casualties_", "security_forces_casualties", "civilian_casualties", "description", "army_name", "force_type_name", "formation_type", "enemy_formation_name", "command_name", "command_coordinates", "comd_tps_loc_name", "comd_tps_coordinates", "terrorists_casualties"],
        "line_format": "coordinates:{coordinates}, terrorist_casualties_:{terrorist_casualties_}, security_forces_casualties:{security_forces_casualties}, civilian_casualties:{civilian_casualties}, description:{description}, army_name:{army_name}, force_type_name:{force_type_name}, formation_type:{formation_type}, enemy_formation_name:{enemy_formation_name}, command_name:{command_name}, command_coordinates:{command_coordinates}, comd_tps_loc_name:{comd_tps_loc_name}, comd_tps_coordinates:{comd_tps_coordinates}, terrorists_casualties:{terrorists_casualties}"
    },
    "elint": {
        "types": ["elint analysis", "Elint Analysis"],
        "fields": ["description", "location_name", "coordinates", "category", "radar_type", "radar_name"],
        "line_format": "description:{description}, location_name:{location_name}, coordinates:{coordinates}, category:{category}, radar_type:{radar_type}, radar_name:{radar_name}"
    },
    "visit": {
        "types": ["visit analysis", "Visit Analysis"],
        "fields": ["description", "visit_name", "purpose", "location_name", "coordinates"],
        "line_format": "description:{description}, visit_name:{visit_name}, purpose:{purpose}, location_name:{location_name}, coordinates:{coordinates}"
    }
}

# ─── Main Processing Function (MODIFIED: mediator replaces basic chunking) ──

def ai_analysis_summary_check(row, ai_trends, ai_summ, ai_change, cursor):
    elastic_query, ai_analysis_summary_id, search_form_type = row
    search_form_type = search_form_type.lower()
    if search_form_type != 'profile analysis':
        model_prompt_dict = get_prompt_and_model(cursor, ai_analysis_summary_id)
    e_response = get_data_from_elastic(elastic_query) if elastic_query else None
    if e_response and e_response['hits']['total']['value'] > 0:
        e_hits = e_response['hits']['hits']
    else:
        e_hits = []
    ai_change_repsonse = ''
    ai_trend_response = ''
    llm_response = ''
    print(f"--{search_form_type}--")

    # ── Change Detection (unchanged) ──
    if ai_change:
        if e_hits:
            start_date = find_lt_value(elastic_query)
            if search_form_type in ["sam deployment analysis", "training areas analysis",
                                     "infra development analysis", "air aspects analysis",
                                     "pla sitrep analysis", "force disposition analysis"]:
                print(f"[INFO] Running change detection for {search_form_type}")
                _lazy_import()
                ai_change_repsonse = _run_change_detection(elastic_query, start_date=start_date)

    # ── Trends (unchanged) ──
    if ai_trends:
        if e_hits:
            start_date = find_lt_value(elastic_query)
            _lazy_import()
            if search_form_type == "sam deployment analysis":
                ai_trend_response = _trends_sam_main(start_date, elastic_query)
            elif search_form_type == "training areas analysis":
                ai_trend_response = _training_main(start_date, elastic_query)
            elif search_form_type == "infra development analysis":
                ai_trend_response = _infra_main(start_date, elastic_query)
            elif search_form_type == "air aspects analysis":
                ai_trend_response = _trends_airfield_main(start_date, elastic_query)
            elif search_form_type == "pla sitrep analysis":
                ai_trend_response = _sitrep_main(start_date, elastic_query)
            elif search_form_type == "force disposition analysis":
                ai_trend_response = _force_disposition_main(start_date, elastic_query)
            print(f"[DONE] Trend Analysis for {search_form_type}")

    # ── AI Summary (MODIFIED: uses OpenClaw mediator) ──
    if ai_summ:
        ai_summ_start_time = time.time()
        extra_prompt = "\n\n(PLEASE NOTE: The response you will give should be in html(hyper text markup language). Any title in the response should be in h2 tag and paragraph should be in p tag.)"

        if search_form_type == 'profile analysis':
            print(f"[INFO] Profile analysis [{ai_analysis_summary_id}]")
            person_names, organization_names = [], []
            if elastic_query and 'query' in elastic_query:
                must = elastic_query.get('query', {}).get('bool', {}).get('must', [])
                for cond in must:
                    if 'match_phrase_prefix' in cond:
                        for field in ['person_name', 'civil_organization.civil_organization_name', 'civil_organization_name']:
                            if field in cond['match_phrase_prefix']:
                                (person_names if 'person' in field else organization_names).append(cond['match_phrase_prefix'][field])

            if person_names or organization_names:
                all_descriptions = []
                for i, hit in enumerate(e_hits):
                    src = hit['_source']
                    if src.get('description'):
                        path = src.get('file_http_path', f'file{i}')
                        date = datetime.fromisoformat(src['@timestamp']).strftime("%Y-%m-%d") if '@timestamp' in src else ''
                        all_descriptions.append({
                            "file_path": path, "file_name": path.split('/')[-1],
                            "date": date, "description": src['description']
                        })
                if all_descriptions:
                    df = pd.DataFrame(all_descriptions)
                    grouped = df.groupby("file_name").agg({
                        "file_path": lambda x: list(set(x)),
                        "description": lambda x: list(set(x)),
                        "date": lambda x: list(set(x))
                    }).reset_index()
                    complete_summary_dict_list = grouped.to_dict(orient="records")
                    llm_prompt = create_llm_prompt_for_profile(complete_summary_dict_list, search_form_type, person_names, organization_names)
                    llm_prompt += extra_prompt
                    temp_llm_response = get_llm_response(llm_prompt, LLM_MODEL)
                    llm_response += f"<div>{temp_llm_response}</div><br>"
        else:
            # ── Type-mapped categories: use OpenClaw mediator ──
            model_name = model_prompt_dict.get("model_info")
            base_prompt = model_prompt_dict.get("prompt")

            for key, value in type_mapping.items():
                if search_form_type in value["types"]:
                    print(f"[INFO] {key} analysis [{ai_analysis_summary_id}]")
                    data_lines = []
                    for hit in e_hits:
                        source = hit["_source"]
                        try:
                            line = value["line_format"].format(**{f: source.get(f, "") for f in value["fields"]})
                            if line not in data_lines:
                                data_lines.append(line)
                        except KeyError:
                            continue

                    if data_lines:
                        print(f"[INFO] {len(data_lines)} data lines → OpenClaw mediator")
                        llm_response += ai_summary_with_mediator(
                            data_lines=data_lines,
                            base_prompt=base_prompt,
                            model_name=model_name,
                            extra_prompt=extra_prompt
                        )

        print(f"[DONE] AI analysis [{ai_analysis_summary_id}] [time={(time.time()-ai_summ_start_time):.2f}s]")

    # ── Build final report (unchanged) ──
    tabbed_html = build_tabbed_html([llm_response, ai_trend_response, ai_change_repsonse])
    ai_analysis_text_base64 = base64.b64encode(tabbed_html.encode("utf-8")).decode("utf-8")
    update_ai_analysis_summary_query_text(cursor, ai_analysis_summary_id, ai_analysis_text_base64)

# ─── IMINT Analysis (unchanged) ──────────────────────────────────────

def imint_ai_analysis_check(row, cursor):
    elastic_query, imint_ai_analysis_id = row
    model_prompt_dict = get_prompt_and_model(cursor, imint_ai_analysis_id, imint=True)
    if elastic_query:
        comments = []
        e_response = get_data_from_elastic(elastic_query)
        if e_response and e_response['hits']['total']['value'] > 0:
            for hit in e_response['hits']['hits']:
                src = hit['_source']
                if src.get("comments"):
                    loc = src.get("location_name", "")
                    date = src.get("activity_date", "")
                    comment = src['comments'][-1].strip().replace('\n', '. ')
                    entry = f"location_name: {loc}, date: {date}, comments: {comment}"
                    if entry not in comments:
                        comments.append(entry)
        if comments:
            llm_prompt = '\n\n'.join(comments) + "\n\n" + model_prompt_dict.get("prompt") + "The response you will give should be in html. Any title in h2 tag and paragraph in p tag."
            llm_response = get_llm_response(llm_prompt, model_prompt_dict.get("model_info"))
            corrected = correct_json_format(str(llm_response))
            ai_analysis_text_base64 = str(base64.b64encode(str(corrected.get("summary", "")).encode('utf-8')).decode('utf-8'))
            update_imint_ai_analysis(cursor, imint_ai_analysis_id, ai_analysis_text_base64)

# ─── Prompt/Model DB Lookup (unchanged) ──────────────────────────────

def get_prompt_and_model(cursor, primary_key, imint=False):
    table_name = "imint_ai_analysis" if imint else "ai_analysis_summary"
    cursor.execute(f"SELECT prompt, prompt_id, model_id FROM {table_name} WHERE {table_name}_id = %s;", (primary_key,))
    result = cursor.fetchone()
    if not result:
        raise Exception(f"No result found for id {primary_key}")
    prompt, prompt_id, model_id = result
    output_dict = {}
    if prompt:
        output_dict["prompt"] = prompt
    elif prompt_id:
        cursor.execute("SELECT prompt FROM prompt_master WHERE prompt_id = %s;", (prompt_id,))
        r = cursor.fetchone()
        if r:
            output_dict["prompt"] = r[0]
        else:
            raise Exception(f"Prompt not found for prompt_id {prompt_id}")
    else:
        raise Exception("Prompt ID is None!")
    if model_id:
        cursor.execute("SELECT ai_model_info FROM ai_model_master WHERE ai_model_id = %s;", (model_id,))
        r = cursor.fetchone()
        if r:
            output_dict["model_info"] = r[0]
        else:
            raise Exception(f"Model not found for model_id {model_id}")
    else:
        raise Exception("Model ID is None!")
    return output_dict

# ─── Utility Functions (unchanged) ───────────────────────────────────

def find_lt_value(data):
    if isinstance(data, dict):
        for key, value in data.items():
            if key == 'lt':
                try:
                    return datetime.fromisoformat(value).strftime('%Y-%m-%d')
                except ValueError:
                    continue
            else:
                result = find_lt_value(value)
                if result:
                    return result
    elif isinstance(data, list):
        for item in data:
            result = find_lt_value(item)
            if result:
                return result
    return None

# ─── Thread-Safe Wrappers (unchanged) ────────────────────────────────

def ai_analysis_summary_check_threadsafe(row, ai_trends, ai_summ, ai_change):
    try:
        conn = postgres_connection()
        with conn.cursor() as cursor:
            ai_analysis_summary_check(row, ai_trends, ai_summ, ai_change, cursor)
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[ERROR] {e}")
        traceback.print_exc()


def imint_ai_analysis_summary_check_threadsafe(row):
    try:
        conn = postgres_connection()
        with conn.cursor() as cursor:
            imint_ai_analysis_check(row, cursor)
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[ERROR] {e}")
        traceback.print_exc()

# ─── Row Locking (unchanged) ─────────────────────────────────────────

def lock_rows_for_processing_1(conn):
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                UPDATE public.ai_analysis_summary SET query_status = 2
                WHERE ai_analysis_summary_id IN (
                    SELECT ai_analysis_summary_id FROM public.ai_analysis_summary
                    WHERE query_status = 0 ORDER BY ai_analysis_summary_id DESC
                    FOR UPDATE SKIP LOCKED
                ) RETURNING filter_json, ai_analysis_summary_id, search_form_type;
            """)
            return cursor.fetchall()
    except psycopg2.ProgrammingError as e:
        print(f"[ERROR] {e}")
        return []


def lock_rows_for_processing_2(conn):
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                UPDATE public.imint_ai_analysis SET status = 2
                WHERE imint_ai_analysis_id IN (
                    SELECT imint_ai_analysis_id FROM public.imint_ai_analysis
                    WHERE status = 0 ORDER BY imint_ai_analysis_id DESC
                    FOR UPDATE SKIP LOCKED
                ) RETURNING filter_json, imint_ai_analysis_id;
            """)
            return cursor.fetchall()
    except psycopg2.ProgrammingError as e:
        print(f"[ERROR] {e}")
        return []


def ensure_connection(conn):
    try:
        if conn.closed != 0:
            return postgres_connection()
        with conn.cursor() as cursor:
            cursor.execute("SELECT 1;")
        return conn
    except Exception:
        return postgres_connection()

# ─── Main Loop (unchanged) ───────────────────────────────────────────

def run_ai_analysis_summary_loop(ai_trends, ai_summ, ai_change, poll_interval):
    conn = postgres_connection()
    while True:
        try:
            conn = ensure_connection(conn)
            ai_rows = lock_rows_for_processing_1(conn)
            conn.commit()
            conn = ensure_connection(conn)
            imint_rows = lock_rows_for_processing_2(conn)
            conn.commit()
            if ai_rows:
                print(f"[INFO] {len(ai_rows)} rows for ai_analysis")
                for row in ai_rows:
                    p = multiprocessing.Process(
                        target=ai_analysis_summary_check_threadsafe,
                        args=(row, ai_trends, ai_summ, ai_change))
                    p.daemon = True
                    p.start()
            if imint_rows:
                print(f"[INFO] {len(imint_rows)} rows for imint")
                for irow in imint_rows:
                    p = multiprocessing.Process(
                        target=imint_ai_analysis_summary_check_threadsafe,
                        args=(irow,))
                    p.daemon = True
                    p.start()
        except Exception as e:
            print(f"[ERROR] {e}")
            traceback.print_exc()
        time.sleep(poll_interval)
    if conn:
        conn.close()


def call_main_func():
    parser = argparse.ArgumentParser()
    parser.add_argument('--ai_summary', action='store_true')
    parser.add_argument('--ai_trends', action='store_true')
    parser.add_argument('--ai_change', action='store_true')
    args = parser.parse_args()
    ai_summ = args.ai_summary
    ai_trends = args.ai_trends
    ai_change = args.ai_change
    poll_interval = 5
    if not ai_summ and not ai_trends and not ai_change:
        sys.exit(1)
    run_ai_analysis_summary_loop(ai_trends, ai_summ, ai_change, poll_interval)


if __name__ == '__main__':
    while True:
        call_main_func()
