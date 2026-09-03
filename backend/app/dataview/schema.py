"""
Pydantic wire-format contract for the Data View API -- mirrors ../schema.py's
`Camel`/`event_to_sse_data()` pattern exactly: snake_case Python attributes,
camelCase over the wire, one discriminated union on `type` for the SSE
stream. Kept as its OWN union (`DataViewEvent`), not merged into
`WorldviewEvent` -- per the plan's architecture decision, Data View doesn't
reuse Story View's shapes, it mirrors the pattern.

Unlike Story View's factors (a single national Pearson-correlation filter,
so a factor either "is" or "isn't" globally significant), Data View's active
factor set is PER STATE (see models.py's module docstring) -- so there is no
single global correlation r/p-value to report per factor. `FactorDefinedEvent`
instead carries the state it was activated for plus that state's own
univariate fit quality (`r2`), and one event is emitted per (state, factor)
pair -- the same factor name can legitimately appear in more than one event
if it's active in more than one state.

If you change a shape here, keep it in sync with whatever frontend types
consume it (mirrors ../schema.py's own docstring instruction) -- there's no
code generation between them.
"""

from __future__ import annotations

from typing import Annotated, Literal, Optional, Union

from pydantic import Field

from ..schema import Camel, event_to_sse_data
from .prescriptive import BucketPriority

__all__ = [
    "DistrictScoredEvent",
    "StateScoredEvent",
    "FactorDefinedEvent",
    "DataViewDoneEvent",
    "DataViewErrorEvent",
    "DataViewEvent",
    "event_to_sse_data",
    "DistrictFactorSensitivity",
    "DistrictProfileResponse",
    "PrescribedFactor",
    "PrescriptionResponse",
    "FactorDistrictSensitivity",
    "FactorSensitivityResponse",
    "BudgetFactorShare",
    "BudgetAllocationResponse",
    "BudgetRequest",
    "VerdictResponse",
]


# ── Streaming events (discriminated union on `type`, mirrors ../schema.py) ────


class DataViewEventBase(Camel):
    run_id: str = Field(alias="runId")


class DistrictScoredEvent(DataViewEventBase):
    type: Literal["district_scored"] = "district_scored"
    district_id: str = Field(alias="districtId")
    state_code: str = Field(alias="stateCode")
    outcome_value: float = Field(alias="outcomeValue")


class StateScoredEvent(DataViewEventBase):
    type: Literal["state_scored"] = "state_scored"
    state_code: str = Field(alias="stateCode")
    avg_outcome: float = Field(alias="avgOutcome")
    confidence_value: float = Field(alias="confidenceValue")
    intervention_index: float = Field(alias="interventionIndex")


class FactorDefinedEvent(DataViewEventBase):
    """One per (state, active factor) pair -- see module docstring for why
    there's no global correlation r/p-value to report here the way Story
    View's factors might imply; `r2` is this state's OWN univariate fit for
    this factor (state_model.univariate[factor_name].r2), not a national
    statistic."""

    type: Literal["factor_defined"] = "factor_defined"
    factor_id: str = Field(alias="factorId")
    label: str
    bucket: str
    state_code: str = Field(alias="stateCode")
    r2: float


class DataViewDoneEvent(DataViewEventBase):
    type: Literal["done"] = "done"
    district_count: int = Field(alias="districtCount")
    factor_count: int = Field(alias="factorCount")
    state_count: int = Field(alias="stateCount")


class DataViewErrorEvent(DataViewEventBase):
    type: Literal["error"] = "error"
    message: str


DataViewEvent = Annotated[
    Union[
        DistrictScoredEvent,
        StateScoredEvent,
        FactorDefinedEvent,
        DataViewDoneEvent,
        DataViewErrorEvent,
    ],
    Field(discriminator="type"),
]


# ── Plain REST response/request models (not SSE, still Camel over the wire) ───


class DistrictFactorSensitivity(Camel):
    factor_name: str = Field(alias="factorName")
    bucket: str
    sensitivity_pct: float = Field(alias="sensitivityPct")


class DistrictProfileResponse(Camel):
    district_id: str = Field(alias="districtId")
    state_code: str = Field(alias="stateCode")
    outcome_value: float = Field(alias="outcomeValue")
    factors: list[DistrictFactorSensitivity]


class PrescribedFactor(Camel):
    factor_name: str = Field(alias="factorName")
    bucket: str
    original: float
    prescribed: float


class PrescriptionResponse(Camel):
    district_id: str = Field(alias="districtId")
    target_reduction: float = Field(alias="targetReduction")
    confidence_value: float = Field(alias="confidenceValue")
    factors: list[PrescribedFactor]


class FactorDistrictSensitivity(Camel):
    district_id: str = Field(alias="districtId")
    sensitivity_pct: float = Field(alias="sensitivityPct")


class FactorSensitivityResponse(Camel):
    factor_id: str = Field(alias="factorId")
    state_code: str = Field(alias="stateCode")
    districts: list[FactorDistrictSensitivity]


class BudgetFactorShare(Camel):
    factor_name: str = Field(alias="factorName")
    bucket: str
    amount: float


class BudgetAllocationResponse(Camel):
    state_code: str = Field(alias="stateCode")
    total_budget: float = Field(alias="totalBudget")
    shares: list[BudgetFactorShare]


class BudgetRequest(Camel):
    """POST /state/{state_code}/budget body. `bucket_priorities` is optional --
    allocate_budget() itself defaults every present bucket to "medium" when
    omitted (see prescriptive.py's _default_priorities)."""

    total_budget: float = Field(alias="totalBudget")
    bucket_priorities: Optional[dict[str, BucketPriority]] = Field(default=None, alias="bucketPriorities")


class VerdictResponse(Camel):
    """GET /district/{id}/verdict and GET /state/{code}/verdict -- a real,
    LLM-generated (gemma_remote by default, see connectors/llm.py's
    `generate_verdict`) multi-paragraph narrative (plain text, paragraphs
    separated by "\\n\\n") explaining WHY children in this area are dropping
    out of secondary school, grounded strictly in that area's own real
    computed data -- see verdict.py's context builders for exactly what's
    handed to the model. Fixed wire shape per the API contract; do not add or
    rename fields without updating the frontend's `VerdictResult` in
    lockstep (types.ts)."""

    area_id: str = Field(alias="areaId")
    area_kind: Literal["district", "state"] = Field(alias="areaKind")
    area_name: str = Field(alias="areaName")
    state_name: str = Field(alias="stateName")
    verdict: str
