#!/usr/bin/env python3
"""Measure yt-dlp sourcing wall-clock through the REAL LangGraph `source_posts`
node -- the open end-to-end-latency question left by the yt-dlp trial.

This runs the sourcing stage at production fidelity: the same `source_posts`
function from graph/build.py, the same `YouTubeDlpConnector`, the same 6-wide
asyncio semaphore, and the same fan-out shape per mode (framing searches, plus
the 36 per-state searches that extrahigh alone fires). The ONLY substitution is
the LLM: a tiny deterministic stub returning realistic India-topic framings and
keeping every post. No LLM endpoint is configured on this machine, and the
stages that genuinely need one (research / clustering / geo-resolution /
deflection / synthesis) don't depend on the yt-dlp swap anyway.

What the reported numbers therefore mean: the yt-dlp-dominated portion of a full
run at each mode. The still-unmeasured remainder is the LLM stages, which add
their own wall-clock regardless of which YouTube connector is used.

Usage:
  scripts/.smoke-venv/Scripts/python.exe scripts/measure_ytdlp_sourcing.py [query]
      [--modes basic,medium]      subset of basic/medium/high/extrahigh
      [--baseline]                also time 3 sequential single-search calls

Default query: "Diwali" (same as earlier validation, for comparability).
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import time
import traceback
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND))  # noqa: E402 -- must precede app imports

from app.config import Settings  # noqa: E402
from app.connectors.sources import YouTubeDlpConnector, get_reddit_connector  # noqa: E402
from app.data.subreddit_map import STATE_PRIORITY_ORDER  # noqa: E402
from app.graph.build import load_gazetteer, source_posts  # noqa: E402
from app.graph.state import EmitFn, new_pipeline_state  # noqa: E402

# Windows consoles default to cp1252 and crash on non-Latin comment text.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

MODE_ORDER = ["basic", "medium", "high", "extrahigh"]

# One realistic India-on-topic framing per index, so the fan-out is the same
# shape (and same search count) production's suggest_framings produces, and each
# search actually surfaces regional YouTube content to crawl. Base faults to the
# query itself if it's not a known topic.
_BASE_FRAMINGS: dict[str, list[str]] = {
    "diwali": [
        "Diwali celebrations in India",
        "Diwali customs and traditions",
        "Diwali in different Indian states",
        "Diwali regional variations",
        "Diwali festival lights and fireworks",
        "Diwali north vs south India",
        "Diwali city vs village celebrations",
        "Diwali modern vs traditional",
        "Diwali debates and controversies",
        "Diwali stories and history",
    ],
}


def _framings_for(query: str, count: int) -> list[str]:
    base = _BASE_FRAMINGS.get(query.strip().lower())
    if base:
        return base[:count]
    return [f"{query} in India", f"{query} regional views", f"{query} north vs south",
            f"{query} city vs village", f"{query} traditions", f"{query} debates",
            f"{query} history", f"{query} opinions", f"{query} stories", f"{query} future"][:count]


class _MeasureLLM:
    """Deterministic stand-in for the only two LLM calls source_posts makes:
    suggest_framings (realistic list => real fan-out shape) and
    judge_text_relevance (keeps everything -- we're timing yt-dlp, not the
    per-post relevance pass, which here would be an actual LLM call)."""

    def __init__(self, query: str, max_framings: int) -> None:
        self._framings = _framings_for(query, max_framings)

    async def suggest_framings(self, query: str, max_count: int) -> list[str]:  # noqa: ARG002
        return self._framings[:max_count]

    async def judge_text_relevance(self, question: str) -> bool:  # noqa: ARG002
        return True


async def _noop_emit(event) -> None:  # noqa: ARG001
    return None


async def _run_mode(settings: Settings, conn: YouTubeDlpConnector, query: str, mode: str) -> dict:
    llm = _MeasureLLM(query, 10)
    state = new_pipeline_state(f"measure_{mode}", query, mode)  # type: ignore[arg-type]
    print(f"\n=== source_posts mode={mode} query={query!r} ===", flush=True)

    t0 = time.perf_counter()
    out = await source_posts(
        state, _noop_emit, get_reddit_connector(settings), conn, llm, load_gazetteer()
    )
    elapsed = time.perf_counter() - t0

    posts = out["posts"]
    by_video: dict[str, int] = {}
    for p in posts:
        by_video[p["permalink"] or "?"] = by_video.get(p["permalink"] or "?", 0) + 1
    video_counts = sorted(by_video.values(), reverse=True)
    total_searches = len(out["framings"]) + (len(STATE_PRIORITY_ORDER) if mode == "extrahigh" else 0)

    res = {
        "mode": mode,
        "elapsed_s": elapsed,
        "searches": total_searches,
        "posts": len(posts),
        "videos": len(by_video),
        "avg_posts_per_video": round(len(posts) / len(by_video), 1) if by_video else 0,
        "video_counts": video_counts,
        # Full stretches wall-clock at least as long as the longest lane; the 6-wide
        # semaphore means pure yt-dlp work = ~sum(call_time)/6. Both are useful bounds.
        "min_waves_s": elapsed,  # wall-clock IS the waves time here; single-search latency comes from --baseline
    }
    if posts:
        sources = sorted({p["source_hint"] for p in posts})
        print(f"  {len(posts)} posts · {len(by_video)} videos · {elapsed:.1f}s", flush=True)
        print(f"  posts per video (desc): {video_counts[:10]}", flush=True)
        print(f"  sample sources: {sources[:4]}", flush=True)
    else:
        print(f"  0 posts collected in {elapsed:.1f}s", flush=True)
    return res


async def _baseline(settings: Settings, conn: YouTubeDlpConnector, query: str) -> None:
    """Three sequential single-search calls => a per-call latency reference
    (search phase + comment-crawl phase), and the per-search video diversity:
    how many videos' comments a single search's post budget comes from."""
    print(f"\n=== baseline: 3 sequential single searches of {query!r} (limit 25) ===", flush=True)
    for i in range(3):
        q = f"{query} {['Maharashtra', 'Kerala', 'Bengal'][i]}"
        t0 = time.perf_counter()
        posts = await conn.search(q, 25)
        dt = time.perf_counter() - t0
        videos = sorted({p["permalink"] for p in posts if p.get("permalink")})
        print(f"  #{i + 1} {q!r:<28} {dt:5.1f}s  {len(posts):>3} posts  {len(videos):>2} videos", flush=True)


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("query", nargs="?", default="Diwali")
    parser.add_argument("--modes", default=",".join(MODE_ORDER), help="comma-separated subset of modes")
    parser.add_argument("--baseline", action="store_true", help="include the sequential single-search reference")
    args = parser.parse_args()

    modes = [m for m in args.modes.split(",") if m in MODE_ORDER]
    if not modes:
        print(f"no valid modes in {args.modes!r}; expected subset of {MODE_ORDER}", file=sys.stderr)
        return 2

    settings = Settings(youtube_provider="ytdlp")
    conn = YouTubeDlpConnector(settings)
    print(f"youtube_provider={settings.youtube_provider}  (has_youtube={settings.has_youtube})", flush=True)

    if args.baseline:
        await _baseline(settings, conn, args.query)

    results = []
    for mode in modes:
        try:
            results.append(await _run_mode(settings, conn, args.query, mode))
        except Exception as exc:  # noqa: BLE001 -- one mode failing shouldn't kill the sweep
            print(f"[measure] mode {mode} FAILED: {exc}", flush=True)
            traceback.print_exc()

    if not results:
        print("no modes completed", file=sys.stderr)
        return 1

    print("\n\n  MODE       searches  posts  videos  posts/video  wall-clock", flush=True)
    for r in results:
        print(f"  {r['mode']:<10} {r['searches']:>6}  {r['posts']:>5}  {r['videos']:>6}  "
              f"{r['avg_posts_per_video']:>10}  {r['elapsed_s']:>6.1f}s", flush=True)
    print("\n  (posts/video = mean comments kept per distinct video; a low mean with high "
          "total means good spread)", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))