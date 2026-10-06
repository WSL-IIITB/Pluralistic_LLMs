"""
Per-state active-factor discovery + bucket classification.

LKI's own "Statistical Filtering" (their doc: keep factors with p < 0.05 and
|Pearson r| >= 0.4) is already reflected in which columns are populated for
a given state in casefile.xlsx -- see models.py's module docstring for how
this was confirmed. So this module does NOT re-run a correlation filter;
it just reads off each state's already-selected factor set, with one cheap
extra safety pass (drop_multicollinear) to guard against near-duplicate
columns within that small set feeding a degenerate regression.

Bucket classification is a KEYWORD-MATCHING RECONSTRUCTION, not sourced from
LKI's data -- metadata.xlsx (their own project-metadata file) was inspected
directly and contains only a project-level description, no factor->bucket
column.
"""

from __future__ import annotations

import numpy as np
from scipy import stats as scipy_stats

from .models import CaseFile, DistrictRecord

_PAIRWISE_R_MAX = 0.95  # only guards against near-identical columns -- LKI's own filtering already did the real correlation-vs-outcome work


def active_factors_for_state(state_districts: list[DistrictRecord], factor_names: list[str]) -> list[str]:
    """A factor is "active" for this state if every one of its districts (in
    the ORIGINAL casefile, before our crosswalk drops any) has a value --
    the signature of LKI's own per-state factor selection, per models.py's
    docstring."""
    if not state_districts:
        return []
    return [name for name in factor_names if all(d.factors.get(name) is not None for d in state_districts)]


def drop_multicollinear(
    factor_names: list[str], state_districts: list[DistrictRecord], pairwise_r_max: float = _PAIRWISE_R_MAX
) -> list[str]:
    """Greedy pass over an already-small, already-dense factor set (every
    district in state_districts has a value for every factor here, by
    construction of active_factors_for_state): drop any factor that's
    near-perfectly correlated with one already kept."""
    kept: list[str] = []
    kept_values: list[np.ndarray] = []

    for name in factor_names:
        values = np.array([d.factors[name] for d in state_districts], dtype=float)
        redundant = False
        if np.std(values) > 0:
            for kv in kept_values:
                if np.std(kv) == 0:
                    continue
                r, _ = scipy_stats.pearsonr(values, kv)
                if abs(r) >= pairwise_r_max:
                    redundant = True
                    break
        if not redundant:
            kept.append(name)
            kept_values.append(values)

    return kept


# Keyword -> bucket, checked against the factor's lowercased column name.
# First matching bucket wins; anything unmatched falls into socio_economic
# (the catch-all for NFHS-sourced household/demographic factors, which don't
# share a single consistent keyword the way school-infrastructure columns do).
_BUCKET_KEYWORDS: dict[str, tuple[str, ...]] = {
    "infrastructure": (
        "toilet", "electric", "building", "boundary", "furniture", "playground",
        "water", "drinking", "sanitation", "tap_", "hand_pump", "rain_water",
        "solar", "handwash", "urinal", "classroom",
    ),
    "digital_ict": ("internet", "comp", "ict", "desktop", "smart_class", "digital"),
    "teacher_profile": (
        "tch", "teach", "crc_coordinator", "district_officers",
        "block_level_officers", "acad_inspections", "smc_smdc",
    ),
}


def classify_bucket(factor_name: str) -> str:
    lowered = factor_name.lower()
    for bucket, keywords in _BUCKET_KEYWORDS.items():
        if any(kw in lowered for kw in keywords):
            return bucket
    return "socio_economic"


def bucket_factors(factor_names: list[str]) -> dict[str, list[str]]:
    buckets: dict[str, list[str]] = {}
    for name in factor_names:
        buckets.setdefault(classify_bucket(name), []).append(name)
    return buckets
