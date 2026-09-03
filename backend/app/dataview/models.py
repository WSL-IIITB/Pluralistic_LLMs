"""
Plain dataclasses for the Data View pipeline. Deliberately NOT the
graph/state.py TypedDict shapes -- this pipeline has no LLM, no LangGraph
node fan-out, and no per-request mutation; it's a pure numeric computation
over one static dataset, cached once per process (see pipeline.py).

IMPORTANT, discovered by inspecting casefile.xlsx directly (not assumed):
the casefile is NOT one dense national factor table with random missing
values. For a given state, a small set of factor columns (typically 6-12)
is populated for EVERY one of that state's districts, and every other
factor column is null for the entire state. Different states have different
active factor sets. This is LKI's own per-state "Statistical Filtering"
step (Pearson r/p-value selection, per their doc) already baked into the
file -- confirmed empirically: for the first 8 states checked, "factors with
any data" == "factors fully populated for every district" every time,
which would be a wild coincidence under random missingness. So modeling
here is inherently PER STATE, using each state's own pre-selected,
fully-dense factor set -- not a second, redundant national correlation
filter (an earlier version of this module tried that and it destroyed
almost all the usable signal).
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class DistrictRecord:
    """One row of the LKI-SSM casefile, after crosswalking onto our own
    map's district id scheme. `district_id` is None for the ~12% of
    districts the crosswalk can't resolve (see build_dataview_crosswalk.py's
    docstring for why) -- callers must skip these for map rendering, never
    guess."""

    raw_key: str  # "{state}|{district}" exactly as it appears in casefile.xlsx
    district_id: str | None
    state_name: str
    district_name: str
    dropout_rate: float
    factors: dict[str, float | None]  # factor_name -> value, None if not part of this state's active set


@dataclass
class CaseFile:
    factor_names: list[str]  # every factor column that appears anywhere in the file, across all states
    districts: list[DistrictRecord]

    def resolved_districts(self) -> list[DistrictRecord]:
        """Districts with a real district_id -- the only ones that can be
        rendered on the map or aggregated into a state score."""
        return [d for d in self.districts if d.district_id is not None]


@dataclass
class UnivariateModel:
    factor_name: str
    m: float
    c: float
    r2: float
    n: int
    bucket: str


@dataclass
class MultivariateModel:
    factor_names: list[str]
    coefficients: dict[str, float]
    intercept: float
    r2: float
    n: int


@dataclass
class StateModel:
    """One state's own fitted model, using only ITS active factor set (the
    columns LKI's own per-state filtering left populated for every district
    in this state).

    CAVEAT for small states/UTs: `multivariate.r2` (used as the "Confidence
    Value") can hit a suspicious-looking 1.0 when a state's district count
    is close to its factor count (e.g. Nagaland: 11 districts, 12 factors)
    -- the system is nearly saturated/overdetermined, so a "perfect" fit
    reflects too few data points relative to model complexity, not genuine
    predictive strength. This is a real limitation of fitting per state on
    a small-N country subdivision, not a bug; the UI should not present a
    1.0 confidence for a tiny state the same way as a 1.0 for e.g. Uttar
    Pradesh's 75-district fit."""

    state_name: str
    factor_names: list[str]
    univariate: dict[str, UnivariateModel]  # keyed by factor_name, fit over this state's own districts only
    multivariate: MultivariateModel


@dataclass
class DataViewModel:
    """The one fully-fit model, built once per process by pipeline.py and
    reused by every request -- deterministic given the static input files."""

    casefile: CaseFile
    buckets: dict[str, list[str]] = field(default_factory=dict)  # bucket_name -> factor_names, union across all states
    states: dict[str, StateModel] = field(default_factory=dict)  # state_name -> StateModel
