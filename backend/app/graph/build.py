"""
Wires the pipeline stages into a LangGraph StateGraph. Two topologies,
selected by `mode` at graph-construction time in `build_graph()`:

    basic/medium/high (unchanged): source -> research -> cluster -> resolve -> deflect -> synthesize -> END
    extrahigh:                     source -> research -> geo_resolve -> cluster -> resolve -> deflect -> synthesize -> END

`source` is small enough (fan out to the two connectors, flatten into
`state["posts"]`) that it's defined here rather than as its own node file.
Every other stage lives in graph/nodes/ and was built to the exact
`(state, emit, ...)` signature this module calls. extrahigh's `cluster`/
`resolve`/`deflect` bind to different (additive, not modified) functions that
cluster and extract deflections PER STATE instead of once globally — see
graph/nodes/geo_resolve.py's and cluster_viewpoints.py's module docstrings for
why. `synthesize` is the same function either way.

The graph is rebuilt per request (cheap — this isn't a compiled model) so each
request gets its own `emit` closure without threading dependency-injection
through LangGraph's config machinery. Building two different topologies in
that same per-request construction is consistent with, not a departure from,
that existing cost model — `mode` is already known before `ainvoke` runs, so
this is a graph-construction-time choice, not something that needs LangGraph's
`add_conditional_edges` runtime-predicate machinery.
"""

from __future__ import annotations

import asyncio
import itertools
import json
import re

import httpx
from langgraph.graph import END, StateGraph

from ..config import DATA_DIR, Settings
from ..connectors.base import LLMClient, SourceConnector, SourcedPost
from ..connectors.llm import get_llm_client
from ..connectors.sources import get_reddit_connector, get_youtube_connector
from ..data.language_regions import detect_script_region
from ..data.subreddit_map import STATE_PRIORITY_ORDER, STATE_SUBREDDIT, lookup_subreddit
from ..reasoning_modes import (
    FRAMING_COUNT,
    REDDIT_PER_STATE_LIMIT,
    YOUTUBE_POSTS_PER_FRAMING_CAP,
    LlmProvider,
    ResearchMode,
)
from ..schema import CollectionCounts, StatusEvent
from .nodes.cluster_viewpoints import cluster_viewpoints, cluster_viewpoints_per_state
from .nodes.deflection_and_synthesis import (
    extract_deflections,
    extract_deflections_per_state,
    synthesize_answer,
)
from .nodes.geo_resolve import resolve_posts_geography
from .nodes.research import gather_research
from .nodes.resolve_district import finalize_districts, resolve_districts
from .state import EmitFn, PipelineState, RawPost, new_pipeline_state

_gazetteer_cache: dict | None = None


def load_gazetteer() -> dict:
    global _gazetteer_cache
    if _gazetteer_cache is None:
        with open(f"{DATA_DIR}/district_gazetteer.json", encoding="utf-8") as f:
            _gazetteer_cache = json.load(f)
    return _gazetteer_cache


def counts_from_state(state: PipelineState) -> CollectionCounts:
    return CollectionCounts(
        postsCollected=state["posts_collected"],
        districtsResolved=state["districts_resolved"],
        clustersFound=state["clusters_found"],
        deflectionsFound=state["deflections_found"],
        sourcesGathered=len(state.get("research_documents", [])),
    )


# ── Reasoning mode -> volume/thoroughness, NOT geographic coverage ──────────
# Geographic coverage is always the full STATE_PRIORITY_ORDER regardless of
# mode (see reasoning_modes.py's module docstring for why: partial state
# coverage would directly undermine the product's cross-India-representation
# point). What mode actually controls: how many distinct regional/cultural
# framings get searched for (FRAMING_COUNT), how many posts each state's
# Reddit search asks for (REDDIT_PER_STATE_LIMIT), and how many posts each
# YouTube framing-search keeps (YOUTUBE_POSTS_PER_FRAMING_CAP).
_MAX_CONCURRENT_FETCHES = 6

