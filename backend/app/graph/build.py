"""
Wires the pipeline stages into a LangGraph StateGraph -- one topology for every
reasoning mode, working region by region across Karnataka's four persona
regions (see ../karnataka.py):

    source -> research -> resolve_regions -> cluster -> aggregate -> deflect
           -> synthesize -> answer_regions -> divergence -> END

`synthesize` writes the Karnataka-wide overview; `answer_regions` writes one
persona reply per region; `divergence` re-asks each region without its persona
and measures how far the two replies diverge.

The graph is rebuilt per request (cheap) so each request gets its own `emit`
closure.
"""

from __future__ import annotations

import asyncio
import itertools
import json
import re

from langgraph.graph import END, StateGraph

from ..config import DATA_DIR, Settings
from ..connectors.base import LLMClient, SourceConnector, SourcedPost
from ..connectors.llm import get_llm_client
from ..connectors.sources import get_reddit_connector, get_youtube_connector
from ..data.subreddit_map import lookup_subreddit
from ..karnataka import persona_regions, statewide_region_id
from ..reasoning_modes import (
    FRAMING_COUNT,
    REDDIT_PER_STATE_LIMIT,
    REGION_YOUTUBE_LIMIT,
    YOUTUBE_POSTS_PER_FRAMING_CAP,
    LlmProvider,
    ResearchMode,
)
from ..schema import CollectionCounts, StatusEvent
from .nodes.cluster_viewpoints import cluster_viewpoints_per_region
from .nodes.deflection_and_synthesis import extract_region_deflections, synthesize_answer
from .nodes.divergence import measure_divergence
from .nodes.persona_answers import answer_regions
from .nodes.research import gather_research
from .nodes.resolve_regions import aggregate_regions, resolve_regions
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
        regionsFound=len(state.get("region_stats") or {}),
    )


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


def _is_quota_exceeded(exc: Exception) -> bool:
    """True if `exc` is YouTube Data API's daily-quota-exhausted error (HTTP
    429, `reason: rateLimitExceeded`, distinct from an ordinary transient
    failure). Detected two ways: the structured HttpError status code when
    available, and a plain string match otherwise -- keeps this robust to
    whichever shape actually reaches a given call site (asyncio.to_thread
    wrapping in connectors/sources.py's YouTubeConnector.search means the
    original exception type does survive, but checking the message text too
    costs nothing and guards against that ever changing)."""
    try:
        from googleapiclient.errors import HttpError

        if isinstance(exc, HttpError) and getattr(exc, "status_code", None) == 429:
            return True
        if isinstance(exc, HttpError) and getattr(getattr(exc, "resp", None), "status", None) == 429:
            return True
    except ImportError:  # pragma: no cover -- googleapiclient always installed here
        pass
    return "quota" in str(exc).lower()


# Relevance gate: runs once per post (hundreds per pipeline run) via the
# run's OWN LLMClient (llm.judge_text_relevance), not a separately-hardcoded
# local model -- this used to hardcode a local Ollama model specifically to
# avoid multiplying a paid provider's per-post cost, but that made the whole
# gate fragile to a machine-specific detail (the hardcoded model tag not
# being pulled locally silently failed the check open, defeating the gate --
# confirmed happened in practice). Routing through `llm` instead means it
# rides whatever provider the run is already using -- for the app's default,
# gemma_remote, that's free and always available, so the original cost
# concern doesn't even apply; for a genuinely metered provider, this is one
# extra call per post same as any other per-post LLM step already in this
# pipeline (e.g. resolve_regions.py's extract_place_mentions).
#
# An embedding-similarity threshold was tried first and rejected: real
# on-topic posts and genuinely off-topic ones didn't separate cleanly at any
# single cosine-similarity cutoff (a threshold that caught obvious spam also
# dropped a real "dropped out to work the harvest" testimony), so this asks
# the model the actual question in words instead of proxying it through
# vector distance.
_RELEVANCE_CONCURRENCY = 6  # mirrors RemoteGemmaLLMClient's own semaphore width


async def _is_relevant(llm: LLMClient, text: str, query: str, framings: list[str]) -> bool:
    framing_line = "; ".join(framings) if framings else "(no specific known framings)"
    question = (
        f'Topic: "{query}"\n'
        f"Known angles on this topic: {framing_line}\n\n"
        f'Post: "{text}"\n\n'
        "Is this post substantively about the topic above -- even tangentially, e.g. "
        "a specific complaint, a skeptical take, or a related opinion? Off-topic chatter, "
        "spam, or garbled/nonsense text is NOT relevant."
    )
    return await llm.judge_text_relevance(question)


