#!/usr/bin/env python3
"""yt-dlp smoke test for the Pluralistic LLMs backend.

Empirically answers whether yt-dlp can satisfy the backend's YouTube
comment-sourcing stage (backend/app/connectors/sources.py) with NO cookies
and NO API key -- i.e. the exact condition it would run under on the server.

The real pipeline (backend/app/graph/build.py:source_posts) does:
  * one search per LLM-suggested "framing" (3-10 depending on mode) and, in
    extrahigh mode, one search per state (36 states);
  * all fetches fanned out behind a 6-wide semaphore (_MAX_CONCURRENT_FETCHES).
Today every fetch is one Data-API search.list (100 quota units) + per-video
commentThreads.list (1 unit); quota exhaustion is the dominant failure mode.

This script checks the same shape against yt-dlp:

  [1] SEARCH       ytsearchN:{query} returns videos with id/title/channel
  [2] COMMENTS     extract_info(watch_url, getcomments=True) returns comments
                   AND reply threads (the API path drops replies entirely)
  [3] BLOCKS       any "Sign in to confirm you're not a bot" / 403 / 429
  [4] SPEED        seconds per search / per comment pass
  [5] CONCURRENT   6 parallel searches (the pipeline's semaphore width) --
                   does the burst trip rate-limiting?

Usage:
    python smoke_ytdlp.py [--query "Diwali"] [--videos 3] [--max-comments 100]
                          [--concurrent 6]        # 0 disables check 5

Only dependency: `pip install yt-dlp`. This is a THROWAWAY test -- it does
not touch backend code or config, and leaks no state into the repo.
"""

from __future__ import annotations

import argparse
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import yt_dlp

WATCH_URL = "https://www.youtube.com/watch?v={id}"

# Windows consoles default to cp1252 and crash on non-Latin video titles;
# never let that kill a smoke run (unrenderable glyphs print as '?').
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# Substrings seen in the exception text when YouTube blocks an anonymous
# client. Lowercased before matching.
BLOCK_SIGNATURES = (
    "sign in to confirm you're not a bot",
    "sign in to confirm",
    "not a bot",
    "captcha",
    "recaptcha",
    "http error 403",
    "forbidden",
    "http error 429",
    "too many requests",
    "rate limit",
    "unable to fetch",
)


def _new_ydl(max_comments: int | None, get_comments: bool = False) -> yt_dlp.YoutubeDL:
    """Fresh YoutubeDL per operation, mirroring connectors/sources.py's rule
    of never sharing one client across threads. `max_comments` bounds the
    crawl so the test stays fast (matches the API path's 100/video cap).

    `getcomments` must be a constructor OPTION on this yt-dlp (2026.08.x)
    -- passing it to extract_info() as a keyword raises TypeError."""
    opts = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "socket_timeout": 30,
        "retries": 2,
        # A single dead entry in a ytsearch playlist raises out of the whole
        # call otherwise -- skip it instead.
        "ignoreerrors": True,
    }
    if get_comments:
        opts["getcomments"] = True
    if max_comments:
        opts["extractor_args"] = {"youtube": {"max_comments": [str(max_comments)]}}
    return yt_dlp.YoutubeDL(opts)


def classify_error(exc: Exception) -> str:
    msg = str(exc).lower()
    for sig in BLOCK_SIGNATURES:
        if sig in msg:
            return f"BLOCK[{sig}]"
    return type(exc).__name__


def search(query: str, n: int, max_comments: int | None) -> dict:
    """One ytsearch fetch. Returns {entries, dt, error}."""
    t0 = time.perf_counter()
    try:
        with _new_ydl(max_comments) as ydl:
            info = ydl.extract_info(f"ytsearch{n}:{query}", download=False)
        entries = [e for e in (info or {}).get("entries", []) if e]
        return {"entries": entries, "dt": time.perf_counter() - t0, "error": None}
    except Exception as exc:  # noqa: BLE001 - a smoke test wants one exception per op
        return {"entries": [], "dt": time.perf_counter() - t0, "error": classify_error(exc)}