# Below this many substantive "words" (Unicode-aware — covers Hindi/Bengali/
# Tamil/etc. scripts too, not just Latin), a post is dropped before it ever
# reaches clustering. A cluster built from "Yes", "🙏🙏🙏", or a single word
# has no actual stance to summarize -- any labeler, stub or real LLM alike,
# can only echo the raw text back, which is exactly what reads as a bogus
# "viewpoint" instead of a genuine one.
_MIN_SIGNAL_WORDS = 4
_WORD_RE = re.compile(r"\w{2,}", re.UNICODE)


def _is_low_signal(text: str) -> bool:
    return len(_WORD_RE.findall(text)) < _MIN_SIGNAL_WORDS


# Local-only relevance gate: a small model running via Ollama on this
# machine, never the paid LLM provider -- this runs once per post (hundreds
# per pipeline run), so routing it through Claude/OpenAI would multiply the
# per-post cost that's already the run's dominant expense (see
# resolve_district.py's extract_place_mentions, which already calls the paid
# provider once per post). An embedding-similarity threshold was tried first
# and rejected: real on-topic posts and genuinely off-topic ones didn't
# separate cleanly at any single cosine-similarity cutoff (a threshold that
# caught obvious spam also dropped a real "dropped out to work the harvest"
# testimony), so this asks a small model the actual question in words
# instead of proxying it through vector distance.
_OLLAMA_URL = "http://localhost:11434/api/chat"
_RELEVANCE_MODEL = "gemma3:4b"
_RELEVANCE_CONCURRENCY = 4  # local single-GPU/CPU inference -- mild parallelism, not a fan-out


async def _is_relevant(client: httpx.AsyncClient, text: str, query: str, framings: list[str]) -> bool:
    framing_line = "; ".join(framings) if framings else "(no specific known framings)"
    prompt = (
        f'Topic: "{query}"\n'
        f"Known angles on this topic: {framing_line}\n\n"
        f'Post: "{text}"\n\n'
        "Is this post substantively about the topic above -- even tangentially, e.g. "
        "a specific complaint, a skeptical take, or a related opinion? Off-topic chatter, "
        "spam, or garbled/nonsense text is NOT relevant. Answer with exactly one word: yes or no."
    )
    resp = await client.post(
        _OLLAMA_URL,
        json={
            "model": _RELEVANCE_MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
            "options": {"temperature": 0},
        },
        timeout=30.0,
    )
    resp.raise_for_status()
    answer = resp.json()["message"]["content"].strip().lower()
    return answer.startswith("y")


async def _filter_by_relevance(posts: list[RawPost], query: str, framings: list[str]) -> list[RawPost]:
    """Drop posts a local small model judges off-topic. Two things slip past
    the word-count check in `_is_low_signal` and land here instead: unrelated
    comment-thread noise on an otherwise on-topic video (real words, wrong
    topic), and garbled/corrupted text (real word-shaped tokens, no actual
    meaning) -- the latter also happens to be a known trigger for the paid
    LLM's safety classifier to refuse the label/paraphrase call outright, so
    filtering it here avoids that failure mode too, not just the bogus
    cluster it produces.

    Fails open: if Ollama isn't reachable, or any individual check errors,
    those posts are KEPT rather than dropped -- this is a quality gate, not
    a required stage, and losing real data to a local-model hiccup would be
    worse than letting a few off-topic posts through.
    """
    if not posts:
        return posts

    async with httpx.AsyncClient() as client:
        try:
            await client.get("http://localhost:11434/api/tags", timeout=5.0)
        except Exception as exc:  # noqa: BLE001
            print(
                f"[source_posts] local relevance filter unavailable (Ollama not reachable at "
                f"localhost:11434): {exc} -- skipping filter",
                flush=True,
            )
            return posts

        semaphore = asyncio.Semaphore(_RELEVANCE_CONCURRENCY)

        async def check(post: RawPost) -> bool:
            async with semaphore:
                try:
                    return await _is_relevant(client, post["text"], query, framings)
                except Exception as exc:  # noqa: BLE001
                    print(f"[source_posts] relevance check failed, keeping post: {exc}", flush=True)
                    return True

        keep_flags = await asyncio.gather(*(check(post) for post in posts))

    kept = [post for post, keep in zip(posts, keep_flags) if keep]
    dropped = len(posts) - len(kept)
    if dropped:
        print(f"[source_posts] dropped {dropped} off-topic post(s) before clustering (local relevance filter)", flush=True)
    return kept


