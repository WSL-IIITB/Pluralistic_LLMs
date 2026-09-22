# Pluralistic India — Worldview Explorer

A dark, cartographic "data-instrument" dashboard that shows how different regions of
India hold different viewpoints on a shared topic. Enter a topic and a backend agent
graph (LangGraph) streams results in real time: it sources social-media posts (Reddit +
YouTube), resolves each to an Indian **district**, clusters the posts into distinct
**viewpoints**, extracts the **point of deflection** between co-occurring viewpoints, and
synthesizes an all-views-inclusive **consolidated answer**. The map builds progressively
as each stage streams in.

This repo started as a static UI shell (built in Lovable) and is now the real, functional
product: a live 3D map, a typed streaming layer, and fully wired panels. It ships with a
self-contained **offline mock run** so the whole thing is demoable with no backend, no
Mapbox token, and no external data.

> Preserve the visual language when editing: dark theme, floating glass panels
> (`panel-surface`), small uppercase labels (`label-micro`), warm categorical data palette
> (`--cluster-1..6`), cool-neutral chrome.

## Quick start

The dashboard runs fully offline (mock mode) — no backend, no Mapbox token, no API keys
needed to see it working.

**Prereq — Node 22+.** The frontend builds on Vite 8 (rolldown), which requires **Node ≥ 22**.
The global Node installed on this machine is **v20.10.0 and will crash `vite dev`** with
`SyntaxError: node:util does not provide 'styleText'`, so a **portable Node v22.23.2 LTS**
(global Node untouched) is sideloaded here:

```
%LOCALAPPDATA%\Programs\Node22\node-v22.23.2\    ← node.exe + npm 10.9.8
```

On a fresh machine, download the latest v22.x LTS `win-x64` zip from nodejs.org, extract it
anywhere, and use that folder's `node.exe` the same way.

1. **Install dependencies** (first time only, from the repo root):
   ```sh
   npm install
   ```
2. **Start the dev server** — pointed at the portable Node, **not** plain `npm run dev`:
   ```sh
   "C:/Users/saket/AppData/Local/Programs/Node22/node-v22.23.2/node.exe" node_modules/vite/bin/vite.js dev
   ```
   (Plain `npm run dev` re-resolves the global Node 20 through npm's `npm.cmd` shim and the
   build dies immediately. On a machine where Node 22+ is the global `node`, `npm run dev`
   works as written.)
3. **Open the dashboard** at http://localhost:8080 — the offline **Diwali** demo plays
   automatically. Type a topic and press **Explore** to run again; type a policy-style
   question (e.g. _"high-school dropouts: where should government intervene?"_) to see the
   **policy** answer mode.
4. **Stop it** with `Ctrl+C` in the terminal that runs the server.

> All of the above runs the mock. To swap in the real backend pipeline it's still a one-line
> flip — see the "Backend stream" plug point below.

## Wiring it to real data — the plug points

Everything runs offline by default. There are exactly three seams to make it live:

### 1. Mapbox basemap (optional) — `VITE_MAPBOX_TOKEN`

Set a token in `.env` (see `.env.example`) to render a Mapbox **dark** basemap _under_ the
deck.gl columns. **Without a token the map still works** — deck.gl draws the districts and
columns on the dark canvas alone. The token is read in
[`WorldviewMap.tsx`](src/components/dashboard/map/WorldviewMap.tsx) (`readMapboxToken`) and
passed to `react-map-gl` in [`DeckMap.tsx`](src/components/dashboard/map/DeckMap.tsx).

### 2. District boundaries — `public/geo/india-districts.geojson`

A simplified Census-2011 district GeoJSON (760 districts, ~0.5 MB) ships in
[`public/geo/`](public/geo/). To use official Survey of India / Datameet boundaries, drop
in a replacement whose feature properties expose `st_code`, `dt_code`, `st_nm`, `district`
(LGD/Census codes) — **no code changes needed**. The typed loader
([`geo/districts.ts`](src/lib/worldview/geo/districts.ts)) recomputes centroids/bboxes on
load and keys each district as `${st_code}-${dt_code}`. If the file is missing, the map
degrades to the backdrop and the rest of the dashboard keeps working. See
[`public/geo/README.md`](public/geo/README.md).

