# Project Context — Living Record

> Read this first every session. Updated incrementally as changes happen.

## Current Branch
- `dev/saketh` (off `dashboard-main`)

## What's Done
- **Installed dependencies** via `npm install` (only tracked file change: `package-lock.json` gained a nested `nitro/node_modules/lru-cache` entry — no manual package.json edits).
- **Frontend dev server running locally**: `npm run dev` (`vite dev` under `cmd.exe`; PID 5748) from the repo root, serving the app at http://localhost:8080 (Vite + TanStack Start SSR — verified responding 200 with the real "Pluralistic India — Worldview Explorer" page, dev-mode SSR output).
- **App currently runs in offline mock mode**: `src/lib/worldview/stream/config.ts` is unmodified, `DEFAULT_SOURCE` still `"mock"` — the Diwali demo plays without backend or API keys. Backend (`backend/`, Python/FastAPI) and `proxy/` (Cloudflare Worker) are **not** running and were not needed.

## In Progress
- **yt-dlp integration (assigned task):** **`YouTubeDlpConnector` IMPLEMENTED + VALIDATED live** (2026-09-06). All-yt-dlp (search + comments), no hybrid. Details below. **Full-pipeline latency measurement IN PROGRESS** — the backend venv is not the blocker it first looked like (see below); sourcing-stage wall-clock is being measured directly. **Awaiting an LLM key** for the true full end-to-end run (research/cluster/synthesize stages need OPENAI_API_KEY or an Azure/gemma endpoint — none configured on this machine; system can't run those stages without one).
- **Code changes (backend):** new `YouTubeDlpConnector` in `backend/app/connectors/sources.py` (`ytsearchN:{query}` for search + per-video `getcomments` crawl), selected by `Settings.youtube_provider` (config.py; **default is now `"ytdlp"`** since 2026-09-06, per user decision — flipped from `"api"`, see decisions.md). Factory `get_youtube_connector()` branches to it FIRST (yt-dlp needs no credentials). Zero LangGraph/pipeline changes — the `SourceConnector` protocol is untouched. Also: `requirements.txt` += `yt-dlp>=2026.1.1`; `.env.example` (`YOUTUBE_PROVIDER=ytdlp` default + comment) + README ("optional" → "default" subsection) updated; healthz reports `youtube_provider`. `YOUTUBE_PROVIDER=api` + `YOUTUBE_API_KEY` returns to the Data API path unchanged.
- **Validation (live, via `scripts/validate_ytdlp_connector.py` through the REAL connector object):** `Diwali` limit=150 → 150 posts; `Diwali Kerala` limit=60 → 60 posts (Oneindia regional explainer — the per-state suffix works); long policy query limit=60 → 22 posts across **8 videos**. All posts have correct `SourcedPost` shape, id prefix `ytdlp_`, `platform=youtube`.
- **Implementation findings (re-verify on any yt-dlp upgrade):** `getcomments` is a YoutubeDL constructor **option** on 2026.08.x, not an `extract_info()` kwarg (TypeError otherwise); a single dead entry in a ytsearch playlist ABORTS the whole `extract_info` unless `ignoreerrors: True` (and skipped entries become `None` in the entries list — must filter); ~5/25 live "Diwali" search hits came back "video not available" (anonymous-scrape tolerance) — `ignoreerrors` absorbs them; the pipeline's downstream `_filter_by_relevance` should still drop non-English comments (one Arabic comment came through).
- **Open trade-offs, still to characterize in a full-pipeline run:** (a) latency — ~5-7s per search and per video-crawl through the 6-wide semaphore, vs the API's sub-second calls; (b) per-search diversity — limit=150 filled from only **2 videos** (100-comment cap fills fast), narrower than the API path's spread across many videos; (c) no `regionCode` — relies on per-state query-suffixing.
- **Scipts (untracked, dev tools):** `scripts/smoke_ytdlp.py` (raw yt-dlp capability test) + `scripts/validate_ytdlp_connector.py` (through the real connector) in venv `scripts/.smoke-venv/` (also has pydantic/praw/google-api-python-client for importing the connector). **NEW (2026-09-06): `scripts/measure_ytdlp_sourcing.py`** runs the REAL `source_posts` node (graph/build.py) with the real `YouTubeDlpConnector` at each mode's real fan-out shape (framing searches + extrahigh's 32 per-state searches), timed, with per-mode video-diversity stats. Uses a tiny inline stub LLM (`_MeasureLLM`: realistic framings + keep-all relevance) because no LLM endpoint is configured — the LLM stages aren't part of the yt-dlp timing question.
- **Sourcing wall-clock measured (Diwali, 2026-09-06, real runs via `scripts/measure_ytdlp_sourcing.py` through the real `source_posts` node):** basic (3 framings) = **49 posts / 7 videos / 66.9s**; medium (5 framings) = **210 posts / 6 videos / 55.2s**; high (8 framings) = **848 posts / 24 videos / 121.1s**; extrahigh (10 framings + 32 per-state) = **1427 posts / 70 videos / 374.0s**. Raw collected before low-signal drops was higher (high dropped 352, extrahigh dropped 521 low-signal posts). Findings: (a) wall-clock is dominated by comment-crawl + dead-video retry tax (`ERROR: video not available` with up to 2 auto-retries each); ~6-7s per bare ytsearch but 15-30s+ per call once crawls+retries stack; (b) 30-35% of harvested comments are low-signal (<4 Unicode words — "Happy diwali", emoji-only) and dropped by `_is_low_signal` before clustering; (c) same dead video IDs (SKCisZeb300, vfEGIrMexaI, -YSN5qICTog, 74LTtXAlT2o, V6PLvRW-szQ, XXCOa6KnBns, …) recur across different framing searches — a per-run seen-set would stop re-crawling them; (d) DIVERSITY is better at full fan-out than single-search validation suggested — 70 distinct videos / 20 posts-per-video mean at extrahigh; the "2-videos" concern applies mostly to shallow/basic runs; (e) extrahigh at 374s Sourcing alone is the clear bottleneck, and it's mostly throwaway crawl work — the two candidate fixes are max_comments=50 and a per-run dead-ID seen-set. Timing EXCLUDES the per-post relevance LLM pass + all LLM stages (research/cluster/synthesize), which add their own wall-clock regardless of connector.
- **Remaining work if the full run is green:** decide whether to keep `YOUTUBE_PROVIDER=ytdlp` as the repo's default, run a basic-mode pass, then extrahigh to measure wall-clock. The app itself still demos fine on :8080 in mock mode (untouched).
- **Next action (2026-09-07 call):** Report status on the call (summary page `ytdlp-trial.html` made for it) — the sourcing latency question is now answered (numbers just above). **Proposed follow-up work (awaiting go-ahead):** (a) apply the two extrahigh speedups — `max_comments` 100→50 in `_ytdlp_client` (halves crawl time, pipeline drops most of the second 50 anyway) and a per-run seen-set of dead/skipped video IDs to stop re-crawling across framings — then re-measure; (b) a TRUE full end-to-end pass needs an LLM backend — install the full backend venv (torch/chromadb/sentence-transformers) and provide `OPENAI_API_KEY` or an Azure/gemma endpoint via `backend/.env` (none exists yet), then run one real question through `GET /api/worldview/stream` with `YOUTUBE_PROVIDER=ytdlp` to time the LLM stages too and confirm total wall-clock at basic → extrahigh; (c) decide whether yt-dlp becomes the repo default (`YOUTUBE_PROVIDER`), likely keep API as the default until (a)+(b) close.

