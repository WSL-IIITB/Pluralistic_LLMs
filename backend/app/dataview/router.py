"""
FastAPI surface for Data View -- own `APIRouter` (the first router in a
codebase where `main.py` has historically kept every route inline; see
main.py's docstring), wired in via `app.include_router(dataview_router)`.

`GET /stream` mirrors main.py's existing SSE scaffold exactly (asyncio.Queue
+ emit() + background asyncio.create_task + EventSourceResponse draining the
queue) for the one-time nationwide bootstrap load. Every other route is a
small synchronous JSON endpoint recomputing off the one process-cached
`DataViewModel` (`get_dataview_model()`, see pipeline.py) -- cheap enough
after the first call to run inline in the request handler, unlike the
stream's initial full-model build.
"""

from __future__ import annotations

import asyncio
import re
import traceback
import uuid

from fastapi import APIRouter, HTTPException, Query
from sse_starlette.sse import EventSourceResponse

from ..config import get_settings
from ..graph.build import load_gazetteer
from .models import DataViewModel, DistrictRecord
from .pipeline import compute_state_scores, get_dataview_model
from .prescriptive import BucketPriority, allocate_budget, prescribe_factor_changes
from .regression import district_sensitivity_ratio, factor_sensitivity_ratio
from .schema import (
    BudgetAllocationResponse,
    BudgetFactorShare,
    BudgetRequest,
    DataViewDoneEvent,
    DataViewErrorEvent,
    DataViewEvent,
    DistrictFactorSensitivity,
    DistrictProfileResponse,
    DistrictScoredEvent,
    FactorDefinedEvent,
    FactorDistrictSensitivity,
    FactorSensitivityResponse,
    PrescribedFactor,
    PrescriptionResponse,
    StateScoredEvent,
    VerdictResponse,
    event_to_sse_data,
)
from .stats import classify_bucket
from .verdict import build_district_verdict_context, build_state_verdict_context

router = APIRouter(prefix="/api/dataview")

# Purely a UX stagger between emitted batches so the map visibly "builds" the
# way Story View's does -- the computation itself (get_dataview_model() is
# process-cached after the first call, everything else here is cheap
# dict/list work) needs no throttling on its own.
_STREAM_BATCH_DELAY = 0.01


# ── state code <-> state name, adapted from graph/build.py's
# _state_names_from_gazetteer() idea (same gazetteer, same "derive a lookup
# once" pattern) plus the "&"/"and" conjunction fold build_dataview_crosswalk.py
# needed for the same underlying reason: the casefile spells state names in
# raw UPPERCASE with "&" (e.g. "JAMMU & KASHMIR", see models.py/pipeline.py's
# StateModel.state_name), the gazetteer in Title Case with "and" ("Jammu and
# Kashmir") -- comparison folds both sides to the same normalized form rather
# than hardcoding a third table or relying on a direct string match. ──

_NORMALIZE_RE = re.compile(r"[^a-z0-9]+")
_AND_WORD_RE = re.compile(r"\band\b")
_WHITESPACE_RE = re.compile(r"\s+")


def _normalize_state_name(name: str) -> str:
    n = _NORMALIZE_RE.sub(" ", str(name).lower()).strip()
    n = _AND_WORD_RE.sub(" ", n)
    return _WHITESPACE_RE.sub(" ", n).strip()


_state_code_to_gazetteer_name_cache: dict[str, str] | None = None


def _state_code_to_gazetteer_name() -> dict[str, str]:
    global _state_code_to_gazetteer_name_cache
    if _state_code_to_gazetteer_name_cache is None:
        names: dict[str, str] = {}
        for candidates in load_gazetteer().values():
            for cand in candidates:
                code, name = cand.get("stateCode"), cand.get("stateName")
                if code and name and code not in names:
                    names[code] = name
        _state_code_to_gazetteer_name_cache = names
    return _state_code_to_gazetteer_name_cache


def _state_name_to_code(state_name: str) -> str | None:
    """A StateModel/StateScore key (casefile's own raw state-name spelling)
    -> stateCode. None only if the gazetteer genuinely has no such state at
    all, which shouldn't happen for anything in model.states (every one of
    the 29 fitted states was confirmed to match the gazetteer by name) --
    never fabricate a code, skip instead."""
    target = _normalize_state_name(state_name)
    for code, name in _state_code_to_gazetteer_name().items():
        if _normalize_state_name(name) == target:
            return code
    return None


