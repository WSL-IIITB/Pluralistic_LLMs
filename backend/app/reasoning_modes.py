"""
The "reasoning mode" replaces the old numeric depth-as-states-surveyed model.

Geographic coverage is now CONSTANT: every run always surveys the full state
list (see data/subreddit_map.py's STATE_PRIORITY_ORDER) regardless of mode --
"how thorough is this run" should never mean "we skipped whole regions of
India," since that directly undermines the point of the product (equal
cross-India representation). What actually varies between modes is the VOLUME
of sources gathered per state/angle and how much effort (research breadth,
requested write-up length) goes into finding them -- basic, medium, high.

"extrahigh" is qualitatively different, not just "more of the same": instead
of one global clustering pass across every state's posts pooled together (see
graph/nodes/cluster_viewpoints.py), it resolves each post's geography FIRST
(graph/nodes/geo_resolve.py) and then clusters EACH STATE'S posts
independently (cluster_viewpoints_per_state), so a low-volume state's genuine
viewpoint can't get absorbed into a high-volume state's dominant cluster.
Deflection-extraction is correspondingly scoped per-state too. See the
"extrahigh reasoning mode" plan for the full design.

This is the single source of truth for every mode-dependent constant so
graph/build.py (sourcing), graph/nodes/research.py (web research), and
connectors/llm.py (research prompt tuning) all read the same numbers.
"""

from __future__ import annotations

from typing import Literal

ResearchMode = Literal["basic", "medium", "high", "extrahigh"]

MODE_ORDER: tuple[ResearchMode, ...] = ("basic", "medium", "high", "extrahigh")


def parse_mode(raw: str | None, default: ResearchMode = "medium") -> ResearchMode:
    """Validate a mode string from a query param; unknown/missing -> default."""
    if raw and raw.lower() in MODE_ORDER:
        return raw.lower()  # type: ignore[return-value]
    return default


def escalate(mode: ResearchMode) -> ResearchMode:
    """One step more thorough, capped at the last entry in MODE_ORDER -- what
    "Go deeper" conceptually does: escalate the mode and merge in the
    additional sources it finds, rather than incrementing a states-surveyed
    counter (coverage is already full). Unused server-side today (the
    frontend computes and sends the already-escalated mode itself, capping
    its own walk before "extrahigh" -- see types.ts's escalateMode) -- kept
    here as the canonical definition of what escalating a mode means."""
    idx = MODE_ORDER.index(mode)
    return MODE_ORDER[min(idx + 1, len(MODE_ORDER) - 1)]


# Which LLM backend answers this run. "azure_anthropic" is Claude via Azure AI
# Foundry (AzureAnthropicLLMClient) -- it was removed at one point and then
# restored on request, so it is once again a fully selectable provider; it is
# NOT the default, though (see parse_provider below). "openai" is kept as a
# selectable value (the UI shows it, greyed out, since that account is out of
# credits) even though nothing currently prevents selecting it server-side --
# the frontend is what enforces "disabled." "gemma_local"/"mistral_local"
# route through LocalOllamaLLMClient (see connectors/llm.py) instead of a
# hosted API. "gemma_remote" routes through RemoteGemmaLLMClient -- a
# self-hosted, OpenAI-compatible Gemma server (not Ollama-native), needs no
# credential -- and is the DEFAULT provider for this app.
LlmProvider = Literal["azure_anthropic", "openai", "gemma_local", "mistral_local", "gemma_remote"]

PROVIDER_ORDER: tuple[LlmProvider, ...] = (
    "azure_anthropic",
    "openai",
    "gemma_local",
    "mistral_local",
    "gemma_remote",
)


def parse_provider(raw: str | None, default: LlmProvider = "gemma_remote") -> LlmProvider:
    """Validate a provider string from a query param; unknown/missing -> default."""
    if raw and raw.lower() in PROVIDER_ORDER:
        return raw.lower()  # type: ignore[return-value]
    return default


