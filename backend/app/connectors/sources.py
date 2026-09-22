"""
Source connectors: Reddit, YouTube, and NITI district-indicator CSVs.

Each platform gets a `Stub*` implementation (deterministic fixture data, zero
external calls or credentials) and a real implementation gated by
`config.Settings.has_reddit` / `has_youtube` / `has_niti_csv`.
`get_reddit_connector()` / `get_youtube_connector()` / `get_niti_connector()`
pick the right one automatically — nodes in the graph should call those
factories rather than instantiating a class directly.

The NITI CSV connector is REAL data (no stub) — it ships in the repo's /niti
folder and needs no credentials, so "stub" for it would mean fabricating
government statistics, which is exactly what the stub variants are for the
noisy social sources and deliberately NOT done here. If the folder is
missing it simply contributes zero posts (NullSourceConnector), same as any
other unconfigured source.

Both stub connectors share one template bank (`FRAMINGS`) so a topic fed
through either source comes back with the same handful of recurring
"viewpoints" (economic-pragmatist, cultural-traditionalist, youth-aspirational,
policy-skeptic, regional-pride, data-driven-neutral) recombined with the query
and a place name. That's deliberate: it gives the downstream clustering stage
(which runs before district resolution in this pipeline — see
../graph/state.py) real signal to split 3-6 distinct clusters out of, instead
of a homogeneous blob of near-identical text.

Determinism: every stub post is generated from a `random.Random` seeded by a
SHA-256 hash of the query (+ a per-connector salt) — never Python's built-in
`hash()` (randomized per-process by PYTHONHASHSEED) and never wall-clock time.
The same query always yields the same posts, and a smaller `limit` always
yields a prefix of a larger `limit`'s results, since each post's content is a
pure function of (query, index) and doesn't depend on `limit` itself.
"""

from __future__ import annotations

import asyncio
import csv
import hashlib
import os
import random
import re
from dataclasses import dataclass

import praw
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from ..config import Settings
from ..data.subreddit_map import SUBREDDIT_DISTRICT_MAP
from .base import SourceConnector, SourcedPost

# ── Shared deterministic-content helpers ──────────────────────────────────────


def _stable_seed(*parts: str) -> int:
    """Deterministic integer seed from arbitrary strings (query, salt, ...).
    Uses SHA-256, not builtin hash(), so it's stable across processes/runs."""
    digest = hashlib.sha256("||".join(parts).encode("utf-8")).hexdigest()
    return int(digest[:16], 16)


def _short_hash(*parts: str) -> str:
    """Short deterministic hex id fragment, for building stable post/video ids."""
    return hashlib.sha256("||".join(parts).encode("utf-8")).hexdigest()[:10]


def _slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug or "topic"


# ── Subreddit pools, derived from the real subreddit -> district map ─────────
# (so stub source_hints are always names the resolver actually recognizes).

_CITY_SUBS = [k for k, v in SUBREDDIT_DISTRICT_MAP.items() if v["district_id"] is not None]
_STATE_SUBS = [
    k for k, v in SUBREDDIT_DISTRICT_MAP.items() if v["district_id"] is None and v["state_code"] is not None
]
_PAN_INDIA_SUBS = [k for k, v in SUBREDDIT_DISTRICT_MAP.items() if v["state_code"] is None]

# Weighted toward city subreddits (the richest single geo-signal), with state
# and pan-India ones mixed in — mirrors how a real India-focused search would
# skew (lots of city talk, some state-wide and national threads).
_SUBREDDIT_POOL = _CITY_SUBS * 3 + _STATE_SUBS * 2 + _PAN_INDIA_SUBS

# A modest, realistic subreddit set for the *real* PRAW search (kept small —
# very long "sub1+sub2+...+subN" strings are unwieldy and unnecessary; r/india
# plus a dozen big city subs already covers most relevant traffic).
_REDDIT_SEARCH_SUBS = ["india"] + _CITY_SUBS[:12]

_PAN_INDIA_KEYS = set(_PAN_INDIA_SUBS)

_SPECIAL_DISPLAY_NAMES: dict[str, str] = {
    "westbengal": "West Bengal",
    "tamilnadu": "Tamil Nadu",
    "andhrapradesh": "Andhra Pradesh",
    "uttarpradesh": "Uttar Pradesh",
    "madhyapradesh": "Madhya Pradesh",
    "himachalpradesh": "Himachal Pradesh",
    "arunachalpradesh": "Arunachal Pradesh",
    "vizag": "Visakhapatnam",
    "visakhapatnam": "Visakhapatnam",
    "bengaluru": "Bengaluru",
    "bangalore": "Bengaluru",
    "trivandrum": "Thiruvananthapuram",
    "thiruvananthapuram": "Thiruvananthapuram",
    "mysuru": "Mysuru",
    "mysore": "Mysuru",
    "pondicherry": "Puducherry",
    "puducherry": "Puducherry",
    "gurugram": "Gurugram",
    "gurgaon": "Gurugram",
}