def fetch_comments(video_id: str, max_comments: int) -> dict:
    """One watch-URL fetch with getcomments=True. Returns stats + first text."""
    t0 = time.perf_counter()
    try:
        with _new_ydl(max_comments, get_comments=True) as ydl:
            info = ydl.extract_info(WATCH_URL.format(id=video_id), download=False)
        dt = time.perf_counter() - t0
        if not info:
            return {"comment_count": None, "roots": 0, "replies": 0, "dt": dt,
                    "error": "extract_info returned nothing"}
        if "comments" not in info:
            return {"comment_count": None, "roots": 0, "replies": 0, "dt": dt,
                    "error": "no 'comments' key (usually = comments disabled or auth wall)"}
        comments = info["comments"] or []
        roots = sum(1 for c in comments if c.get("parent", "root") in (None, "root"))
        sample = (comments[0].get("text") or "")[:120] if comments else ""
        return {
            "comment_count": len(comments),
            "roots": roots,
            "replies": len(comments) - roots,
            "dt": dt,
            "error": None,
            "sample": sample,
        }
    except Exception as exc:  # noqa: BLE001
        return {"comment_count": None, "roots": 0, "replies": 0,
                "dt": time.perf_counter() - t0, "error": classify_error(exc)}


def _fmt(dt: float) -> str:
    return f"{dt:5.1f}s"