def _resolve_state_name(model: DataViewModel, state_code: str) -> str | None:
    """stateCode -> the exact key model.states uses -- the inverse of
    _state_name_to_code, resolved through the same normalized-name join."""
    gazetteer_name = _state_code_to_gazetteer_name().get(state_code)
    if gazetteer_name is None:
        return None
    target = _normalize_state_name(gazetteer_name)
    for state_name in model.states:
        if _normalize_state_name(state_name) == target:
            return state_name
    return None


def _find_resolved_district(model: DataViewModel, district_id: str) -> DistrictRecord | None:
    for d in model.casefile.resolved_districts():
        if d.district_id == district_id:
            return d
    return None


_district_id_to_gazetteer_name_cache: dict[str, str] | None = None


def _district_id_to_gazetteer_name() -> dict[str, str]:
    """districtId -> the gazetteer's own properly-cased `districtName` (e.g.
    "Banda", not casefile.xlsx's raw lowercase "banda") -- used only for
    display in verdict responses/prompts; never for matching (the crosswalk
    already resolved district_id, this is purely cosmetic casing)."""
    global _district_id_to_gazetteer_name_cache
    if _district_id_to_gazetteer_name_cache is None:
        names: dict[str, str] = {}
        for candidates in load_gazetteer().values():
            for cand in candidates:
                did, name = cand.get("districtId"), cand.get("districtName")
                if did and name and did not in names:
                    names[did] = name
        _district_id_to_gazetteer_name_cache = names
    return _district_id_to_gazetteer_name_cache


# ── SSE bootstrap ──────────────────────────────────────────────────────────


@router.get("/stream")
async def stream():
    run_id = f"dvrun_{uuid.uuid4().hex}"

    async def event_generator():
        queue: asyncio.Queue[DataViewEvent | None] = asyncio.Queue()

        async def emit(event: DataViewEvent) -> None:
            await queue.put(event)

        async def run() -> None:
            try:
                # Heavy lifting (loading casefile.xlsx, fitting 29 states'
                # worth of univariate + multivariate regressions) happens
                # here, inside the background task -- not blocking the route
                # handler itself -- mirroring how main.py's stream() runs the
                # LangGraph pipeline inside its own background task. Cached
                # after the first call (pipeline.get_dataview_model()), so
                # only the very first /stream request pays this cost.
                model = get_dataview_model()

                factor_count = 0
                for state_name, state_model in model.states.items():
                    state_code = _state_name_to_code(state_name)
                    if state_code is None:
                        continue
                    for factor_name in state_model.factor_names:
                        univariate = state_model.univariate.get(factor_name)
                        await emit(
                            FactorDefinedEvent(
                                runId=run_id,
                                factorId=factor_name,
                                label=factor_name,
                                bucket=classify_bucket(factor_name),
                                stateCode=state_code,
                                r2=univariate.r2 if univariate is not None else 0.0,
                            )
                        )
                        factor_count += 1
                    await asyncio.sleep(_STREAM_BATCH_DELAY)

                resolved = model.casefile.resolved_districts()
                districts_by_state: dict[str, list[DistrictRecord]] = {}
                for d in resolved:
                    districts_by_state.setdefault(d.state_name, []).append(d)
                for districts in districts_by_state.values():
                    for d in districts:
                        await emit(
                            DistrictScoredEvent(
                                runId=run_id,
                                districtId=d.district_id,
                                stateCode=d.district_id.split("-", 1)[0],
                                outcomeValue=d.dropout_rate,
                            )
                        )
                    await asyncio.sleep(_STREAM_BATCH_DELAY)

                state_scores = compute_state_scores(model)
                for state_name, score in state_scores.items():
                    state_code = _state_name_to_code(state_name)
                    if state_code is None:
                        continue
                    await emit(
                        StateScoredEvent(
                            runId=run_id,
                            stateCode=state_code,
                            avgOutcome=score.avg_outcome,
                            confidenceValue=score.confidence_value,
                            interventionIndex=score.intervention_index,
                        )
                    )
                    await asyncio.sleep(_STREAM_BATCH_DELAY)

                await emit(
                    DataViewDoneEvent(
                        runId=run_id,
                        districtCount=len(resolved),
                        factorCount=factor_count,
                        stateCount=len(state_scores),
                    )
                )
            except Exception as exc:  # noqa: BLE001 -- surface any failure as a stream error, never a bare 500
                traceback.print_exc()
                await emit(DataViewErrorEvent(runId=run_id, message=str(exc)))
            finally:
                await queue.put(None)

        task = asyncio.create_task(run())
        try:
            while True:
                item = await queue.get()
                if item is None:
                    break
                yield {"event": item.type, "data": event_to_sse_data(item)}
        finally:
            task.cancel()

    return EventSourceResponse(event_generator())


