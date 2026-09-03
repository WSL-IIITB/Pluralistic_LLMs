"""
Second pipeline stage (source → **research** → cluster → resolve → deflect →
synthesize).

Social-media chatter alone is thin for many queries — a bare Reddit/YouTube
search for `"high-school dropouts: where should government intervene?"` mostly
returns generic reactions or unrelated content. What that policy question needs
is *actual research*: UDISE reports, NGO briefs, government policy documents,
regional news coverage. This node fires web-search-grounded LLM calls to gather
that material as `ResearchDocument`s, streams them to the frontend as they
arrive (so the "Sources" section builds up progressively, like the map does),
and stashes them on `PipelineState` for the synthesis stage to ground its
consolidated answer in — with real citations.

Runs unconditionally per user directive ("always run"). basic/medium/high
cost one gpt-4o call per angle; angle count is normally
`len(state["framings"])` (one angle per known regional/cultural framing) and
only falls back to `reasoning_modes.FRAMING_COUNT[mode]` when no framings
were found, to size the on-the-fly decomposition `research()` does in that
case. Geographic coverage never varies for these modes — see
reasoning_modes.py's module docstring; mode only affects breadth-when-no-
framings and the requested write-up length.

extrahigh REPLACES that angle-based fan-out entirely with
`gather_research_per_state`: one targeted research call per Indian state/UT
(the pipeline's own `STATE_PRIORITY_ORDER`), each document tagged with which
state's query produced it, feeding into the SAME `_posts_from_research_documents`
below unchanged. This is the systematic geographic sweep the per-state/
per-region consolidation stages downstream (cluster_viewpoints_per_region,
extract_deflections_per_state, condition_states) are built to consume.

Each gathered ResearchDocument is ALSO turned into a RawPost (see
_posts_from_research_documents) and appended to state["posts"], so official
sources (connectors/llm.py's _OFFICIAL_SOURCE_BIAS biases these toward NITI
Aayog/data.gov.in/PIB/state-government releases) flow through the SAME
geo-resolution + clustering pipeline real social posts do, not just the
synthesis stage's citations. Many of these documents already name a specific
state/district in their own title (a data.gov.in "State/UTs-wise..." dataset,
a PIB release about one state's program), so the existing place_ner/LLM-
geolocation fallback chain can attribute them to real geography with no new
resolution logic. This also makes the map meaningfully resilient to a social
source outage (e.g. YouTube's daily quota exhausted, or no Reddit credentials
configured) -- research runs through a wholly separate API and stays
available even when social sourcing goes to zero.
"""

from __future__ import annotations

import asyncio

from ...connectors.base import LLMClient
from ...data.subreddit_map import STATE_PRIORITY_ORDER, _state_names_from_gazetteer
from ...reasoning_modes import FRAMING_COUNT
from ...research_cache import _merge_documents, get_research
from ...schema import (
    CollectionCounts,
    ResearchDocument,
    ResearchDocumentEvent,
    StatusEvent,
)
from ..state import EmitFn, PipelineState, RawPost
from .resolve_district import _normalize_name


# Bounds concurrent place-extraction calls in
# _posts_from_research_documents -- mirrors RemoteGemmaLLMClient's own
# _MAX_CONCURRENT_REQUESTS width, since that's the provider these calls
# actually land on by default.
_MAX_CONCURRENT_PLACE_EXTRACTIONS = 6

# extrahigh-only: bounds concurrent per-state research calls in
# gather_research_per_state below -- consistent with every other concurrency
# knob in this codebase (build.py's _MAX_CONCURRENT_FETCHES, this module's
# own _MAX_CONCURRENT_PLACE_EXTRACTIONS, cluster_viewpoints.py's
# _MAX_CONCURRENT_STATE_CLUSTERING, etc.). None of these are independently
# load-tested against the actual providers in use; see the "extrahigh
# per-state research chain" plan's cost section for the current estimate and
# why "alongside the existing per-region pass" was still the right call
# despite it.
_MAX_CONCURRENT_STATE_RESEARCH = 6

# Progress band gather_research_per_state's per-state ticker interpolates
# within -- the same "researching" phase band gather_research already
# occupies for every other mode (see its own 0.12 kickoff / 0.32 handoff
# emits below), just with per-state progress climbing smoothly across it
# instead of a single before/after pair.
_STATE_RESEARCH_PROGRESS_START = 0.12
_STATE_RESEARCH_PROGRESS_END = 0.32


def _counts_from_state(state: PipelineState) -> CollectionCounts:
    return CollectionCounts(
        posts_collected=state["posts_collected"],
        districts_resolved=state["districts_resolved"],
        clusters_found=state["clusters_found"],
        deflections_found=state["deflections_found"],
        sources_gathered=len(state.get("research_documents", [])),
    )


