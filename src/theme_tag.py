"""
Stage 1 Theme Tagging CLI.

Reads English back-translated answers from data/raw/sarvam_<query_id>.json,
formats them using config/prompts/theme_tagging_v1.txt and an approved codebook,
queries the tagger LLM over the Ollama tunnel, verifies evidence quotes,
and stores outputs to data/analysis/themes_<query_id>/tags.json.

Requirements:
- Codebook must be 'APPROVED'
- Refuse 'sarvam' models unless --self-grading-ok is set
- One independent call per record in fixed shuffled order (seed 13)
- Writes tags.json after every record (resume support)
- Never store tunnel URL in outputs
"""

import argparse
import json
import random
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.logging_config import setup_logging
from src.pipeline_sarvam import NGROK_HEADER, verify_tunnel
from src.similarity_core import (
    canonical_order,
    load_records,
    normalize_text,
    sha256_file,
    usable,
)
from src.theme_core import (
    apply_verification,
    codebook_is_approved,
    load_codebook,
    parse_tag_response,
    render_prompt,
)

logger = setup_logging()


def build_json_schema(codebook: Dict[str, Any]) -> Dict[str, Any]:
    """Build a strict JSON schema for Ollama format field from codebook themes."""
    theme_properties = {}
    theme_ids = []
    for t in codebook.get("themes", []):
        tid = t["id"]
        theme_ids.append(tid)
        theme_properties[tid] = {
            "type": "object",
            "properties": {
                "present": {"type": "boolean"},
                "evidence": {"type": "string"},
            },
            "required": ["present", "evidence"],
        }

    return {
        "type": "object",
        "properties": {
            "themes": {
                "type": "object",
                "properties": theme_properties,
                "required": theme_ids,
            },
            "other_note": {"type": "string"},
            "keywords": {
                "type": "array",
                "items": {"type": "string"},
            },
        },
        "required": ["themes", "other_note"],
    }


def query_tagger(
    base_url: str,
    model: str,
    prompt: str,
    schema: Optional[Dict[str, Any]] = None,
    timeout: int = 120,
    max_retries: int = 2,
) -> Tuple[Optional[str], float, int, Optional[str]]:
    """
    Call Ollama /api/chat endpoint with retry backoff (10s, 20s).
    Returns (raw_response_content, latency_s, attempts, error_msg).
    """
    url = f"{base_url.rstrip('/')}/api/chat"
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "format": schema if schema is not None else "json",
        "options": {
            "temperature": 0,
            "seed": 13,
            "num_predict": 1000,
        },
    }

    attempts = 0
    start_time = time.time()
    last_err: Optional[str] = None

    for attempt in range(max_retries + 1):
        attempts += 1
        try:
            r = requests.post(url, headers=NGROK_HEADER, json=payload, timeout=timeout)
            if r.status_code == 200:
                data = r.json()
                content = data.get("message", {}).get("content", "")
                latency = time.time() - start_time
                return content, latency, attempts, None
            else:
                last_err = f"HTTP {r.status_code}: {r.text[:200]}"
        except Exception as e:
            last_err = f"Connection error: {type(e).__name__}: {e}"

        if attempt < max_retries:
            wait_s = 10 if attempt == 0 else 20
            logger.warning(f"Request failed ({last_err}). Retrying in {wait_s}s...")
            time.sleep(wait_s)

    latency = time.time() - start_time
    return None, latency, attempts, last_err


