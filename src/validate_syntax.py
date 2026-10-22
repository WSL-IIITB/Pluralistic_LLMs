"""validate_syntax.py — structural / fluency validation of native answers.

Two independent layers, run against all records in a dataset (read-only):

LAYER 1 — Script well-formedness (no external model; pure Python + `regex`):
  1. Literal unrendered Unicode escapes leaking into the text (hard flag).
  2. Per-character Unicode-script detection vs. the language's officially valid
     script(s) from config/languages.json (`script` + `official_scripts`).
  3. Orphaned combining marks (Mc/Mn) without a valid base character.

LAYER 2 — Fluency / anomaly scoring (Masked-LM pseudo-perplexity):
  Uses google/muril-base-cased (cached in models/muril-base-cased), a BERT-base
  trained on 17 Indic languages + English. Coverage is checked per language;
  languages the model was NOT trained on are reported NO-SCORER-AVAILABLE.

This validator only REPORTS; it never writes to data/raw/.
"""

import argparse
import json
import math
import unicodedata

import regex

from src.logging_config import PROJECT_ROOT
from src.validation_io import update_validation, now_iso

DEFAULT_QUERY_ID = "self_image_life_goal"
LANG_FILE = PROJECT_ROOT / "config" / "languages.json"
MURIL_DIR = PROJECT_ROOT / "models" / "muril-base-cased"

# ---------------------------------------------------------------------------
# Layer 1 — script well-formedness
# ---------------------------------------------------------------------------

# A literal backslash-u-4hex (or \U-8hex) substring means unrendered Unicode
# escapes leaked into the text instead of real characters. This happened in
# mni-IN's back-translation historically, so it is a hard flag.
UNICODE_ESCAPE_RE = regex.compile(r"\\u[0-9a-fA-F]{4}|\\U[0-9a-fA-F]{8}")

# Map the human-readable script strings used in config/languages.json to the
# Unicode Script property names recognised by the `regex` module.
CONFIG_SCRIPT_TO_UNICODE = {
    "Bengali script": "Bengali",
    "Bengali script (Assamese)": "Bengali",
    "Devanagari script": "Devanagari",
    "Gujarati script": "Gujarati",
    "Kannada script": "Kannada",
    "Malayalam script": "Malayalam",
    "Odia (Oriya) script": "Oriya",
    "Gurmukhi script": "Gurmukhi",
    "Ol Chiki script": "Ol_Chiki",
    "Perso-Arabic script": "Arabic",
    "Perso-Arabic (Urdu) script": "Arabic",
    "Tamil script": "Tamil",
    "Telugu script": "Telugu",
    "Latin script": "Latin",
}

# Fraction of on-script *letter* characters below which a record is OK.
# A stray Latin email address, an isolated symbol, etc. should not trip this;
# only a meaningful amount of out-of-script letters does.
OUT_SCRIPT_RATIO = 0.03
OUT_SCRIPT_MIN_COUNT = 3


# Candidate script names relevant to this project's 22 languages. Used only to
# LABEL a character's script; using the `regex` module's \p{Script=...} property
# matching, not hand-rolled range tables.
SCRIPT_NAME_CANDIDATES = [
    "Bengali", "Devanagari", "Gujarati", "Kannada", "Malayalam", "Oriya",
    "Gurmukhi", "Ol_Chiki", "Arabic", "Tamil", "Telugu", "Latin",
    "Common", "Inherited",
]


def _script_of_char(ch: str) -> str:
    """Return the Unicode Script property name for a character (via regex)."""
    for name in SCRIPT_NAME_CANDIDATES:
        try:
            if regex.fullmatch(rf"\p{{Script={name}}}", ch):
                return name
        except regex.error:
            continue
    return ""


def _is_letter(ch: str) -> bool:
    cat = unicodedata.category(ch)
    return cat.startswith("L")


def _is_combining_mark(ch: str) -> bool:
    cat = unicodedata.category(ch)
    return cat in ("Mn", "Mc")


def _valid_scripts_for_lang(lang_entry: dict) -> list[str]:
    """Unicode script names that are officially valid for a language."""
    scripts = []
    for key in ("script",):
        raw = lang_entry.get(key)
        if raw and raw in CONFIG_SCRIPT_TO_UNICODE:
            scripts.append(CONFIG_SCRIPT_TO_UNICODE[raw])
    for raw in lang_entry.get("official_scripts", []):
        if raw in CONFIG_SCRIPT_TO_UNICODE:
            scripts.append(CONFIG_SCRIPT_TO_UNICODE[raw])
    # de-dup while preserving order (sd-IN lists Arabic in both fields)
    return list(dict.fromkeys(scripts))


