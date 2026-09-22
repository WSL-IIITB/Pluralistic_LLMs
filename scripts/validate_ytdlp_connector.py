#!/usr/bin/env python3
"""Validate the real YouTubeDlpConnector (backend/app/connectors/sources.py)
against live YouTube, through the exact object the pipeline calls, without
standing up the full backend (needs only light deps: pydantic-settings,
praw, google-api-python-client, yt-dlp).

Runs the same fan-out shape as graph/build.py's source_posts: several queries
at the framing + per-state pattern (`query`, `query StateName`), each with the
per-mode youtube limits. Confirms the connector returns SourcedPosts the
pipeline accepts: id/platform/text/source_hint/permalink, all platform=youtube.

Usage:  scripts/.smoke-venv/Scripts/python.exe scripts/validate_ytdlp_connector.py
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND))  # noqa: E402 -- must precede app imports

from app.config import Settings  # noqa: E402
from app.connectors.sources import YouTubeDlpConnector  # noqa: E402

# Windows consoles default to cp1252 and crash on non-Latin comment text.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

CASES = [
    ("Diwali", 150),                                            # extrahigh cap, bare topic
    ("Diwali Kerala", 60),                                      # per-state suffix pattern
    ("high-school dropouts: where should government intervene?", 60),  # long policy query
]


async def main() -> int:
    settings = Settings(youtube_provider="ytdlp")
    print(f"has_youtube (API key present): {settings.has_youtube}  "
          f"(should be False -- yt-dlp needs no key)")
    conn = YouTubeDlpConnector(settings)

    for query, limit in CASES:
        print(f"\n=== search({query!r}, limit={limit}) ===")
        posts = await conn.search(query, limit)
        print(f"posts returned: {len(posts)}")
        if not posts:
            print("  ** EMPTY -- investigate **")
            continue
        keys_ok = all({"id", "platform", "text", "source_hint", "permalink"} <= set(p) for p in posts)
        print(f"all have id/platform/text/source_hint/permalink: {keys_ok}")
        print(f"platforms: {sorted({p['platform'] for p in posts})}")
        print(f"unique source_hints: {len({p['source_hint'] for p in posts})}")
        print(f"unique permalinks:   {len({p['permalink'] for p in posts})}")
        print(f"id prefix distinct from API path ('ytdlp_'): "
              f"{all(p['id'].startswith('ytdlp_') for p in posts)}")
        for p in posts[:4]:
            print(f"  - {p['id'][:18]:<18} {p['source_hint'][:46]:<46} {p['text'][:52]!r}")
        print(f"  ... {len(posts) - 4} more")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))