"""
Core pure functions for LLM-assisted theme coding and keyword extraction.

Standard library + numpy only.
May import from src.similarity_core and src.auto_document read-only.
Must not import torch, sentence_transformers, or requests.
"""

import json
import math
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

import numpy as np

# Pattern for valid theme ID: lowercase starting with letter, followed by lowercase alphanumeric/underscore
THEME_ID_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")

# Pattern for valid word token: lowercase a-z with optional hyphens/apostrophes
TOKEN_PATTERN = re.compile(r"[a-z]+(?:[-'][a-z]+)*")

# Sentence/segment split punctuation: . ! ? ; : ( ) , " and curly quotes
SEGMENT_SPLIT_PATTERN = re.compile(r'[.!?;:(),"\u201c\u201d\u2018\u2019]+')


def load_codebook(path: str | Path) -> Dict[str, Any]:
    """
    Load and validate a codebook JSON per Section 3.4 rules:
    - theme ids match ^[a-z][a-z0-9_]*$
    - theme ids are unique
    - 3 to 12 themes
    - every theme has non-empty 'label' and 'definition'
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Codebook file not found: {path}")

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    if not isinstance(data, dict):
        raise ValueError(f"Codebook root must be an object, got {type(data)}")

    themes = data.get("themes")
    if not isinstance(themes, list):
        raise ValueError("Codebook must contain a 'themes' list")

    if not (3 <= len(themes) <= 12):
        raise ValueError(f"Codebook must have 3 to 12 themes, got {len(themes)}")

    seen_ids: Set[str] = set()
    for idx, t in enumerate(themes):
        if not isinstance(t, dict):
            raise ValueError(f"Theme at index {idx} must be an object")

        tid = t.get("id")
        label = t.get("label")
        definition = t.get("definition")

        if not tid or not isinstance(tid, str) or not THEME_ID_PATTERN.match(tid):
            raise ValueError(f"Invalid theme id '{tid}' at index {idx}. Must match ^[a-z][a-z0-9_]*$")

        if tid in seen_ids:
            raise ValueError(f"Duplicate theme id '{tid}' at index {idx}")
        seen_ids.add(tid)

        if not label or not isinstance(label, str) or not label.strip():
            raise ValueError(f"Theme '{tid}' has empty label")

        if not definition or not isinstance(definition, str) or not definition.strip():
            raise ValueError(f"Theme '{tid}' has empty definition")

    return data


def codebook_is_approved(codebook: Dict[str, Any]) -> bool:
    """Return True if codebook status is 'APPROVED'."""
    return codebook.get("status") == "APPROVED"


def render_prompt(
    template: str, query: str, codebook: Dict[str, Any], text: str
) -> str:
    """
    Render prompt template with {query}, {theme_lines}, and {text}.
    theme_lines is formatted as:
      - <id>: <label>. <definition>
    """
    theme_lines_list = []
    for t in codebook.get("themes", []):
        theme_lines_list.append(f"- {t['id']}: {t['label']}. {t['definition']}")
    theme_lines = "\n".join(theme_lines_list)

    return template.format(
        query=query,
        theme_lines=theme_lines,
        text=text,
    )


def norm_for_match(text: str) -> str:
    """
    Normalize text for evidence quote matching:
    - Lowercase
    - Map curly quotes to straight quotes
    - Collapse all whitespace to single spaces and trim
    """
    if not text:
        return ""
    # Map curly quotes to straight quotes
    t = text.replace("\u201c", '"').replace("\u201d", '"').replace("\u2018", "'").replace("\u2019", "'")
    t = t.lower()
    return re.sub(r"\s+", " ", t).strip()


def verify_evidence(evidence: str, text: str) -> bool:
    """
    Verify evidence quote against text per Section 3.6:
    - Match after lowercasing, whitespace collapsing, curly quote normalization
    - Strip surrounding quotation marks and leading/trailing '...'
    - Quote must be 1 to 40 words
    - Must be a contiguous substring of the matching-normalized input text
    """
    if not evidence or not text:
        return False

    norm_quote = norm_for_match(evidence)

    # Strip surrounding whitespace, quotes, and leading/trailing '...'
    quote_clean = norm_quote.strip(" '\"")
    while quote_clean.startswith("...") or quote_clean.endswith("..."):
        if quote_clean.startswith("..."):
            quote_clean = quote_clean[3:].strip(" '\"")
        if quote_clean.endswith("..."):
            quote_clean = quote_clean[:-3].strip(" '\"")

    if not quote_clean:
        return False

    words = quote_clean.split()
    if not (1 <= len(words) <= 40):
        return False

    norm_full_text = norm_for_match(text)
    return quote_clean in norm_full_text


def apply_verification(
    themes: Dict[str, Dict[str, Any]], text: str
) -> Dict[str, Dict[str, Any]]:
    """
    Take a parsed themes dict and return a new dict with 'evidence_verified'
    boolean added to each theme entry.
    """
    verified_themes: Dict[str, Dict[str, Any]] = {}
    for tid, tinfo in themes.items():
        present = bool(tinfo.get("present", False))
        ev = str(tinfo.get("evidence", "") or "")
        ev_ok = verify_evidence(ev, text) if present else False
        verified_themes[tid] = {
            "present": present,
            "evidence": ev,
            "evidence_verified": ev_ok,
        }
    return verified_themes


def parse_tag_response(
    raw: str, codebook: Dict[str, Any]
) -> Tuple[Optional[Dict[str, Dict[str, Any]]], str, Optional[str], List[str]]:
    """
    Parse model response JSON into (themes_dict, other_note, error_message, keywords_list).
    Rules:
      - Must be strict JSON (no extra text before/after)
      - Must contain 'themes' dict
      - Must contain every codebook theme id exactly once
      - Each theme value must have 'present' (bool) and 'evidence' (str)
      - Must contain 'other_note' (str)
      - Optionally contains 'keywords' (list of str)
    Returns (None, "", error_msg, []) on failure.
    """
    if not raw or not isinstance(raw, str):
        return None, "", "Raw response is empty or not string", []

    s = raw.strip()
    try:
        data = json.loads(s)
    except Exception as e:
        return None, "", f"JSON decode error: {e}", []

    if not isinstance(data, dict):
        return None, "", f"Root JSON must be object, got {type(data).__name__}", []

    themes_obj = data.get("themes")
    if not isinstance(themes_obj, dict):
        return None, "", "Missing or invalid 'themes' object", []

    other_note = str(data.get("other_note", "") or "")
    raw_kw = data.get("keywords", [])
    keywords_list = [str(k).strip() for k in raw_kw if isinstance(k, (str, int, float)) and str(k).strip()]

    expected_ids = {t["id"] for t in codebook.get("themes", [])}
    actual_ids = set(themes_obj.keys())

    if actual_ids != expected_ids:
        missing = expected_ids - actual_ids
        extra = actual_ids - expected_ids
        errs = []
        if missing:
            errs.append(f"missing themes: {sorted(missing)}")
        if extra:
            errs.append(f"extra themes: {sorted(extra)}")
        return None, "", "; ".join(errs), []

    validated_themes: Dict[str, Dict[str, Any]] = {}
    for tid in expected_ids:
        tval = themes_obj[tid]
        if not isinstance(tval, dict):
            return None, "", f"Theme '{tid}' value must be an object", []

        if "present" not in tval or not isinstance(tval["present"], bool):
            return None, "", f"Theme '{tid}' must have boolean 'present'", []

        if "evidence" not in tval or not isinstance(tval["evidence"], str):
            return None, "", f"Theme '{tid}' must have string 'evidence'", []

        validated_themes[tid] = {
            "present": tval["present"],
            "evidence": tval["evidence"],
        }

    return validated_themes, other_note, None, keywords_list


def tokenize_segments(text: str) -> List[List[str]]:
    """
    Split text into segments at . ! ? ; : ( ) , " and curly quotes.
    Extract lowercase tokens [a-z]+(?:[-'][a-z]+)* within each segment.
    Tokens/n-grams never cross segment boundaries.
    """
    if not text:
        return []

    segments = SEGMENT_SPLIT_PATTERN.split(text)
    tokenized_segments = []
    for seg in segments:
        tokens = TOKEN_PATTERN.findall(seg.lower())
        if tokens:
            tokenized_segments.append(tokens)
    return tokenized_segments


def build_stopwords(stopwords_file_path: str | Path, query_text: str) -> Set[str]:
    """
    Build set of stopwords: words from config/stopwords_en.txt plus
    every token of 3 or more letters from the query's source_query_en.
    """
    stopwords = set()
    path = Path(stopwords_file_path)
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                w = line.strip().lower()
                if w:
                    stopwords.add(w)

    if query_text:
        q_tokens = TOKEN_PATTERN.findall(query_text.lower())
        for qt in q_tokens:
            if len(qt) >= 3:
                stopwords.add(qt)

    return stopwords


def candidate_terms(text: str, stopwords: Set[str]) -> List[str]:
    """
    Generate candidate unigrams and bigrams from text:
    - Unigrams: >= 3 letters, not in stopwords
    - Bigrams: both tokens not in stopwords, never crossing segment boundaries
    Returns unique candidates preserving order of first appearance.
    """
    segments = tokenize_segments(text)
    candidates: List[str] = []
    seen: Set[str] = set()

    for seg in segments:
        # Unigrams
        for tok in seg:
            if len(tok) >= 3 and tok not in stopwords:
                if tok not in seen:
                    seen.add(tok)
                    candidates.append(tok)

        # Bigrams
        for i in range(len(seg) - 1):
            t1, t2 = seg[i], seg[i + 1]
            if t1 not in stopwords and t2 not in stopwords:
                bg = f"{t1} {t2}"
                if bg not in seen:
                    seen.add(bg)
                    candidates.append(bg)

    return candidates


def tfidf_scores(
    docs_terms: List[List[str]],
) -> List[Dict[str, float]]:
    """
    Compute TF-IDF scores for each document per Section 3.8:
    - N = total number of documents
    - tf = raw count of term in document
    - df = number of documents containing term
    - idf = ln((1 + N) / (1 + df)) + 1
    - score = tf * idf
    """
    n_docs = len(docs_terms)
    # Compute df
    df: Dict[str, int] = {}
    for terms in docs_terms:
        unique_in_doc = set(terms)
        for t in unique_in_doc:
            df[t] = df.get(t, 0) + 1

    # Compute idf
    idf: Dict[str, float] = {}
    for t, doc_freq in df.items():
        idf[t] = math.log((1.0 + n_docs) / (1.0 + doc_freq)) + 1.0

    scores_list: List[Dict[str, float]] = []
    for terms in docs_terms:
        tf: Dict[str, int] = {}
        for t in terms:
            tf[t] = tf.get(t, 0) + 1

        doc_scores: Dict[str, float] = {}
        for t, count in tf.items():
            doc_scores[t] = count * idf[t]
        scores_list.append(doc_scores)

    return scores_list


def select_top_k(scored_terms: Dict[str, float], k: int = 10) -> List[Tuple[str, float]]:
    """
    Rank terms by score descending, ties alphabetically ascending.
    De-duplication walk: skip a unigram if it is a token of an already selected bigram.
    Returns list of (term, score) of up to length k.
    """
    if not scored_terms:
        return []

    # Sort items: (-score, term)
    sorted_items = sorted(scored_terms.items(), key=lambda item: (-item[1], item[0]))

    selected: List[Tuple[str, float]] = []
    selected_bigram_tokens: Set[str] = set()

    for term, score in sorted_items:
        if len(selected) >= k:
            break

        is_unigram = " " not in term
        if is_unigram:
            if term in selected_bigram_tokens:
                continue
            selected.append((term, score))
        else:
            # Bigram
            selected.append((term, score))
            for tok in term.split():
                selected_bigram_tokens.add(tok)

    return selected


def jaccard(a: Set[Any], b: Set[Any]) -> Optional[float]:
    """
    Compute Jaccard similarity: |a & b| / |a | b|.
    Returns None if both sets are empty.
    """
    if not a and not b:
        return None
    union_len = len(a | b)
    if union_len == 0:
        return None
    return float(len(a & b) / union_len)


def cohens_kappa(labels_a: Sequence[int], labels_b: Sequence[int]) -> Optional[float]:
    """
    Compute Cohen's kappa for two binary sequences (0 and 1).
    Returns None if undefined (e.g. fewer than 2 items or expected agreement == 1.0).
    """
    if len(labels_a) != len(labels_b) or len(labels_a) == 0:
        return None

    n = len(labels_a)
    # Observed agreement
    agree = sum(1 for a, b in zip(labels_a, labels_b) if a == b)
    po = agree / n

    # Marginals
    a1 = sum(labels_a) / n
    a0 = 1.0 - a1
    b1 = sum(labels_b) / n
    b0 = 1.0 - b1

    pe = (a1 * b1) + (a0 * b0)
    if abs(1.0 - pe) < 1e-12:
        return None

    return float((po - pe) / (1.0 - pe))


def percent_agreement(labels_a: Sequence[int], labels_b: Sequence[int]) -> Optional[float]:
    """Compute percentage of agreeing pairs (0.0 to 100.0). Returns None if empty."""
    if len(labels_a) != len(labels_b) or len(labels_a) == 0:
        return None
    agree = sum(1 for a, b in zip(labels_a, labels_b) if a == b)
    return float((agree / len(labels_a)) * 100.0)


# -------------------------------------------------------------------------
# Theme Table Builders for Stage 2
# -------------------------------------------------------------------------


def build_theme_frequency_rows(
    theme_ids: List[str],
    presence_by_lang: Dict[str, Dict[str, bool]],
    considered_langs: List[str],
    baseline_code: str = "en",
) -> List[List[Any]]:
    """
    Produce rows for theme_frequency.csv:
    theme_id, n_considered, n_present, proportion, en_present, languages_present
    """
    rows = []
    en_pres_dict = presence_by_lang.get(baseline_code, {})

    for tid in theme_ids:
        langs_with_theme = [
            code for code in considered_langs
            if presence_by_lang.get(code, {}).get(tid, False)
        ]
        n_cons = len(considered_langs)
        n_pres = len(langs_with_theme)
        prop = (n_pres / n_cons) if n_cons > 0 else 0.0

        en_pres = ""
        if baseline_code in presence_by_lang:
            en_pres = "1" if en_pres_dict.get(tid, False) else "0"

        rows.append([
            tid,
            n_cons,
            n_pres,
            f"{prop:.4f}",
            en_pres,
            " ".join(langs_with_theme),
        ])
    return rows


def build_language_vs_english_rows(
    presence_by_lang: Dict[str, Dict[str, bool]],
    claimed_presence_by_lang: Dict[str, Dict[str, bool]],
    considered_langs: List[str],
    baseline_code: str = "en",
) -> List[List[Any]]:
    """
    Produce rows for language_vs_english.csv:
    code, n_themes, jaccard_with_en, themes_in_lang_not_en, themes_in_en_not_lang, verification_rate
    """
    en_themes = {
        tid for tid, pres in presence_by_lang.get(baseline_code, {}).items() if pres
    }

    rows = []
    for code in considered_langs:
        lang_themes = {
            tid for tid, pres in presence_by_lang.get(code, {}).items() if pres
        }
        n_themes = len(lang_themes)

        jac = jaccard(lang_themes, en_themes)
        jac_str = f"{jac:.4f}" if jac is not None else ""

        only_lang = sorted(lang_themes - en_themes)
        only_en = sorted(en_themes - lang_themes)

        # Verification rate: verified present / claimed present
        claimed_themes = {
            tid for tid, pres in claimed_presence_by_lang.get(code, {}).items() if pres
        }
        if len(claimed_themes) == 0:
            ver_rate_str = ""
        else:
            ver_rate = len(lang_themes) / len(claimed_themes)
            ver_rate_str = f"{ver_rate:.4f}"

        rows.append([
            code,
            n_themes,
            jac_str,
            " ".join(only_lang),
            " ".join(only_en),
            ver_rate_str,
        ])
    return rows


def build_group_theme_rates_rows(
    theme_ids: List[str],
    presence_by_lang: Dict[str, Dict[str, bool]],
    groups_cfg: Dict[str, Dict[str, List[str]]],
    considered_langs: List[str],
) -> List[List[Any]]:
    """
    Produce rows for group_theme_rates.csv:
    grouping, group, theme, n, n_present, rate
    """
    considered_set = set(considered_langs)
    rows = []

    for grouping_name in ["families", "scripts"]:
        groups = groups_cfg.get(grouping_name, {})
        for grp_name, members in groups.items():
            valid_members = [m for m in members if m in considered_set]
            n_m = len(valid_members)
            for tid in theme_ids:
                if n_m == 0:
                    rows.append([grouping_name, grp_name, tid, 0, 0, ""])
                    continue
                pres_count = sum(
                    1 for m in valid_members
                    if presence_by_lang.get(m, {}).get(tid, False)
                )
                rate = pres_count / n_m
                rows.append([grouping_name, grp_name, tid, n_m, pres_count, f"{rate:.4f}"])

    return rows


def build_distinctive_themes_rows(
    theme_ids: List[str],
    presence_by_lang: Dict[str, Dict[str, bool]],
    considered_langs: List[str],
    rare_threshold: int = 2,
) -> List[List[Any]]:
    """
    Produce rows for distinctive_themes.csv:
    theme, type ('rare_present' | 'rare_absent'), count, languages
    """
    rows = []
    n_tot = len(considered_langs)

    for tid in theme_ids:
        present_langs = [
            code for code in considered_langs
            if presence_by_lang.get(code, {}).get(tid, False)
        ]
        absent_langs = [
            code for code in considered_langs
            if not presence_by_lang.get(code, {}).get(tid, False)
        ]

        # rare_present: present in <= rare_threshold
        if 0 < len(present_langs) <= rare_threshold:
            rows.append([tid, "rare_present", len(present_langs), " ".join(present_langs)])

        # rare_absent: absent in <= rare_threshold
        if 0 < len(absent_langs) <= rare_threshold:
            rows.append([tid, "rare_absent", len(absent_langs), " ".join(absent_langs)])

    return rows


def build_keyword_df_rows(
    terms_by_lang: Dict[str, Set[str]],
    considered_langs: List[str],
    baseline_code: str = "en",
) -> List[List[Any]]:
    """
    Produce rows for keyword_df.csv:
    term, n_languages, languages, in_en, class ('shared' | 'rare' | 'mid')
    """
    all_terms: Set[str] = set()
    for tset in terms_by_lang.values():
        all_terms.update(tset)

    n_cons = len(considered_langs)
    en_terms = terms_by_lang.get(baseline_code, set())
    rows = []

    for term in sorted(all_terms):
        matching_langs = [
            code for code in considered_langs
            if term in terms_by_lang.get(code, set())
        ]
        n_l = len(matching_langs)
        in_en = "1" if term in en_terms else "0"

        # Classification:
        # shared: n_l >= n_cons / 2
        # rare: n_l <= 2
        # else: mid
        if n_l >= math.ceil(n_cons / 2.0):
            cls = "shared"
        elif n_l <= 2:
            cls = "rare"
        else:
            cls = "mid"

        rows.append([
            term,
            n_l,
            " ".join(matching_langs),
            in_en,
            cls,
        ])
    return rows


def build_keyword_overlap_rows(
    terms_by_lang: Dict[str, Set[str]],
    considered_langs: List[str],
    baseline_code: str = "en",
) -> List[List[Any]]:
    """
    Produce rows for keyword_overlap_with_en.csv:
    code, jaccard_with_en, shared_terms
    """
    en_terms = terms_by_lang.get(baseline_code, set())
    rows = []

    for code in considered_langs:
        l_terms = terms_by_lang.get(code, set())
        jac = jaccard(l_terms, en_terms)
        jac_str = f"{jac:.4f}" if jac is not None else ""
        shared = sorted(l_terms & en_terms)
        rows.append([code, jac_str, " ".join(shared)])

    return rows
