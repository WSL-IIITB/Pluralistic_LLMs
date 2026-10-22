"""run_new_query.py — one command: generate + fully validate a new query.

Orchestrates, for a single query:

  1. tunnel reachability check (shared verify_tunnel from pipeline_sarvam)
  2. generation via src.pipeline_sarvam (22 languages + English baseline)
  3. all four validators, each writing its own validation sub-key
  4. a final summary table across all four validation dimensions

Produces data/raw/sarvam_<query_id>.json with the same schema/shape/merge
behaviour as the self_image_life_goal dataset. Exclusively for NEW queries;
never touches existing datasets beyond the shared merge-aware write path.
"""

import argparse
import json
import os
import subprocess
import sys

from src.logging_config import PROJECT_ROOT
from src.pipeline_sarvam import OLLAMA_BASE_URL, verify_tunnel

DEFAULT_QUERY_ID = "self_image_life_goal"
DEFAULT_QUERY_TEXT = "Can you give an example of a life goal related to self-image?"

VENV_IT2 = PROJECT_ROOT / ".venv-it2" / "bin" / "python"
VENV_LID = PROJECT_ROOT / ".venv" / "bin" / "python"


def _run(venv_python, module: str, extra_args: list[str]) -> None:
    cmd = [str(venv_python), "-m", f"src.{module}", *extra_args]
    print(f"\n### {module}: {' '.join(cmd)}")
    proc = subprocess.run(cmd, cwd=str(PROJECT_ROOT), env=os.environ.copy())
    if proc.returncode != 0:
        raise SystemExit(f"FAILED: {' '.join(cmd)} (exit {proc.returncode})")


def summarize(query_id: str) -> None:
    path = PROJECT_ROOT / "data" / "raw" / f"sarvam_{query_id}.json"
    records = json.loads(path.read_text(encoding="utf-8"))

    print("\n" + "=" * 100)
    print(f"SUMMARY — query_id={query_id!r}  ({path.name})")
    print("=" * 100)

    header = f"{'code':7s} | {'lang_id':18s} | {'back_trans':11s} | {'roundtrip':9s} | {'script':7s} | {'fluency'}"
    print(header)
    print("-" * len(header))

    langs = json.loads(
        (PROJECT_ROOT / "config" / "languages.json").read_text(encoding="utf-8")
    )["languages"]
    name_by_code = {e["code"]: e["name"] for e in langs}
    name_by_code["en"] = "English"

    counts = {
        "MATCH": 0, "MISMATCH": 0, "DETECTOR-AMBIGUOUS": 0, "UNVERIFIED": 0,
        "back_translation OK": 0, "back_translation FLAGGED": 0,
        "roundtrip OK": 0, "roundtrip FLAGGED": 0,
        "script OK": 0, "script FLAGGED": 0,
        "fluency OK": 0, "fluency FLAGGED": 0, "NO-SCORER-AVAILABLE": 0,
    }

    for rec in sorted(records, key=lambda r: r["target_lang_code"]):
        code = rec["target_lang_code"]
        v = rec.get("validation", {})
        lid = v.get("language_id", {}).get("status", "?")
        bt = v.get("back_translation", {}).get("status", "?")
        qr = v.get("query_roundtrip", {}).get("status", "?")
        syn = v.get("syntax", {})
        sc = syn.get("script_check", "?")
        fc = syn.get("fluency_check", "?")

        counts[lid if lid in counts else "UNVERIFIED"] += 1 if lid in ("MATCH", "MISMATCH", "DETECTOR-AMBIGUOUS", "UNVERIFIED") else 0
        counts[f"back_translation {bt}"] = counts.get(f"back_translation {bt}", 0) + 1
        counts[f"roundtrip {qr}"] = counts.get(f"roundtrip {qr}", 0) + 1
        counts[f"script {sc}"] = counts.get(f"script {sc}", 0) + 1
        counts[f"fluency {fc}"] = counts.get(f"fluency {fc}", 0) + 1

        print(f"{code:7s} | {lid:18s} | {bt:11s} | {qr:9s} | {sc:7s} | {fc}")

    print("-" * len(header))
    print("counts:")
    for key, val in counts.items():
        if val:
            print(f"  {key}: {val}")

    documented = sum(1 for r in records if r.get("auto_notes"))
    review = [r["target_lang_code"] for r in records if r.get("review_required")]
    print()
    print(f"  auto-documented records (self-explaining): {documented}")
    print(f"  needs manual review: {len(review)} -> {review or 'none'}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate + fully validate a new query in one command (data/raw/sarvam_<query_id>.json)."
    )
    parser.add_argument("--query-id", default=DEFAULT_QUERY_ID, help=f"query id (default: {DEFAULT_QUERY_ID})")
    parser.add_argument("--query-text", default=DEFAULT_QUERY_TEXT, help="query text in English")
    parser.add_argument("--url", default=None, help="ngrok/Ollama tunnel URL (default: OLLAMA_BASE_URL or pipeline default)")
    parser.add_argument("--output", default=None, help="optional output path override for generation step")
    parser.add_argument(
        "--languages",
        default=None,
        help="comma-separated subset of target language codes (passes through to pipeline)",
    )
    parser.add_argument(
        "--no-auto-document",
        action="store_true",
        help="skip the auto-documentation step (notes/review_required)",
    )
    args = parser.parse_args()

    url = args.url or os.environ.get("OLLAMA_BASE_URL") or OLLAMA_BASE_URL

    # 1. Tunnel health check (shared, from src/pipeline_sarvam.py).
    print(f"Checking tunnel: {url}/api/tags")
    if not verify_tunnel(url):
        raise SystemExit(f"ERROR: tunnel not reachable at {url}. Start Colab + ngrok first.")

    # 2. Generation.
    pipeline_args = ["--query-id", args.query_id, "--query-text", args.query_text]
    if args.output:
        pipeline_args += ["--output", args.output]
    if args.languages:
        pipeline_args += ["--languages", args.languages]
    print(f"\n### pipeline (generation): python -m src.pipeline_sarvam {' '.join(pipeline_args)}")
    env = os.environ.copy()
    env["OLLAMA_BASE_URL"] = url
    proc = subprocess.run(
        [str(VENV_IT2), "-m", "src.pipeline_sarvam", *pipeline_args],
        cwd=str(PROJECT_ROOT), env=env,
    )
    if proc.returncode != 0:
        raise SystemExit(f"FAILED: pipeline (exit {proc.returncode})")

    # 3. Validators — each writes only its own sub-key via validation_io.
    query_args = ["--query-id", args.query_id]
    _run(VENV_LID, "validate_language_id", query_args)
    _run(VENV_IT2, "validate_back_translation", query_args)
    _run(VENV_IT2, "validate_query_roundtrip", query_args)
    _run(VENV_IT2, "validate_syntax", query_args)

    # 4. Auto-documentation — makes the dataset self-documenting without hand
    #    editing: structural flags are explained automatically and genuine
    #    content flags are queued for review.
    if not args.no_auto_document:
        _run(VENV_IT2, "auto_document", query_args)

    # 5. Final summary.
    summarize(args.query_id)


if __name__ == "__main__":
    main()