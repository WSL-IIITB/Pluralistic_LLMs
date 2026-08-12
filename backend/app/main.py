"""
FastAPI SSE gateway. `GET /api/worldview/stream` runs the LangGraph pipeline
in a background task and forwards every event a node `emit()`s to the client
as an SSE message, JSON-encoded exactly per ../src/lib/worldview/types.ts.

Run: uvicorn app.main:app --reload --port 8001   (from backend/, venv active)
Point the frontend at it: VITE_WORLDVIEW_STREAM=sse, VITE_WORLDVIEW_API_URL=http://localhost:8001/api/worldview/stream
"""

from __future__ import annotations

import asyncio
import traceback
import uuid

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from sse_starlette.sse import EventSourceResponse

from .config import get_settings
from .graph.build import counts_from_state, run_pipeline
from .reasoning_modes import parse_mode, parse_provider
from .schema import DoneEvent, QueryStartedEvent, StreamErrorEvent, WorldviewEvent, event_to_sse_data

settings = get_settings()

app = FastAPI(title="Worldview Explorer — collector-agent backend")
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/healthz")
def healthz() -> dict:
    return {
        "ok": True,
        "has_llm": settings.has_llm,
        "has_reddit": settings.has_reddit,
        "has_youtube": settings.has_youtube,
    }


@app.get("/api/worldview/stream")
async def stream(
    q: str = Query(..., min_length=1),
    mode: str = Query("medium"),
    provider: str = Query(None),
    deeper: int = Query(0),
):
    query_run_id = f"run_{uuid.uuid4().hex}"
    parsed_mode = parse_mode(mode)
    parsed_provider = parse_provider(provider, default=settings.llm_provider)

    async def event_generator():
        queue: asyncio.Queue[WorldviewEvent | None] = asyncio.Queue()

        async def emit(event: WorldviewEvent) -> None:
            await queue.put(event)

        async def run() -> None:
            try:
                from .connectors.llm import get_llm_client

                llm = get_llm_client(settings, parsed_provider)
                query_type = await llm.classify_query_type(q)
                await emit(
                    QueryStartedEvent(
                        queryRunId=query_run_id,
                        query=q,
                        queryType=query_type,
                        mode=parsed_mode,
                        provider=parsed_provider,
                    )
                )
                final_state = await run_pipeline(
                    query=q,
                    mode=parsed_mode,
                    provider=parsed_provider,
                    query_run_id=query_run_id,
                    query_type=query_type,
                    settings=settings,
                    emit=emit,
                )
                await emit(DoneEvent(queryRunId=query_run_id, counts=counts_from_state(final_state)))
            except Exception as exc:  # noqa: BLE001 — surface any failure as a stream error, never a bare 500
                traceback.print_exc()
                await emit(StreamErrorEvent(queryRunId=query_run_id, message=str(exc), recoverable=False))
            finally:
                await queue.put(None)

        task = asyncio.create_task(run())
        try:
            while True:
                item = await queue.get()
                if item is None:
                    break
                yield {"event": item.type, "data": event_to_sse_data(item)}
        finally:
            task.cancel()

    return EventSourceResponse(event_generator())
