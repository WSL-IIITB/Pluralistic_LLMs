"""
Viewpoint divergence: persona reply vs. no-persona reply, per region.

The no-persona reply is produced by the SAME llm.answer_for_region call with
the SAME question and the SAME evidence bundle the persona reply got
(state["region_evidence"]); only the persona text is removed. A second,
independent no-persona sample gives the noise floor -- how similar two replies
are when nothing changes but sampling -- so a persona effect can be read
against it.

Metrics (all cosine, all from the local sentence-transformers model, never a
provider's embeddings API, so scores are comparable across LLM providers):
  - semantic similarity (primary): mean of each reply's sentence embeddings
    (sentence-level so long replies aren't truncated at the model's 256-token
    limit); divergence = 1 - similarity
  - noise floor: the same similarity between the two no-persona samples
  - point alignment: BERTScore-style F1 over LLM-extracted points
  - which points are shared / reframed / only-with / only-without persona,
    by each point's best-matching counterpart
Plus, across regions: an 8x8 reply-similarity matrix and a t-SNE projection of
every extracted point.

All of this runs once PER MODEL (reasoning_modes.DIVERGENCE_PROVIDERS that are
configured, plus the run's own provider) on the SAME evidence and persona; the
measuring instruments stay fixed across models -- one point extractor (the
run's own LLM) and one embedding model -- so only the answering model varies.
A final cross-model event compares the models' replies to each other.
"""

from __future__ import annotations

import asyncio
import re

import numpy as np

from ...config import Settings
from ...connectors.base import LLMClient
from ...connectors.llm import _local_semantic_embed, get_llm_client
from ...karnataka import build_persona_prompt, persona_regions, persona_version, region_by_id
from ...reasoning_modes import DIVERGENCE_PROVIDERS, PROVIDER_LABELS
from ...schema import (
    CollectionCounts,
    DivergenceEmbeddingPoint,
    DivergenceModelsEvent,
    DivergencePointMatch,
    DivergenceRegionEvent,
    DivergenceSummaryEvent,
    ModelAgreement,
    StatusEvent,
)
from ..state import EmitFn, PipelineState
from .persona_answers import reply_text

EMBEDDING_MODEL = "all-MiniLM-L6-v2"
# all-MiniLM-L6-v2 cosine bands: paraphrases of one claim land well above
# SHARED; the same topic stated with a different claim or emphasis lands
# between the two; unrelated claims fall below REFRAMED.
SHARED_THRESHOLD = 0.75
REFRAMED_THRESHOLD = 0.55
_CONCURRENCY = 4
_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+")


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in _SENTENCE_RE.split(text) if len(s.strip()) > 3] or [text]


