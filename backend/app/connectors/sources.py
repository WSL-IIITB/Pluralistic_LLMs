"""
Source connectors: Reddit and YouTube.

Each platform gets a `Stub*` implementation (deterministic fixture data, zero
external calls or credentials) and a real implementation gated by
`config.Settings.has_reddit` / `has_youtube`. `get_reddit_connector()` /
`get_youtube_connector()` pick the right one automatically — nodes in the
graph should call those factories rather than instantiating a class directly.

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
import hashlib
import random
import re

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


def get_youtube_connector(settings: Settings) -> SourceConnector:
    if settings.has_youtube:
        return YouTubeConnector(settings)
    if settings.allow_stub_fallback:
        return StubYouTubeConnector()
    return NullSourceConnector()