def script_check(native_answer: str, valid_scripts: list[str]) -> list[str]:
    """Layer-1 checks. Returns a list of human-readable flag reasons ([]=OK)."""
    flags = []
    valid = set(valid_scripts)

    # 1) Unrendered unicode escapes — hard flag.
    escapes = UNICODE_ESCAPE_RE.findall(native_answer)
    if escapes:
        flags.append(f"literal unrendered unicode escapes: {', '.join(sorted(set(escapes))[:4])}")

    # 2) Out-of-script letters. Combining marks are attributed to their base
    #    letter so matras/viramas (Unicode "Inherited") don't get miscounted.
    chars = list(native_answer)
    letter_count = 0
    out_count = 0
    out_examples = []
    for i, ch in enumerate(chars):
        if _is_combining_mark(ch):
            # belongs to the last letter seen (its base)
            continue
        if not _is_letter(ch):
            continue
        script = _script_of_char(ch)
        if not script or script in ("Common", "Inherited"):
            continue
        letter_count += 1
        if script not in valid:
            out_count += 1
            if len(out_examples) < 6:
                out_examples.append(f"{ch!r}({script})")

    if letter_count and out_count >= OUT_SCRIPT_MIN_COUNT and out_count / letter_count >= OUT_SCRIPT_RATIO:
        pct = 100.0 * out_count / letter_count
        flags.append(
            f"out-of-script letters: {out_count}/{letter_count} ({pct:.1f}%) "
            f"e.g. {', '.join(out_examples)}"
        )

    # 3) Orphaned combining marks: an Mc/Mn char with no valid base of an
    #    allowed script in the same word. Stacked marks (e.g. vowel sign +
    #    virama) are fine as long as an allowed-script base letter exists.
    orphan_chars = []
    for i, ch in enumerate(chars):
        if not _is_combining_mark(ch):
            continue
        base_script = None
        for j in range(i - 1, -1, -1):
            pcat = unicodedata.category(chars[j])
            if pcat.startswith("P") or pcat.startswith("S") or pcat.startswith("Z"):
                break  # hit punctuation/symbol/space: no base in this word
            if pcat in ("Mn", "Mc"):
                continue  # stacked mark: keep looking past it
            if _is_letter(chars[j]):
                base_script = _script_of_char(chars[j])
                break
        if base_script is None or base_script not in valid:
            orphan_chars.append(f"U+{ord(ch):04X}({unicodedata.category(ch)})")

    if orphan_chars:
        flags.append(f"orphaned combining marks: {', '.join(orphan_chars[:8])}")

    return flags


# ---------------------------------------------------------------------------
# Layer 2 — fluency / anomaly scoring (MuRIL masked-LM)
# ---------------------------------------------------------------------------

# Languages MuRIL was pretrained on (paper + model card): 16 Indic + English.
MURIL_SUPPORTED = {
    "as-IN", "bn-IN", "gu-IN", "hi-IN", "kn-IN", "ks-IN", "ml-IN", "mr-IN",
    "ne-IN", "od-IN", "pa-IN", "sa-IN", "sd-IN", "ta-IN", "te-IN", "ur-IN",
    "en",
}

# Pseudo-perplexity outlier rule: flag scores above Q3 + 1.5*IQR (within-run).
OUTLIER_MULT = 1.5


def _masked_lm_scores(texts: list[str], model, tokenizer) -> list[float]:
    """Per-text pseudo-perplexity via masked-LM likelihood (lower = better).

    Each real token is masked in turn (batch of masks per text, one forward
    pass), the probability of the true token is read off, and the result is
    aggregated as exp(-mean log P(token)).
    """
    import torch

    model.eval()
    scores = []
    for text in texts:
        enc = tokenizer(text, return_tensors="pt", add_special_tokens=True, truncation=False)
        input_ids = enc["input_ids"]
        seq = input_ids[0]
        n = seq.size(0)
        # token positions that are real content (skip CLS/SEP)
        content_idx = [
            i for i in range(1, n - 1)
            if seq[i].item() not in (tokenizer.cls_token_id, tokenizer.sep_token_id, tokenizer.pad_token_id)
        ]
        total_logp = 0.0
        mask_token_id = tokenizer.mask_token_id
        # Small batch keeps peak memory low: the logits tensor is [B, seq, vocab]
        # (vocab ~105k for MuRIL), which is the dominant RAM consumer on CPU.
        B = 4
        with torch.no_grad():
            for start in range(0, len(content_idx), B):
                chunk = content_idx[start:start + B]
                batch = input_ids.repeat(len(chunk), 1)
                for bi, pos in enumerate(chunk):
                    batch[bi, pos] = mask_token_id
                logits = model(batch).logits  # [b, L, V]
                for bi, pos in enumerate(chunk):
                    true_id = seq[pos].item()
                    lp = logits[bi, pos].log_softmax(dim=-1)[true_id].item()
                    total_logp += lp
        mean_logp = total_logp / max(1, len(content_idx))
        scores.append(math.exp(-mean_logp))
    return scores


