# Worldview Explorer — collector-agent backend

A real Python/LangGraph service that replaces the frontend's hardcoded mock: it
sources Reddit/YouTube posts about a topic, resolves each post's Indian
district, clusters posts into distinct viewpoints, extracts the "point of
deflection" between co-occurring viewpoints, and synthesizes a consolidated
answer — streamed to the frontend as Server-Sent Events matching the exact
`WorldviewEvent` schema in `../src/lib/worldview/types.ts`.

## Real-data-only by default

Every external call (Reddit, YouTube, the LLM) has a deterministic **stub**
implementation, but **stub fallback is OFF by default** (`ALLOW_STUB_FALLBACK=false`).
That means: a source with no credentials is simply **skipped** — it
contributes zero posts rather than fabricating fixture data — and a missing
`OPENAI_API_KEY` **fails the run outright** with a clear error, since the LLM
drives clustering/resolution/synthesis and isn't optional the way a data
source is. Add credentials to `.env` one at a time to bring each source online
(`Settings.has_reddit` / `has_youtube` / `has_llm`), no code changes needed.
Set `ALLOW_STUB_FALLBACK=true` to restore the old zero-credential offline-demo
behavior for local testing.

## Balanced multi-state sourcing ("reasoning level")

Rather than one flat keyword search, the sourcing stage explicitly surveys a
set of Indian states — every surveyed state gets an **equal** post budget, so
the corpus is a deliberate cross-India sample of viewpoints instead of one
skewed toward whichever region happens to be most active online. The
frontend's reasoning-level slider (1–5) sets how many states get surveyed,
region-interleaved (see `data/subreddit_map.py`'s `STATE_PRIORITY_ORDER`) so
even level 1 spans multiple regions, not just alphabetically-first states:

| Level | States surveyed | Approx. YouTube quota cost* |
| ----- | ---------------- | ---------------------------- |
| 1 (Quick)      | 4  | 400 units  |
| 2 (Balanced)   | 8  | 800 units  |
| 3 (Thorough)   | 12 | 1,200 units |
| 4 (Deep)       | 16 | 1,600 units |
| 5 (Exhaustive) | 20 | 2,000 units |

\* `search.list` costs 100 units/call against YouTube's 10,000-unit daily free
quota — even the highest level leaves room for several runs/day. Tune
`_LEVEL_STATE_COUNTS` / `_PER_STATE_LIMIT` in `graph/build.py` if you need
different limits (and keep the frontend's `REASONING_LEVELS` table in
`QueryBar.tsx` in sync — it's descriptive only, not read from the backend).

Reddit is targeted directly at each state's subreddit (a real geographic
signal — see `STATE_SUBREDDIT` in `data/subreddit_map.py`). YouTube has no
per-state search filter, so the query itself is augmented with the state's
name to improve *recall* of state-relevant content — that augmentation does
NOT itself certify a post's origin; `resolve_district`'s hierarchy is still
the sole source of truth for where a post actually resolves.

### YouTube via yt-dlp (default, no quota)

yt-dlp scraping is now the default YouTube source (since 2026-09-06). It needs
`pip install yt-dlp` and no API key, has no 10k/day quota, and reply threads
are included (the API path only gets top-level comments). Costs: ~5-7s per
search and per video-comment crawl (vs sub-second API calls), no native
`regionCode="IN"` geo-filter (relies on the per-state query-suffixing above),
and scraping YouTube's public endpoints is ToS-gray — fine for this internal
tool, a real concern before any public deployment. An exhaustive (`extrahigh`)
run's sourcing stage is slow (~6 min measured) — see `decisions.md` (2026-09-06)
for the speedup plan. The Data API path is kept as an opt-in fallback: set
`YOUTUBE_PROVIDER=api` (and a `YOUTUBE_API_KEY`) to return to it.

## Substance-aware sourcing (`suggest_framings`)

A bare keyword search mostly surfaces generic reactions/opinions, not content
that explains *why* regions differ — searching just "Diwali" rarely turns up
a comment that says "we celebrate Rama's return to Ayodhya." Before sourcing,
`LLMClient.suggest_framings(query, max_count)` asks the LLM for the topic's
well-known distinct regional/cultural/religious framings (e.g. for "Diwali":
Rama's return to Ayodhya, Krishna defeating Narakasura, Kali Puja in Bengal,
Lakshmi puja in Gujarat, Bandi Chhor Divas for Sikhs, Mahavira's nirvana for
Jains) — empty if the topic has none. `source_posts` then cycles these
framings across the surveyed (state, platform) slots instead of always
searching the bare query, so the corpus actually contains content that
articulates the real variation, which clustering can then separate into
genuinely distinct viewpoints.

The same framings are threaded through to `synthesize_answer` (via
`state["framings"]`) so the final answer can name real regional/religious
substance directly (the specific deity/story/event) instead of hedging with
vague language like "various deities" — but only where a cluster's actual
label/summary supports it; the prompt explicitly forbids introducing a known
framing with no corresponding cluster just to sound authoritative.

Because this runs against live, non-deterministic YouTube search results,
which specific framings surface a strong cluster **varies run to run** —
don't expect every known framing to appear in every single run, especially at
lower reasoning levels or before Reddit is configured (Reddit's subreddit-
scoped search is a stronger substance signal than YouTube's augmented
keyword search once it's live).

## Setup

```sh
cd backend
uv venv .venv --python 3.13        # or: python3 -m venv .venv
source .venv/bin/activate
uv pip install -r requirements.txt  # or: pip install -r requirements.txt
cp .env.example .env                # optional — fill in credentials to go live

# Rebuild the district gazetteer if you ever replace ../public/geo/india-districts.geojson
# (already committed and up to date — you don't need to run this on a fresh clone)
python -m app.data.build_gazetteer

uvicorn app.main:app --reload --port 8001
```

Check it's alive: `curl http://localhost:8001/healthz` — reports which
credentials (if any) are configured.

Test the stream directly:

```sh
curl -N "http://localhost:8001/api/worldview/stream?q=Diwali&depth=1"
```

## Point the frontend at it

In `../` (the frontend), create `.env.local`:

```
VITE_WORLDVIEW_STREAM=sse
VITE_WORLDVIEW_API_URL=http://localhost:8001/api/worldview/stream
```

Restart `npm run dev` and press Explore — the map should build from this
backend's real (or stubbed) output instead of the offline demo.

## Architecture

```
app/
  schema.py            — Pydantic mirror of the frontend's WorldviewEvent union (the wire contract)
  config.py             — env-driven Settings; has_llm/has_reddit/has_youtube flags
  main.py                — FastAPI app; GET /api/worldview/stream (SSE gateway)
  graph/
    state.py              — PipelineState (LangGraph shared state) + EmitFn
    build.py                — balanced multi-state source_posts + wires
                               source -> cluster -> resolve -> deflect -> synthesize
    nodes/
      cluster_viewpoints.py   — embeds + clusters posts (KMeans, run CONCURRENTLY per
                                  cluster), labels via LLM
      resolve_district.py      — hierarchical resolver (posts resolved CONCURRENTLY per
                                   batch): city-subreddit -> place NER -> script/language
                                   -> LLM geolocation -> state/unresolved fallback
      deflection_and_synthesis.py — extract_deflections + synthesize_answer
  connectors/
    base.py                — SourceConnector / LLMClient Protocols (the frozen interfaces)
    sources.py               — Reddit + YouTube: Stub*Connector, NullSourceConnector
                                (credentials absent + stub fallback off), real
                                (PRAW / googleapiclient — fresh client per call, see below)
    llm.py                    — StubLLMClient + OpenAILLMClient (explicit 20s timeout)
  data/
    build_gazetteer.py        — derives district_gazetteer.json from the FRONTEND's own GeoJSON
    district_gazetteer.json    — committed; district/state name -> districtId lookup
    subreddit_map.py            — city/state/pan-India subreddit -> district_id lookup,
                                    plus STATE_SUBREDDIT + STATE_PRIORITY_ORDER for
                                    balanced multi-state sourcing
    language_regions.py          — Unicode-script heuristic -> likely state
```

**Concurrency and thread-safety.** Real per-post/per-cluster/per-state LLM and
API calls run concurrently (`asyncio.gather` / `asyncio.as_completed`) rather
than one-after-another — this was the difference between a run finishing in
~60s and one stalling well past a minute. One real gotcha this surfaced:
PRAW and `googleapiclient`'s `httplib2` transport are **not** safe to share
across threads — caching a single client instance and hitting it from many
concurrent `asyncio.to_thread` calls (one per state) produced corrupted
connections (garbled SSL/socket errors). Both `RedditConnector` and
`YouTubeConnector` now construct a fresh, cheap (no network call) client
per call instead of caching one on `self`.

**Why clustering runs before district resolution.** The frontend's
`district_resolved` event requires a `clusterId` — so this graph clusters
first (assigning every post a `cluster_id`), then resolution just aggregates
volume per `(district, cluster)`, matching the wire contract exactly. This is
the one place the implementation order differs from the plain-language spec
("source → resolve → cluster → deflect → synthesize"); the *data* ends up
identical, only the *order of computation* changes to satisfy the schema.

**Confidence tiers.** `city_subreddit` (highest) → `place_ner` →
`script_language` → `llm_geolocation` → `state_fallback` / `unresolved`
(lowest), mirroring `ResolutionMethod` in the frontend types exactly.

**Extending the stub content.** The Reddit/YouTube stubs generate templated,
hash-seeded (never random) posts across several "framing" archetypes so
clustering has genuine signal to work with — see `FRAMINGS` in
`connectors/sources.py`. Add more templates there for richer demo variety.

## Known limitations of this first pass

- Clustering uses `sklearn.cluster.KMeans` with a heuristic `k` — good enough
  to produce a handful of distinct viewpoints, not a production-tuned
  clustering pipeline (no silhouette-based k selection, no re-clustering as
  more data streams in).
- `synthesize_answer` calls the LLM once and then re-emits its segments with a
  short delay between each — not true token-level streaming. Wiring the
  OpenAI client's native streaming API through to `answer_chunk` events is a
  natural next step.
- No caching/rate-limit backoff around the real Reddit/YouTube/OpenAI calls
  yet — add before pointing this at production traffic.
