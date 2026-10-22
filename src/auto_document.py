"""auto_document.py — automatically make a dataset self-documenting.

Runs after the four validators. For every record it inspects the validation
sub-keys and writes machine-generated notes explaining each non-OK status,
classifying each into one of two buckets:

  * structural  — a known tool limitation (detector lacks the language, MuRIL
    has no scorer, known IndicTrans2 limitation). Auto-resolved; no human
    action needed.
  * review      — a genuine content signal (language mismatch, unexpected
    back-translation / round-trip / script / fluency flag) that a human
    should confirm.

Generated notes live in ``record["auto_notes"]`` (a list of strings), so the
human-authored ``record["notes"]`` is never modified. ``review_required`` is
set on the record. Re-running is idempotent: auto_notes is recomputed from
the current validation state.

Usage:
    python -m src.auto_document --query-id <id>
"""

import argparse
import json

from src.logging_config import PROJECT_ROOT

DEFAULT_QUERY_ID = "self_image_life_goal"
LANG_FILE = PROJECT_ROOT / "config" / "languages.json"

# Back-translation failures that are known model limitations, not pipeline bugs.
# These get a "structural" note instead of being queued for manual review.
KNOWN_BACKTRANSLATION_LIMITS = {
    "mni-IN": "IndicTrans2 Manipuri->English (raw \\u09BC escape + repetition)",
}


def _language_names() -> dict[str, str]:
    langs = json.loads(LANG_FILE.read_text(encoding="utf-8"))["languages"]
    names = {entry["code"]: entry["name"] for entry in langs}
    names["en"] = "English"
    return names


def build_auto_notes(record: dict, names: dict[str, str]) -> tuple[list[str], list[str]]:
    """Return (auto_notes, review_items) for a single record."""
    notes: list[str] = []
    review: list[str] = []
    code = record["target_lang_code"]
    name = names.get(code, code)
    v = record.get("validation", {})

    # A failed generation means there is no answer to validate at all; say so
    # plainly and queue it for review instead of emitting derivative notes.
    if record.get("generation_failed"):
        notes.append(
            f"generation: no native_answer for {name} ({code}) after all retry "
            f"attempts - tunnel/model failure; record is empty and was not validated."
        )
        review.append("generation FAILED")
        return notes, review

    # --- language / script (fastText LID) ---
    lid = v.get("language_id", {})
    lid_status = lid.get("status")
    detected = lid.get("detected_name") or lid.get("detected_label") or "?"
    if lid_status == "UNVERIFIED":
        notes.append(
            f"language_id: fastText lid.176 has no reliable label for {name} "
            f"({code}); language/script is not auto-verifiable (structural limitation)."
        )
    elif lid_status == "DETECTOR-AMBIGUOUS":
        notes.append(
            f"language_id: fastText detected {detected}, a known adjacent/confusable "
            f"language for {name}; treated as expected script/language proximity "
            f"(structural)."
        )
    elif lid_status == "MISMATCH":
        notes.append(
            f"language_id: expected {name} but fastText detected {detected} "
            f"- possible language/script defect."
        )
        review.append("language_id MISMATCH")

    # --- back-translation coherence ---
    bt = v.get("back_translation", {})
    if bt.get("status") == "FLAGGED":
        reason = bt.get("reason", "")
        if code in KNOWN_BACKTRANSLATION_LIMITS:
            notes.append(
                f"back_translation: {reason or 'failed'}; known limitation — "
                f"{KNOWN_BACKTRANSLATION_LIMITS[code]} (structural, not a pipeline bug)."
            )
        else:
            notes.append(f"back_translation: {reason or 'flagged'}.")
            review.append("back_translation FLAGGED")

    # --- query round-trip fidelity ---
    qr = v.get("query_roundtrip", {})
    if qr.get("status") == "FLAGGED":
        notes.append(f"query_roundtrip: {qr.get('reason', 'flagged')}.")
        review.append("query_roundtrip FLAGGED")

    # --- syntax: script well-formedness + fluency ---
    syn = v.get("syntax", {})
    if syn.get("script_check") == "FLAGGED":
        reason = syn.get("script_reason") or "out-of-script or orphaned combining marks"
        notes.append(f"script_check: {reason} - possible script defect.")
        review.append("script FLAGGED")
    if syn.get("fluency_check") == "NO-SCORER-AVAILABLE":
        notes.append(
            f"fluency: MuRIL has no scorer for {name} ({code}); fluency is not "
            f"auto-verifiable (structural limitation)."
        )
    elif syn.get("fluency_check") == "FLAGGED":
        score = syn.get("fluency_score")
        score_txt = (
            f" (pseudo-perplexity {score:.2f})"
            if isinstance(score, (int, float)) else ""
        )
        notes.append(
            f"fluency: pseudo-perplexity outlier{score_txt} relative to the batch "
            f"- possible fluency issue."
        )
        review.append("fluency FLAGGED")

    return notes, review


def auto_document(query_id: str) -> dict:
    """Recompute and merge auto_notes + review_required for a dataset.

    Returns a summary dict: {structural_records, review_records, review_by_code}.
    """
    path = PROJECT_ROOT / "data" / "raw" / f"sarvam_{query_id}.json"
    records = json.loads(path.read_text(encoding="utf-8"))
    names = _language_names()

    structural = 0
    review_by_code: dict[str, list[str]] = {}
    for record in records:
        notes, review = build_auto_notes(record, names)
        code = record["target_lang_code"]
        if notes:
            record["auto_notes"] = notes
        else:
            record.pop("auto_notes", None)
        record["review_required"] = bool(review)
        if review:
            review_by_code[code] = review
        elif notes:
            structural += 1

    path.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
    return {
        "structural_records": structural,
        "review_records": len(review_by_code),
        "review_by_code": review_by_code,
        "path": path,
    }


def print_report(query_id: str, result: dict) -> None:
    print("\n" + "=" * 100)
    print(f"AUTO-DOCUMENTATION — query_id={query_id!r}")
    print("=" * 100)
    print(f"Structural-only records (documented, no action): {result['structural_records']}")
    print(f"Records needing manual review: {result['review_records']}")
    for code, items in sorted(result["review_by_code"].items()):
        print(f"  {code}: {', '.join(items)}")
    if not result["review_by_code"]:
        print("  none — all flags are documented structural limitations.")
    print(f"  wrote auto_notes -> {result['path']}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Auto-document validation flags into a dataset (self-documenting, idempotent)."
    )
    parser.add_argument(
        "--query-id",
        default=DEFAULT_QUERY_ID,
        help=f"query id; resolves to data/raw/sarvam_<query_id>.json (default: {DEFAULT_QUERY_ID})",
    )
    args = parser.parse_args()

    path = PROJECT_ROOT / "data" / "raw" / f"sarvam_{args.query_id}.json"
    if not path.exists():
        parser.error(f"dataset not found: {path}")

    result = auto_document(args.query_id)
    print_report(args.query_id, result)


if __name__ == "__main__":
    main()