_GENERIC_PLACE_FILLERS = ["this country", "the country", "most of the country", "the national conversation"]


def _display_name(subreddit_key: str) -> str:
    return _SPECIAL_DISPLAY_NAMES.get(subreddit_key, subreddit_key.capitalize())


def _place_phrase(subreddit_key: str, rng: random.Random) -> str:
    """A noun phrase usable as '...in {place}.' — a real place name for
    city/state subreddits, a generic filler for pan-India ones."""
    if subreddit_key in _PAN_INDIA_KEYS:
        return rng.choice(_GENERIC_PLACE_FILLERS)
    return _display_name(subreddit_key)


# ── Shared "viewpoint" template bank ──────────────────────────────────────────
# Six recurring framings. Every template takes {query} and {place}, and
# {place} is always placed mid-sentence (never sentence-initial) so it can be
# a lowercase generic filler ("in this country") or a proper noun ("in Kerala")
# without a capitalization mismatch either way.

FRAMINGS: list[list[str]] = [
    [  # economic pragmatist
        "The real question about {query} is who actually benefits economically in {place}.",
        "Until {query} turns into real jobs and income in {place}, it's just noise.",
        "Everyone's excited about {query}, but nobody in {place} is asking who pays for it.",
    ],
    [  # cultural traditionalist
        "{query} sounds progressive on paper, but it ignores how things actually work in {place}.",
        "Elders in {place} have seen ideas like {query} come and go for decades.",
        "There's a way of doing things in {place}, and {query} doesn't quite fit it.",
    ],
    [  # youth aspirational
        "Young people in {place} have been asking for exactly this kind of movement on {query}.",
        "{query} finally feels like change my generation in {place} can actually use.",
        "Honestly {query} is overdue — we've been stuck in the same conversation in {place} for years.",
    ],
    [  # policy skeptic
        "Another headline about {query}, another set of promises that will quietly disappear in {place}.",
        "Has anyone in {place} actually seen {query} deliver results, or is it all press releases?",
        "{query} gets announced every few years and somehow nothing changes on the ground in {place}.",
    ],
    [  # regional pride
        "People in {place} were already dealing with {query} long before it became a national talking point.",
        "Funny how {query} only gets attention when it's not about {place}.",
        "Folks forget {place} has its own way of handling {query}, and it works fine.",
    ],
    [  # data-driven neutral
        "The numbers on {query} look very different depending on the region, {place} included.",
        "Without proper data on {query} in {place}, everyone's just guessing at this point.",
        "Comparing districts, {query} plays out inconsistently — {place} is a good example.",
    ],
]


def _compose_text(query: str, place: str, framing_index: int, rng: random.Random) -> str:
    first_framing = framing_index % len(FRAMINGS)
    first = rng.choice(FRAMINGS[first_framing]).format(query=query, place=place)
    if rng.random() < 0.35:
        # Occasional second sentence from a *different* framing, for length
        # variety, like a title + a bit of body text — never the same framing
        # (which could otherwise pick the same template and repeat itself).
        other_framings = [i for i in range(len(FRAMINGS)) if i != first_framing]
        second_framing = rng.choice(other_framings)
        second = rng.choice(FRAMINGS[second_framing]).format(query=query, place=place)
        return f"{first} {second}"
    return first


class NullSourceConnector:
    """A source with no credentials and stub fallback disabled: contributes
    zero posts rather than fabricating fixture data. Implements both the
    generic `search()` Protocol and the Reddit-only `search_subreddit()` so it
    can stand in for either platform in the balanced multi-state sourcing pass."""

    async def search(self, query: str, limit: int) -> list[SourcedPost]:
        return []

    async def search_subreddit(self, subreddit: str, query: str, limit: int) -> list[SourcedPost]:
        return []


# ── Reddit ─────────────────────────────────────────────────────────────────────


