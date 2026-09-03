"""
Grounding-context builders for the Data View "verdict" narrative endpoints
(`GET /district/{id}/verdict`, `GET /state/{code}/verdict` — see router.py).

Pure data-gathering + plaintext formatting, ZERO LLM calls here — every
number below comes straight from the same already-fitted regression model
and prescriptive/budget math the rest of Data View's endpoints already use
(`regression.district_sensitivity_ratio`, `prescriptive.prescribe_factor_changes`,
`prescriptive.allocate_budget`), so the digest handed to the LLM is exactly
what the UI's own Major-factors table / Original-vs-Prescribed table / budget
panel would show for the same area -- never a second, independent source of
truth that could drift out of sync with what a user sees on screen.

Kept as a separate module from router.py (rather than inlined in the two
endpoint handlers) so this formatting logic is trivially unit-testable
without an event loop or an LLM client in the loop.
"""

from __future__ import annotations

from .models import DistrictRecord, StateModel
from .pipeline import StateScore
from .prescriptive import allocate_budget, prescribe_factor_changes
from .stats import classify_bucket

# A fixed, representative reference point for the "what would it take"
# framing -- NOT user-configurable (unlike the interactive Intervention &
# Budget tab's own slider/₹ input), since the verdict is a single narrative
# generated once per area, not a live recompute. Matches the same 20%
# reference pipeline.py's own intervention-index scoring uses
# (`_INTERVENTION_REFERENCE_TARGET_REDUCTION`) and the frontend prescriptive
# slider's own default position (`store.ts`'s `targetReduction: 0.2`), so the
# narrative's "prescriptive implication" framing lines up with what a user
# sees by default when they switch to the Intervention & Budget tab.
VERDICT_TARGET_REDUCTION = 0.2

# A representative budget figure for the "state budget priority context"
# section -- matches `BudgetAllocationPanel.tsx`'s own `DEFAULT_BUDGET`
# (₹1 crore) so the narrative's budget framing is consistent with what a
# user sees by default on that tab, not an arbitrarily different number.
VERDICT_TOTAL_BUDGET = 10_000_000.0

_TOP_SENSITIVITY_FACTORS = 6
_TOP_STATE_FACTORS = 8
_TOP_PRESCRIPTION_FACTORS = 5
_TOP_BUDGET_FACTORS = 6

_BUCKET_LABELS = {
    "infrastructure": "Infrastructure",
    "digital_ict": "Digital and ICT",
    "teacher_profile": "Teacher Profile",
    "socio_economic": "Socio-Economic",
}


def _bucket_label(bucket: str) -> str:
    return _BUCKET_LABELS.get(bucket, bucket)


def _fmt_pct(v: float) -> str:
    return f"{v:.1f}%"


def _fmt_rupees(v: float) -> str:
    return f"Rs {v:,.0f}"


def build_district_verdict_context(
    district: DistrictRecord,
    state_model: StateModel,
    state_score: StateScore | None,
    districts_in_state: list[DistrictRecord],
) -> str:
    """Plaintext digest for one district: its own factor-sensitivity profile
    (district_sensitivity_ratio -- the same numbers `DataDistrictInfoPanel`'s
    "District Profile" bar renders), a prescriptive what-if at
    VERDICT_TARGET_REDUCTION (the same math `prescribe_factor_changes` feeds
    the Original-vs-Prescribed table), and its STATE's own budget-priority
    context (allocate_budget) -- the API contract calls for "intervention/
    budget context for its state", not a district-scoped budget (there is no
    district-scoped budget endpoint at all; see BudgetAllocationPanel.tsx's
    header comment on why budget is always state-scoped)."""
    from .regression import district_sensitivity_ratio  # local import: avoid a cycle with regression.py importing models only

    lines: list[str] = []

    lines.append(f"District: {district.district_name}, State: {district.state_name}")
    lines.append(f"Current dropout rate: {district.dropout_rate:.2f}%")
    lines.append("")

    ratios = district_sensitivity_ratio(state_model, district)
    top_ratios = sorted(ratios.items(), key=lambda kv: kv[1], reverse=True)[:_TOP_SENSITIVITY_FACTORS]
    lines.append(
        "TOP FACTORS DRIVING THIS DISTRICT'S DROPOUT RATE (each factor's share of the "
        "district's total modeled impact, from a linear regression fit on this state's own "
        "districts):"
    )
    if top_ratios:
        for name, pct in top_ratios:
            lines.append(f"- {name} [{_bucket_label(classify_bucket(name))}]: {_fmt_pct(pct)} of modeled impact")
    else:
        lines.append("- No factor-sensitivity data available for this district.")
    lines.append("")

    if state_score is not None:
        lines.append(f"STATE MODEL CONTEXT ({district.state_name}):")
        lines.append(f"- Model confidence value (in-sample R-squared of the state's fitted model): {state_score.confidence_value:.2f}")
        lines.append(
            "- State intervention index (0-1, normalized across every modeled state; higher = "
            f"this state needs comparatively more intervention effort to hit the same reference "
            f"reduction): {state_score.intervention_index:.2f}"
        )
        lines.append(f"- State average dropout rate across its own districts: {state_score.avg_outcome:.2f}%")
        lines.append("")

    factor_buckets = {f: classify_bucket(f) for f in state_model.factor_names}
    prescription = prescribe_factor_changes(district, state_model, factor_buckets, VERDICT_TARGET_REDUCTION)
    moved = sorted(
        (f for f in prescription.factors if abs(f.prescribed - f.original) > 1e-9),
        key=lambda f: abs(f.prescribed - f.original),
        reverse=True,
    )[:_TOP_PRESCRIPTION_FACTORS]
    pct_label = round(VERDICT_TARGET_REDUCTION * 100)
    lines.append(
        f"PRESCRIPTIVE SCENARIO -- modeled factor movement needed to cut THIS DISTRICT's dropout "
        f"rate by {pct_label}% (from {district.dropout_rate:.2f}% toward "
        f"{district.dropout_rate * (1 - VERDICT_TARGET_REDUCTION):.2f}%), holding the state's "
        f"fitted regression relationships fixed:"
    )
    if moved:
        for f in moved:
            direction = "increase" if f.prescribed > f.original else "decrease"
            lines.append(
                f"- {f.factor_name} [{_bucket_label(f.bucket)}]: {direction} from {f.original:.2f} "
                f"to {f.prescribed:.2f} (change of {abs(f.prescribed - f.original):.2f})"
            )
    else:
        lines.append("- No material factor movement was modeled for this district/target.")
    lines.append("")

    budget_shares = allocate_budget(districts_in_state, state_model, factor_buckets, VERDICT_TOTAL_BUDGET)
    budget_shares = sorted(budget_shares, key=lambda s: s.amount, reverse=True)[:_TOP_BUDGET_FACTORS]
    lines.append(
        f"STATE BUDGET PRIORITY CONTEXT -- a representative {_fmt_rupees(VERDICT_TOTAL_BUDGET)} "
        f"intervention budget split across {district.state_name} (relative allocation by required "
        f"factor movement and bucket priority, not a unit-costed estimate):"
    )
    if budget_shares:
        for s in budget_shares:
            pct_of_budget = (s.amount / VERDICT_TOTAL_BUDGET) * 100 if VERDICT_TOTAL_BUDGET else 0.0
            lines.append(f"- {s.factor_name} [{_bucket_label(s.bucket)}]: {_fmt_rupees(s.amount)} ({_fmt_pct(pct_of_budget)})")
    else:
        lines.append("- No budget allocation could be modeled for this state.")

    return "\n".join(lines)


