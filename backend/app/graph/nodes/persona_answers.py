"""
Persona replies: for each Karnataka persona region, one reply per persona
variant (karnataka.persona_variants -- today "male" and "female"), written in
that variant's persona (karnataka.build_persona_prompt) and grounded in the
SAME region evidence for both variants. The evidence bundle is cached on
state["region_evidence"] so the second variant reuses exactly what the first
one built, rather than recomputing it.
"""

from __future__ import annotations

import asyncio
from collections import Counter

from ...connectors.base import LLMClient
from ...karnataka import build_persona_prompt, persona_regions, persona_variants
from ...schema import AnswerChunkEvent, AnswerSegment, CollectionCounts, StatusEvent
from ..state import EmitFn, PipelineState

_CONCURRENCY = 4
# Sources handed to each region's reply -- more for deeper modes, which gather more.
_MAX_DOCS_PER_REGION: dict[str, int] = {"basic": 10, "medium": 15, "high": 20, "extrahigh": 25}


def build_region_evidence(state: PipelineState, region_id: str) -> dict:
    posts = [p for p in state["posts"] if p.get("region_id") == region_id]
    region_urls = {p["permalink"] for p in posts if p["platform"] == "research" and p.get("permalink")}
    docs = [
        d
        for d in state.get("research_documents") or []
        if d.get("source_region_id") == region_id or d.get("url") in region_urls
    ][: _MAX_DOCS_PER_REGION.get(state["mode"], 15)]

    platform_by_post = {p["id"]: p["platform"] for p in posts}
    clusters = []
    for c in state["clusters"].values():
        if c.get("region_id") != region_id:
            continue
        sources = Counter(platform_by_post.get(pid, "other") for pid in c.get("post_ids") or [])
        clusters.append(
            {
                "id": c["id"],
                "label": c.get("label"),
                "summary": c.get("summary"),
                "postCount": len(c.get("post_ids") or []),
                "sources": dict(sources),
            }
        )
    clusters.sort(key=lambda c: c["postCount"], reverse=True)

    cluster_ids = {c["id"] for c in clusters}
    deflections = [
        {"between": [d["cluster_a"], d["cluster_b"]], "point": d["point"]}
        for d in state.get("deflections") or []
        if d.get("level") == "intra-region" and d.get("cluster_a") in cluster_ids
    ]
    return {
        "research_documents": [
            {"id": d["id"], "title": d.get("title"), "domain": d.get("domain"), "snippet": d.get("snippet")}
            for d in docs
        ],
        "clusters": clusters,
        "deflections": deflections,
    }


def reply_text(segments: list[dict]) -> str:
    return " ".join(s["text"].strip() for s in segments if s.get("text")).strip()


async def answer_regions(state: PipelineState, emit: EmitFn, llm: LLMClient) -> PipelineState:
    state["phase"] = "synthesizing"
    regions = persona_regions()
    jobs = [(spec, variant) for spec in regions for variant in persona_variants(spec["id"])]
    semaphore = asyncio.Semaphore(_CONCURRENCY)
    done = 0

    async def _one(spec: dict, variant: dict) -> None:
        nonlocal done
        region_id = spec["id"]
        variant_id = variant["id"]
        # Evidence is per-region, shared across that region's persona variants --
        # build it once (first variant to reach this region wins the race; both
        # variants then read the same dict, so only the persona differs between
        # a region's male and female replies).
        if region_id not in state["region_evidence"]:
            state["region_evidence"][region_id] = build_region_evidence(state, region_id)
        evidence = state["region_evidence"][region_id]
        segments: list[dict] = []
        for attempt in range(2):  # one retry: provider refusals/timeouts are intermittent
            try:
                async with semaphore:
                    segments = await llm.answer_for_region(
                        state["query"],
                        state["query_type"],
                        f"{spec['name']} -- {variant['label']}",
                        build_persona_prompt(region_id, variant_id),
                        evidence["research_documents"],
                        evidence["clusters"],
                        evidence["deflections"],
                        mode=state["mode"],
                    )
                break
            except Exception as exc:  # noqa: BLE001 -- one persona reply must not kill the others
                print(
                    f"[answer_regions] {region_id}/{variant_id} persona reply attempt {attempt + 1} failed: {exc}",
                    flush=True,
                )

        for seg in segments:
            kwargs: dict = {
                "text": seg["text"],
                "kind": seg.get("kind"),
                "region": spec["short_name"],
                "region_id": region_id,
                "persona_id": variant_id,
            }
            if seg.get("clusterId"):
                kwargs["cluster_id"] = seg["clusterId"]
            if seg.get("citations"):
                kwargs["citations"] = seg["citations"]
            segment = AnswerSegment(**kwargs)
            await emit(AnswerChunkEvent(query_run_id=state["query_run_id"], segment=segment))
            state["answer_segments"].append(segment.model_dump(by_alias=True, exclude_none=True))
        if segments:
            state["region_replies"].setdefault(region_id, {})[variant_id] = {
                "segments": segments,
                "text": reply_text(segments),
            }

        done += 1
        await emit(
            StatusEvent(
                query_run_id=state["query_run_id"],
                ticker=(
                    f"Persona replies {done}/{len(jobs)} ({spec['short_name']} · {variant['label']}"
                    f"{'' if segments else ' — failed'})…"
                ),
                phase="synthesizing",
                counts=CollectionCounts(
                    posts_collected=state["posts_collected"],
                    districts_resolved=state["districts_resolved"],
                    clusters_found=state["clusters_found"],
                    deflections_found=state["deflections_found"],
                    sources_gathered=len(state.get("research_documents") or []),
                    regions_found=len(state.get("region_stats") or {}),
                ),
                progress=0.88 + 0.05 * done / len(jobs),
            )
        )

    await asyncio.gather(*(_one(spec, variant) for spec, variant in jobs))
    return state
