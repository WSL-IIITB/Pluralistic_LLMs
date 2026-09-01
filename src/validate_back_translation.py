import json
import re

from src.logging_config import PROJECT_ROOT

RAW_FILE = PROJECT_ROOT / "data" / "raw" / "sarvam_self_image_life_goal.json"
LANG_FILE = PROJECT_ROOT / "config" / "languages.json"

UNICODE_ESCAPE_RE = re.compile(r"\\u[0-9a-fA-F]{4}")

# Core topic terms that a genuine answer to this query must preserve.
# The query is specifically about "self-image"; a faithful back-translation should
# retain some self-image concept (self/image/confidence/worth/body). "goal"/"life"
# alone is too generic (every life-goal answer has it).
TOPIC_SUBSTRINGS = ("self", "image", "confiden", "worth", "body")

MIN_TOKENS = 5


def validate_back_translation(
    source_en: str, back_en: str,
) -> list[str]:
    """Return a list of human-readable flag reasons. Empty list == looks OK."""
    flags: list[str] = []
    # 1) Raw Unicode escapes leaking into the rendered text.
    escapes = UNICODE_ESCAPE_RE.findall(back_en)
    if escapes:
        flags.append(f"raw unicode escapes: {', '.join(sorted(set(escapes)))}")

    # 2) Core topic preservation: a real answer should keep the self-image concept,
    #    however paraphrased (self/image/confidence/worth/body).
    text_lower = back_en.lower()
    if not any(term in text_lower for term in TOPIC_SUBSTRINGS):
        flags.append("missing topic keywords (no self/image/confidence/worth/body)")

    # 3) Suspiciously short or repetitive output.
    tokens = back_en.split()
    if len(tokens) < MIN_TOKENS:
        flags.append(f"output too short ({len(tokens)} tokens)")
    elif len(tokens) >= 30 and len(set(tokens)) / len(tokens) < 0.5:
        flags.append("output highly repetitive")

    return flags


def main() -> None:
    records = json.loads(RAW_FILE.read_text(encoding="utf-8"))
    langs = json.loads(LANG_FILE.read_text(encoding="utf-8"))["languages"]
    name_by_code = {entry["code"]: entry["name"] for entry in langs}
    name_by_code["en"] = "English"

    print(
        f"{'code':7s} | {'lang':11s} | {'verdict':9s} | reason"
    )
    print("-" * 84)

    flagged = []
    for record in records:
        code = record["target_lang_code"]
        name = name_by_code[code]
        source_en = record["source_query_en"]
        back_en = record["back_translated_answer_en"]

        if not back_en:
            flags = ["back-translation is empty"]
        else:
            flags = validate_back_translation(source_en, back_en)

        if flags:
            verdict = "FLAGGED"
            reason = flags[0]
            flagged.append((code, name, reason))
        else:
            verdict = "looks OK"
            reason = ""

        print(f"{code:7s} | {name:11s} | {verdict:9s} | {reason}")

    print()
    print(f"Total records checked: {len(records)}")
    print(f"Unflagged: {len(records) - len(flagged)}")
    print(f"FLAGGED: {len(flagged)}")
    for code, name, reason in flagged:
        print(f"  {code} ({name}): {reason}")


if __name__ == "__main__":
    main()
