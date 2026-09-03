"""
Orchestrates the full Data View model build: load -> per state, read off its
own active (already-selected, fully-dense) factor set -> drop near-duplicate
columns -> fit univariate (each factor) + multivariate (all active factors
together) -> per-state scores.

See models.py's module docstring for why this is fit PER STATE rather than
one national model: casefile.xlsx's sparsity pattern IS LKI's own per-state
factor selection, not missing data to filter around.

Deterministic given the static input files, so the result is built once per
process and cached (get_dataview_model()) -- mirrors build.py's gazetteer
cache, just for a heavier one-time computation instead of a JSON load.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .loader import load_casefile
from .models import CaseFile, DataViewModel, DistrictRecord, StateModel
from .prescriptive import raw_intervention_score
from .regression import fit_multivariate, fit_univariate
from .stats import active_factors_for_state, bucket_factors, classify_bucket, drop_multicollinear

_INTERVENTION_REFERENCE_TARGET_REDUCTION = 0.2


@dataclass
class StateScore:
    state_name: str
    avg_outcome: float
    confidence_value: float
    intervention_index: float  # normalized to [0, 1] across all states


def _fit_state_model(state_name: str, all_districts_in_state: list[DistrictRecord], casefile: CaseFile) -> StateModel | None:
    """`all_districts_in_state` uses EVERY casefile row for this state
    (including ones our crosswalk couldn't resolve to a map id) -- active
    factor discovery is a property of the source data, independent of
    whether we can render a given district on our map."""
    active = active_factors_for_state(all_districts_in_state, casefile.factor_names)
    active = drop_multicollinear(active, all_districts_in_state)
    if not active:
        return None

    univariate = {}
    for name in active:
        model = fit_univariate(name, all_districts_in_state, classify_bucket(name))
        if model is not None:
            univariate[name] = model

    multivariate = fit_multivariate(active, all_districts_in_state)
    if multivariate is None:
        return None

    return StateModel(state_name=state_name, factor_names=active, univariate=univariate, multivariate=multivariate)


def build_dataview_model() -> DataViewModel:
    casefile = load_casefile()

    by_state: dict[str, list[DistrictRecord]] = {}
    for d in casefile.districts:
        by_state.setdefault(d.state_name, []).append(d)

    states: dict[str, StateModel] = {}
    for state_name, districts in by_state.items():
        state_model = _fit_state_model(state_name, districts, casefile)
        if state_model is not None:
            states[state_name] = state_model

    if not states:
        raise RuntimeError("could not fit a model for any state")

    all_active_factors = sorted({f for sm in states.values() for f in sm.factor_names})
    buckets = bucket_factors(all_active_factors)

    return DataViewModel(casefile=casefile, buckets=buckets, states=states)


def compute_state_scores(model: DataViewModel) -> dict[str, StateScore]:
    """Covers every state with a fitted StateModel -- with per-state fitting
    now using each state's own small, dense, pre-selected factor set (see
    module docstring), this should be all/nearly all states, unlike the
    earlier national-refiltering approach."""
    resolved = model.casefile.resolved_districts()
    by_state: dict[str, list[DistrictRecord]] = {}
    for d in resolved:
        by_state.setdefault(d.state_name, []).append(d)

    raw_scores: dict[str, float] = {}
    avg_outcomes: dict[str, float] = {}
    confidences: dict[str, float] = {}

    for state_name, state_model in model.states.items():
        districts = by_state.get(state_name, [])
        if not districts:
            continue  # every district in this state was unresolvable by our crosswalk -- nothing to render or score
        avg_outcomes[state_name] = float(np.mean([d.dropout_rate for d in districts]))
        confidences[state_name] = state_model.multivariate.r2
        factor_buckets = {f: classify_bucket(f) for f in state_model.factor_names}
        raw_scores[state_name] = raw_intervention_score(
            districts, state_model, factor_buckets, _INTERVENTION_REFERENCE_TARGET_REDUCTION
        )

    values = list(raw_scores.values())
    lo, hi = (min(values), max(values)) if values else (0.0, 0.0)
    span = hi - lo

    return {
        state_name: StateScore(
            state_name=state_name,
            avg_outcome=avg_outcomes[state_name],
            confidence_value=confidences[state_name],
            intervention_index=((raw_scores[state_name] - lo) / span) if span > 0 else 0.0,
        )
        for state_name in raw_scores
    }


_model_cache: DataViewModel | None = None


def get_dataview_model() -> DataViewModel:
    global _model_cache
    if _model_cache is None:
        _model_cache = build_dataview_model()
    return _model_cache