# ── District Profile ───────────────────────────────────────────────────────


@router.get("/district/{district_id}/profile")
async def get_district_profile(district_id: str) -> DistrictProfileResponse:
    try:
        model = get_dataview_model()
        district = _find_resolved_district(model, district_id)
        if district is None:
            raise HTTPException(status_code=404, detail=f"district {district_id!r} not found among resolved districts")

        state_model = model.states.get(district.state_name)
        if state_model is None:
            raise HTTPException(status_code=404, detail=f"no fitted model for state {district.state_name!r}")

        ratios = district_sensitivity_ratio(state_model, district)
        factors = [
            DistrictFactorSensitivity(factorName=name, bucket=classify_bucket(name), sensitivityPct=pct)
            for name, pct in sorted(ratios.items(), key=lambda kv: kv[1], reverse=True)
        ]
        return DistrictProfileResponse(
            districtId=district.district_id,
            stateCode=district.district_id.split("-", 1)[0],
            outcomeValue=district.dropout_rate,
            factors=factors,
        )
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001 -- never a bare unhandled 500
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(exc)) from exc


# ── Prescriptive what-if ───────────────────────────────────────────────────


@router.get("/district/{district_id}/prescription")
async def get_district_prescription(
    district_id: str,
    target_reduction: float = Query(..., ge=0.0, le=1.0),
    bucket_priority_infrastructure: BucketPriority = Query("medium"),
    bucket_priority_digital_ict: BucketPriority = Query("medium"),
    bucket_priority_teacher_profile: BucketPriority = Query("medium"),
    bucket_priority_socio_economic: BucketPriority = Query("medium"),
) -> PrescriptionResponse:
    try:
        model = get_dataview_model()
        district = _find_resolved_district(model, district_id)
        if district is None:
            raise HTTPException(status_code=404, detail=f"district {district_id!r} not found among resolved districts")

        state_model = model.states.get(district.state_name)
        if state_model is None:
            raise HTTPException(status_code=404, detail=f"no fitted model for state {district.state_name!r}")

        bucket_priorities: dict[str, BucketPriority] = {
            "infrastructure": bucket_priority_infrastructure,
            "digital_ict": bucket_priority_digital_ict,
            "teacher_profile": bucket_priority_teacher_profile,
            "socio_economic": bucket_priority_socio_economic,
        }
        factor_buckets = {f: classify_bucket(f) for f in state_model.factor_names}

        result = prescribe_factor_changes(district, state_model, factor_buckets, target_reduction, bucket_priorities)

        return PrescriptionResponse(
            districtId=district.district_id,
            targetReduction=target_reduction,
            confidenceValue=state_model.multivariate.r2,
            factors=[
                PrescribedFactor(factorName=f.factor_name, bucket=f.bucket, original=f.original, prescribed=f.prescribed)
                for f in result.factors
            ],
        )
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(exc)) from exc


# ── Factor Sensitivity Profile ─────────────────────────────────────────────


@router.get("/factor/{factor_id}/sensitivity")
async def get_factor_sensitivity(factor_id: str, state_code: str = Query(...)) -> FactorSensitivityResponse:
    try:
        model = get_dataview_model()
        state_name = _resolve_state_name(model, state_code)
        if state_name is None:
            raise HTTPException(status_code=404, detail=f"no fitted model for stateCode {state_code!r}")

        state_model = model.states[state_name]
        if factor_id not in state_model.factor_names:
            raise HTTPException(status_code=404, detail=f"factor {factor_id!r} is not active for state {state_name!r}")

        districts = [d for d in model.casefile.resolved_districts() if d.state_name == state_name]
        ratios = factor_sensitivity_ratio(state_model, factor_id, districts)

        return FactorSensitivityResponse(
            factorId=factor_id,
            stateCode=state_code,
            districts=[
                FactorDistrictSensitivity(districtId=district_id, sensitivityPct=pct)
                for district_id, pct in sorted(ratios.items(), key=lambda kv: kv[1], reverse=True)
            ],
        )
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(exc)) from exc


# ── Budget Allocation ───────────────────────────────────────────────────────


