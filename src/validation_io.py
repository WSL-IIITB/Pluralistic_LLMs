"""Shared I/O for writing validation results into dataset records.

Every validator writes its results under data[i]["validation"][KEY], never
touching the record's own content fields or any other validator's sub-key.
The merge follows the same load-existing → merge-by-code → write pattern
established for the main pipeline.
"""

import json
import re
from datetime import datetime, timezone

from src.logging_config import PROJECT_ROOT

DEFAULT_SELF_IMAGE_QUERY = "Can you give an example of a life goal related to self-image?"

# Words that carry no topic signal and are dropped when deriving keywords from
# an arbitrary query text.
_STOPWORDS = {
    "a", "an", "the", "and", "or", "but", "if", "then", "else", "for", "to",
    "with", "without", "of", "from", "in", "on", "at", "by", "about", "than",
    "into", "over", "under", "can", "could", "would", "should", "will", "shall",
    "may", "might", "do", "does", "did", "this", "that", "these", "those",
    "there", "their", "they", "them", "we", "you", "your", "our", "us", "me",
    "my", "is", "are", "was", "were", "be", "been", "being", "have", "has",
    "had", "not", "no", "yes", "please", "write", "give", "me", "up", "down",
}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def derive_topic_substrings(query_en: str) -> tuple[str, ...]:
    """Content-word substrings extracted from a query's English text."""
    words = re.findall(r"[a-zA-Z]+", (query_en or "").lower())
    seen = set()
    out = []
    for w in words:
        if len(w) < 4 or w in _STOPWORDS or w in seen:
            continue
        seen.add(w)
        out.append(w)
    return tuple(out)


def resolve_topic_substrings(
    query_en: str, legacy_substrings: tuple[str, ...]
) -> tuple[str, ...]:
    """Topic keywords for a record, preserving legacy behaviour for the
    original self-image query and deriving fresh keywords for any other query."""
    if (query_en or "").strip() == DEFAULT_SELF_IMAGE_QUERY:
        return legacy_substrings
    derived = derive_topic_substrings(query_en)
    return derived or legacy_substrings


def update_validation(dataset_path, validator_key: str, results_by_code: dict) -> None:
    """Merge validation[validator_key] into each matching record, then write.

    Parameters
    ----------
    dataset_path : Path
        The full dataset file (e.g. data/raw/sarvam_self_image_life_goal.json).
    validator_key : str
        The sub-key to update, e.g. "language_id", "back_translation".
    results_by_code : dict
        ``{target_lang_code: {status: ..., checked_at: ..., ...}}``.
    """
    data = json.loads(dataset_path.read_text(encoding="utf-8"))
    changed = 0
    for rec in data:
        code = rec["target_lang_code"]
        if code in results_by_code:
            rec.setdefault("validation", {})[validator_key] = results_by_code[code]
            changed += 1
    dataset_path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"  [validation_io] wrote {validator_key} for {changed} records → {dataset_path}")


def staleness_status(record: dict, validator_key: str) -> str | None:
    """Return ``"STALE"`` if the record was regenerated after the last validation run."""
    checked = (
        record.get("validation", {}).get(validator_key, {}).get("checked_at", "")
    )
    record_ts = record.get("timestamp", "")
    if checked and record_ts and record_ts > checked:
        return "STALE"
    return None