async def source_posts(
    state: PipelineState,
    emit: EmitFn,
    reddit: SourceConnector,
    youtube: SourceConnector,
    llm: LLMClient,
) -> PipelineState:
    """First pipeline stage: a BALANCED multi-state, multi-framing fan-out,
    not one flat keyword search. Geographic coverage is always the full
    region-interleaved state list (see data/subreddit_map.py's
    STATE_PRIORITY_ORDER) -- the "reasoning mode" (state["mode"],
    basic/medium/high) instead scales how many distinct regional/cultural
    framings of the topic get searched for (see llm.suggest_framings) and how
    many posts get pulled per state/framing, so the corpus is a deliberate
    cross-India sample of the topic's actual substantive variation, not an
    emergent, population/activity-biased one, and not just whatever generic
    reactions a bare keyword search happens to surface.

    Reddit is targeted directly at each state's subreddit (a real geographic
    signal), one search per state. YouTube search has no per-state filter, so
    instead of faking one via query augmentation, it runs one search per
    FRAMING (not per state) -- that's the axis YouTube can actually
    discriminate on, and resolve_district's hierarchy plus the clustering
    stage remain the sole sources of truth for where a post resolves and what
    viewpoint it actually expresses.
    """
    mode: ResearchMode = state["mode"]
    target_states = STATE_PRIORITY_ORDER
    reddit_limit = REDDIT_PER_STATE_LIMIT[mode]
    youtube_limit = YOUTUBE_POSTS_PER_FRAMING_CAP[mode]

    known_framings = await llm.suggest_framings(state["query"], FRAMING_COUNT[mode])
    state["framings"] = known_framings  # kept empty if the LLM found none — used later to
    # ground synthesis in real-world knowledge; do NOT fall back to [query] here, that
    # would misrepresent "no known regional variation" as if it were one.
    framings = known_framings or [state["query"]]

    def framing_for(i: int) -> str:
        return framings[i % len(framings)]

    await emit(
        StatusEvent(
            queryRunId=state["query_run_id"],
            ticker=(
                f"Surveying {len(target_states)} states across "
                f"{len(framings)} angle{'s' if len(framings) != 1 else ''} for "
                f"“{state['query']}” ({mode} mode)…"
            ),
            phase="sourcing",
            counts=counts_from_state(state),
            progress=0.02,
        )
    )

    semaphore = asyncio.Semaphore(_MAX_CONCURRENT_FETCHES)

    async def fetch_reddit(index: int, state_code: str) -> list[SourcedPost]:
        subreddit = STATE_SUBREDDIT.get(state_code)
        search_subreddit = getattr(reddit, "search_subreddit", None)
        if not subreddit or search_subreddit is None:
            return []
        async with semaphore:
            try:
                return await search_subreddit(subreddit, framing_for(index), reddit_limit)
            except Exception as exc:  # noqa: BLE001 — one state's failure must not kill the run
                print(f"[source_posts] reddit/{subreddit} failed: {exc}", flush=True)
                return []

    async def fetch_youtube(framing: str) -> list[SourcedPost]:
        async with semaphore:
            try:
                return await youtube.search(framing, youtube_limit)
            except Exception as exc:  # noqa: BLE001
                print(f"[source_posts] youtube/{framing!r} failed: {exc}", flush=True)
                return []

    fetched = await asyncio.gather(
        *(fetch_reddit(i, code) for i, code in enumerate(target_states)),
        *(fetch_youtube(framing) for framing in framings),
    )

    posts: list[RawPost] = []
    dropped = 0
    for i, p in enumerate(itertools.chain.from_iterable(fetched)):
        if _is_low_signal(p["text"]):
            dropped += 1
            continue
        posts.append(
            RawPost(
                id=p.get("id") or f"p{i}",
                platform=p["platform"],
                text=p["text"],
                source_hint=p["source_hint"],
                permalink=p.get("permalink"),
                cluster_id=None,
                state_code=None,
                district_id=None,
                resolution_method=None,
                resolution_confidence=None,
            )
        )
    if dropped:
        print(f"[source_posts] dropped {dropped} low-signal post(s) before clustering", flush=True)

    posts = await _filter_by_relevance(posts, state["query"], framings)
    state["posts"] = posts
    state["posts_collected"] = len(posts)

    await emit(
        StatusEvent(
            queryRunId=state["query_run_id"],
            ticker=(
                f"Collected {len(posts)} posts across {len(target_states)} states · "
                "resolving districts…"
            ),
            phase="sourcing",
            counts=counts_from_state(state),
            progress=0.1,
        )
    )
    return state