class StubRedditConnector:
    """Deterministic fixture Reddit connector — zero external calls."""

    async def search(self, query: str, limit: int) -> list[SourcedPost]:
        rng = random.Random(_stable_seed(query, "reddit"))
        slug = _slugify(query)
        posts: list[SourcedPost] = []
        for i in range(limit):
            subreddit = rng.choice(_SUBREDDIT_POOL)
            place = _place_phrase(subreddit, rng)
            text = _compose_text(query, place, i, rng)
            post_id = f"stub-reddit-{_short_hash(query, str(i))}"
            posts.append(
                SourcedPost(
                    id=post_id,
                    platform="reddit",
                    text=text,
                    source_hint=subreddit,
                    permalink=f"https://reddit.com/r/{subreddit}/comments/{post_id}/{slug}",
                )
            )
        return posts

    async def search_subreddit(self, subreddit: str, query: str, limit: int) -> list[SourcedPost]:
        rng = random.Random(_stable_seed(query, "reddit", subreddit))
        slug = _slugify(query)
        place = _place_phrase(subreddit, rng)
        posts: list[SourcedPost] = []
        for i in range(limit):
            text = _compose_text(query, place, i, rng)
            post_id = f"stub-reddit-{_short_hash(query, subreddit, str(i))}"
            posts.append(
                SourcedPost(
                    id=post_id,
                    platform="reddit",
                    text=text,
                    source_hint=subreddit,
                    permalink=f"https://reddit.com/r/{subreddit}/comments/{post_id}/{slug}",
                )
            )
        return posts


