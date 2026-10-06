"""
Research stage (source -> **research** -> resolve_regions -> cluster -> ...).

Fires web-search-grounded research REGION BY REGION across Karnataka's persona
regions (reasoning_modes.REGION_RESEARCH_ANGLES[mode] targeted angles each)
plus one statewide call, streams every gathered ResearchDocument to the
frontend, and keeps them on state for the region replies to cite.

Each document is tagged with the region whose query produced it
(`source_region_id`, server-side only -- never on the wire) and is ALSO turned
into region-attributed RawPosts (see _posts_from_research_documents), so
mainstream/official sources flow through the same clustering as social posts.
That keeps the map and every region's viewpoints populated even when social
sourcing yields nothing (YouTube quota exhausted, no Reddit credentials).
"""

from __future__ import annotations

import asyncio

from ...config import Settings
from ...connectors.base import LLMClient
from ...connectors.llm import get_llm_client
from ...karnataka import (
    karnataka_state_code,
    load_karnataka_gazetteer,
    normalize_place,
    persona_regions,
    region_from_alias,
    region_of_district,
    statewide_region_id,
)
from ...reasoning_modes import REGION_RESEARCH_ANGLES
from ...research_cache import _merge_documents, get_research
from ...schema import CollectionCounts, ResearchDocument, ResearchDocumentEvent, StatusEvent
from ..state import EmitFn, PipelineState, RawPost

_MAX_CONCURRENT_RESEARCH = 6
_MAX_CONCURRENT_PLACE_EXTRACTIONS = 6
_PROGRESS_START = 0.12
_PROGRESS_END = 0.32
# state["research_findings"] is every job's findings write-up joined into one
# string, consumed ONLY by synthesize_answer's single Karnataka-wide-overview
# call (persona_answers.py uses the per-region ResearchDocuments instead, so
# this cap never touches it). With 6 regions x up to 4 angles +
# 1 statewide, that's up to 25 jobs -- capping each job's own contribution
# keeps the join bounded regardless of region/mode count, and keeps every
# region a fair, comparable share of the summary rather than letting whichever
# jobs happen to finish first dominate it.
_MAX_FINDING_CHARS_PER_JOB = 900

# One targeted web search per template, per region; the first N (by mode) run.
REGION_RESEARCH_ANGLE_TEMPLATES = (
    "{query} — {name}, Karnataka ({terms})",
    "{query} {short} Karnataka government data statistics",
    "{query} {short} Karnataka local news",
    "{query} {short} Karnataka district study report",
)


def _counts_from_state(state: PipelineState) -> CollectionCounts:
    return CollectionCounts(
        posts_collected=state["posts_collected"],
        districts_resolved=state["districts_resolved"],
        clusters_found=state["clusters_found"],
        deflections_found=state["deflections_found"],
        sources_gathered=len(state.get("research_documents", [])),
    )


def _research_post(doc: dict, text: str, region_id: str, method: str, confidence: str, district_id: str | None) -> RawPost:
    return RawPost(
        id=f"research-{doc.get('id')}-{region_id}",
        platform="research",
        text=text,
        source_hint=str(doc.get("domain") or "research"),
        permalink=doc.get("url"),
        cluster_id=None,
        state_code=karnataka_state_code(),
        district_id=district_id,
        resolution_method=method,
        resolution_confidence=confidence,
        region_id=region_id,
        source_region_id=doc.get("source_region_id"),
    )


async def _posts_from_research_documents(documents: list[dict], llm: LLMClient, gazetteer: dict) -> list[RawPost]:
    """One post PER KARNATAKA REGION a document is about (not per district --
    several districts of one region would double-count the same source).
    A document naming only places outside Karnataka is dropped; one naming only
    "Karnataka" goes to the statewide bucket; one naming no place at all goes
    to the region whose targeted search found it (weak "search_context"
    signal) or, for the statewide search, to the statewide bucket."""
    semaphore = asyncio.Semaphore(_MAX_CONCURRENT_PLACE_EXTRACTIONS)
    ka_code = karnataka_state_code()
    district_region = region_of_district()
    statewide = statewide_region_id()

    def _texts_for(doc: dict) -> tuple[str, str]:
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
                print(f"[gather_research] place extraction failed for doc {doc.get('id')}: {exc}", flush=True)
                return []

    places_per_doc = await asyncio.gather(*(_places_for(doc) for doc in documents))

    posts: list[RawPost] = []
    for doc, places in zip(documents, places_per_doc):
        text, geo_text = _texts_for(doc)
        if not text:
            continue
        regions: dict[str, tuple[str, str | None]] = {}  # region -> (confidence, district_id)
        mentions_karnataka = False
        mentions_elsewhere = False
        for place in places:
            key = normalize_place(place)
            if key == "karnataka":
                mentions_karnataka = True
                continue
            alias_region = region_from_alias(place)
            if alias_region:
                regions.setdefault(alias_region, ("medium", None))
                continue
            cand = (gazetteer.get(key) or [None])[0]
            if not cand:
                continue
            if cand.get("stateCode") == ka_code and cand.get("districtId") in district_region:
                regions[district_region[cand["districtId"]]] = ("high", cand["districtId"])
            else:
                mentions_elsewhere = True
        if not regions:
            alias_region = region_from_alias(geo_text)
            if alias_region:
                regions[alias_region] = ("medium", None)

        if regions:
            for region_id, (confidence, district_id) in regions.items():
                posts.append(_research_post(doc, text, region_id, "place_ner", confidence, district_id))
        elif mentions_karnataka or "karnataka" in normalize_place(geo_text):
            posts.append(_research_post(doc, text, statewide, "state_fallback", "medium", None))
        elif mentions_elsewhere:
            continue
        elif doc.get("source_region_id") and doc["source_region_id"] != statewide:
            posts.append(_research_post(doc, text, doc["source_region_id"], "search_context", "low", None))
        else:
            posts.append(_research_post(doc, text, statewide, "state_fallback", "low", None))
    return posts