After replacing the district file, regenerate the dissolved state-boundary layer (the bold,
always-visible state borders + solid landmass backing that keep the map reading as one
continuous piece rather than a translucent patchwork of district polygons):

```sh
node scripts/build-state-boundaries.mjs
```

This runs `turf.union` once, offline, per state and writes `public/geo/india-states.geojson`
(~80 KB). It's purely additive — `turf` is a devDependency only (never shipped to the
client), and if this file is absent the map still works, just without the dedicated
state-border/backing layers ([`geo/states.ts`](src/lib/worldview/geo/states.ts)).

### 3. Backend stream — `src/lib/worldview/stream/config.ts`

Flip **one line** to go from mock to a real backend:

```ts
// stream/config.ts
const DEFAULT_SOURCE: SourceKind = "mock"; // change to "sse"
```

…or set env vars without editing code: `VITE_WORLDVIEW_STREAM=sse` and
`VITE_WORLDVIEW_API_URL=https://your-api/worldview/stream`.

The real endpoint should accept `?q=<query>&depth=<n>` and emit a **Server-Sent-Events**
stream of JSON [`WorldviewEvent`](src/lib/worldview/types.ts)s — one event object per
`data:` line, ideally mirroring the event `type` in the SSE `event:` field, ending with a
`done` (or `error`) event. The SSE client is
[`stream/sseStream.ts`](src/lib/worldview/stream/sseStream.ts); it already handles
reconnect and cancellation. To use WebSockets instead, implement one more `StreamSource`
against the same interface ([`stream/source.ts`](src/lib/worldview/stream/source.ts)) and
return it from `createStreamSource()`.

### 4. Real data with zero credentials — the `/niti` run

The repo ships two **real, credential-free sources**: the NITI Aayog district-indicator
CSVs in [`/niti`](niti/) (sourced by `NitiCsvConnector` behind the same connector seam as
Reddit/YouTube) and the yt-dlp YouTube connector. With `ALLOW_STUB_FALLBACK=true` in
`backend/.env`, you can run the **real backend** end-to-end with no keys at all — the CSV
rows stream into the pipeline and the stub LLM (deterministic) drives clustering/resolution/
synthesis, so adding a real key later just upgrades the reasoning, not the wiring.

```sh
# 1. Python venv (light core — the heavy torch/sentence-transformers/chromadb stack is
#    only needed once a real LLM path is configured; `pip install -r requirements.txt`
#    in backend/ upgrades to it later)
cd backend
py -3.10 -m venv .venv
.venv/Scripts/pip install fastapi "uvicorn[standard]" sse-starlette pydantic pydantic-settings \
  langgraph openai anthropic httpx praw google-api-python-client yt-dlp numpy scipy scikit-learn openpyxl

# 2. Config
#    backend/.env:            ALLOW_STUB_FALLBACK=true   (+ the Gemini lines below once you have a key)
#    .env.local (repo root):  VITE_WORLDVIEW_STREAM=sse
#                             VITE_WORLDVIEW_API_URL=http://localhost:8001/api/worldview/stream

# 3. Run the backend (port 8001) and restart the frontend dev server (the .env.local flip
#    only takes effect on restart)
.venv/Scripts/uvicorn app.main:app --reload --port 8001   # from backend/
# …then the portable-node vite command from Quick start in another terminal.

# 4. Try it — the stream is plain SSE, one JSON WorldviewEvent per data: line
curl -Ns "http://localhost:8001/api/worldview/stream?q=high%20school%20dropouts%20in%20kerala&mode=basic"
```

Going **live with real reasoning**: the app's default provider is `gemma_remote`. Point it at
Google Gemini's OpenAI-compatible endpoint (free credits at https://aistudio.google.com/) in
`backend/.env`, then set `ALLOW_STUB_FALLBACK=false`:

```sh
REMOTE_GEMMA_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai/
REMOTE_GEMMA_API_KEY=<your Gemini API key>
```

`/niti` column names are the query vocabulary: tokens match district/state names and
indicator column names (e.g. "dropout", "internet", "sanitation"), results are
interleaved round-robin across states, and each post resolves to its real district.
To add another data source later (a real YouTube/Reddit credential, another CSV export):
implement `SourceConnector.search` in [`backend/app/connectors/sources.py`](backend/app/connectors/sources.py),
select it in a `get_*_connector()` factory, and bind it in
[`build_graph`](backend/app/graph/build.py) — no other pipeline change.