class RedditConnector:
    """Real Reddit connector, backed by PRAW. Only constructed when
    settings.has_reddit is True — see get_reddit_connector()."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def _new_client(self) -> praw.Reddit:
        # Deliberately NOT cached on self: the balanced multi-state sourcing
        # pass runs many searches concurrently via asyncio.to_thread, each on
        # its own OS thread. PRAW's underlying HTTP session is not documented
        # as safe for concurrent use from multiple threads, and sharing one
        # instance across them was producing corrupted-connection errors
        # (garbled SSL/socket errors) under concurrency. A fresh, cheap,
        # no-network-call client per call keeps every thread isolated.
        return praw.Reddit(
            client_id=self._settings.reddit_client_id,
            client_secret=self._settings.reddit_client_secret,
            user_agent=self._settings.reddit_user_agent,
        )

    async def search(self, query: str, limit: int) -> list[SourcedPost]:
        # PRAW is a synchronous/blocking client — keep it off the event loop.
        return await asyncio.to_thread(self._search_sync, "+".join(_REDDIT_SEARCH_SUBS), query, limit)

    async def search_subreddit(self, subreddit: str, query: str, limit: int) -> list[SourcedPost]:
        """State-scoped search, used by the balanced multi-state sourcing pass
        (see ../graph/build.py) — targets one subreddit directly instead of
        the fixed aggregate set `.search()` uses."""
        return await asyncio.to_thread(self._search_sync, subreddit, query, limit)

    def _search_sync(self, subreddit_name: str, query: str, limit: int) -> list[SourcedPost]:
        reddit = self._new_client()
        subreddit = reddit.subreddit(subreddit_name)
        posts: list[SourcedPost] = []
        for submission in subreddit.search(query, limit=limit, sort="relevance"):
            title = (submission.title or "").strip()
            body = (submission.selftext or "").strip()
            text = f"{title} {body}".strip() if body else title
            posts.append(
                SourcedPost(
                    id=f"reddit_{submission.id}",
                    platform="reddit",
                    text=text,
                    source_hint=submission.subreddit.display_name,
                    permalink=f"https://reddit.com{submission.permalink}",
                )
            )
            if len(posts) >= limit:
                break
        return posts


def get_reddit_connector(settings: Settings) -> SourceConnector:
    if settings.has_reddit:
        return RedditConnector(settings)
    if settings.allow_stub_fallback:
        return StubRedditConnector()
    return NullSourceConnector()


# ── YouTube ────────────────────────────────────────────────────────────────────

# See the comments at each call site: both of these are the API's actual
# per-call maximums, requested unconditionally because the quota cost of each
# endpoint doesn't scale with maxResults (100 units/call for search.list,
# 1 unit/call for commentThreads.list, regardless of how many results you ask
# for). `limit` (the per-call SourceConnector.search parameter) is what
# actually bounds total volume, not these.
_YOUTUBE_SEARCH_MAX_RESULTS = 25
_YOUTUBE_COMMENTS_PER_VIDEO = 100

_CHANNEL_NAMES = [
    "National Desk",
    "Ground Report India",
    "The Daily Angle",
    "PolicyWatch India",
    "Youth Speaks",
    "Desi Analysis",
    "CityLens",
    "Bharat Bol",
    "The Local Take",
    "OpenMic News",
    "Real India Now",
    "Southern Voice",
    "Northern Digest",
    "The Field Report",
    "Public Opinion Hub",
]

_VIDEO_TITLE_TEMPLATES = [
    "{query} — what people are actually saying",
    "{query}: ground report",
    "Explained: {query}",
    "{query} debate gets heated | full discussion",
    "Is {query} working? We asked around",
    "{query} — regional reactions",
]


class StubYouTubeConnector:
    """Deterministic fixture YouTube connector — zero external calls."""

    async def search(self, query: str, limit: int) -> list[SourcedPost]:
        rng = random.Random(_stable_seed(query, "youtube"))
        # Comments cluster under a handful of "videos", like a real search
        # would return a few videos each with several top-level comments.
        # Fixed video-pool size (independent of `limit`) so that a smaller
        # `limit` always yields a prefix of a larger `limit`'s results.
        num_videos = 5
        videos: list[tuple[str, str, str]] = []
        for v in range(num_videos):
            channel = rng.choice(_CHANNEL_NAMES)
            title = rng.choice(_VIDEO_TITLE_TEMPLATES).format(query=query)
            video_id = _short_hash(query, "video", str(v))[:11]
            videos.append((channel, title, video_id))

        posts: list[SourcedPost] = []
        for i in range(limit):
            channel, title, video_id = videos[i % num_videos]
            # YouTube comments skew less geo-specific than subreddits — mostly
            # a generic filler, occasionally a named city for flavor.
            if rng.random() < 0.35:
                place = _display_name(rng.choice(_CITY_SUBS))
            else:
                place = rng.choice(_GENERIC_PLACE_FILLERS)
            text = _compose_text(query, place, i, rng)
            comment_id = f"stub-youtube-{_short_hash(query, str(i))}"
            posts.append(
                SourcedPost(
                    id=comment_id,
                    platform="youtube",
                    text=text,
                    source_hint=f"{channel} · {title}",
                    permalink=f"https://www.youtube.com/watch?v={video_id}",
                )
            )
        return posts


class YouTubeConnector:
    """Real YouTube connector, backed by the YouTube Data API v3. Only
    constructed when settings.has_youtube is True — see get_youtube_connector()."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def _new_client(self):
        # Deliberately NOT cached on self, for the same reason as
        # RedditConnector._new_client(): the balanced multi-state sourcing
        # pass fires many of these concurrently via asyncio.to_thread, and
        # googleapiclient's httplib2-backed transport is not safe to share
        # across threads -- doing so was producing corrupted-connection SSL
        # errors under concurrency. build() makes no network call, so a
        # fresh client per thread is cheap.
        return build("youtube", "v3", developerKey=self._settings.youtube_api_key)

    async def search(self, query: str, limit: int) -> list[SourcedPost]:
        # The googleapiclient client is synchronous/blocking too.
        return await asyncio.to_thread(self._search_sync, query, limit)

    def _search_sync(self, query: str, limit: int) -> list[SourcedPost]:
        youtube = self._new_client()
        posts: list[SourcedPost] = []

        # search.list costs a FLAT 100 quota units per call regardless of how
        # many results you request (up to its max of 50) -- so always ask for
        # a healthy video count rather than tying it to `limit`; the actual
        # volume control is `limit` itself (via how many videos' comments we
        # bother pulling below) and how many comments we harvest per video.
        search_resp = (
            youtube.search()
            .list(
                q=query,
                part="snippet",
                type="video",
                maxResults=_YOUTUBE_SEARCH_MAX_RESULTS,
                regionCode="IN",
                relevanceLanguage="en",
            )
            .execute()
        )

        for item in search_resp.get("items", []):
            if len(posts) >= limit:
                break
            video_id = item.get("id", {}).get("videoId")
            if not video_id:
                continue
            snippet = item.get("snippet", {})
            source_hint = f"{snippet.get('channelTitle', 'Unknown Channel')} · {snippet.get('title', '')}"
            video_url = f"https://www.youtube.com/watch?v={video_id}"

            try:
                # commentThreads.list costs a flat 1 quota unit per call
                # regardless of maxResults (up to 100) -- always request the
                # max rather than trimming to `remaining`; trimming here was
                # the main reason a single search used to return only a
                # handful of posts (maxResults=min(remaining,20) throttled to
                # ~4 posts across a whole state, for the same 1-unit cost as
                # asking for 100).
                comments_resp = (
                    youtube.commentThreads()
                    .list(
                        videoId=video_id,
                        part="snippet",
                        maxResults=_YOUTUBE_COMMENTS_PER_VIDEO,
                        textFormat="plainText",
                    )
                    .execute()
                )
            except HttpError:
                # Comments disabled on this video (or a transient API/quota
                # issue) — skip it and keep collecting from other videos.
                continue

            for c_item in comments_resp.get("items", []):
                if len(posts) >= limit:
                    break
                top_comment = c_item["snippet"]["topLevelComment"]
                comment_text = top_comment["snippet"].get("textDisplay", "").strip()
                if not comment_text:
                    continue
                posts.append(
                    SourcedPost(
                        id=f"youtube_{top_comment['id']}",
                        platform="youtube",
                        text=comment_text,
                        source_hint=source_hint,
                        permalink=video_url,
                    )
                )

        return posts