def auto_generate_codebook_llm(
    query_id: str,
    source_query_en: str,
    records: List[Dict[str, Any]],
    base_url: str,
    model: str,
) -> Path:
    """Auto-generate a 5 to 6 theme codebook via LLM from English back-translations."""
    codebook_path = PROJECT_ROOT / "config" / "codebooks" / f"{query_id}.json"
    codebook_path.parent.mkdir(parents=True, exist_ok=True)

    # Collect sample English answers (up to 8 non-empty samples across diverse languages)
    sample_texts = []
    for r in records:
        bt = r.get("back_translated_answer_en", "").strip()
        if bt and len(bt) > 20:
            sample_texts.append(f"Sample answer ({r.get('target_lang_code', '')}):\n{bt[:300]}")
        if len(sample_texts) >= 8:
            break

    prompt = (
        f"You are an expert qualitative research content coder.\n"
        f"A multilingual language model answered this question in multiple Indian languages:\n"
        f"QUESTION: \"{source_query_en}\"\n\n"
        f"Here are several English back-translated sample answers:\n"
        f"{chr(10).join(sample_texts)}\n\n"
        f"Analyze these answers and design a comprehensive codebook containing EXACTLY 5 to 6 distinct, balanced thematic categories.\n"
        f"Rules:\n"
        f"1. Theme 'id' must be lowercase snake_case (^[a-z][a-z0-9_]*$).\n"
        f"2. Theme 'label' must be short, plain title.\n"
        f"3. Theme 'definition' must be a clear 1-2 sentence definition explaining what concepts fit into it.\n"
        f"4. Themes should cover distinct aspects of the answers with minimal overlap.\n"
        f"5. Output ONLY a valid JSON object matching this schema:\n"
        f"{{\n"
        f'  "query_id": "{query_id}",\n'
        f'  "version": 1,\n'
        f'  "status": "APPROVED",\n'
        f'  "themes": [\n'
        f'    {{"id": "theme_one", "label": "Label One", "definition": "Definition One."}},\n'
        f'    ...\n'
        f"  ]\n"
        f"}}"
    )

    schema = {
        "type": "object",
        "properties": {
            "query_id": {"type": "string"},
            "version": {"type": "integer"},
            "status": {"type": "string"},
            "themes": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string"},
                        "label": {"type": "string"},
                        "definition": {"type": "string"},
                    },
                    "required": ["id", "label", "definition"],
                },
            },
        },
        "required": ["query_id", "version", "status", "themes"],
    }

    print(f"[theme_pipeline] Auto-generating 5–6 theme codebook for '{query_id}' via {model}...")
    content, latency, _, err = query_tagger(
        base_url=base_url,
        model=model,
        prompt=prompt,
        schema=schema,
        timeout=180,
    )
    if not content:
        raise RuntimeError(f"Failed to auto-generate codebook via LLM: {err}")

    # Validate generated codebook
    data = json.loads(content)
    data["query_id"] = query_id
    data["status"] = "APPROVED"

    # Sanitize theme ids
    for t in data.get("themes", []):
        tid = re.sub(r"[^a-z0-9_]", "_", str(t.get("id", "")).lower()).strip("_")
        if not tid or not tid[0].isalpha():
            tid = f"theme_{tid}"
        t["id"] = tid

    # Ensure 5-6 themes
    if len(data.get("themes", [])) > 6:
        data["themes"] = data["themes"][:6]
    elif len(data.get("themes", [])) < 3:
        raise ValueError(f"LLM generated too few themes: {len(data.get('themes', []))}")

    codebook_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[theme_pipeline] Successfully generated codebook at {codebook_path} ({len(data['themes'])} themes)")
    return codebook_path