## Streaming event schema

All event types are defined in one place — [`src/lib/worldview/types.ts`](src/lib/worldview/types.ts).
Every event carries a `queryRunId` (multiple passes of "Go deeper" share one run).

| `type`              | payload (key fields)                                                        | drives                                  |
| ------------------- | -------------------------------------------------------------------------- | --------------------------------------- |
| `query_started`     | `query`, `queryType` (`descriptive`\|`policy`), `depth`                     | run identity + answer mode              |
| `status`            | `ticker`, `phase`, `counts`, `progress` (0–1)                              | query-bar ticker + progress bar         |
| `cluster_defined`   | `clusterId`, `label`, `color` (RGB), `summary`, `representativePosts`       | legend, column colours, click-through   |
| `district_resolved` | `districtId`, `stateCode`, `clusterId`, `confidence`, `volume`, `method`   | 3D columns, choropleth, split-state calc |
| `deflection`        | `clusterA/B`, `level`, `unitA/B`, `point`, `confidence`                    | deflection panel + map arcs             |
| `answer_chunk`      | `segment` (`{ text, kind?, clusterId?, region? }`)                          | streamed consolidated answer            |
| `done` / `error`    | `counts` / `message`                                                        | terminal state / reconnect              |

## Architecture

```
src/lib/worldview/
  types.ts          — event + data schema (single source of truth)
  palette.ts        — cluster colours (match --cluster-1..6), confidence, camera consts
  store.ts          — Zustand run store; applyEvent reducer; "Go deeper" MERGES
  selectors.ts      — legend, per-state entropy (split-state metric)
  useQueryStream.ts — the hook the UI calls: run() / cancel() / retry()
  geo/districts.ts  — typed GeoJSON loader (centroids/bboxes, graceful failure)
  geo/states.ts     — typed loader for the precomputed dissolved state boundaries
  stream/
    source.ts        — StreamSource interface
    config.ts        — mock↔real swap (the one place)
    mockStream.ts    — timed offline replay (Diwali + policy)
    sseStream.ts     — real SSE backend client (reconnect/cancel)
    mockContent.ts   — authored clusters/deflections/answer
    generatedDistricts.ts — frozen realistic district→viewpoint distribution
src/components/dashboard/
  map/WorldviewMap.tsx — SSR-safe wrapper (backdrop + client-gated lazy map + chips)
  map/DeckMap.tsx      — client-only deck.gl + react-map-gl (columns/arcs/drill-down)
  map/layers.ts        — builds the deck.gl layer stack from live store data
  map/useStateGeo.ts   — loads public/geo/india-states.geojson (client, cached)
  QueryBar / ConsolidatedPanel / LegendPanel / DeflectionPanel / ProgressBar /
  DistrictInfoPanel    — panels, all bound to the store
scripts/
  generate-mock-districts.mjs — rebuilds the offline demo's district→cluster mock data
  build-state-boundaries.mjs  — dissolves districts → india-states.geojson (turf, dev-only)
```

**State model.** A single Zustand store holds the current run keyed by `queryRunId`
(posts→districts, clusters, deflections, answer, progress, layer toggles, selection).
`prepareRun({ deeper: true })` keeps the accumulated data so **"Go deeper" merges** more
districts and higher-confidence refinements into the existing view rather than wiping it.

**SSR safety.** deck.gl / mapbox-gl (which need `window`/WebGL) are `lazy`-imported and
only mounted on the client after `useEffect`, wrapped in an error boundary. The server
renders just the dark backdrop, so there is no `window is not defined` crash and no map
code in the SSR path.

**Regenerating the mock distribution.** `node scripts/generate-mock-districts.mjs` rebuilds
`generatedDistricts.ts` from whatever GeoJSON is in `public/geo/`.

## Scripts

```sh
npm run dev       # dev server (SSR) — needs Node ≥22; see Quick start for the portable-Node command on this machine
npm run build     # production build
npm run lint      # eslint
npm run format    # prettier --write
```

---

This project was built with [Lovable](https://lovable.dev). Commits pushed to the connected
branch sync back into the Lovable editor, so keep the branch in a working state and avoid
rewriting published history.
