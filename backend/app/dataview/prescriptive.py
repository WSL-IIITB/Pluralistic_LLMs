"""
Prescriptive what-if, intervention index, and budget allocation.

LKI-SSM's doc gives the CONCEPTS and (for confidence) an example output value
(0.8358) but not the underlying formulas for confidence/intervention
index/budget allocation. Confidence is filled in by pipeline.py directly from
each state's own fitted MultivariateModel.r2 (in-sample R^2, the same
sklearn .score() the model was built with) -- intervention index and budget
allocation below are explicit RECONSTRUCTIONS, not verified against LKI's
actual (unpublished) implementation. Revisit if a better source ever
surfaces; until then, don't present these as more precise than they are.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

import numpy as np

from .models import DistrictRecord, StateModel

BucketPriority = Literal["nil", "low", "medium", "high", "critical"]

PRIORITY_WEIGHT: dict[BucketPriority, float] = {
    "nil": 0.0,
    "low": 0.25,
    "medium": 0.5,
    "high": 0.75,
    "critical": 1.0,
}


def _default_priorities(buckets_present: set[str]) -> dict[str, BucketPriority]:
    return {bucket: "medium" for bucket in buckets_present}


@dataclass
class FactorPrescription:
    factor_name: str
    bucket: str
    original: float
    prescribed: float


@dataclass
class PrescriptionResult:
    district_id: str
    target_reduction: float
    factors: list[FactorPrescription] = field(default_factory=list)


def prescribe_factor_changes(
    district: DistrictRecord,
    state_model: StateModel,
    factor_buckets: dict[str, str],  # factor_name -> bucket, for just this state's active factors
    target_reduction: float,
    bucket_priorities: dict[str, BucketPriority] | None = None,
) -> PrescriptionResult:
    """Distributes the outcome change needed to hit `target_reduction`
    (0-1, fraction of the district's CURRENT dropout_rate) across the
    state's multivariate model's factors, weighted by (a) each factor's
    coefficient magnitude -- a factor that moves the outcome a lot per unit
    needs a smaller absolute change to carry the same share of the total --
    and (b) its bucket's user-set priority (PRIORITY_WEIGHT). A factor whose
    bucket is "nil" priority, or whose model coefficient is exactly 0,
    keeps its original value untouched."""
    model = state_model.multivariate
    priorities = bucket_priorities or _default_priorities(set(factor_buckets.values()))

    delta_outcome = -target_reduction * district.dropout_rate

    weights: dict[str, float] = {}
    for factor_name in model.factor_names:
        beta = model.coefficients.get(factor_name, 0.0)
        value = district.factors.get(factor_name)
        bucket = factor_buckets.get(factor_name, "socio_economic")
        priority_weight = PRIORITY_WEIGHT[priorities.get(bucket, "medium")]
        if beta == 0.0 or value is None or priority_weight == 0.0:
            continue
        weights[factor_name] = priority_weight * abs(beta)

    total_weight = sum(weights.values())
    result = PrescriptionResult(district_id=district.district_id or district.raw_key, target_reduction=target_reduction)

    for factor_name in model.factor_names:
        value = district.factors.get(factor_name)
        bucket = factor_buckets.get(factor_name, "socio_economic")
        if value is None:
            continue
        weight = weights.get(factor_name)
        if weight is None or total_weight == 0:
            result.factors.append(FactorPrescription(factor_name=factor_name, bucket=bucket, original=value, prescribed=value))
            continue
        share = delta_outcome * (weight / total_weight)
        beta = model.coefficients[factor_name]
        delta_factor = share / beta
        result.factors.append(
            FactorPrescription(factor_name=factor_name, bucket=bucket, original=value, prescribed=value + delta_factor)
        )

    return result


def raw_intervention_score(
    state_districts: list[DistrictRecord],
    state_model: StateModel,
    factor_buckets: dict[str, str],
    reference_target_reduction: float = 0.2,
) -> float:
    """RECONSTRUCTED (LKI's doc doesn't give this formula at all): mean,
    across a state's districts, of the total |prescribed - original| factor
    movement required to hit a fixed reference target reduction. This is
    UNNORMALIZED -- pipeline.py min-max normalizes it across all states to
    produce the [0, 1] Intervention Index the choropleth actually renders,
    since "how much movement" is only meaningful relative to other states."""
    totals = []
    for district in state_districts:
        prescription = prescribe_factor_changes(district, state_model, factor_buckets, reference_target_reduction)
        totals.append(sum(abs(f.prescribed - f.original) for f in prescription.factors))
    return float(np.mean(totals)) if totals else 0.0


@dataclass
class BudgetShare:
    factor_name: str
    bucket: str
    amount: float


def allocate_budget(
    state_districts: list[DistrictRecord],
    state_model: StateModel,
    factor_buckets: dict[str, str],
    total_budget: float,
    bucket_priorities: dict[str, BucketPriority] | None = None,
    reference_target_reduction: float = 0.2,
) -> list[BudgetShare]:
    """RECONSTRUCTED, and explicitly a RELATIVE split, not a costed one --
    there is no unit-cost-per-factor data anywhere in LKI's public materials,
    so this distributes `total_budget` in proportion to (a) each factor's
    total required movement across the state's districts (from
    prescribe_factor_changes, which already accounts for coefficient
    magnitude) and (b) its bucket's priority weight. Callers/UI should state
    plainly that this is a relative allocation, not a unit-costed one."""
    priorities = bucket_priorities or _default_priorities(set(factor_buckets.values()))

    movement_by_factor: dict[str, float] = {name: 0.0 for name in state_model.multivariate.factor_names}
    for district in state_districts:
        prescription = prescribe_factor_changes(district, state_model, factor_buckets, reference_target_reduction, priorities)
        for f in prescription.factors:
            movement_by_factor[f.factor_name] += abs(f.prescribed - f.original)

    weighted: dict[str, float] = {}
    for factor_name, movement in movement_by_factor.items():
        bucket = factor_buckets.get(factor_name, "socio_economic")
        priority_weight = PRIORITY_WEIGHT[priorities.get(bucket, "medium")]
        if movement > 0 and priority_weight > 0:
            weighted[factor_name] = movement * priority_weight

    total_weight = sum(weighted.values())
    if total_weight == 0:
        return []

    return [
        BudgetShare(factor_name=name, bucket=factor_buckets.get(name, "socio_economic"), amount=total_budget * (w / total_weight))
        for name, w in weighted.items()
    ]