@router.post("/state/{state_code}/budget")
async def post_state_budget(state_code: str, payload: BudgetRequest) -> BudgetAllocationResponse:
    try:
        model = get_dataview_model()
        state_name = _resolve_state_name(model, state_code)
        if state_name is None:
            raise HTTPException(status_code=404, detail=f"no fitted model for stateCode {state_code!r}")

        state_model = model.states[state_name]
        districts = [d for d in model.casefile.resolved_districts() if d.state_name == state_name]
        if not districts:
            raise HTTPException(status_code=404, detail=f"no resolved districts for stateCode {state_code!r}")

        factor_buckets = {f: classify_bucket(f) for f in state_model.factor_names}
        shares = allocate_budget(districts, state_model, factor_buckets, payload.total_budget, payload.bucket_priorities)

        return BudgetAllocationResponse(
            stateCode=state_code,
            totalBudget=payload.total_budget,
            shares=[BudgetFactorShare(factorName=s.factor_name, bucket=s.bucket, amount=s.amount) for s in shares],
        )
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(exc)) from exc


# ── Verdict (real LLM-backed narrative) ─────────────────────────────────────
#
# The one pair of endpoints in this router that calls out to an LLM --
# everything else above is a synchronous, deterministic numeric recompute.
# `verdict.py`'s context builders gather the real, already-computed numbers
# (zero LLM involvement in that step); `get_llm_client(settings)` below wires
# up whichever provider `LLM_PROVIDER` selects (gemma_remote by default, see
# config.py) exactly the way `main.py`'s own `/api/worldview/stream` route
# does it -- a fresh client per request, no caching, so a provider swap via
# env var takes effect on the very next call. A real call through
# gemma_remote/OpenAI/Claude for this much reasoning+prose can legitimately
# take 15-40+ real seconds; `generate_verdict`'s own implementations use a
# generous per-call timeout (150s, see llm.py) rather than this route
# imposing any timeout of its own -- the route just awaits the client.


@router.get("/district/{district_id}/verdict")
async def get_district_verdict(district_id: str) -> VerdictResponse:
    try:
        model = get_dataview_model()
        district = _find_resolved_district(model, district_id)
        if district is None:
            raise HTTPException(status_code=404, detail=f"district {district_id!r} not found among resolved districts")

        state_model = model.states.get(district.state_name)
        if state_model is None:
            raise HTTPException(status_code=404, detail=f"no fitted model for state {district.state_name!r}")

        state_code = district.district_id.split("-", 1)[0]
        pretty_state_name = _state_code_to_gazetteer_name().get(state_code, district.state_name.title())
        pretty_district_name = _district_id_to_gazetteer_name().get(district.district_id, district.district_name.title())

        state_scores = compute_state_scores(model)
        state_score = state_scores.get(district.state_name)
        districts_in_state = [d for d in model.casefile.resolved_districts() if d.state_name == district.state_name]

        context = build_district_verdict_context(district, state_model, state_score, districts_in_state)

        from ..connectors.llm import get_llm_client  # local import: keep this optional-dep-laden module lazy, mirrors main.py's own stream() route

        settings = get_settings()
        llm = get_llm_client(settings)
        verdict_text = await llm.generate_verdict("district", pretty_district_name, pretty_state_name, context)

        return VerdictResponse(
            areaId=district.district_id,
            areaKind="district",
            areaName=pretty_district_name,
            stateName=pretty_state_name,
            verdict=verdict_text,
        )
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/state/{state_code}/verdict")
async def get_state_verdict(state_code: str) -> VerdictResponse:
    try:
        model = get_dataview_model()
        state_name = _resolve_state_name(model, state_code)
        if state_name is None:
            raise HTTPException(status_code=404, detail=f"no fitted model for stateCode {state_code!r}")

        state_model = model.states[state_name]
        districts = [d for d in model.casefile.resolved_districts() if d.state_name == state_name]
        if not districts:
            raise HTTPException(status_code=404, detail=f"no resolved districts for stateCode {state_code!r}")

        pretty_state_name = _state_code_to_gazetteer_name().get(state_code, state_name.title())
        state_scores = compute_state_scores(model)
        state_score = state_scores.get(state_name)

        context = build_state_verdict_context(state_name, state_model, state_score, districts)

        from ..connectors.llm import get_llm_client  # local import: keep this optional-dep-laden module lazy, mirrors main.py's own stream() route

        settings = get_settings()
        llm = get_llm_client(settings)
        verdict_text = await llm.generate_verdict("state", pretty_state_name, pretty_state_name, context)

        return VerdictResponse(
            areaId=state_code,
            areaKind="state",
            areaName=pretty_state_name,
            stateName=pretty_state_name,
            verdict=verdict_text,
        )
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(exc)) from exc