## Server Status (2026-09-22)
- **Dev server RUNNING again**: Vite v8.2.0 serving the app at http://localhost:8080 (HTTP 200, real "Pluralistic India — Worldview Explorer" SSR page, 29.9 KB). Same as before: frontend only, **mock mode** (`DEFAULT_SOURCE="mock"`), no backend/API keys needed.
- **Blocked once, fixed by sideloading Node 22**: the repo's Vite 8 / rolldown crashes on the machine's global Node **v20.10.0** (`SyntaxError: node:util has no export 'styleText'` — styleText is Node 22+; ALSO note Node 20.10.0 is below vite 8's floor). Fix: portable **Node v22.23.2 LTS** (npm 10.9.8) extracted to `%LOCALAPPDATA%\Programs\Node22\node-v22.23.2\` — global Node 20 untouched.
- **Correct start command (important)**: `npm run dev` FAILS even with the portable Node because `npm.cmd` shims resolve the GLOBAL node 20 (the launched vite then crashes). Must run vite under the portable node directly: `"C:/Users/saket/AppData/Local/Programs/Node22/node-v22.23.2/node.exe" node_modules/vite/bin/vite.js dev` from the repo root. Background task id for this session's run: bjpmdrale.
- **README.md "Quick start" REWRITTEN (2026-09-22)**: now step-by-step (install deps → start with portable-node command → open :8080 → stop with Ctrl+C), including the Node-22 prereq and the warning that plain `npm run dev` re-resolves global Node 20 and crashes. The "Scripts" section's `npm run dev` line got the same caveat. This is the user-facing reference for starting the project next time.

## LIVE-DATA WORK (NITI CSVs through the backend) — 2026-09-22
- **Goal (user-approved):** search the REAL /niti CSVs instead of the pre-recorded mock, via a FastAPI endpoint that streams the full worldview answer; also flip the app itself to live. End goal: same design must let YouTube/Reddit be swapped in later with minimal code change.
- **Backend implementation COMPLETE (all files compile clean):**
  - `connectors/sources.py`: new `NitiCsvConnector` (+ `_CsvCorpus`, module-level corpus cache, `get_niti_connector`) implementing the SAME `SourceConnector.search(query, limit)` Protocol as Reddit/YouTube — zero graph-level coupling. Keyword-overlap scoring (state +5/district +7/indicator-column +4 per token), state ROUND-ROBIN result interleaving, `platform="niti"`, `id="niti_<hash>"`, text rendered `"District, State — indicator value..."`. Deliberately NO stub (fabricating gov stats would be worse than nothing) → missing folder = NullSourceConnector (zero posts).
  - `config.py`: `csv_data_dir` field (default `REPO_ROOT/niti`), `niti_csv_dir()`, `has_niti_csv`. `main.py` healthz now reports `has_niti_csv`.
  - `graph/build.py`: `csv` connector threaded through `source_posts` + `build_graph` (new `fetch_csv(framing)` per-framing closure in the gather). NEW `_STRUCTURED_SOURCE_PLATFORMS={"research","niti"}` — these skip the per-post relevance gate (a stub/failing LLM fails CLOSED → would otherwise wipe the real CSV rows).
  - **CORPUS FACT (verified by probe, 2026-09-22):** the two /niti files (RUN00676: 71 cols, RUN00677: 81 cols) cover the EXACT same 776 (state,district) rows — 677 is a pure column-superset. So `_CsvCorpus` MERGES per district (union of columns, later file wins on conflicts) → 776 rows, not 1552, no duplicated district can bloat a search. Smoke test (`scripts/smoke_niti_connector.py`, run via the smoke venv) passes: `dropout rate in kerala` → 20 posts/20 states (round-robin), `diwali` → 0 posts (honest empty), deterministic.
  - `reasoning_modes.py`: `CSV_POSTS_PER_FRAMING_CAP` (25/60/150/150).
  - Platform literal extended `"niti"` in `schema.py`, `base.py`, `state.py`, and frontend `src/lib/worldview/types.ts` (SamplePost.platform) — kept in manual sync.
- **LLM provider decision:** `gemma_remote` (the FRONTEND's default provider) now degrades to `StubLLMClient` when `REMOTE_GEMMA_BASE_URL` is unset AND `ALLOW_STUB_FALLBACK=true` (see `get_llm_client`, decisions.md). StubLLMClient implements every pipeline method — full graph runs deterministically (research returns empty, embed is hash-based).
- **Env files created:** `backend/.env` (`ALLOW_STUB_FALLBACK=true` + commented Gemini key config); repo-root `.env.local` (`VITE_WORLDVIEW_STREAM=sse`, `VITE_WORLDVIEW_API_URL=http://localhost:8001/api/worldview/stream`) — flips the APP to live (needs a vite restart to take effect). `backend/.env.example` gained the Gemini-as-gemma_remote + CSV_DIR sections.
- **Backend venv `backend/.venv` — CREATED, INSTALLING ITS LIGHT CORE (task b6gj3dw1j, background):** installed WITHOUT the heavy stack (`torch`/`sentence-transformers`/`chromadb`) — confirmed via grep those imports are function-local/lazy, and stub-mode never calls them (embed is hash-based). Included: fastapi, uvicorn[standard], sse-starlette, pydantic, pydantic-settings, langgraph, openai, anthropic, httpx, praw, google-api-python-client, yt-dlp, numpy, scipy, scikit-learn, openpyxl. Machine's only Python is 3.10.11 (Store build).
- **NEXT (once install finishes):** start uvicorn on :8001 (task will be in this section), restart vite so `.env.local` takes effect, then hit `GET http://localhost:8001/api/worldview/stream?q=high+school+dropouts+kerala&mode=basic` and confirm a full SSE run over real CSV rows (sourcing ticker → clusters → answer). Then same query through the app UI at :8080.

## What's Broken / Known Issues
_Nothing yet._

## What to Avoid
- Don't force-push or rewrite history on `main` or `dashboard-main` (Lovable-connected).

## Decisions Made
_None yet._

## FINAL — end-to-end verification 2026-09-22 (NITI live-data milestone CLOSED)
- **Both servers running (final):** uvicorn on :8001 (task b21uu4h1e, debug blocks REMOVED from build.py — verified no `TEMP DEBUG` remnants; `counts_from_state` intact), vite dev on :8080 restarted live (task b4nrlowys) — served module confirms `import.meta.env` now carries `VITE_WORLDVIEW_STREAM:"sse"` and `VITE_WORLDVIEW_API_URL:"http://localhost:8001/api/worldview/stream"`, so `STREAM_SOURCE === "sse"` (was mock).
- **Final query verification (stub LLM, real CSV):** `q=dropout&mode=basic` and `q=high school dropouts in kerala&mode=basic` both complete: **kept 25/25 niti posts** (the cap; was 18 before the low-signal fix), 15 districts resolved, 4 clusters, 3 deflections, full consolidated answer, `done` event. postsCollected=50 in done counts is a pre-existing CUMULATIVE counter = 25 sourced + 25 resolved (`resolve_district.py:319/400` does `state["posts_collected"] += len(batch)`) — NOT a sourcing count; debug counter confirmed exactly 25 entered clustering.
- **Day's fix (the "18 vs 25" bug):** short-district-name CSV rows (e.g. `Delhi, Delhi — dropout_rate 8.9%`) tokenized to <4 words under `_is_low_signal` (numbers split into single-digit tokens, not counted) and were dropped as noise. Structured platforms now bypass the low-signal gate too — see decisions.md.
- **2026-09-22 (later same day): latency fix.** The user's first live UI query (`mode=medium`) took ~50s. Cause: live anonymous yt-dlp crawls per framing, whose results the stub LLM's fail-closed relevance judge deterministically drops (0 social kept) — pure throwaway work. FIXED: `source_posts` now skips the ENTIRE social fan-out (reddit + yt framing crawls + extrahigh per-state yt) when `isinstance(llm, StubLLMClient)` — CSV-only sourcing. Same medium query now: **0.82s**, 17 districts / 6 clusters / 6 deflections / full answer. Real LLM configured → stub gone → crawl returns. See decisions.md. Uvicorn task now **bdcm18w2k**; vite still **b4nrlowys**.
- **Remaining (user-facing, not code):** open http://localhost:8080 in a browser and type a policy query to SEE the live pipeline stream (curl-level proof done). Optional: add a Gemini key to `backend/.env` (REMOTE_GEMMA_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai/ + key) and set `ALLOW_STUB_FALLBACK=false` for real reasoning. Add `YOUTUBE_API_KEY` later e.g. `YOUTUBE_PROVIDER=api` to include real YouTube too. Kill servers: TaskStop b4nrlowys + bdcm18w2k (or Ctrl+C in their shells).

## HOW A QUERY BECOMES AN ANSWER (plain-language, kept for future sessions)

### The data
The /niti CSVs are a table of **776 rows — one per Indian district**, with indicator
columns (dropout_rate, internet access %, girls 10+ yrs schooling, ...). Each backend run
uses these rows as "posts": a post = one rendered district row, shaped so the rest of the
pipeline (built for Reddit/YouTube text) can't tell the difference:
`Alappuzha, Kerala — dropout_rate 2.1%`.

### Sourcing (step 1 of the pipeline)
- **Keyword match:** query words are scored against each row's district name (+7),
  state name (+5), and indicator-column names (+4). Matching rows rank by score; rows with
  zero matches are skipped (unrelated queries get an honest empty answer).
- **Round-robin across states:** instead of returning the N highest-scoring rows (which for
  "dropouts in kerala" would all pile into one state), it takes best-in-Kerala → best-in-Maharashtra
  → best-in-UP → ... → 2nd-best-in-Kerala → ... until it reaches the cap. The map therefore
  always spans many states and shows *where* an issue is worse, not one blob.
- **Per-mode caps:** basic=25, medium=60, high=150, extrahigh=150 rows per framing search.
- **Under the stub LLM the social crawl (reddit/youtube) is skipped entirely** — the stub's
  fail-closed relevance judge drops every social post, so crawling is pure wall-clock waste.

### End-to-end flow (what the user sees, in order)
1. Type query + Explore → frontend opens SSE to GET :8001/api/worldview/stream?q=&mode=&provider=.
   provider=gemma_remote with no key → run gets a StubLLMClient (deterministic stand-in).
2. **Sourcing** — 60 real CSV rows (ticker: "Surveying 32 states..." → "Collected 60 posts...").
3. **Research** — web research per angle; stub returns 0 sources ("Gathered 0 sources..."). A real
   key populates this.
4. **Clustering** — groups rows into 6 viewpoints → 6 colored map columns + legend entries.
5. **District resolution** — each row's district/state parsed → 3D columns at real map locations.
6. **Deflection** — divergence between co-occurring viewpoints → arcs + panel.
7. **Synthesis** — streamed consolidated answer (TD;DR → recommendations) → done event.
   Real run output: 71 SSE events, ~0.8s: 17 districts / 6 clusters / 6 deflections / full answer.

### What a real LLM key changes
- Research fills with real web sources; sourcing **stops skipping YouTube/Reddit**, whose posts
  now survive the relevance judge. Those runs take ~30-60s again (time well spent — real social
  voices appear on the map). CSV rows themselves are always instant.