async def _filter_by_relevance(posts: list[RawPost], query: str, framings: list[str], llm: LLMClient) -> list[RawPost]:
    """Drop posts the run's own LLM judges off-topic. Two things slip past
    the word-count check in `_is_low_signal` and land here instead: unrelated
    comment-thread noise on an otherwise on-topic video (real words, wrong
    topic), and garbled/corrupted text (real word-shaped tokens, no actual
    meaning) -- the latter also happens to be a known trigger for a paid
    LLM's safety classifier to refuse the label/paraphrase call outright, so
    filtering it here avoids that failure mode too, not just the bogus
    cluster it produces.

    Fails open at THIS call site whenever an exception actually propagates
    (keeps the post rather than dropping it) -- a quality gate shouldn't cost
    real data over one bad call. Note `llm.judge_text_relevance` itself fails
    CLOSED (False, not a raise) on its own internal errors per that method's
    documented contract, so a systemic provider outage here reads as "nothing is
    relevant" rather than tripping this function's own except-branch --
    already-logged inside judge_text_relevance either way, and the pipeline's
    zero-posts path (see source_posts) handles the resulting empty corpus
    gracefully rather than crashing, so this isn't a silent-corruption risk,
    just a less graceful degradation than a true fail-open would be.
    """
    if not posts:
        return posts

    semaphore = asyncio.Semaphore(_RELEVANCE_CONCURRENCY)

    async def check(post: RawPost) -> bool:
        async with semaphore:
            try:
                return await _is_relevant(llm, post["text"], query, framings)
            except Exception as exc:  # noqa: BLE001
                print(f"[source_posts] relevance check failed, keeping post: {exc}", flush=True)
                return True

    keep_flags = await asyncio.gather(*(check(post) for post in posts))

    kept = [post for post, keep in zip(posts, keep_flags) if keep]
    dropped = len(posts) - len(kept)
    if dropped:
        print(f"[source_posts] dropped {dropped} off-topic post(s) before clustering (relevance filter)", flush=True)
    return kept


# Karnataka subreddits worth searching per region (Reddit is only used when
# credentials are configured -- see connectors/sources.py).
REGION_SUBREDDITS: dict[str, list[str]] = {
    "mysuru-bengaluru": ["bangalore", "mysore"],
    "karavali": ["mangalore"],
    "malnad": [],
    "north-karnataka": [],
}
STATEWIDE_SUBREDDITS = ["karnataka"]


