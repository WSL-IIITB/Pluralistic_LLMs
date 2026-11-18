"""
Core cross-lingual similarity analysis functions.

Dependencies: standard library and numpy ONLY.
Do not import torch, transformers, sentence_transformers, or other project modules.
"""

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np


def load_records(path: str | Path) -> List[Dict[str, Any]]:
    """Load JSON records from a file path."""
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise ValueError(f"Expected a list of records in {path}, got {type(data)}")
    return data


def canonical_order(languages_json_path: str | Path) -> List[str]:
    """
    Return the canonical order of languages:
    codes from config/languages.json in file order, followed by 'en'.
    """
    with open(languages_json_path, "r", encoding="utf-8") as f:
        cfg = json.load(f)
    codes = [entry["code"] for entry in cfg["languages"]]
    return codes + ["en"]


def normalize_text(text: str) -> str:
    """
    Apply text normalisation per Section 3.3:
    - Remove markdown bold markers '**'
    - Remove list markers at line start: '1.', '1)', '-', '*', '•' followed by whitespace
    - Collapse all whitespace and newlines into single spaces and trim
    - Preserve all script characters, matras, etc. exactly without Unicode normalisation.
    """
    if not text:
        return ""

    lines = text.splitlines()
    cleaned_lines = []
    # Pattern: optional whitespace, then list marker (digit+(.|\\)) or [-*•]), then 1+ whitespace
    marker_pattern = re.compile(r"^\s*(?:\d+[.)]|[-*•])\s+")

    for line in lines:
        # Remove bold markers
        line_clean = line.replace("**", "")
        # Remove leading list markers
        line_clean = marker_pattern.sub("", line_clean)
        cleaned_lines.append(line_clean)

    joined = " ".join(cleaned_lines)
    # Collapse whitespace into single space and trim
    return re.sub(r"\s+", " ", joined).strip()


def usable(record: Dict[str, Any], space: str) -> bool:
    """
    A record is usable in a space if:
    - generation_failed is not True
    - normalised text is non-empty
    space must be 'native' or 'english'.
    """
    if record.get("generation_failed", False) is True:
        return False

    if space == "native":
        raw_text = record.get("native_answer", "")
    elif space == "english":
        raw_text = record.get("back_translated_answer_en", "")
    else:
        raise ValueError(f"Invalid space: {space}. Must be 'native' or 'english'.")

    norm_text = normalize_text(raw_text or "")
    return bool(norm_text)


def reliable(
    record: Dict[str, Any], space: str, known_bt_limits: Optional[set] = None
) -> Tuple[bool, List[str]]:
    """
    Determine if record is in the reliable view per Section 3.5.
    'en' is always reliable if usable.
    Returns (is_reliable, list_of_reasons_if_unreliable).
    """
    reasons: List[str] = []
    code = record.get("target_lang_code", "")

    # Check usability first
    if not usable(record, space):
        if record.get("generation_failed", False) is True:
            reasons.append("generation_failed")
        else:
            reasons.append("empty_text")
        return False, reasons

    # 'en' is always reliable if usable
    if code == "en":
        return True, []

    # Check review_required
    if record.get("review_required") is True:
        reasons.append("review_required")

    if space == "english":
        # Check back_translation status
        val = record.get("validation", {})
        bt = val.get("back_translation", {}) if isinstance(val, dict) else {}
        bt_status = bt.get("status") if isinstance(bt, dict) else None
        if bt_status != "OK":
            reasons.append(f"back_translation_status_{bt_status or 'MISSING'}")

        # Check known back-translation limits
        limits = known_bt_limits if known_bt_limits is not None else set()
        if code in limits:
            reasons.append("known_backtranslation_limit")

    is_rel = len(reasons) == 0
    return is_rel, reasons


def cosine_matrix(embeddings: np.ndarray, usable_mask: np.ndarray) -> np.ndarray:
    """
    Compute cosine similarity matrix from embeddings (shape N x D) and usable_mask (shape N).
    Unusable rows/columns are set to NaN.
    Vectors must be L2-normalised (asserted within 1e-5 of 1.0).
    """
    n = len(embeddings)
    matrix = np.full((n, n), np.nan, dtype=np.float64)

    # Verify unit norms for usable embeddings
    for i in range(n):
        if usable_mask[i]:
            norm = float(np.linalg.norm(embeddings[i]))
            if abs(norm - 1.0) > 1e-5:
                raise ValueError(
                    f"Vector at index {i} is not unit norm: {norm:.8f} (tol=1e-5)"
                )

    usable_indices = np.where(usable_mask)[0]
    if len(usable_indices) > 0:
        sub_emb = embeddings[usable_indices]
        # Dot product of normalized vectors = cosine similarity
        sim_sub = np.dot(sub_emb, sub_emb.T)
        for i_idx, r in enumerate(usable_indices):
            for j_idx, c in enumerate(usable_indices):
                matrix[r, c] = sim_sub[i_idx, j_idx]

    return matrix


def sim_to_baseline(
    matrix: np.ndarray, order: List[str], baseline: str = "en"
) -> Dict[str, Optional[float]]:
    """
    Return dictionary mapping each language code L (except baseline)
    to its cosine similarity with the baseline.
    Returns None if either entry is unusable (NaN).
    """
    if baseline not in order:
        raise ValueError(f"Baseline '{baseline}' not found in order {order}")
    base_idx = order.index(baseline)

    res: Dict[str, Optional[float]] = {}
    for idx, code in enumerate(order):
        if code == baseline:
            continue
        val = matrix[idx, base_idx]
        res[code] = None if np.isnan(val) else float(val)
    return res