def _bind(fn, **extra):
    async def wrapped(state: PipelineState) -> PipelineState:
        return await fn(state, **extra)

    return wrapped


def build_graph(emit: EmitFn, llm: LLMClient, settings: Settings, mode: ResearchMode):
    """Constructs and compiles the pipeline graph for one request. `mode`
    selects the topology (see module docstring) — known before `ainvoke` runs,
    so this is a one-time branch at construction, not a runtime predicate."""
    reddit = get_reddit_connector(settings)
    youtube = get_youtube_connector(settings)
    gazetteer = load_gazetteer()

    graph = StateGraph(PipelineState)
    graph.add_node(
        "source", _bind(source_posts, emit=emit, reddit=reddit, youtube=youtube, llm=llm)
    )
    graph.add_node("research", _bind(gather_research, emit=emit, llm=llm))

    if mode == "extrahigh":
        graph.add_node(
            "geo_resolve",
            _bind(
                resolve_posts_geography,
                emit=emit,
                llm=llm,
                gazetteer=gazetteer,
                subreddit_lookup=lookup_subreddit,
                script_region_detect=detect_script_region,
            ),
        )
        graph.add_node("cluster", _bind(cluster_viewpoints_per_state, emit=emit, llm=llm))
        graph.add_node("resolve", _bind(finalize_districts, emit=emit, llm=llm))
        graph.add_node("deflect", _bind(extract_deflections_per_state, emit=emit, llm=llm))
        graph.add_node("synthesize", _bind(synthesize_answer, emit=emit, llm=llm))

        graph.set_entry_point("source")
        graph.add_edge("source", "research")
        graph.add_edge("research", "geo_resolve")
        graph.add_edge("geo_resolve", "cluster")
        graph.add_edge("cluster", "resolve")
        graph.add_edge("resolve", "deflect")
        graph.add_edge("deflect", "synthesize")
        graph.add_edge("synthesize", END)
    else:
        graph.add_node("cluster", _bind(cluster_viewpoints, emit=emit, llm=llm))
        graph.add_node(
            "resolve",
            _bind(
                resolve_districts,
                emit=emit,
                llm=llm,
                gazetteer=gazetteer,
                subreddit_lookup=lookup_subreddit,
                script_region_detect=detect_script_region,
            ),
        )
        graph.add_node("deflect", _bind(extract_deflections, emit=emit, llm=llm))
        graph.add_node("synthesize", _bind(synthesize_answer, emit=emit, llm=llm))

        graph.set_entry_point("source")
        graph.add_edge("source", "research")
        graph.add_edge("research", "cluster")
        graph.add_edge("cluster", "resolve")
        graph.add_edge("resolve", "deflect")
        graph.add_edge("deflect", "synthesize")
        graph.add_edge("synthesize", END)

    return graph.compile()


async def run_pipeline(
    query: str,
    mode: ResearchMode,
    provider: LlmProvider,
    query_run_id: str,
    query_type: str,
    settings: Settings,
    emit: EmitFn,
) -> PipelineState:
    """Runs one full pass. Caller has already emitted `query_started` and will
    emit `done`/`error` based on this function's return/exception."""
    llm = get_llm_client(settings, provider)
    state = new_pipeline_state(query_run_id, query, mode)
    state["query_type"] = query_type
    graph = build_graph(emit, llm, settings, mode)
    return await graph.ainvoke(state)