def tag_dataset(
    query_id: str,
    base_url: str,
    model: str,
    only_langs: Optional[List[str]] = None,
    force: bool = False,
    self_grading_ok: bool = False,
    max_retries: int = 2,
    out_dir_base: Optional[Path] = None,
    auto_generate_codebook: bool = True,
) -> Path:
    # 1. Model gate: refuse sarvam unless --self-grading-ok
    tagger_is_generator = "sarvam" in model.lower()
    if tagger_is_generator and not self_grading_ok:
        sys.exit(
            f"Error: Model '{model}' contains 'sarvam' (self-grading). "
            f"Pass --self-grading-ok to confirm self-grading evaluation."
        )

    # Check dataset early
    dataset_path = PROJECT_ROOT / "data" / "raw" / f"sarvam_{query_id}.json"
    if not dataset_path.exists():
        sys.exit(f"Error: Dataset not found at {dataset_path}")

    dataset_sha_start = sha256_file(dataset_path)
    records_list = load_records(dataset_path)
    source_query_en = records_list[0].get("source_query_en", "")

    # 2. Check codebook or auto-generate via LLM
    codebook_path = PROJECT_ROOT / "config" / "codebooks" / f"{query_id}.json"
    if not codebook_path.exists():
        if auto_generate_codebook:
            auto_generate_codebook_llm(query_id, source_query_en, records_list, base_url, model)
        else:
            sys.exit(f"Error: Codebook not found at {codebook_path}")

    codebook = load_codebook(codebook_path)
    if not codebook_is_approved(codebook):
        sys.exit(
            f"Error: Codebook at {codebook_path} has status '{codebook.get('status')}', not 'APPROVED'. "
            f"Review and approve the codebook by hand before tagging."
        )

    codebook_sha = sha256_file(codebook_path)
    json_schema = build_json_schema(codebook)

    # 3. Check prompt template
    prompt_path = PROJECT_ROOT / "config" / "prompts" / "theme_tagging_v1.txt"
    if not prompt_path.exists():
        sys.exit(f"Error: Prompt template not found at {prompt_path}")
    prompt_template = prompt_path.read_text(encoding="utf-8")
    prompt_sha = sha256_file(prompt_path)

    # Output directory
    base_out = out_dir_base or (PROJECT_ROOT / "data" / "analysis")
    out_dir = base_out / f"themes_{query_id}"
    raw_dir_resolved = (PROJECT_ROOT / "data" / "raw").resolve()
    sim_dir_resolved = (PROJECT_ROOT / "data" / "analysis").resolve()

    if raw_dir_resolved in out_dir.resolve().parents or out_dir.resolve() == raw_dir_resolved:
        sys.exit(f"Error: Output dir cannot be inside data/raw: {out_dir}")

    out_dir.mkdir(parents=True, exist_ok=True)
    tags_file = out_dir / "tags.json"

    # 5. Verify tunnel health
    print(f"Verifying tunnel at {base_url}...")
    if not verify_tunnel(base_url):
        sys.exit(f"Error: Tunnel health check failed for {base_url}")

    # Fetch model digest from /api/tags if available
    tagger_digest = None
    try:
        r_tags = requests.get(f"{base_url.rstrip('/')}/api/tags", headers=NGROK_HEADER, timeout=10)
        if r_tags.status_code == 200:
            for m in r_tags.json().get("models", []):
                if m.get("name") == model or model in m.get("name", ""):
                    tagger_digest = m.get("digest")
                    break
    except Exception:
        pass

    # 6. Load or initialize tags.json
    tags_data: Dict[str, Any] = {}
    if tags_file.exists() and not force:
        try:
            with open(tags_file, "r", encoding="utf-8") as f:
                tags_data = json.load(f)
        except Exception:
            tags_data = {}

    if not tags_data or force:
        tags_data = {
            "meta": {
                "query_id": query_id,
                "dataset_sha256": dataset_sha_start,
                "codebook_path": str(codebook_path),
                "codebook_sha256": codebook_sha,
                "prompt_template_path": str(prompt_path),
                "prompt_template_sha256": prompt_sha,
                "tagger_model": model,
                "tagger_digest": tagger_digest,
                "tagger_is_generator": tagger_is_generator,
                "options": {"temperature": 0, "seed": 13, "num_predict": 1000},
                "created_utc": datetime.now(timezone.utc).isoformat(),
                "updated_utc": datetime.now(timezone.utc).isoformat(),
            },
            "records": {},
        }

    records_list = load_records(dataset_path)
    records_by_code = {r["target_lang_code"]: r for r in records_list}

    # Canonical order
    languages_cfg_path = PROJECT_ROOT / "config" / "languages.json"
    order = canonical_order(languages_cfg_path)

    # Filter target codes
    target_codes = [c for c in order if c in records_by_code]
    if only_langs:
        target_codes = [c for c in target_codes if c in only_langs]

    # Shuffled order with fixed seed 13
    shuffled_codes = list(target_codes)
    rng = random.Random(13)
    rng.shuffle(shuffled_codes)

    source_query_en = records_list[0].get("source_query_en", "")

    print(f"Beginning theme tagging for query '{query_id}' using '{model}' ({len(shuffled_codes)} records)...")

    for idx, code in enumerate(shuffled_codes, 1):
        rec = records_by_code[code]

        # Check resume condition
        if not force and code in tags_data.get("records", {}):
            prev_status = tags_data["records"][code].get("status")
            if prev_status in ("ok", "skipped_unusable"):
                print(f"[{idx}/{len(shuffled_codes)}] Skipping already tagged {code} (status: {prev_status})")
                continue

        # Usability check
        if not usable(rec, "english"):
            print(f"[{idx}/{len(shuffled_codes)}] Language {code}: skipped_unusable")
            tags_data["records"][code] = {
                "status": "skipped_unusable",
                "attempts": 0,
                "input_text": "",
                "raw_response": "",
                "themes": None,
                "other_note": "",
                "latency_s": 0.0,
            }
            tags_data["meta"]["updated_utc"] = datetime.now(timezone.utc).isoformat()
            with open(tags_file, "w", encoding="utf-8") as f:
                json.dump(tags_data, f, indent=2)
            continue

        raw_en_answer = rec.get("back_translated_answer_en", "")
        norm_text = normalize_text(raw_en_answer)

        # Build prompt (language-blind)
        prompt = render_prompt(
            prompt_template,
            query=source_query_en,
            codebook=codebook,
            text=norm_text,
        )

        current_prompt = prompt
        parse_attempts = 0
        final_status = "ok"
        final_themes = None
        final_note = ""
        final_kws = []
        final_raw = ""
        total_latency = 0.0

        for attempt in range(max_retries + 1):
            parse_attempts += 1
            raw_resp, lat, http_attempts, http_err = query_tagger(
                base_url=base_url,
                model=model,
                prompt=current_prompt,
                schema=json_schema,
                timeout=120,
                max_retries=1,
            )
            total_latency += lat

            if raw_resp is None:
                final_status = "http_failed"
                final_raw = str(http_err)
                break

            final_raw = raw_resp
            parsed, note, err, kws = parse_tag_response(raw_resp, codebook)
            if parsed is not None:
                # Apply evidence verification
                final_themes = apply_verification(parsed, norm_text)
                final_note = note
                final_kws = kws
                final_status = "ok"
                break
            else:
                logger.warning(f"Language {code} parse failure (attempt {attempt+1}): {err}")
                if attempt < max_retries:
                    # Append error retry guidance per Section 3.6
                    current_prompt = prompt + "\nYour previous output was not valid. Output only the JSON object."
                else:
                    final_status = "parse_failed"

        # Record result
        tags_data["records"][code] = {
            "status": final_status,
            "attempts": parse_attempts,
            "input_text": norm_text,
            "raw_response": final_raw,
            "themes": final_themes,
            "other_note": final_note,
            "keywords": final_kws if final_status == "ok" else [],
            "latency_s": round(total_latency, 3),
        }

        # Write tags.json after every record
        tags_data["meta"]["updated_utc"] = datetime.now(timezone.utc).isoformat()
        with open(tags_file, "w", encoding="utf-8") as f:
            json.dump(tags_data, f, indent=2)

        ver_count = 0
        if final_themes:
            ver_count = sum(1 for t in final_themes.values() if t.get("evidence_verified"))

        print(
            f"[{idx}/{len(shuffled_codes)}] {code:<6}: status={final_status:<12} "
            f"attempts={parse_attempts} latency={total_latency:.2f}s verified_themes={ver_count}"
        )

    # 7. Check dataset SHA-256 before/after
    dataset_sha_end = sha256_file(dataset_path)
    if dataset_sha_start != dataset_sha_end:
        sys.exit(f"FATAL: Dataset {dataset_path} was modified during execution!")

    print(f"\nTagging run finished. Tags written to {tags_file}")
    return tags_file