def _ytdlp_client(get_comments: bool = False, max_comments: int | None = None):
    """Fresh YoutubeDL instance per operation.

    Deliberately NOT cached on `self`, for the same reason as the other real
    connectors' `_new_client()` (the balanced multi-state sourcing pass runs
    many of these concurrently via asyncio.to_thread, and a YoutubeDL is not
    safe to share across threads). yt-dlp is imported lazily so this module
    still imports -- and the API path still works -- without it installed;
    only the ytdlp path reports the missing dependency.

    `getcomments` must be a constructor OPTION on current yt-dlp (2026.08.x+)
    -- passing it to extract_info() as a keyword now raises TypeError. A fresh
    instance with `getcomments` off is used for the search pass so that pass
    doesn't crawl every result's comments.
    """
    try:
        import yt_dlp  # noqa: PLC0415
    except ImportError as exc:  # pragma: no cover - env setup, not a code path
        raise RuntimeError("youtube_provider=ytdlp requires yt-dlp: `pip install yt-dlp`") from exc

    opts: dict[str, object] = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "socket_timeout": 30,
        "retries": 2,
        # A single dead/unavailable entry in a ytsearch playlist makes
        # extract_info RAISE out of the whole call otherwise (verified live:
        # "[youtube] <id>: This video is not available") -- skip it instead.
        "ignoreerrors": True,
    }
    if get_comments:
        opts["getcomments"] = True
    if max_comments:
        # Per-video TOTAL (top-level + replies), matching the API path's cap.
        opts["extractor_args"] = {"youtube": {"max_comments": [str(max_comments)]}}
    return yt_dlp.YoutubeDL(opts)