def _row(op: str, video: str, result: dict, q: str) -> str:
    if result.get("error"):
        return (
            f"[{op:<8}] {video:<14} {result['error']:<42} {_fmt(result['dt'])}"
        )
    if op == "search":
        title = (result["entries"][0].get("title") or "?") if result.get("entries") else "?"
        return (
            f"[{op:<8}] {video:<14} "
            f"{len(result['entries']):>2} videos, first: {title[:52]:<52} {_fmt(result['dt'])}"
        )
    # comment row
    n = result.get("comment_count")
    if n is None:
        return f"[{op:<8}] {video:<14} {'no data':<42} {_fmt(result['dt'])}"
    cap = " (capped)" if n >= 100 else ""
    sample = result.get("sample") or ""
    return (
        f"[{op:<8}] {video:<14} {n:>4} comments, "
        f"{result['roots']} top, {result['replies']} replies{cap:<8} {_fmt(result['dt'])} "
        f"| {sample}"
    )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--query", default="Diwali", help="topic to search (default: Diwali)")
    ap.add_argument("--videos", type=int, default=3, help="how many top videos to pull comments from")
    ap.add_argument("--max-comments", type=int, default=100,
                    help="per-video comment cap (default 100 = the API path's cap)")
    ap.add_argument("--concurrent", type=int, default=6,
                    help="concurrent-search stress test width (0 disables; default 6)")
    args = ap.parse_args()

    print(f"yt-dlp {yt_dlp.version.__version__}  |  python {sys.version.split()[0]}  "
          f"|  no cookies, no API key")
    verdict = {"searches": 0, "search_err": 0, "comment_ops": 0, "comment_err": 0,
               "blocks": [], "search_dts": [], "comment_dts": [], "total_comments": 0}

    # [1] SEARCH -------------------------------------------------------------
    q, N = args.query, args.videos
    print(f"\n[1/5] SEARCH   ytsearch{N}:{q!r}")
    res = search(q, N, args.max_comments)
    verdict["searches"] += 1
    if res["error"]:
        verdict["search_err"] += 1
        verdict["blocks"].append(("search", res["error"]))
        print(_row("search", f"ytsearch{N}", res, q))
    else:
        entries = res["entries"]
        verdict["search_dts"].append(res["dt"])
        print(_row("search", f"ytsearch{N}", res, q))
        for e in entries[:N]:
            title = (e.get("title") or "?")[:58]
            chan = (e.get("channel") or e.get("uploader") or "?")[:30]
            views = e.get("view_count")
            v = f", {views:,} views" if views else ""
            print(f"        - {e['id']:<12} {chan:<32} {title}{v}")

    # [2] COMMENTS -----------------------------------------------------------
    print(f"\n[2/5] COMMENTS up to {args.max_comments} per video, top {args.videos} results")
    sampled = 0
    if res.get("entries"):
        for e in res["entries"][: args.videos]:
            kid = e.get("id")
            if not kid:
                continue
            vr = fetch_comments(kid, args.max_comments)
            verdict["comment_ops"] += 1
            if vr.get("error"):
                verdict["comment_err"] += 1
                verdict["blocks"].append((kid, vr["error"]))
            else:
                verdict["comment_dts"].append(vr["dt"])
                verdict["total_comments"] += vr.get("comment_count") or 0
            print(_row("comments", kid, vr, q))
            sampled += 1
    else:
        print("        (search produced no videos -- nothing to fetch comments from)")

    # [3] BLOCKS -------------------------------------------------------------
    print("\n[3/5] BLOCKS")
    if verdict["blocks"]:
        for op, err in verdict["blocks"]:
            print(f"        {op:<12} {err}")
    else:
        print(f"        none across {verdict['searches'] + verdict['comment_ops']} requests")

    # [4] SPEED --------------------------------------------------------------
    print("\n[4/5] SPEED   (backend fans out behind a 6-wide semaphore)")
    def _stats(dts):
        return (min(dts), sum(dts) / len(dts), max(dts)) if dts else (0.0, 0.0, 0.0)
    for label, dts in (("search  ", verdict["search_dts"]), ("comments", verdict["comment_dts"])):
        lo, avg, hi = _stats(dts)
        print(f"        {label}  min {_fmt(lo)}  avg {_fmt(avg)}  max {_fmt(hi)}   ({len(dts)} ops)")

    # [5] CONCURRENT stress --------------------------------------------------
    wall = 0.0
    if args.concurrent > 0:
        print(f"\n[5/5] CONCURRENT {args.concurrent} simultaneous searches (semaphore width)")
        t0 = time.perf_counter()
        per = {}
        with ThreadPoolExecutor(max_workers=args.concurrent) as pool:
            futs = [pool.submit(search, q, 3, args.max_comments) for _ in range(args.concurrent)]
            for i, fut in enumerate(as_completed(futs)):
                per[i] = fut.result()
        wall = time.perf_counter() - t0
        ok = sum(1 for r in per.values() if not r["error"])
        bad = [r["error"] for r in per.values() if r["error"]]
        for sig in set(bad):
            verdict["blocks"].append((f"x{args.concurrent}", sig))
        print(f"        {ok}/{args.concurrent} ok, {len(bad)} failed, wall {_fmt(wall)} "
              f"(max single {_fmt(max(r['dt'] for r in per.values()))})")
        if bad:
            print("        first failure signatures: " + ", ".join(sorted(set(bad))[:5]))

    # VERDICT ----------------------------------------------------------------
    print("\n" + "=" * 62)
    had_block = any("BLOCK[" in b for _, b in verdict["blocks"])
    no_comments = verdict["comment_ops"] > 0 and verdict["total_comments"] == 0
    if verdict["search_err"]:
        print(f"FAIL -- search itself {' / '.join(b for _, b in verdict['blocks']) }.")
        print("      yt-dlp cannot replace the API while anonymous scraping is blocked.")
        print("      Options: --cookies from a browser session, or keep the Data API.")
        return 1
    if had_block and verdict["comment_ops"] == 0:
        print(f"FAIL -- comments blocked ({' / '.join(b for _, b in verdict['blocks'])}).")
        print("      No comment data available without cookies under this network.")
        return 1
    if had_block:
        print(f"PARTIAL -- {len([b for b in verdict['blocks'] if 'BLOCK[' in b])} blocked request(s), "
              f"but enough succeeded to be usable. Expect rate-limiting under "
              f"extrahigh's 36-state fan-out; may need throttling/cookies.")
        return 2
    if no_comments:
        print("FAIL -- all video fetches returned zero comments (auth wall or all "
              "sampled videos disabled comments).")
        return 1
    print("PASS -- search + comments (incl. replies) work with no cookies/API key "
          f"({verdict['total_comments']} comments, "
          f"stressed at {args.concurrent} concurrent).")
    print("      Next: wiring behind the SourceConnector seam is worth doing.")
    return 0


if __name__ == "__main__":
    sys.exit(main())