def mean_sim_to_others(
    matrix: np.ndarray, order: List[str], exclude: Tuple[str, ...] = ("en",)
) -> Dict[str, Optional[float]]:
    """
    Return dictionary mapping each language code L (except excluded codes)
    to the mean of matrix[L, M] over all M not in exclude and M != L, ignoring NaN.
    Returns None if no valid pairs exist.
    """
    res: Dict[str, Optional[float]] = {}
    n = len(order)

    for i, code in enumerate(order):
        if code in exclude:
            continue
        other_vals = []
        for j, other_code in enumerate(order):
            if j == i or other_code in exclude:
                continue
            val = matrix[i, j]
            if not np.isnan(val):
                other_vals.append(val)

        if len(other_vals) == 0:
            res[code] = None
        else:
            res[code] = float(np.mean(other_vals))
    return res


def group_stats(
    matrix: np.ndarray,
    order: List[str],
    groups: Dict[str, List[str]],
    baseline: str = "en",
) -> List[Dict[str, Any]]:
    """
    Compute group statistics per Section 3.6.
    baseline ('en') is never a group member.
    For each group:
      - n (usable members with valid sim_to_en)
      - mean_sim_to_en, std (population ddof=0), min, max
      - within_mean (mean pairwise similarity within group, None if n < 2)
      - between_mean (mean similarity between group members and non-baseline languages outside group)
    """
    if baseline not in order:
        raise ValueError(f"Baseline '{baseline}' not found in order")
    base_idx = order.index(baseline)
    code_to_idx = {code: idx for idx, code in enumerate(order)}

    # Exclude baseline from outside pool
    non_baseline_indices = {
        idx for code, idx in code_to_idx.items() if code != baseline
    }

    stats = []
    for grp_name, members in groups.items():
        # Clean members: exclude baseline if present
        clean_members = [m for m in members if m != baseline and m in code_to_idx]
        member_indices = [code_to_idx[m] for m in clean_members]

        # sim_to_en for usable members
        sim_en_vals = []
        usable_member_indices = []
        for idx in member_indices:
            val = matrix[idx, base_idx]
            if not np.isnan(val):
                sim_en_vals.append(val)
                usable_member_indices.append(idx)

        n = len(sim_en_vals)
        if n == 0:
            stats.append(
                {
                    "group": grp_name,
                    "n": 0,
                    "mean_sim_to_en": None,
                    "std": None,
                    "min": None,
                    "max": None,
                    "within_mean": None,
                    "between_mean": None,
                }
            )
            continue

        mean_sim = float(np.mean(sim_en_vals))
        std_sim = float(np.std(sim_en_vals, ddof=0))
        min_sim = float(np.min(sim_en_vals))
        max_sim = float(np.max(sim_en_vals))

        # within_mean: pairwise (i, j) for i < j in usable_member_indices
        within_vals = []
        for i_pos in range(len(usable_member_indices)):
            for j_pos in range(i_pos + 1, len(usable_member_indices)):
                val = matrix[
                    usable_member_indices[i_pos], usable_member_indices[j_pos]
                ]
                if not np.isnan(val):
                    within_vals.append(val)
        within_mean = (
            float(np.mean(within_vals)) if len(within_vals) > 0 else None
        )

        # between_mean: between usable_member_indices and usable non-baseline outside members
        outside_indices = (
            non_baseline_indices - set(member_indices)
        )
        between_vals = []
        for m_idx in usable_member_indices:
            for out_idx in outside_indices:
                val = matrix[m_idx, out_idx]
                if not np.isnan(val):
                    between_vals.append(val)
        between_mean = (
            float(np.mean(between_vals)) if len(between_vals) > 0 else None
        )

        stats.append(
            {
                "group": grp_name,
                "n": n,
                "mean_sim_to_en": mean_sim,
                "std": std_sim,
                "min": min_sim,
                "max": max_sim,
                "within_mean": within_mean,
                "between_mean": between_mean,
            }
        )

    return stats


def spearman(x: List[float], y: List[float]) -> Optional[float]:
    """
    Spearman rank correlation using numpy.
    Drops pairs where either x or y is NaN or None.
    Handles ties by assigning average ranks.
    Returns None if fewer than 3 valid pairs or if either variable has zero variance.
    """
    valid_pairs = []
    for a, b in zip(x, y):
        if a is not None and b is not None and not np.isnan(a) and not np.isnan(b):
            valid_pairs.append((float(a), float(b)))

    if len(valid_pairs) < 3:
        return None

    arr = np.array(valid_pairs, dtype=np.float64)
    x_vals = arr[:, 0]
    y_vals = arr[:, 1]

    def rankdata_avg(vals: np.ndarray) -> np.ndarray:
        n = len(vals)
        sort_indices = np.argsort(vals)
        ranks = np.empty(n, dtype=np.float64)
        i = 0
        while i < n:
            j = i
            while j + 1 < n and vals[sort_indices[j + 1]] == vals[sort_indices[i]]:
                j += 1
            # Average rank: 1-based indexing
            avg_rank = (i + 1 + j + 1) / 2.0
            for k in range(i, j + 1):
                ranks[sort_indices[k]] = avg_rank
            i = j + 1
        return ranks

    rank_x = rankdata_avg(x_vals)
    rank_y = rankdata_avg(y_vals)

    std_x = np.std(rank_x, ddof=0)
    std_y = np.std(rank_y, ddof=0)

    if std_x < 1e-12 or std_y < 1e-12:
        return None

    cov = np.mean((rank_x - np.mean(rank_x)) * (rank_y - np.mean(rank_y)))
    return float(cov / (std_x * std_y))


def sha256_file(path: str | Path) -> str:
    """Compute sha256 hex digest of a file."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()