async def source_posts(
    state: PipelineState,
    emit: EmitFn,
    reddit: SourceConnector,
    youtube: SourceConnector,
    llm: LLMClient,
) -> PipelineState:
    """Karnataka-targeted social sourcing: one YouTube search per persona
    region (query + that region's own place terms -- the geographic guarantee
    that every region gets an actual attempt), one per Karnataka-scoped
    framing, and each region's subreddits when Reddit is configured. Posts
    from a region-targeted search carry `source_region_id` so a post naming no
    place can still be weakly attributed (resolve_regions.py)."""
    mode: ResearchMode = state["mode"]
    regions = persona_regions()
    statewide = statewide_region_id()

    known_framings = await llm.suggest_framings(state["query"], FRAMING_COUNT[mode])
    state["framings"] = known_framings
    framings = known_framings or [state["query"]]

    await emit(
        StatusEvent(
            queryRunId=state["query_run_id"],
            ticker=(
                f"Surveying Karnataka's {len(regions)} regions across {len(framings)} "
                f"angle{'s' if len(framings) != 1 else ''} for “{state['query']}” ({mode} mode)…"
            ),
            phase="sourcing",
            counts=counts_from_state(state),
            progress=0.02,
        )
    )

    semaphore = asyncio.Semaphore(_MAX_CONCURRENT_FETCHES)
    youtube_quota_hit = False

    async def fetch_youtube(term: str, limit: int, source_region_id: str | None) -> list[tuple[SourcedPost, str | None]]:
        nonlocal youtube_quota_hit
        async with semaphore:
            try:
                return [(p, source_region_id) for p in await youtube.search(term, limit)]
            except Exception as exc:  # noqa: BLE001 — one search's failure must not kill the run
                if _is_quota_exceeded(exc):
                    youtube_quota_hit = True
                print(f"[source_posts] youtube/{term!r} failed: {exc}", flush=True)
                return []

    async def fetch_reddit(subreddit: str, source_region_id: str | None) -> list[tuple[SourcedPost, str | None]]:
        search_subreddit = getattr(reddit, "search_subreddit", None)
        if search_subreddit is None:
            return []
        async with semaphore:
            try:
                posts = await search_subreddit(subreddit, state["query"], REDDIT_PER_STATE_LIMIT[mode])
                return [(p, source_region_id) for p in posts]
            except Exception as exc:  # noqa: BLE001
                print(f"[source_posts] reddit/{subreddit} failed: {exc}", flush=True)
                return []

    tasks = [
        fetch_youtube(f"{state['query']} {r['search_terms']}", REGION_YOUTUBE_LIMIT[mode], r["id"]) for r in regions
    ]
    tasks += [fetch_youtube(f"{f} Karnataka", YOUTUBE_POSTS_PER_FRAMING_CAP[mode], None) for f in framings]
    tasks += [fetch_reddit(sub, r["id"]) for r in regions for sub in REGION_SUBREDDITS.get(r["id"], [])]
    tasks += [fetch_reddit(sub, statewide) for sub in STATEWIDE_SUBREDDITS]
    fetched = await asyncio.gather(*tasks)

    posts: list[RawPost] = []
    seen_ids: set[str] = set()
    dropped = 0
    for i, (p, source_region_id) in enumerate(itertools.chain.from_iterable(fetched)):
        post_id = p.get("id") or f"p{i}"
        if post_id in seen_ids:
            continue
        seen_ids.add(post_id)
        if _is_low_signal(p["text"]):
            dropped += 1
            continue
        posts.append(
            RawPost(
                id=post_id,
                platform=p["platform"],
                text=p["text"],
                source_hint=p["source_hint"],
                permalink=p.get("permalink"),
                cluster_id=None,
                state_code=None,
                district_id=None,
                resolution_method=None,
                resolution_confidence=None,
                region_id=None,
                source_region_id=source_region_id,
            )
        )
    if dropped:
        print(f"[source_posts] dropped {dropped} low-signal post(s) before clustering", flush=True)

    posts = await _filter_by_relevance(posts, state["query"], framings, llm)
    state["posts"] = posts
    state["posts_collected"] = len(posts)

    if not posts and youtube_quota_hit:
        await emit(
            StatusEvent(
                queryRunId=state["query_run_id"],
                ticker=(
                    "YouTube's daily API quota is exhausted and no Reddit credentials are configured — "
                    "continuing with mainstream and official web sources only…"
                ),
                phase="sourcing",
                counts=counts_from_state(state),
                progress=0.1,
            )
        )
        return state

    await emit(
        StatusEvent(
            queryRunId=state["query_run_id"],
            ticker=f"Collected {len(posts)} social posts · researching the open web…",
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
    """One topology for every mode (mode only scales volume -- see
    reasoning_modes.py):

      source -> research -> resolve_regions -> cluster -> aggregate -> deflect
             -> synthesize -> answer_regions -> divergence -> END
    """
    reddit = get_reddit_connector(settings)
    youtube = get_youtube_connector(settings)
    gazetteer = load_gazetteer()

    graph = StateGraph(PipelineState)
    graph.add_node("source", _bind(source_posts, emit=emit, reddit=reddit, youtube=youtube, llm=llm))
    graph.add_node("research", _bind(gather_research, emit=emit, llm=llm, gazetteer=gazetteer))
    graph.add_node(
        "resolve_regions",
        _bind(resolve_regions, emit=emit, llm=llm, gazetteer=gazetteer, subreddit_lookup=lookup_subreddit),
    )
    graph.add_node("cluster", _bind(cluster_viewpoints_per_region, emit=emit, llm=llm))
    graph.add_node("aggregate", _bind(aggregate_regions, emit=emit))
    graph.add_node("deflect", _bind(extract_region_deflections, emit=emit, llm=llm))
    graph.add_node("synthesize", _bind(synthesize_answer, emit=emit, llm=llm))
    graph.add_node("answer_regions", _bind(answer_regions, emit=emit, llm=llm))
    graph.add_node("divergence", _bind(measure_divergence, emit=emit, llm=llm))

    order = [
        "source",
        "research",
        "resolve_regions",
        "cluster",
        "aggregate",
        "deflect",
        "synthesize",
        "answer_regions",
        "divergence",
    ]
    graph.set_entry_point(order[0])
    for a, b in zip(order, order[1:]):
        graph.add_edge(a, b)
    graph.add_edge(order[-1], END)
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