# Ollama model tag pulled locally for each local provider (see LocalOllamaLLMClient).
# Both were verified (via Ollama's own model pages) to support native tool-calling
# at ~8B-effective-parameter scale -- smaller/older local tags (e.g. gemma3) were
# ruled out specifically because they lack tool-calling, which research() needs.
OLLAMA_MODEL_TAGS: dict[LlmProvider, str] = {
    "gemma_local": "gemma4:e4b",
    "mistral_local": "mistral:7b",
}


# How many distinct regional/cultural framings (see LLMClient.suggest_framings)
# to search for. Shared by sourcing (each framing becomes a YouTube search / a
# Reddit search term) and research (each framing becomes a web-search angle) —
# one number, one meaning, used both places instead of two mappings that used
# to drift out of sync.
FRAMING_COUNT: dict[ResearchMode, int] = {"basic": 3, "medium": 5, "high": 8, "extrahigh": 10}

# Reddit: posts requested per state's subreddit search. State coverage itself
# is constant (always the full list) — only this per-state volume scales.
REDDIT_PER_STATE_LIMIT: dict[ResearchMode, int] = {"basic": 3, "medium": 6, "high": 10, "extrahigh": 14}

# YouTube: search.list's quota cost is a FLAT 100 units regardless of how many
# results you request (up to its max of 50) — so always ask for a healthy
# video count per search rather than economizing there; the real lever is how
# many comments you harvest per video, and commentThreads.list costs a flat 1
# unit per call regardless of maxResults (up to 100) — so always request the
# max there too. What actually varies by mode is how many TOTAL posts we keep
# per framing (which bounds how many videos get their comments pulled).
# extrahigh keeps this flat at "high"'s value, deliberately not escalated:
# YouTube has no per-state targeting (see graph/build.py's source_posts --
# fetch_youtube is keyed by framing, not state), so more YouTube posts here
# mostly inflate the geo-resolution fallback load (extract_place_mentions/
# geolocate calls in geo_resolve.py) without feeding a *specific* state's
# cluster diversity the way REDDIT_PER_STATE_LIMIT does.
YOUTUBE_POSTS_PER_FRAMING_CAP: dict[ResearchMode, int] = {
    "basic": 25,
    "medium": 60,
    "high": 150,
    "extrahigh": 150,
}

# NITI CSV: posts kept per framing search, mirroring the YouTube cap's shape.
# The corpus is finite (two ~776-row case files, one row per district's
# indicator set) and every row is data worth keeping, so this cap only bounds
# how many rows a single framing search returns — and the connector's
# round-robin spread means each state's best row(s) count before any state can
# flood the list, so the numbers here steer diversity, not noise. Sized like
# YouTube's cap: extrahigh deliberately doesn't escalate (a framing search
# already returns its best cross-state spread at "high"'s value).
CSV_POSTS_PER_FRAMING_CAP: dict[ResearchMode, int] = {
    "basic": 25,
    "medium": 60,
    "high": 150,
    "extrahigh": 150,
}

# Web research: how thorough a write-up to ask gpt-4o's web_search call for,
# per angle. Longer asks correlate with more sources actually being read and
# cited, not just more words — this is the "how long it looks for sources"
# lever the research stage has, since the angle-count above is already fixed
# by FRAMING_COUNT and every angle already runs concurrently.
RESEARCH_WORDCOUNT_HINT: dict[ResearchMode, str] = {
    "basic": "120-180 words",
    "medium": "250-350 words",
    "high": "400-600 words, and consider more than one search query internally if the topic is broad",
    "extrahigh": (
        "500-700 words, considering multiple search queries internally, prioritizing "
        "breadth across regions"
    ),
}