async def _posts_from_research_documents(
    documents: list[dict], llm: LLMClient, gazetteer: dict
) -> list[RawPost]:
    """Turn each ResearchDocument into RawPost-shaped entries -- see this
    module's own docstring for why. Text is the document's title + snippet
    (never the full page content, which this pipeline never fetches) --
    already grounded, curated-by-search text, so this skips the low-signal/
    relevance filters `source_posts` applies to raw social posts (those exist
    to catch spam/off-topic noise in an open-ended social feed; a search
    result this pipeline itself asked for doesn't need the same gate).

    Emits one post PER DISTINCT PLACE the document mentions, not one per
    document: an official source routinely covers several states at once
    ("...tribal children in Jharkhand and Odisha", a multi-state PIB release,
    a comparative study), and resolve_district.py's `_resolve_post` returns a
    single district by design -- so a one-post-per-document mapping would
    silently drop every state after the first. Each emitted post carries its
    own pre-resolved district/state (resolution_method "place_ner", the same
    method+gazetteer the social path uses for the identical signal), so
    geo_resolve.py passes them straight through rather than re-deriving --
    see that module's already-resolved guard.

    A document naming no recognizable place (an all-India dataset like
    "State/UTs-wise Retention Rate...", or a bare "Dropout Rate of School
    Children") yields ONE unresolved post: it still contributes its content
    to clustering and the answer, it just has no honest geography to claim.
    """
    # One LLM place-extraction call per document, run CONCURRENTLY (bounded)
    # rather than in a sequential await loop: a run gathers tens of documents
    # (more since connectors/llm.py's _WEB_SEARCH_MAX_RESULTS went up), and
    # serializing one round-trip each made this stage's latency scale linearly
    # with source count. Mirrors the bounded-fan-out pattern the resolve/
    # cluster stages already use for their own per-item LLM calls.
    semaphore = asyncio.Semaphore(_MAX_CONCURRENT_PLACE_EXTRACTIONS)

    def _texts_for(doc: dict) -> tuple[str, str]:
        """(display_text, geo_text) for one document. Prefers the longer body
        text for place extraction -- a source's state/district is far more
        often named in its body than its title (see connectors/llm.py's
        _GEO_TEXT_CHARS). Falls back to the short display text for documents
        that never carried one (cached entries written before geo_text
        existed, and OpenAI's research path, whose snippets come from findings
        prose rather than page content)."""
        title = str(doc.get("title") or "").strip()
        snippet = str(doc.get("snippet") or "").strip()
        text = f"{title}. {snippet}".strip(". ").strip()
        geo_source = str(doc.get("geo_text") or "").strip()
        geo_text = f"{title}. {geo_source}".strip(". ").strip() if geo_source else text
        return text, geo_text

    async def _places_for(doc: dict) -> list[str]:
        _, geo_text = _texts_for(doc)
        if not geo_text:
            return []
        async with semaphore:
            try:
                return await llm.extract_place_mentions(geo_text)
            except Exception as exc:  # noqa: BLE001 -- one doc's failure must not kill the stage
                print(
                    f"[gather_research] place extraction failed for doc {doc.get('id')}: {exc}",
                    flush=True,
                )
                return []

    places_per_doc = await asyncio.gather(*(_places_for(doc) for doc in documents))

    posts: list[RawPost] = []
    for doc, places in zip(documents, places_per_doc):
        text, _ = _texts_for(doc)
        if not text:
            continue

        doc_id = doc.get("id")
        source_hint = str(doc.get("domain") or "research")
        permalink = doc.get("url")

        # Resolve every mention first, then emit -- so a document naming both
        # a district and its parent state ("Sonitpur district of Assam") can
        # drop the vaguer state-level hit instead of double-counting one
        # source as two places. Confidence mirrors _resolve_post's own
        # place_ner rule exactly: "high" for an exact district-name hit,
        # "medium" for a state-name hit resolved to a representative district.
        resolved_places: list[tuple[str, dict, str]] = []  # (place, cand, confidence)
        seen_districts: set[str] = set()
        for place in places:
            candidates = gazetteer.get(_normalize_name(place))
            if not candidates:
                continue
            cand = candidates[0]
            district_id = cand.get("districtId")
            if not district_id or district_id in seen_districts:
                continue
            seen_districts.add(district_id)
            confidence = (
                "high" if _normalize_name(place) == _normalize_name(cand.get("districtName", ""))
                else "medium"
            )
            resolved_places.append((place, cand, confidence))

        # A state already covered by an exact district hit doesn't also need
        # its representative-district stand-in.
        states_with_exact_district = {
            cand.get("stateCode") for _, cand, conf in resolved_places if conf == "high"
        }
        resolved_places = [
            entry
            for entry in resolved_places
            if entry[2] == "high" or entry[1].get("stateCode") not in states_with_exact_district
        ]
        seen_districts = {cand["districtId"] for _, cand, _ in resolved_places}

        for place, cand, confidence in resolved_places:
            district_id = cand["districtId"]
            posts.append(
                RawPost(
                    id=f"research-{doc_id}-{district_id}",
                    platform="research",
                    # Lead with the place so any downstream re-read of this
                    # post's text (cluster labeling, paraphrase) keeps the
                    # geography this entry actually stands for.
                    text=f"{place}: {text}",
                    source_hint=source_hint,
                    permalink=permalink,
                    cluster_id=None,
                    state_code=cand.get("stateCode"),
                    district_id=district_id,
                    resolution_method="place_ner",
                    resolution_confidence=confidence,
                    region_id=None,
                )
            )

        if not seen_districts:
            posts.append(
                RawPost(
                    id=f"research-{doc_id}",
                    platform="research",
                    text=text,
                    source_hint=source_hint,
                    permalink=permalink,
                    cluster_id=None,
                    state_code=None,
                    district_id=None,
                    resolution_method=None,
                    resolution_confidence=None,
                    region_id=None,
                )
            )
    return posts


