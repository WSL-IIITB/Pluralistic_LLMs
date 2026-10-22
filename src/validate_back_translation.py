import argparse
import json
import re

from src.logging_config import PROJECT_ROOT
from src.validation_io import (
    update_validation, now_iso, resolve_topic_substrings, DEFAULT_SELF_IMAGE_QUERY,
)

DEFAULT_QUERY_ID = "self_image_life_goal"
LANG_FILE = PROJECT_ROOT / "config" / "languages.json"

UNICODE_ESCAPE_RE = re.compile(r"\\u[0-9a-fA-F]{4}")

# Core topic terms that a genuine answer to this query must preserve.
# The query is specifically about "self-image"; a faithful back-translation should
# retain some self-image concept (self/image/confidence/worth/body). "goal"/"life"
# alone is too generic (every life-goal answer has it).
TOPIC_SUBSTRINGS = ("self", "image", "confiden", "worth", "body")

MIN_TOKENS = 5

# Generic structural sanity checks on the native (source-language) answer.
# These are intentionally language/topic-agnostic so they apply to any query:
# a real answer to a substantive question must be more than a fragment
# (MIN_NATIVE_ANSWER_CHARS) and must not just end by asking a fresh question
# (answers phrased as a bare question usually mean the model dodged answering).
MIN_NATIVE_ANSWER_CHARS = 40


def _native_answer_flags(native_answer: str) -> list[str]:
    """Generic, topic-agnostic structural checks on the native answer."""
    flags: list[str] = []
    if len(native_answer) < MIN_NATIVE_ANSWER_CHARS:
        flags.append(
            f"native answer too short ({len(native_answer)} chars < {MIN_NATIVE_ANSWER_CHARS})"
        )
    if native_answer.rstrip().endswith("?"):
        flags.append("native answer ends with a question mark (possible non-answer)")
    return flags


def _punctuation_garbage(back_en: str) -> str | None:
    """True when the output is dominated by non-letter tokens (e.g. stars).

    A real answer is made of words; an answer whose tokens are almost all
    punctuation (``* * * *``) is a decoding/formatting artifact, not a
    paraphrase. Short outputs are left to the too-short check.
    """
    tokens = back_en.split()
    if len(tokens) < MIN_TOKENS:
        return None
    meaningful = sum(1 for t in tokens if any(c.isalpha() for c in t))
    if meaningful / len(tokens) < 0.5:
        return f"output dominated by non-letter tokens ({meaningful}/{len(tokens)} meaningful)"
    return None


def validate_back_translation(
    source_en: str, back_en: str, native_answer: str | None = None,
    topic_substrings: tuple[str, ...] | None = None,
    derived_topics: bool = False,
) -> tuple[list[str], list[str]]:
    """Return ``(flags, notes)``. Empty flags == looks OK.

    ``flags`` are hard defects that flip the record to FLAGGED; ``notes`` are
    soft observations that are recorded for transparency but do not fail the
    check. A derived-keyword miss is demoted to a note because auto-derived
    keywords are the query's *surface* words and a faithful paraphrase
    legitimately avoids repeating them (that failure mode never hit the legacy
    self-image query, whose keywords are hand-picked *answer* words).
    """
    flags: list[str] = []
    notes: list[str] = []

    # 0) Generic structural check on the native-language answer (topic-agnostic).
    if native_answer is not None:
        flags.extend(_native_answer_flags(native_answer))

    # 1) Raw Unicode escapes leaking into the rendered text.
    escapes = UNICODE_ESCAPE_RE.findall(back_en)
    if escapes:
        flags.append(f"raw unicode escapes: {', '.join(sorted(set(escapes)))}")

    # 1b) Formatting-garbage output (dominated by punctuation, not words).
    garbage = _punctuation_garbage(back_en)
    if garbage:
        flags.append(garbage)

    # 2) Core topic preservation: the back-translation should keep the source
    #    query's core concept, however paraphrased. Keywords are derived from the
    #    actual query text (legacy keyword list is kept for the self-image query).
    terms = topic_substrings if topic_substrings is not None else TOPIC_SUBSTRINGS
    text_lower = back_en.lower()
    if not any(term in text_lower for term in terms):
        msg = f"missing topic keywords (none of {', '.join(terms)} present)"
        if derived_topics:
            notes.append(msg)
        else:
            flags.append(msg)

    # 3) Suspiciously short or repetitive output.
    tokens = back_en.split()
    if len(tokens) < MIN_TOKENS:
        flags.append(f"output too short ({len(tokens)} tokens)")
    elif len(tokens) >= 30 and len(set(tokens)) / len(tokens) < 0.5:
        flags.append("output highly repetitive")

    return flags, notes


def main(raw_file) -> None:
    records = json.loads(raw_file.read_text(encoding="utf-8"))
    langs = json.loads(LANG_FILE.read_text(encoding="utf-8"))["languages"]
    name_by_code = {entry["code"]: entry["name"] for entry in langs}
    name_by_code["en"] = "English"

    print(
        f"{'code':7s} | {'lang':11s} | {'verdict':9s} | reason"
    )
    print("-" * 84)

    flagged = []
    results_by_code = {}
    for record in records:
        code = record["target_lang_code"]
        name = name_by_code[code]
        source_en = record["source_query_en"]
        back_en = record["back_translated_answer_en"]
        derived_topics = (source_en or "").strip() != DEFAULT_SELF_IMAGE_QUERY

        if not back_en:
            flags = ["back-translation is empty"]
            notes: list[str] = []
        else:
            flags, notes = validate_back_translation(
                source_en, back_en, native_answer=record["native_answer"],
                topic_substrings=resolve_topic_substrings(
                    source_en, TOPIC_SUBSTRINGS
                ),
                derived_topics=derived_topics,
            )

        if flags:
            verdict = "FLAGGED"
            reason = flags[0]
            flagged.append((code, name, reason))
        else:
            verdict = "looks OK"
            reason = ""
            if notes:
                reason = f"note: {'; '.join(notes)}"

        result = {
            "status": "OK" if verdict == "looks OK" else "FLAGGED",
            "reason": reason,
            "checked_at": now_iso(),
        }
        if notes:
            result["notes"] = notes

        results_by_code[code] = result

        print(f"{code:7s} | {name:11s} | {verdict:9s} | {reason}")

    print()
    print(f"Total records checked: {len(records)}")
    print(f"Unflagged: {len(records) - len(flagged)}")
    print(f"FLAGGED: {len(flagged)}")
    for code, name, reason in flagged:
        print(f"  {code} ({name}): {reason}")

    update_validation(raw_file, "back_translation", results_by_code)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Validate back_translated_answer_en coherence for a dataset."
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
