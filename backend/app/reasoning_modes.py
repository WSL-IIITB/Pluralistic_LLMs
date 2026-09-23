"""
The "reasoning mode" -- how thorough a run is. Geographic coverage never
varies: every mode covers all four Karnataka persona regions (see karnataka.py).
What mode scales is the VOLUME of sources gathered per region (targeted web
searches per region, YouTube posts kept per search, framings searched) and how
thorough each research write-up is asked to be.

Single source of truth for every mode-dependent constant.
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


PROVIDER_LABELS: dict[LlmProvider, str] = {
    "azure_anthropic": "Claude",
    "openai": "OpenAI",
    "gemma_local": "Gemma (local)",
    "mistral_local": "Mistral (local)",
    "gemma_remote": "Gemma",
}

# Models the divergence stage compares, when configured (see
# graph/nodes/divergence.py) -- the run's own provider is always included.
DIVERGENCE_PROVIDERS: tuple[LlmProvider, ...] = ("gemma_remote", "azure_anthropic")


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

# Reddit: posts requested per subreddit search (only when Reddit is configured).
REDDIT_PER_STATE_LIMIT: dict[ResearchMode, int] = {"basic": 3, "medium": 6, "high": 10, "extrahigh": 14}

# YouTube: search.list's quota cost is a FLAT 100 units regardless of how many
# results you request (up to its max of 50) — so always ask for a healthy
# video count per search rather than economizing there; the real lever is how
# many comments you harvest per video, and commentThreads.list costs a flat 1
# unit per call regardless of maxResults (up to 100) — so always request the
# max there too. What actually varies by mode is how many TOTAL posts we keep
# per framing (which bounds how many videos get their comments pulled).
YOUTUBE_POSTS_PER_FRAMING_CAP: dict[ResearchMode, int] = {
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
    "extrahigh": "500-700 words, considering multiple search queries internally",
}

# Per-region cluster-count bounds for cluster_viewpoints_per_region's
# silhouette sweep (graph/nodes/cluster_viewpoints.py). k_max is additionally
# capped so a sweep never proposes a k averaging fewer than ~3 posts per
# cluster (a 1-post "cluster" has no viewpoint to summarize).
EXTRAHIGH_CLUSTER_K_MIN = 2
EXTRAHIGH_CLUSTER_K_MAX = 10
EXTRAHIGH_MIN_POSTS_PER_CLUSTER = 3

# Intra-region deflection pairs extracted per region (extract_region_deflections).
EXTRAHIGH_DEFLECTIONS_PER_REGION_CAP = 2

# ── Karnataka persona-region pipeline ─────────────────────────────────────────
# Research angles fired PER REGION (4 regions), each its own targeted web
# search -- see graph/nodes/research.py's REGION_RESEARCH_ANGLE_TEMPLATES.
REGION_RESEARCH_ANGLES: dict[ResearchMode, int] = {"basic": 1, "medium": 2, "high": 3, "extrahigh": 4}

# YouTube posts kept per region-targeted search (query + region search terms).
# search.list costs a flat 100 quota units regardless, so 4 regions = 400 units.
REGION_YOUTUBE_LIMIT: dict[ResearchMode, int] = {"basic": 20, "medium": 40, "high": 80, "extrahigh": 120}