async def gather_research(
    state: PipelineState, emit: EmitFn, llm: LLMClient, gazetteer: dict, settings: Settings
) -> PipelineState:
    state["phase"] = "researching"
    mode = state["mode"]
    query = state["query"]
    n_angles = REGION_RESEARCH_ANGLES[mode]
    statewide = statewide_region_id()

    jobs: list[tuple[str, str, str]] = [(statewide, "Karnataka (statewide)", f"{query} Karnataka")]
    for region in persona_regions():
        for template in REGION_RESEARCH_ANGLE_TEMPLATES[:n_angles]:
            jobs.append(
                (
                    region["id"],
                    region["short_name"],
                    template.format(
                        query=query, name=region["name"], short=region["short_name"], terms=region["search_terms"]
                    ),
                )
            )

    await emit(
        StatusEvent(
            query_run_id=state["query_run_id"],
            ticker=(
                f"Researching “{query}” across Karnataka's {len(persona_regions())} regions "
                f"({len(jobs)} targeted web searches)…"
            ),
            phase="researching",
            counts=_counts_from_state(state),
            progress=_PROGRESS_START,
        )
    )

    semaphore = asyncio.Semaphore(_MAX_CONCURRENT_RESEARCH)
    # Web research goes through Claude's native web search whenever Claude is
    # configured -- the free Ollama search backend other models rely on
    # rate-limits (HTTP 429) a fan-out this size and silently yields almost
    # nothing. The run's own model stays the fallback, and does everything else.
    researcher = (
        get_llm_client(settings, "azure_anthropic")
        if state["provider"] != "azure_anthropic" and settings.has_azure_anthropic
        else llm
    )
    fallbacks_used = 0

    async def _run(region_id: str, label: str, angle: str) -> tuple[str, list[dict], str]:
        nonlocal fallbacks_used
        async with semaphore:
            findings, docs = await get_research(researcher, angle, [angle], 1, mode)
            if not docs and researcher is not llm:
                fallbacks_used += 1
                findings, docs = await get_research(llm, angle, [angle], 1, mode)
        return findings, [{**d, "source_region_id": region_id} for d in docs], label

    findings_parts: list[str] = []
    all_docs: list[dict] = []
    done = 0
    for finished in asyncio.as_completed([asyncio.ensure_future(_run(*job)) for job in jobs]):
        findings, docs, label = await finished
        if findings:
            findings_parts.append(
                findings
                if len(findings) <= _MAX_FINDING_CHARS_PER_JOB
                else findings[:_MAX_FINDING_CHARS_PER_JOB].rstrip() + "…"
            )
        all_docs.extend(docs)
        # Dedupe by url + renumber after each call so the sources count climbs live.
        state["research_documents"] = _merge_documents([], all_docs)
        done += 1
        await emit(
            StatusEvent(
                query_run_id=state["query_run_id"],
                ticker=f"Researching “{query}”… {done}/{len(jobs)} ({label})",
                phase="researching",
                counts=_counts_from_state(state),
                progress=_PROGRESS_START + (_PROGRESS_END - _PROGRESS_START) * done / len(jobs),
            )
        )

    docs = state["research_documents"]
    state["research_findings"] = "\n\n".join(findings_parts).strip()

    research_posts = await _posts_from_research_documents(docs, llm, load_karnataka_gazetteer(gazetteer))
    if research_posts:
        state["posts"].extend(research_posts)
        state["posts_collected"] = len(state["posts"])

    for doc in docs:
        try:
            await emit(
                ResearchDocumentEvent(query_run_id=state["query_run_id"], document=ResearchDocument.model_validate(doc))
            )
        except Exception as exc:  # noqa: BLE001 — one malformed doc shouldn't kill the stream
            print(f"[gather_research] skipped malformed doc {doc!r}: {exc}", flush=True)

    await emit(
        StatusEvent(
            query_run_id=state["query_run_id"],
            ticker=(
                f"Gathered {len(docs)} source{'s' if len(docs) != 1 else ''} from the web "
                f"({len(research_posts)} mapped to regions"
                f"{f', {fallbacks_used} fell back to the run model' if fallbacks_used else ''}) · resolving regions…"
            ),
            phase="researching",
            counts=_counts_from_state(state),
            progress=_PROGRESS_END,
        )
    )
    return state