def build_state_verdict_context(
    state_name: str,
    state_model: StateModel,
    state_score: StateScore | None,
    districts: list[DistrictRecord],
) -> str:
    """Plaintext digest for one state: its top factors ranked by each
    factor's OWN univariate fit quality (r-squared) -- the same ranking
    `topFactorsForState` uses on the frontend for the Major-factors table --
    plus the same state-wide prescriptive/budget math `allocate_budget`
    already powers on the Intervention & Budget tab."""
    lines: list[str] = []

    n = len(districts)
    lines.append(f"State: {state_name} ({n} district{'s' if n != 1 else ''} in this model)")
    if state_score is not None:
        lines.append(f"Average dropout rate across these districts: {state_score.avg_outcome:.2f}%")
        lines.append(f"Model confidence value (in-sample R-squared of the state's fitted multivariate model): {state_score.confidence_value:.2f}")
        lines.append(
            "Intervention index (0-1, normalized across every modeled state; higher = this state "
            f"needs comparatively more intervention effort): {state_score.intervention_index:.2f}"
        )
    lines.append("")

    top_factors = sorted(state_model.univariate.items(), key=lambda kv: kv[1].r2, reverse=True)[:_TOP_STATE_FACTORS]
    lines.append(
        f"TOP FACTORS DRIVING DROPOUT ACROSS {state_name} (each factor's own univariate fit "
        "quality, R-squared, predicting a district's dropout rate from that one factor alone "
        "across this state's own districts -- higher R-squared means that factor alone explains "
        "more of the district-to-district variation in this state):"
    )
    if top_factors:
        for name, model in top_factors:
            lines.append(f"- {name} [{_bucket_label(classify_bucket(name))}]: R-squared={model.r2:.2f} (n={model.n} districts)")
    else:
        lines.append("- No fitted factors available for this state.")
    lines.append("")

    factor_buckets = {f: classify_bucket(f) for f in state_model.factor_names}
    budget_shares = allocate_budget(districts, state_model, factor_buckets, VERDICT_TOTAL_BUDGET)
    budget_shares = sorted(budget_shares, key=lambda s: s.amount, reverse=True)[:_TOP_BUDGET_FACTORS]
    pct_label = round(VERDICT_TARGET_REDUCTION * 100)
    lines.append(
        f"STATE-WIDE PRESCRIPTIVE / BUDGET CONTEXT -- a representative "
        f"{_fmt_rupees(VERDICT_TOTAL_BUDGET)} intervention budget split across {state_name}'s "
        f"{n} districts (relative allocation, weighted by how much each factor would need to move "
        f"across the state's own districts to hit a modeled {pct_label}% dropout-rate reduction, "
        "and by bucket priority -- not a unit-costed estimate):"
    )
    if budget_shares:
        for s in budget_shares:
            pct_of_budget = (s.amount / VERDICT_TOTAL_BUDGET) * 100 if VERDICT_TOTAL_BUDGET else 0.0
            lines.append(f"- {s.factor_name} [{_bucket_label(s.bucket)}]: {_fmt_rupees(s.amount)} ({_fmt_pct(pct_of_budget)})")
    else:
        lines.append("- No budget allocation could be modeled for this state.")

    return "\n".join(lines)