class YouTubeDlpConnector:
    """Real YouTube connector backed by yt-dlp — no API key, no daily quota.

    Selected via Settings.youtube_provider == "ytdlp" (see get_youtube_connector
    and config.py). Every quota-expensive Data-API call is replaced by scraping
    YouTube's public endpoints: `ytsearchN:{query}` for the video pass, then a
    per-video crawl with `getcomments`. Reply threads are included (the API
    path drops them — see the Data-API connector above).

    Trade-offs, accepted deliberately (see decisions.md 2026-09-06):
      * slower — each search is ~5-7s and each video's comment crawl ~5-7s (vs
        sub-second API calls); volume is bounded by _YOUTUBE_SEARCH_MAX_RESULTS
        videos and _YOUTUBE_COMMENTS_PER_VIDEO comments, same caps as the API
        path;
      * no native regionCode="IN" geo-targeting — relies on the pipeline's
        per-state query-suffixing (build.py source_posts) to bias recall, which
        the API connector already does for the state pass;
      * scraping YouTube's public endpoints violates ToS — acceptable for this
        internal research/demo tool, a real legal concern before any public use.
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    async def search(self, query: str, limit: int) -> list[SourcedPost]:
        # yt-dlp is synchronous/blocking — keep it off the event loop.
        return await asyncio.to_thread(self._search_sync, query, limit)

    def _search_sync(self, query: str, limit: int) -> list[SourcedPost]:
        with _ytdlp_client() as ydl:
            info = ydl.extract_info(
                f"ytsearch{_YOUTUBE_SEARCH_MAX_RESULTS}:{query}", download=False
            )
            # ignoreerrors=True leaves None placeholders for skipped entries.
            entries = [e for e in (info or {}).get("entries", []) if e and e.get("id")]

        posts: list[SourcedPost] = []
        videos_with_comments = 0
        for item in entries:
            if len(posts) >= limit:
                break
            video_id = item["id"]
            source_hint = (
                f"{item.get('channel') or item.get('uploader') or 'Unknown Channel'} · "
                f"{item.get('title') or 'Untitled'}"
            )
            video_url = f"https://www.youtube.com/watch?v={video_id}"

            comments = self._get_comments(video_id)
            if comments is None:
                continue  # comments disabled / removed / blocked — next video
            videos_with_comments += 1
            for c in comments:
                if len(posts) >= limit:
                    break
                text = (c.get("text") or "").strip()
                if not text:
                    continue
                cid = c.get("id")
                post_id = (
                    f"ytdlp_{cid}" if cid else f"ytdlp_{_short_hash('ytdlp', video_id, text)}"
                )
                posts.append(
                    SourcedPost(
                        id=post_id,
                        platform="youtube",
                        text=text,
                        source_hint=source_hint,
                        permalink=video_url,
                    )
                )

        if not posts and entries:
            # Either every video disabled comments, or this yt-dlp is too old to
            # support getcomments-as-option — an empty result can't tell them
            # apart, and silent corpus-weakening is the worst outcome. A run
            # with all-comments-disabled videos is normal; a stale yt-dlp is not.
            print(
                "[ytdlp] search found videos but collected zero comments — if all "
                "sampled videos genuinely disabled comments this is fine, but if "
                "suspicion falls on the install: `pip install -U yt-dlp` "
                "(getcomments-as-option needs a recent version).",
                flush=True,
            )
        return posts

    def _get_comments(self, video_id: str) -> list[dict] | None:
        """Comments for one video, or None when the video has none/blocked —
        None (not []) so the caller can tell "no comment section" from
        "crawled, genuinely empty", which the zero-posts warning depends on."""
        try:
            with _ytdlp_client(get_comments=True, max_comments=_YOUTUBE_COMMENTS_PER_VIDEO) as ydl:
                info = ydl.extract_info(
                    f"https://www.youtube.com/watch?v={video_id}", download=False
                )
        except Exception:  # noqa: BLE001 — one video's failure must not kill the search
            return None
        if not info or "comments" not in info:
            return None
        return info.get("comments") or []


def get_youtube_connector(settings: Settings) -> SourceConnector:
    if settings.youtube_provider == "ytdlp":
        # yt-dlp needs no credentials — this branch deliberately comes FIRST so
        # it wins even when YOUTUBE_API_KEY is absent (which is the whole point).
        return YouTubeDlpConnector(settings)
    if settings.has_youtube:
        return YouTubeConnector(settings)
    if settings.allow_stub_fallback:
        return StubYouTubeConnector()
    return NullSourceConnector()


# ── NITI Aayog district-indicator CSVs (repo /niti folder) ────────────────────
# A credential-free, REAL-data "source" the way yt-dlp is for YouTube: the two
# RUN00{676,677}_ALL_INDIA_CASEFILE_MATCHING.csv case files ship in the repo's
# /niti folder, one row per district (~776 rows), with a `state`, `district`,
# a `dropout_rate` headline column, and ~70 sparse numeric indicator columns.
#
# It implements the exact same SourceConnector.search(query, limit) protocol as
# Reddit/YouTube, so the graph treats it identically and no pipeline details
# leak in here. The connector-specific choices all live in this section:
#
#   - scoring:    query tokens get +5 per state-name word match, +7 per
#                 district-name word match, +4 per indicator column whose name
#                 the token matches (word-exact, or substring for tokens of
#                 length >= 3 so "dropout" hits "dropout_rate" but "in" hits
#                 nothing). A row with score 0 is never returned — the query
#                 must genuinely touch the data, which is also the honest gate
#                 a "relevance filter" would otherwise have to duplicate.
#   - diversity:  matched rows are interleaved ROUND-ROBIN across states (each
#                 state's best row first, states ordered by their top score) so
#                 the corpus always spans India instead of one dominant state,
#                 mirroring the pipeline's per-state fan-out guarantee.
#   - rendering:  a post's text is `District, State — indicator value; ...`,
#                 up to 3 indicators (matched columns first, the headline
#                 dropout_rate column as the fill), which the geo-resolver can
#                 place (district + state names are literally in the text) and
#                 a reader can quote as a real statistic.
#
# `platform` is "niti" so the frontend can label a curated statistics row
# differently from a web source ("research") or a social post — see schema.py's
# Platform literal, kept in sync with src/lib/worldview/types.ts.

_CSV_STOP_TOKENS = frozenset(
    {
        "the", "a", "an", "and", "or", "of", "for", "to", "with", "in", "on",
        "has", "have", "had", "is", "are", "was", "were", "be", "been", "this",
        "that", "these", "those", "there", "where", "what", "who", "how", "why",
        "which", "when", "do", "does", "did", "it", "its", "they", "them", "we",
        "you", "your", "how", "much", "many", "about", "should", "across",
    }
)

# Fill-in column shown when the query matched nothing else to quote: the
# dataset's headline statistic. Kept explicit (not "any column") because the
# ~70 indicator columns are sparse and most carry no meaningful headline value.
_CSV_HEADLINE_COLUMNS = ("dropout_rate",)


def _words(text: str) -> set[str]:
    """Lowercased alphanumeric word tokens (2+ chars, skips stopwords)."""
    return {
        w for w in re.findall(r"[a-z0-9]+", text.lower())
        if len(w) >= 2 and w not in _CSV_STOP_TOKENS
    }


def _to_number(value: str) -> float | None:
    s = (value or "").strip().replace(",", "")
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _format_value(value: float) -> str:
    """7.5 -> "7.5", 30.0 -> "30", 0.0 -> "0" — no floating-point artefacts."""
    return f"{value:.2f}".rstrip("0").rstrip(".")


def _value_unit(column: str) -> str:
    low = column.lower()
    if low == "dropout_rate" or "%" not in low and "percent" not in low:
        return "%"
    # The column name already carries the unit (e.g. "... (%)").
    return ""


def _title_case(name: str) -> str:
    return name.strip().title()


@dataclass
class _CsvRow:
    state_code: str  # e.g. "SIKKIM"
    district: str  # e.g. "gangtok"
    indicators: dict[str, float]  # column name -> value (only non-empty cells)


class _CsvCorpus:
    """In-memory index over every *.csv in the configured directory.

    Loaded once and cached per directory path (module-level) — the files are
    static and small (~1550 rows total), so per-request connector construction
    must not pay the parse cost. Determinism matters here (see sources.py's
    module docstring): iteration order comes from dicts/lists built in file
    and row order, never sets, so equal scores resolve identically across
    processes.
    """

    def __init__(self, dirpath: str):
        self.dirpath = dirpath
        self.rows: list[_CsvRow] = []
        self.state_tokens: dict[str, set[str]] = {}
        self.district_tokens: dict[str, set[str]] = {}
        self.column_tokens: dict[str, set[str]] = {}
        self.column_order: list[str] = []  # deterministic first-seen column order
        self.column_by_lower: dict[str, str] = {}
        self.source_hint = "NITI Aayog district indicators"
        self._load()

    def _load(self) -> None:
        try:
            entries = sorted(
                f for f in os.listdir(self.dirpath) if f.lower().endswith(".csv")
            )
        except OSError:
            return
        # The two shipped case files cover THE SAME districts (677 is a
        # column-superset of 676) — so the corpus MERGES per (state, district):
        # union of every file's indicator columns, later file winning on a
        # shared column. 776 rows, not 1552, and no duplicated district can
        # ever bloat a search's round-robin again. Iteration order is file
        # (sorted) then row order — repositories for state/district tokens and
        # column order are built from this same deterministic pass.
        merged: dict[tuple[str, str], dict[str, float]] = {}
        order: list[tuple[str, str]] = []
        for fname in entries:
            with open(
                os.path.join(self.dirpath, fname), newline="", encoding="utf-8-sig"
            ) as fh:
                for raw in csv.DictReader(fh):
                    state = (raw.get("state") or "").strip().upper()
                    district = (raw.get("district") or "").strip()
                    if not state or not district:
                        continue
                    key = (state, district)
                    if key not in merged:
                        merged[key] = {}
                        order.append(key)
                    indicators = merged[key]
                    for column, cell in raw.items():
                        if column in ("state", "district"):
                            continue
                        num = _to_number(cell)
                        if num is None:
                            continue
                        indicators[column] = num  # later file wins on overlap
                        if column not in self.column_by_lower:
                            self.column_by_lower[column.lower()] = column
                            self.column_order.append(column)
        for key in order:
            state, district = key
            self.rows.append(
                _CsvRow(state_code=state, district=district, indicators=merged[key])
            )
            self.state_tokens.setdefault(state, set()).update(_words(state))
            self.district_tokens.setdefault(district, set()).update(_words(district))
        for col in self.column_order:
            self.column_tokens[col] = set(_words(col))

    def best(self, tokens: list[str], limit: int) -> list[tuple[_CsvRow, list[str]]]:
        """Score every row against the token list, then round-robin across
        states to `limit`. Returns (row, matched_columns_in_score_order)."""
        rank: dict[int, int] = {}  # row index -> score
        matched_cols: dict[int, list[str]] = {}

        for tok in tokens:
            if len(tok) < 2 or tok in _CSV_STOP_TOKENS:
                continue
            # Columns this token touches, in deterministic first-seen order.
            col_hits: list[str] = []
            seen: set[str] = set()

            def add(orig: str) -> None:
                if orig not in seen:
                    seen.add(orig)
                    col_hits.append(orig)

            if len(tok) >= 3:
                for low, orig in self.column_by_lower.items():
                    if tok in low:
                        add(orig)
            for orig, tset in self.column_tokens.items():
                if tok in tset:
                    add(orig)

            for i, row in enumerate(self.rows):
                score = rank.get(i, 0)
                if tok in self.state_tokens.get(row.state_code, ()):
                    score += 5
                if tok in self.district_tokens.get(row.district, ()):
                    score += 7
                row_hits = [c for c in col_hits if c in row.indicators]
                if row_hits:
                    score += 4 * len(row_hits)
                    have = matched_cols.get(i, [])
                    matched_cols[i] = have + [c for c in row_hits if c not in have]
                rank[i] = score

        ranked = sorted(rank.items(), key=lambda kv: (-kv[1], kv[0]))
        by_state: dict[str, list[tuple[int, list[str]]]] = {}
        for i, score in ranked:
            if score <= 0:
                break  # ranked desc — everything left scores 0 too (no token touched it)
            by_state.setdefault(self.rows[i].state_code, []).append((i, matched_cols.get(i, [])))

        # Round-robin: each state contributes its best remaining row before any
        # state gets a second; states lead with their best-scoring row.
        pools = [list(v) for v in by_state.values()]
        pools.sort(key=lambda pool: -rank[pool[0][0]])

        chosen: list[tuple[_CsvRow, list[str]]] = []
        while pools and len(chosen) < limit:
            advanced = False
            for pool in pools:
                if not pool:
                    continue
                i, cols = pool.pop(0)
                chosen.append((self.rows[i], cols))
                advanced = True
                if len(chosen) >= limit:
                    break
            if not advanced:
                break
        return chosen


_corpus_cache: dict[str, _CsvCorpus] = {}


def _get_corpus(dirpath: str) -> _CsvCorpus | None:
    if not os.path.isdir(dirpath):
        return None
    if dirpath not in _corpus_cache:
        _corpus_cache[dirpath] = _CsvCorpus(dirpath)
    return _corpus_cache[dirpath]


def get_niti_connector(settings: Settings) -> SourceConnector:
    if settings.has_niti_csv:
        return NitiCsvConnector(settings)
    # Deliberately no stub: fabricating government statistics would be worse
    # than nothing. Absent data => this source contributes zero posts.
    return NullSourceConnector()


class NitiCsvConnector:
    """Real district-level NITI indicator data over the SourceConnector seam —
    see the section comment above the corpus classes for scoring, round-robin
    spread, and text rendering. Posts carry platform "niti"."""

    def __init__(self, settings: Settings):
        self.dirpath = settings.niti_csv_dir()
        self._corpus = _get_corpus(self.dirpath)

    async def search(self, query: str, limit: int) -> list[SourcedPost]:
        corpus = self._corpus
        if corpus is None or not corpus.rows:
            return []
        tokens = re.findall(r"[a-z0-9]+", query.lower())
        if not tokens:
            return []
        chosen = corpus.best(tokens, max(limit, 1))
        posts: list[SourcedPost] = []
        for row, cols in chosen[:limit]:
            posts.append(
                SourcedPost(
                    id=f"niti_{_short_hash(row.state_code, row.district)}",
                    platform="niti",
                    text=self._render(corpus, row, cols),
                    source_hint=corpus.source_hint,
                    permalink=None,
                )
            )
        return posts

    @staticmethod
    def _render(corpus: _CsvCorpus, row: _CsvRow, matched: list[str]) -> str:
        shown: list[str] = matched[:3]
        for col in _CSV_HEADLINE_COLUMNS:
            if len(shown) >= 3:
                break
            if col in row.indicators and col not in shown:
                shown.append(col)
        bits = [
            f"{col} {_format_value(row.indicators[col])}{_value_unit(col)}" for col in shown
        ]
        parts = "; ".join(bits) if bits else "no indicator values"
        return f"{_title_case(row.district)}, {_title_case(row.state_code)} — {parts}"
