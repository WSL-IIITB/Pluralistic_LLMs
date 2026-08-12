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

Runs unconditionally per user directive ("always run"). Costs one gpt-4o call
per angle; angle count is normally `len(state["framings"])` (one angle per
known regional/cultural framing) and only falls back to
`reasoning_modes.FRAMING_COUNT[mode]` when no framings were found, to size
the on-the-fly decomposition `research()` does in that case. Geographic
coverage never varies here — see reasoning_modes.py's module docstring; mode
only affects breadth-when-no-framings and the requested write-up length.
"""

from __future__ import annotations

from ...connectors.base import LLMClient
from ...reasoning_modes import FRAMING_COUNT
from ...research_cache import get_research
from ...schema import (
    CollectionCounts,
    ResearchDocument,
    ResearchDocumentEvent,
    StatusEvent,
)
from ..state import EmitFn, PipelineState


def _counts_from_state(state: PipelineState) -> CollectionCounts:
    return CollectionCounts(
        posts_collected=state["posts_collected"],
        districts_resolved=state["districts_resolved"],
        clusters_found=state["clusters_found"],
        deflections_found=state["deflections_found"],
        sources_gathered=len(state.get("research_documents", [])),
    )


async def gather_research(
    state: PipelineState,
    emit: EmitFn,
    llm: LLMClient,
) -> PipelineState:
    """Fires web-search-grounded research calls in parallel across angles
    derived from `state["framings"]` (or generated on the fly if empty),
    accumulates ResearchDocuments, and emits per-document events so the
    frontend's Sources section builds up progressively."""
    state["phase"] = "researching"
    mode = state["mode"]
    framings = state.get("framings") or []
    breadth = len(framings) if framings else FRAMING_COUNT[mode]

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
    # research_cache.py's module docstring -- that reuses previously-gathered
    # sources for a semantically-similar past query (LLM-judged, not a fixed
    # similarity cutoff) instead of always re-running the full fan-out.
    findings, docs = await get_research(llm, state["query"], framings, breadth, mode)

    state["research_findings"] = findings
    state["research_documents"] = docs

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
                f"Gathered {len(docs)} source{'s' if len(docs) != 1 else ''} from the web · "
                "clustering viewpoints…"
            ),
            phase="researching",
            counts=_counts_from_state(state),
            progress=0.32,
        )
    )
    return state
