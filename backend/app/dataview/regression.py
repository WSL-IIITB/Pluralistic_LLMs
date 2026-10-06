"""
Univariate + multivariate regression, and the two sensitivity-ratio views
built from them -- LKI-SSM doc section 3.1 (Appendix: Formulas and
Calculations):

  Univariate: O = m*f + c, fit independently per factor, PER STATE (using
  only that state's own active factor set and districts -- see models.py's
  module docstring for why this is state-scoped, not national).
  a. Factor Profile: district i's share of factor f's total impact across
     all districts in the state.
  b. District Profile: factor i's share of the cumulative impact of all
     factors within one district (a stacked bar summing to 100%).

Both profiles are built from the SAME per-district contribution value,
contribution(factor, district) = m_factor * value_factor_district, just
normalized over a different axis (districts, vs. factors). Absolute value
is used for normalization -- a factor with a strong NEGATIVE correlation
(e.g. more electrified schools -> lower dropout) still represents a large
share of what's driving the district's outcome, which is what these charts
are meant to show.
"""

from __future__ import annotations

import numpy as np
from sklearn.linear_model import LinearRegression

from .models import DistrictRecord, MultivariateModel, StateModel, UnivariateModel

_MIN_MULTIVARIATE_SAMPLE = 5  # a state's own active factor set is already small (6-12) and dense; this only guards against a handful of tiny UTs


def fit_univariate(factor_name: str, districts: list[DistrictRecord], bucket: str) -> UnivariateModel | None:
    xs = [d.factors[factor_name] for d in districts]
    ys = [d.dropout_rate for d in districts]
    if len(xs) < 2 or np.std(xs) == 0:
        return None
    x = np.array(xs, dtype=float).reshape(-1, 1)
    y = np.array(ys, dtype=float)
    model = LinearRegression().fit(x, y)
    r2 = model.score(x, y)
    return UnivariateModel(
        factor_name=factor_name, m=float(model.coef_[0]), c=float(model.intercept_), r2=float(r2), n=len(xs), bucket=bucket
    )


def fit_multivariate(factor_names: list[str], districts: list[DistrictRecord]) -> MultivariateModel | None:
    """factor_names must already be this state's own active (fully dense)
    set -- every district here is expected to have a value for every one of
    them, by construction of stats.active_factors_for_state."""
    if len(districts) < _MIN_MULTIVARIATE_SAMPLE or not factor_names:
        return None
    rows = [[d.factors[f] for f in factor_names] for d in districts]
    outcomes = [d.dropout_rate for d in districts]

    x = np.array(rows, dtype=float)
    y = np.array(outcomes, dtype=float)
    model = LinearRegression().fit(x, y)
    r2 = model.score(x, y)
    coefficients = {name: float(coef) for name, coef in zip(factor_names, model.coef_)}
    return MultivariateModel(
        factor_names=list(factor_names), coefficients=coefficients, intercept=float(model.intercept_), r2=float(r2), n=len(rows)
    )


def _contribution(state_model: StateModel, district: DistrictRecord, factor_name: str) -> float | None:
    model = state_model.univariate.get(factor_name)
    value = district.factors.get(factor_name)
    if model is None or value is None:
        return None
    return abs(model.m * value)


def district_sensitivity_ratio(state_model: StateModel, district: DistrictRecord) -> dict[str, float]:
    """District Profile: each factor's share of this one district's total
    contribution magnitude, normalized to sum to 100 (percent)."""
    contributions = {
        name: c for name in state_model.factor_names for c in [_contribution(state_model, district, name)] if c is not None
    }
    total = sum(contributions.values())
    if total == 0:
        return {}
    return {name: (value / total) * 100 for name, value in contributions.items()}


def factor_sensitivity_ratio(state_model: StateModel, factor_name: str, districts: list[DistrictRecord]) -> dict[str, float]:
    """Factor Profile: each district's share of one factor's total
    contribution magnitude across the given district set (callers pass one
    state's districts), normalized to sum to 100 (percent). Keyed by
    district_id."""
    contributions = {
        d.district_id: c
        for d in districts
        if d.district_id is not None
        for c in [_contribution(state_model, d, factor_name)]
        if c is not None
    }
    total = sum(contributions.values())
    if total == 0:
        return {}
    return {district_id: (value / total) * 100 for district_id, value in contributions.items()}
