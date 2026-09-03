"""
Throwaway verification script for the Data View regression module -- not
part of the shipped API surface. Run: python -m app.dataview.verify_standalone
(from backend/, venv active). Prints enough to eyeball correctness by hand:
per-state factor counts, one district's sensitivity ratios (should sum to
~100), one factor's (m, c, r2), and per-state confidence/intervention-index
ranges.
"""

from __future__ import annotations

from .pipeline import build_dataview_model, compute_state_scores
from .regression import district_sensitivity_ratio


def main() -> None:
    print("Loading casefile + building per-state models...")
    model = build_dataview_model()
    casefile = model.casefile

    all_states = {d.state_name for d in casefile.districts}
    print(f"\ncasefile: {len(casefile.districts)} districts, {len(casefile.factor_names)} distinct factor columns across all states")
    print(f"resolved to a map district_id: {len(casefile.resolved_districts())}")
    print(f"states with a fitted model: {len(model.states)}/{len(all_states)}")
    if len(model.states) < len(all_states):
        print(f"  NOT fitted: {sorted(all_states - set(model.states))}")

    print("\nper-state active factor counts:")
    for state_name, sm in sorted(model.states.items()):
        print(f"  {state_name:40s} {len(sm.factor_names):2d} factors  n={sm.multivariate.n:3d}  r2={sm.multivariate.r2:.3f}")

    example_state = model.states["BIHAR"] if "BIHAR" in model.states else next(iter(model.states.values()))
    example_factor = next(iter(example_state.univariate.values()))
    print(f"\nexample univariate model ({example_state.state_name}, {example_factor.factor_name!r}): m={example_factor.m:.4f} c={example_factor.c:.4f} r2={example_factor.r2:.3f} n={example_factor.n}")

    resolved = casefile.resolved_districts()
    example_district = next(d for d in resolved if d.state_name == example_state.state_name)
    ratios = district_sensitivity_ratio(example_state, example_district)
    total = sum(ratios.values())
    print(f"\ndistrict sensitivity ratio for {example_district.district_name}, {example_district.state_name}:")
    print(f"  {len(ratios)} factors, sums to {total:.1f}% (should be ~100%)")
    for name, pct in sorted(ratios.items(), key=lambda kv: kv[1], reverse=True)[:5]:
        print(f"    {pct:5.1f}%  {name}")

    print("\ncomputing per-state scores (confidence + intervention index)...")
    state_scores = compute_state_scores(model)
    print(f"  {len(state_scores)} states scored (had at least one resolved district)")
    for state_name, score in sorted(state_scores.items(), key=lambda kv: kv[1].intervention_index, reverse=True)[:5]:
        print(f"    {state_name:25s} avg_outcome={score.avg_outcome:5.1f}  confidence={score.confidence_value:.3f}  intervention_index={score.intervention_index:.3f}")

    confidences = [s.confidence_value for s in state_scores.values()]
    indices = [s.intervention_index for s in state_scores.values()]
    print(f"\nconfidence range: [{min(confidences):.3f}, {max(confidences):.3f}] (all must be in [0,1])")
    print(f"intervention_index range: [{min(indices):.3f}, {max(indices):.3f}] (must span [0,1] since it's min-max normalized)")


if __name__ == "__main__":
    main()