# extrahigh-only: dynamic cluster-count bounds for cluster_viewpoints_per_state
# (see graph/nodes/cluster_viewpoints.py). Unlike the other modes' fixed
# `k = min(6, max(2, n // 6))` heuristic, extrahigh selects k per state via a
# silhouette-score sweep over range(EXTRAHIGH_CLUSTER_K_MIN, k_max+1), where
# k_max is additionally capped by EXTRAHIGH_MIN_POSTS_PER_CLUSTER so a sweep
# never proposes a k that would average fewer than ~3 posts per cluster (a
# 1-post "cluster" has no real viewpoint to summarize, only an echo of that
# one post -- same reasoning as graph/build.py's _MIN_SIGNAL_WORDS gate).
EXTRAHIGH_CLUSTER_K_MIN = 2
EXTRAHIGH_CLUSTER_K_MAX = 10
EXTRAHIGH_MIN_POSTS_PER_CLUSTER = 3

# extrahigh-only: how many deflection pairs to extract PER STATE (not
# globally, unlike the other modes' flat top-6-by-volume cap across all of
# India) -- see graph/nodes/deflection_and_synthesis.py's
# extract_deflections_per_state. 2 guarantees every multi-viewpoint state
# surfaces at least one, usually two, genuine deflections without paying for
# a 3rd-ranked, low-combined-volume pair the existing global cap already
# treats as below the signal threshold.
EXTRAHIGH_DEFLECTIONS_PER_STATE_CAP = 2

# extrahigh-only: region-inference bounds (see graph/nodes/infer_regions.py).
# A region is inferred from DISTRICT-averaged embeddings (one level up from
# EXTRAHIGH_CLUSTER_* above, which sweeps over POST embeddings within one
# state) via the exact same silhouette-sweep k-selection pattern -- so region
# *count* is bounded by this sweep, never by how many groups an LLM decides
# to invent. K_MAX is deliberately smaller than a raw district count would
# allow: a "region" is meant to be a handful of broad clusters spanning many
# districts/states, not a district-count-sized partition.
REGION_CLUSTER_K_MIN = 2
REGION_CLUSTER_K_MAX = 12
# Mirrors EXTRAHIGH_MIN_POSTS_PER_CLUSTER's reasoning one level up: a k that
# would average fewer than 2 districts per region isn't a real "spans several
# districts" region, just an echo of one district.
REGION_MIN_DISTRICTS_PER_REGION = 2
# Same role as cluster_viewpoints.py's _MIN_SILHOUETTE_FOR_SPLIT -- collapse
# to a single region if even the sweep's best k scores below this (no
# genuine district-level structure found). Lowered alongside that constant
# for the same reason: too conservative in practice for short social-media
# text embeddings, observed collapsing genuinely multi-state runs to one
# region -- see that constant's own comment for the full rationale.
_MIN_SILHOUETTE_FOR_REGION_SPLIT = 0.03
# Hard cap on propose->critique->revise rounds -- mirrors connectors/llm.py's
# _RESEARCH_TOOL_ROUND_CAP: convergence must be code-enforced (the round after
# this cap force-accepts whatever the current best partition is), never
# dependent on an LLM choosing to stop critiquing.
REGION_REVISION_ROUND_CAP = 1

# extrahigh-only: deflection-extraction caps for extract_deflections_per_region
# (graph/nodes/deflection_and_synthesis.py), mirroring
# EXTRAHIGH_DEFLECTIONS_PER_STATE_CAP one level up. Two separate caps because
# this stage now runs TWO passes: intra-region (pairs of dominant clusters
# within the SAME region -- can legitimately span states) and inter-region (a
# smaller top-K pass across different regions' single most-dominant cluster
# each, finally using DeflectionLevel's "inter-region" value). The
# inter-region cap is a flat top-K over ALL region pairs (not per-region)
# since it's meant to surface only the handful of most striking cross-region
# contrasts, mirroring the pre-extrahigh flat top-6 global cap.
EXTRAHIGH_DEFLECTIONS_PER_REGION_CAP = 2
EXTRAHIGH_INTER_REGION_DEFLECTIONS_CAP = 6