def _outlier_positions(scores: list[float]) -> set[int]:
    """Indices of within-run statistical outliers (high pseudo-PPL = anomalously
    low model fluency relative to the other languages in the same run)."""
    ranked = sorted(scores)
    n = len(ranked)
    if n < 4:
        return set()
    def q(f):
        idx = (n - 1) * f
        lo = math.floor(idx)
        hi = math.ceil(idx)
        if lo == hi:
            return ranked[lo]
        return ranked[lo] + (ranked[hi] - ranked[lo]) * (idx - lo)
    q1, q3 = q(0.25), q(0.75)
    iqr = q3 - q1
    upper = q3 + OUTLIER_MULT * iqr
    return {i for i, s in enumerate(scores) if s > upper}


# ---------------------------------------------------------------------------

_LANG_MODEL = None
_LANG_TOKENIZER = None


def _load_muril():
    global _LANG_MODEL, _LANG_TOKENIZER
    if _LANG_MODEL is None:
        import torch
        from transformers import AutoModelForMaskedLM, AutoTokenizer

        _LANG_TOKENIZER = AutoTokenizer.from_pretrained(str(MURIL_DIR))
        _LANG_MODEL = AutoModelForMaskedLM.from_pretrained(
            str(MURIL_DIR),
            torch_dtype=torch.float16,
            low_cpu_mem_usage=True,
        )
    return _LANG_MODEL, _LANG_TOKENIZER


def main(raw_file) -> None:
    records = json.loads(raw_file.read_text(encoding="utf-8"))
    langs = json.loads(LANG_FILE.read_text(encoding="utf-8"))["languages"]
    entry_by_code = {entry["code"]: entry for entry in langs}

    # Layer 1 — always cheap; do for all records.
    print(f"{'code':7s} | {'script check':33s} | fluency check")
    print("-" * 84)

    layer1_flags = {}        # code -> list[str]
    supported = []           # records MuRIL covers
    for rec in records:
        code = rec["target_lang_code"]
        entry = entry_by_code.get(code, {"script": "Latin script"})
        valid = _valid_scripts_for_lang(entry)
        if code == "en":
            valid = ["Latin"]
        fl = script_check(rec["native_answer"], valid)
        layer1_flags[code] = fl
        if code in MURIL_SUPPORTED:
            supported.append(rec)

    # Layer 2 — batch score the MuRIL-supported records.
    layer2_scores = {}
    if supported:
        model, tokenizer = _load_muril()
        texts = [r["native_answer"] for r in supported]
        scores = _masked_lm_scores(texts, model, tokenizer)
        layer2_scores = dict(zip([r["target_lang_code"] for r in supported], scores))
    outliers = _outlier_positions([layer2_scores[r["target_lang_code"]] for r in supported]) \
        if supported else set()
    outlier_codes = {supported[i]["target_lang_code"] for i in outliers}

    # Build per-record validation results.
    results_by_code = {}
    for rec in records:
        code = rec["target_lang_code"]
        s1 = "OK" if not layer1_flags[code] else "FLAGGED"
        if code not in MURIL_SUPPORTED:
            s2 = "NO-SCORER-AVAILABLE"
            score_val = None
        elif code in outlier_codes:
            s2 = "FLAGGED"
            score_val = layer2_scores.get(code)
        else:
            s2 = "OK"
            score_val = layer2_scores.get(code)
        results_by_code[code] = {
            "script_check": s1,
            "fluency_check": s2,
            "fluency_score": score_val,
            "checked_at": now_iso(),
        }

    for rec in records:
        code = rec["target_lang_code"]
        s1 = "OK" if not layer1_flags[code] else "FLAGGED"
        if code not in MURIL_SUPPORTED:
            s2 = "NO-SCORER-AVAILABLE"
        elif code in outlier_codes:
            s2 = f"FLAGGED"
        else:
            s2 = "OK"
        print(f"{code:7s} | {s1:33s} | {s2}")

    # Detail lines.
    print()
    for code in layer1_flags:
        if layer1_flags[code]:
            print(f"  [script] {code}: {'; '.join(layer1_flags[code])}")
    if layer2_scores:
        ranks = sorted(layer2_scores.items(), key=lambda kv: kv[1])
        print()
        print("  Pseudo-perplexity (MuRIL masked-LM, lower = more fluent):")
        for code, s in ranks:
            mark = "  <-- FLAGGED outlier" if code in outlier_codes else ""
            print(f"    {code:7s} {s:8.2f}{mark}")

    print()
    print(f"Total records checked: {len(records)}")
    print(f"Script check OK: {sum(1 for c in layer1_flags if not layer1_flags[c])}")
    print(f"Script check FLAGGED: {sum(1 for c in layer1_flags if layer1_flags[c])}")
    scored = len(layer2_scores)
    print(f"Fluency scored (MuRIL): {scored}")
    print(f"Fluency NO-SCORER-AVAILABLE: {len(records) - scored}")
    print(f"Fluency FLAGGED outliers: {len(outlier_codes)} -> {sorted(outlier_codes) if outlier_codes else 'none'}")

    update_validation(raw_file, "syntax", results_by_code)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Structural/script (Layer 1) + fluency (Layer 2) validation of native answers."
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