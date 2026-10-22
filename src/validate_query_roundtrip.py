import argparse
import json
import re

from src.logging_config import PROJECT_ROOT
from src.indic_translate import translate_text
from src.validation_io import update_validation, now_iso, resolve_topic_substrings

DEFAULT_QUERY_ID = "self_image_life_goal"
LANG_FILE = PROJECT_ROOT / "config" / "languages.json"

SOURCE_QUERY_EN = "Can you give an example of a life goal related to self-image?"

# Core terms a faithful query round-trip must preserve.
# The query asks about "life goal" + "self-image"; losing both signals drift.
TOPIC_SUBSTRINGS = ("self", "image", "goal", "life")


def main(raw_file) -> None:
    records = json.loads(raw_file.read_text(encoding="utf-8"))
    langs = json.loads(LANG_FILE.read_text(encoding="utf-8"))["languages"]
    name_by_code = {entry["code"]: entry["name"] for entry in langs}
    name_by_code["en"] = "English"

    # Source query key terms for quick comparison
    src_lower = SOURCE_QUERY_EN.lower()

    print(f"{'code':7s} | {'lang':11s} | {'verdict':7s} | round-trip back to English")
    print("-" * 120)

    flagged = []
    results_by_code = {}
    for record in records:
        code = record["target_lang_code"]
        name = name_by_code[code]
        translated_q = record["translated_query"]
        source_en = record["source_query_en"]
        topic_terms = resolve_topic_substrings(source_en, TOPIC_SUBSTRINGS)

        if code == "en":
            # English baseline: query round-trip is trivially exact
            rt_english = translated_q
            verdict = "yes"
            reason = ""
        elif not translated_q:
            rt_english = ""
            verdict = "FLAGGED"
            reason = "translated_query is empty"
        else:
            try:
                rt_english = translate_text(translated_q, code, "en-IN")
            except Exception as e:
                rt_english = f"[translation error: {e}]"
                verdict = "FLAGGED"
                reason = str(e)[:60]
                flagged.append((code, name, reason))
                results_by_code[code] = {
                    "status": "FLAGGED",
                    "reason": reason,
                    "checked_at": now_iso(),
                }
                print(f"{code:7s} | {name:11s} | {verdict:7s} | {rt_english[:100]}")
                continue

            # Heuristic: check if core topic terms from source appear in round-trip
            rt_lower = rt_english.lower()
            hits = [t for t in topic_terms if t in rt_lower]
            if len(hits) >= 2:
                verdict = "yes"
                reason = ""
            else:
                verdict = "FLAGGED"
                reason = f"missing topic keywords (found {hits or 'none'} of {topic_terms})"
                flagged.append((code, name, reason))

        results_by_code[code] = {
            "status": "OK" if verdict == "yes" else "FLAGGED",
            "reason": reason,
            "checked_at": now_iso(),
        }
        print(f"{code:7s} | {name:11s} | {verdict:7s} | {rt_english[:120]}")

    print()
    print(f"Total records checked: {len(records)}")
    print(f"Unflagged: {len(records) - len(flagged)}")
    print(f"FLAGGED: {len(flagged)}")
    for code, name, reason in flagged:
        print(f"  {code} ({name}): {reason}")

    update_validation(raw_file, "query_roundtrip", results_by_code)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Validate that translated_query round-trips back to the source meaning."
    )
    parser.add_argument(
        "--query-id",
        default=DEFAULT_QUERY_ID,
        help=f"query id; resolves to data/raw/sarvam_<query_id>.json (default: {DEFAULT_QUERY_ID})",
    )
    args = parser.parse_args()

    raw_file = PROJECT_ROOT / "data" / "raw" / f"sarvam_{args.query_id}.json"
    if not raw_file.exists():
        parser.error(f"dataset not found: {raw_file}")

    main(raw_file)
