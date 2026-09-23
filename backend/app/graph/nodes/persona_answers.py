"""
Persona replies: one reply per Karnataka persona region, written in that
region's persona (karnataka.build_persona_prompt) and grounded in that region's
own evidence. The evidence bundle is saved on state["region_evidence"] so the
divergence stage can re-ask the SAME question with the SAME evidence and only
the persona removed.
"""

from __future__ import annotations

import asyncio
from collections import Counter

from ...connectors.base import LLMClient
from ...karnataka import build_persona_prompt, persona_regions
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
    semaphore = asyncio.Semaphore(_CONCURRENCY)
    done = 0

    async def _one(spec: dict) -> None:
        nonlocal done
        region_id = spec["id"]
        evidence = build_region_evidence(state, region_id)
        state["region_evidence"][region_id] = evidence
        try:
            async with semaphore:
                segments = await llm.answer_for_region(
                    state["query"],
                    state["query_type"],
                    spec["name"],
                    build_persona_prompt(region_id),
                    evidence["research_documents"],
                    evidence["clusters"],
                    evidence["deflections"],
                    mode=state["mode"],
                )
        except Exception as exc:  # noqa: BLE001 -- one region must not kill the others
            print(f"[answer_regions] {region_id} persona reply failed: {exc}", flush=True)
            segments = []

        for seg in segments:
            kwargs: dict = {"text": seg["text"], "kind": seg.get("kind"), "region": spec["short_name"], "region_id": region_id}
            if seg.get("clusterId"):
                kwargs["cluster_id"] = seg["clusterId"]
            if seg.get("citations"):
                kwargs["citations"] = seg["citations"]
            segment = AnswerSegment(**kwargs)
            await emit(AnswerChunkEvent(query_run_id=state["query_run_id"], segment=segment))
            state["answer_segments"].append(segment.model_dump(by_alias=True, exclude_none=True))
        if segments:
            state["region_replies"][region_id] = {"segments": segments, "text": reply_text(segments)}

        done += 1
        await emit(
            StatusEvent(
                query_run_id=state["query_run_id"],
                ticker=(
                    f"Persona replies {done}/{len(regions)} ({spec['short_name']}"
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
                progress=0.88 + 0.05 * done / len(regions),
            )
        )

    await asyncio.gather(*(_one(spec) for spec in regions))
    return state