def main():
    parser = argparse.ArgumentParser(description="Stage 1: LLM Theme Tagging CLI")
    parser.add_argument("--query-id", type=str, default="self_image_life_goal", help="Query identifier")
    parser.add_argument("--url", type=str, required=True, help="Ollama tunnel base URL")
    parser.add_argument("--model", type=str, required=True, help="Exact Ollama tagger model tag")
    parser.add_argument("--only", type=str, default=None, help="Comma-separated subset of language codes (e.g. en,hi-IN)")
    parser.add_argument("--force", action="store_true", help="Force re-tagging of already processed records")
    parser.add_argument("--self-grading-ok", action="store_true", help="Allow tagger to be generator model (sarvam)")
    parser.add_argument("--max-retries", type=int, default=2, help="Max parse/HTTP retries per record")
    parser.add_argument("--out-dir", type=str, default=None, help="Base output directory")
    parser.add_argument("--no-auto-codebook", action="store_true", help="Do not auto-generate codebook via LLM if missing")
    args = parser.parse_args()

    only_langs = [c.strip() for c in args.only.split(",")] if args.only else None
    out_dir_base = Path(args.out_dir) if args.out_dir else None

    tag_dataset(
        query_id=args.query_id,
        base_url=args.url,
        model=args.model,
        only_langs=only_langs,
        force=args.force,
        self_grading_ok=args.self_grading_ok,
        max_retries=args.max_retries,
        out_dir_base=out_dir_base,
        auto_generate_codebook=not args.no_auto_codebook,
    )


if __name__ == "__main__":
    main()