async def gather_research_per_state(
    state: PipelineState,
    emit: EmitFn,
    llm: LLMClient,
    gazetteer: dict,
    state_names: dict[str, str],
    target_states: list[str],
) -> tuple[str, list[dict]]:
    """extrahigh-mode counterpart to a plain `get_research(...)` call: instead
    of one angle-based research fan-out, fires ONE targeted, state-scoped
    research call per state in `target_states` -- geographic sweep, not
    topical-angle sweep, for this mode only (mirrors build.py's
    `fetch_youtube_state` fan-out shape: per-state task list + shared
    semaphore + `asyncio.as_completed` for progressive ticker events, one
    level up from cluster_viewpoints_per_state's identical
    states_done/total_states pattern).

    Each state's query is `f"{query} — {state_name}"`, passed to
    `get_research` as its OWN sole "known framing" with breadth=1 -- handing
    the query itself as the one framing skips `research()`'s costly
    `_decompose_for_research` fallback and produces exactly one
    `_research_one(state_query, ...)` call per state, with zero LLMClient
    Protocol changes needed. `research_cache.py` keys purely on query TEXT
    (semantic match via embeddings), so baking the state name into the query
    text here gives each state a naturally distinct cache entry with zero
    cache schema changes either.

    Every returned document is tagged with `source_state_code`/
    `source_state_query` before merging -- server-side-only provenance (never
    validated against `ResearchDocument`'s wire schema, so it rides along
    silently, the same way `geo_text` already does) that `condition_states`
    later uses to slice `state["research_documents"]` back apart per state
    for its mainstream/official-sources segment. Documents are merged
    dedupe-by-url across every state (reusing research_cache.py's own
    `_merge_documents` convention, renumbering to 1-based
    order-of-first-appearance) before being handed to the SAME, unmodified
    `_posts_from_research_documents` every mode already uses -- this is what
    already delivers district-level geography where the source content
    supports it, state-level fallback otherwise; no new geo-resolution logic
    is needed here.

    Returns (merged_findings, merged_tagged_docs), the same shape
    `get_research`/`llm.research` return, so `gather_research` below can
    treat both branches identically once this returns."""
    semaphore = asyncio.Semaphore(_MAX_CONCURRENT_STATE_RESEARCH)
    total_states = len(target_states)
    states_done = 0

    async def _research_one_state(state_code: str) -> tuple[str, list[dict], str]:
        name = state_names.get(state_code, state_code)
        state_query = f"{state['query']} — {name}"
        async with semaphore:
            findings, docs = await get_research(llm, state_query, [state_query], 1, "extrahigh")
        tagged_docs = [
            {**doc, "source_state_code": state_code, "source_state_query": state_query}
            for doc in docs
        ]
        return findings, tagged_docs, name

    tasks = [asyncio.ensure_future(_research_one_state(code)) for code in target_states]

    findings_parts: list[str] = []
    all_docs: list[dict] = []
    for finished in asyncio.as_completed(tasks):
        findings, tagged_docs, name = await finished
        if findings:
            findings_parts.append(findings)
        all_docs.extend(tagged_docs)

        # Re-merge (dedupe-by-url, renumber) after every completed state so
        # the ticker's own sources-gathered count (via _counts_from_state,
        # which reads state["research_documents"]) climbs progressively
        # rather than staying at 0 until the whole fan-out finishes.
        state["research_documents"] = _merge_documents([], all_docs)

        states_done += 1
        progress = (
            _STATE_RESEARCH_PROGRESS_START
            + (_STATE_RESEARCH_PROGRESS_END - _STATE_RESEARCH_PROGRESS_START)
            * (states_done / total_states)
        )
        await emit(
            StatusEvent(
                query_run_id=state["query_run_id"],
                ticker=(
                    f"Researching “{state['query']}” across states… "
                    f"{states_done}/{total_states} ({name})"
                ),
                phase="researching",
                counts=_counts_from_state(state),
                progress=progress,
            )
        )

    merged_findings = "\n\n".join(findings_parts).strip()
    return merged_findings, state["research_documents"]