def _unit(m: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(m, axis=-1, keepdims=True)
    return m / np.where(norms == 0, 1, norms)


async def _embed(texts: list[str]) -> np.ndarray:
    return _unit(np.array(await _local_semantic_embed(texts), dtype=float))


async def _reply_vector(text: str) -> np.ndarray:
    return _unit((await _embed(_sentences(text))).mean(axis=0))


def _match_points(persona: list[str], baseline: list[str], p_vec: np.ndarray, b_vec: np.ndarray) -> dict:
    sim = p_vec @ b_vec.T
    shared, reframed, persona_only = [], [], []
    for i, text in enumerate(persona):
        j = int(sim[i].argmax())
        s = float(sim[i, j])
        if s >= SHARED_THRESHOLD:
            shared.append(DivergencePointMatch(persona=text, baseline=baseline[j], similarity=round(s, 3)))
        elif s >= REFRAMED_THRESHOLD:
            reframed.append(DivergencePointMatch(persona=text, baseline=baseline[j], similarity=round(s, 3)))
        else:
            persona_only.append(text)
    baseline_only = [baseline[j] for j in range(len(baseline)) if float(sim[:, j].max()) < REFRAMED_THRESHOLD]
    precision = float(sim.max(axis=1).mean())
    recall = float(sim.max(axis=0).mean())
    f1 = 2 * precision * recall / (precision + recall) if precision + recall > 0 else 0.0
    return {
        "shared": shared,
        "reframed": reframed,
        "persona_only": persona_only,
        "baseline_only": baseline_only,
        "alignment": round(f1, 3),
    }


def _tsne(vectors: np.ndarray) -> tuple[np.ndarray | None, float | None]:
    n = vectors.shape[0]
    if n < 6:
        return None, None
    from sklearn.manifold import TSNE

    perplexity = float(min(30, max(2, (n - 1) // 3)))
    coords = TSNE(n_components=2, perplexity=perplexity, metric="cosine", init="pca", random_state=42).fit_transform(
        vectors
    )
    return coords, perplexity


def divergence_models(settings: Settings, primary: str) -> list[str]:
    available = {"gemma_remote": settings.has_remote_gemma, "azure_anthropic": settings.has_azure_anthropic}
    return [primary] + [m for m in DIVERGENCE_PROVIDERS if m != primary and available.get(m)]


def _summary_event(state: PipelineState, model: str, results: dict[str, dict]) -> DivergenceSummaryEvent | None:
    measured = [spec["id"] for spec in persona_regions() if spec["id"] in results]
    if not measured:
        return None
    labels = [{"regionId": rid, "condition": c} for c in ("persona", "baseline") for rid in measured]
    vectors = np.stack([results[lbl["regionId"]][f"{lbl['condition']}_vec"] for lbl in labels])
    matrix = vectors @ vectors.T
    n = len(measured)

    def _cross(block: np.ndarray) -> float | None:
        return round(float(block[~np.eye(n, dtype=bool)].mean()), 3) if n >= 2 else None

    point_rows = [
        (rid, cond, text) for rid in measured for cond in ("persona", "baseline") for text in results[rid][f"{cond}_points"]
    ]
    point_vecs = np.vstack([results[rid][key] for rid in measured for key in ("p_vec", "b_vec")])
    coords, perplexity = _tsne(point_vecs)
    return DivergenceSummaryEvent(
        query_run_id=state["query_run_id"],
        model=model,  # type: ignore[arg-type]
        embedding_model=EMBEDDING_MODEL,
        labels=[{**lbl, "regionName": region_by_id()[lbl["regionId"]]["short_name"]} for lbl in labels],
        matrix=[[round(float(v), 3) for v in row] for row in matrix],
        persona_cross_region_similarity=_cross(matrix[:n, :n]),
        baseline_cross_region_similarity=_cross(matrix[n:, n:]),
        points=[
            DivergenceEmbeddingPoint(
                x=round(float(coords[i, 0]), 3),
                y=round(float(coords[i, 1]), 3),
                region_id=rid,
                condition=cond,  # type: ignore[arg-type]
                text=text,
            )
            for i, (rid, cond, text) in enumerate(point_rows)
        ]
        if coords is not None
        else [],
        perplexity=perplexity,
    )


async def measure_divergence(
    state: PipelineState, emit: EmitFn, llm: LLMClient, settings: Settings
) -> PipelineState:
    replies = state.get("region_replies") or {}
    regions = [spec for spec in persona_regions() if spec["id"] in replies]
    primary = state["provider"]
    models = divergence_models(settings, primary)
    clients = {m: llm if m == primary else get_llm_client(settings, m) for m in models}
    semaphores = {m: asyncio.Semaphore(_CONCURRENCY) for m in models}
    extractor_semaphore = asyncio.Semaphore(_CONCURRENCY)
    results: dict[str, dict[str, dict]] = {m: {} for m in models}
    total = len(models) * len(regions)
    done = 0

    def _counts() -> CollectionCounts:
        return CollectionCounts(
            posts_collected=state["posts_collected"],
            districts_resolved=state["districts_resolved"],
            clusters_found=state["clusters_found"],
            deflections_found=state["deflections_found"],
            sources_gathered=len(state.get("research_documents") or []),
            regions_found=len(state.get("region_stats") or {}),
        )

    await emit(
        StatusEvent(
            query_run_id=state["query_run_id"],
            ticker=(
                f"Measuring viewpoint divergence on {', '.join(PROVIDER_LABELS.get(m, m) for m in models)}: "  # type: ignore[call-overload]
                f"re-asking {len(regions)} regions without their persona…"
            ),
            phase="synthesizing",
            counts=_counts(),
            progress=0.93,
        )
    )

    async def _reply(model: str, spec: dict, persona: bool) -> list[dict]:
        ev = state["region_evidence"][spec["id"]]
        async with semaphores[model]:
            return await clients[model].answer_for_region(
                state["query"],
                state["query_type"],
                spec["name"],
                build_persona_prompt(spec["id"]) if persona else None,
                ev["research_documents"],
                ev["clusters"],
                ev["deflections"],
                mode=state["mode"],
            )

    async def _one(model: str, spec: dict) -> None:
        nonlocal done
        region_id = spec["id"]
        try:
            persona_segments = (
                replies[region_id]["segments"] if model == primary else await _reply(model, spec, True)
            )
            persona_text = reply_text(persona_segments)
            baseline_segments, noise_segments = await asyncio.gather(
                _reply(model, spec, False), _reply(model, spec, False), return_exceptions=True
            )
            if isinstance(baseline_segments, BaseException):
                raise baseline_segments
            baseline_text = reply_text(baseline_segments)
            # One fixed extractor for every model, so point granularity never varies with the model measured.
            async with extractor_semaphore:
                persona_points, baseline_points = await asyncio.gather(
                    llm.extract_points(persona_text), llm.extract_points(baseline_text)
                )
            persona_vec = await _reply_vector(persona_text)
            baseline_vec = await _reply_vector(baseline_text)
            similarity = float(persona_vec @ baseline_vec)
            noise_floor = None
            if not isinstance(noise_segments, BaseException):
                noise_floor = round(float(baseline_vec @ await _reply_vector(reply_text(noise_segments))), 3)
            p_vec = await _embed(persona_points)
            b_vec = await _embed(baseline_points)
            matched = _match_points(persona_points, baseline_points, p_vec, b_vec)
            results[model][region_id] = {
                "persona_vec": persona_vec,
                "baseline_vec": baseline_vec,
                "persona_points": persona_points,
                "baseline_points": baseline_points,
                "p_vec": p_vec,
                "b_vec": b_vec,
                "divergence": 1 - similarity,
            }
            event = DivergenceRegionEvent(
                query_run_id=state["query_run_id"],
                model=model,  # type: ignore[arg-type]
                region_id=region_id,
                region_name=spec["short_name"],
                status="ok",
                persona_version=persona_version(region_id),
                persona_reply=persona_text,
                baseline_reply=baseline_text,
                semantic_similarity=round(similarity, 3),
                divergence=round(1 - similarity, 3),
                noise_floor=noise_floor,
                point_alignment=matched["alignment"],
                persona_points=persona_points,
                baseline_points=baseline_points,
                shared=matched["shared"],
                reframed=matched["reframed"],
                persona_only=matched["persona_only"],
                baseline_only=matched["baseline_only"],
            )
        except Exception as exc:  # noqa: BLE001 -- report it, never fabricate a score
            print(f"[measure_divergence] {model}/{region_id} failed: {exc}", flush=True)
            event = DivergenceRegionEvent(
                query_run_id=state["query_run_id"],
                model=model,  # type: ignore[arg-type]
                region_id=region_id,
                region_name=spec["short_name"],
                status="failed",
                error=str(exc)[:300],
            )
        await emit(event)
        done += 1
        await emit(
            StatusEvent(
                query_run_id=state["query_run_id"],
                ticker=(
                    f"Divergence measured {done}/{total} "
                    f"({PROVIDER_LABELS.get(model, model)} · {spec['short_name']})…"  # type: ignore[call-overload]
                ),
                phase="synthesizing",
                counts=_counts(),
                progress=0.93 + 0.06 * done / max(1, total),
            )
        )

    await asyncio.gather(*(_one(m, spec) for m in models for spec in regions))

    for model in models:
        summary = await asyncio.to_thread(_summary_event, state, model, results[model])
        if summary:
            await emit(summary)

    agreements: list[ModelAgreement] = []
    for i, a in enumerate(models):
        for b in models[i + 1 :]:
            for spec in persona_regions():
                ra, rb = results[a].get(spec["id"]), results[b].get(spec["id"])
                if not ra or not rb:
                    continue
                agreements.append(
                    ModelAgreement(
                        region_id=spec["id"],
                        model_a=a,  # type: ignore[arg-type]
                        model_b=b,  # type: ignore[arg-type]
                        persona=round(float(ra["persona_vec"] @ rb["persona_vec"]), 3),
                        baseline=round(float(ra["baseline_vec"] @ rb["baseline_vec"]), 3),
                        divergence_a=round(ra["divergence"], 3),
                        divergence_b=round(rb["divergence"], 3),
                    )
                )
    if len(models) > 1:
        await emit(
            DivergenceModelsEvent(
                query_run_id=state["query_run_id"],
                models=[{"id": m, "label": PROVIDER_LABELS.get(m, m)} for m in models],  # type: ignore[call-overload]
                agreements=agreements,
            )
        )

    measured = sum(len(r) for r in results.values())
    state["phase"] = "complete"
    await emit(
        StatusEvent(
            query_run_id=state["query_run_id"],
            ticker=(
                f"Done · {state['posts_collected']} posts · {len(state.get('research_documents') or [])} sources · "
                f"{state['clusters_found']} viewpoints · divergence measured for {measured} region×model pairs"
            ),
            phase="complete",
            counts=_counts(),
            progress=1.0,
        )
    )
    return state