async def gather_research(
    state: PipelineState,
    emit: EmitFn,
    llm: LLMClient,
    gazetteer: dict,
) -> PipelineState:
    """Fires web-search-grounded research calls in parallel, accumulates
    ResearchDocuments, and emits per-document events so the frontend's
    Sources section builds up progressively.

    basic/medium/high (unchanged): angles derived from `state["framings"]`
    (or generated on the fly if empty) -- one call per angle.
    extrahigh (this mode only): REPLACES the angle-based fan-out with one
    targeted call per Indian state/UT instead (`gather_research_per_state`
    above) -- a systematic geographic sweep, not a topical one. Running both
    would mean fighting over the same call budget for no clear benefit, and
    angle diversity is a weaker signal than full state coverage for this
    mode's purpose."""
    state["phase"] = "researching"
    mode = state["mode"]
    framings = state.get("framings") or []
    breadth = len(framings) if framings else FRAMING_COUNT[mode]

    if mode == "extrahigh":
        target_states = STATE_PRIORITY_ORDER
        state_names = _state_names_from_gazetteer(gazetteer)
        await emit(
            StatusEvent(
                query_run_id=state["query_run_id"],
                ticker=(
                    f"Researching “{state['query']}” across {len(target_states)} "
                    "states on the open web…"
                ),
                phase="researching",
                counts=_counts_from_state(state),
                progress=0.12,
            )
        )
        findings, docs = await gather_research_per_state(
            state, emit, llm, gazetteer, state_names, target_states
        )
    else:
        await emit(
            StatusEvent(
                query_run_id=state["query_run_id"],
                ticker=(
                    f"Researching “{state['query']}” across "
                    f"{breadth} angle{'s' if breadth != 1 else ''} on the open web…"
                ),
                phase="researching",
                counts=_counts_from_state(state),
                progress=0.12,
            )
        )
        # get_research() is a drop-in wrapper around llm.research() -- see
        # research_cache.py's module docstring -- that reuses previously-
        # gathered sources for a semantically-similar past query (LLM-judged,
        # not a fixed similarity cutoff) instead of always re-running the
        # full fan-out.
        findings, docs = await get_research(llm, state["query"], framings, breadth, mode)

    state["research_findings"] = findings
    state["research_documents"] = docs

    # extrahigh-only: turn each state-targeted ResearchDocument into geo-
    # tagged RawPosts (see _posts_from_research_documents's docstring) so the
    # per-state/per-region consolidation stages downstream have district-
    # level material to work with. basic/medium/high never ran this -- it is
    # an extra LLM call per document (extract_place_mentions) that changes
    # state["posts"]/posts_collected and downstream clustering input, so it
    # must stay scoped to the mode that actually needs it. Keeping it
    # unconditional would silently feed research-document posts into basic/
    # medium/high's clustering/deflection/synthesis, which the plan for this
    # feature explicitly requires to stay byte-for-byte untouched.
    research_posts: list[RawPost] = []
    if mode == "extrahigh":
        research_posts = await _posts_from_research_documents(docs, llm, gazetteer)
        if research_posts:
            state["posts"].extend(research_posts)
            state["posts_collected"] = len(state["posts"])

    # Emit each document as its own event so the UI can render sources as they
    # arrive rather than in one bulk drop. (In this implementation `research()`
    # returns them all at once because the underlying responses.create call is
    # non-streaming; per-document emission is still the right wire contract for
    # a future streaming implementation.)
    for doc in docs:
        try:
            await emit(
                ResearchDocumentEvent(
                    query_run_id=state["query_run_id"],
                    document=ResearchDocument.model_validate(doc),
                )
            )
        except Exception as exc:  # noqa: BLE001 — one malformed doc shouldn't kill the stream
            print(f"[gather_research] skipped malformed doc {doc!r}: {exc}", flush=True)

    await emit(
        StatusEvent(
            query_run_id=state["query_run_id"],
            ticker=(
                f"Gathered {len(docs)} source{'s' if len(docs) != 1 else ''} from the web"
                + (f" ({len(research_posts)} mapped for geography)" if research_posts else "")
                + " · clustering viewpoints…"
            ),
            phase="researching",
            counts=_counts_from_state(state),
            progress=0.32,
        )
    )
    return state
