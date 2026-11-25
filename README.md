# Pluralistic Karnataka — Worldview Explorer

A dark, cartographic dashboard that shows how Karnataka's four regions —
**Mysuru-Bengaluru**, **North Karnataka**, **Karavali** and **Malnad** — hold different
viewpoints on a shared topic, and how much answering _as each region_ changes an LLM's reply.

Enter a topic and a LangGraph backend streams results in real time: it gathers social
posts (YouTube, Reddit) and mainstream/official web sources region by region, places each
in its region, clusters each region's viewpoints, extracts the **point of deflection**
between co-occurring viewpoints, writes a Karnataka-wide answer, and then writes **one
reply per region in that region's persona** (built from its persona description,
`backend/app/data/personas/`).

The **Divergence** tab then re-asks every region the same question with the same
evidence but _no persona_, and measures how far the two replies diverge: semantic
similarity (primary indicator) against a sampling-noise floor, the specific points that
were added, dropped or reframed, a reply-similarity heatmap, and a t-SNE map of every
extracted point. The **Data** tab (India-wide secondary-school dropout data) is separate
and unchanged.

> Preserve the visual language when editing: dark theme, floating glass panels
> (`panel-surface`), small uppercase labels (`label-micro`), cool-neutral chrome.

## Quick start

```sh
npm install
npm run dev
```

With no backend configured the app replays one recorded real run (`high school dropouts`),
divergence view included. For live runs, start the backend (`backend/`, see
`backend/.env.example`) and set `VITE_WORLDVIEW_STREAM=sse`.

## Regions and personas

- **Membership** — `backend/app/data/karnataka_regions.json` maps all 30 map districts to
  the four regions (Uttara Kannada → Karavali; the seven districts no persona names are
  folded into the nearest region), plus region-name aliases and a town/alt-spelling
  lexicon (Mangaluru, Manipal, Hubballi, Coorg…) used to place posts. Posts about
  Karnataka as a whole go to a non-persona **statewide** bucket; posts about elsewhere are
  dropped.
- **Geometry** — `public/geo/karnataka-regions.geojson` is generated from that file:
  `python -m app.data.build_karnataka_regions_geo` (from `backend/`, needs `shapely`).
- **Personas** — `backend/app/karnataka.py` builds each region's persona prompt
  deterministically from its description file; the prompt's hash is shown with every
  divergence score. `GET /api/personas` serves them.
- **Divergence** — `backend/app/graph/nodes/divergence.py`. Runs on every configured model in
  `reasoning_modes.DIVERGENCE_PROVIDERS` (Gemma and Claude today) plus the run's own model,
  all on the same persona and evidence; the tab switches between models and compares them.
  Points are always extracted by the run's own model and embedded with the local
  `all-MiniLM-L6-v2` (never a provider API), so the measuring tools never vary with the
  model being measured.

## Second study: under-5 stunting

A **Dropout | Stunting** switch in the top bar changes every data view; the personas are shared.

- **Model** — the NITI team's PROVISIONAL stunting workbook (Tableau Public) is stored in
  `backend/app/data/niti/stunting/` and extracted with `scripts/extract_stunting_twbx.py` (needs
  `tableauhyperapi`). `backend/app/stunting.py` reproduces its formulas (`/api/stunting`): NFHS-6
  stunting per district, 11 factors in 4 buckets, and for a target cut the value each factor would need.
  The target slider and bucket priority recompute it in the browser (`prescribe()` in
  `src/lib/worldview/stunting.ts`). Mandya has no figures in the workbook.
- **Media research** — `scripts/research_stunting_districts.py` (Claude web search -> page fetch ->
  Claude compile -> verification: every number must be on a cited page) writes
  `backend/app/data/district_research_stunting/<id>.json` (`/api/stunting/research`), including
  `modelFactorWhy`: local evidence for each district's top prescribed factors.
- **Views** — Map / UIDAI-NITI tabs: statewide overview, key findings, target controls; map district sheet:
  on the ground, news vs data, numbers, media & sources; Personas tab: the district's stunting data and,
  for the 12 researched personas, a stunting lens (`personaCards/stuntingLens/`, `scripts/build_stunting_lenses.py`);
  the Ask chat routes stunting questions to the STUNTING sections of the knowledge pack.
- **Pipeline** — a run on a stunting question ("Run the stunting analysis") compares persona replies with the
  stunting model instead of the dropout workbooks; each topic opens on its own latest run.

## Persona library (Personas tab)

A man and a woman for every district, kept independent of the dropout study
(`backend/app/persona_library.py`, `/api/persona-library`):

- **Researched** — the 12 regional personas, each placed in the district its card names. Their text
  had the dropout framing removed (`scripts/neutralize_personas.py`; removed sentences are listed in
  `docs/persona-research/neutralized-deletions.md`). The study's reading of their household (school
  pressures, NITI data lens) lives in `src/lib/worldview/personaCards/studyLens/` and shows as a
  separate section.
- **Generated** — LLM-written from the region's research brief for the empty slots
  (`scripts/generate_district_personas.py --district 29-577` or `--all`). Not source-verified.
- **Your persona** — created or fine-tuned in the tab (pick region, district, taluk/town and traits,
  generate, edit, save). Stored in `backend/app/data/persona_library/custom/` (git-ignored).

"Ask a question" answers the same question twice with identical evidence — without a persona and as
the persona — and shows how far they differ. Generating, saving and asking need the backend; the
static site shows the library read-only (`public/data/persona-library.json`).

## District profiles (outside context)

Every district sheet, in both topics, has a **Profile** tab with that district's background from
[District Mocha](https://district-mocha.netlify.app/india.html), an AI-assisted development dashboard by another team:
baseline figures (population, per-capita income, GDDP, literacy, HDI, economy split), strengths, challenges,
opportunities, goals, programmes, industries and role-based actions. Items that mention the active topic are marked.
It is labelled as outside context: the figures have no per-figure sources and were not checked by this study.
Vijayanagara's page is shown under Ballari, which shares its map polygon.

- Data: `backend/app/data/district_mocha/karnataka.json` (`GET /api/district-mocha`, `public/data/district-mocha.json`
  on the static site), built by `scripts/import_district_mocha.py` from a full scrape of the site (kept outside the
  repo in `../district-mocha/`).
- Chat: each district has a `DISTRICT CONTEXT` section, tagged (OUTSIDE) and cited to its District Mocha page. It is
  sent only for background questions about a named district (economy, GDDP, HDI, population, industries, profile…)
  and is the first section dropped when the context budget is tight. CAVEATS rule 11 and the chat rules make the
  model attribute it and never use it as evidence for dropout or stunting causes.

To refresh: re-run the scraper in `../district-mocha/scraper/`, then
`python3 scripts/import_district_mocha.py ../district-mocha/district-mocha.json`, re-export the static snapshot and
rebuild the knowledge pack (`python3 scripts/build_knowledge_pack.py`).

## Wiring it to real data — the three plug points

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

The real endpoint accepts `?q=<query>&mode=basic|medium|high|extrahigh&provider=...` and emits a **Server-Sent-Events**
stream of JSON [`WorldviewEvent`](src/lib/worldview/types.ts)s — one event object per
`data:` line, ideally mirroring the event `type` in the SSE `event:` field, ending with a
`done` (or `error`) event. The SSE client is
[`stream/sseStream.ts`](src/lib/worldview/stream/sseStream.ts); it already handles
reconnect and cancellation. To use WebSockets instead, implement one more `StreamSource`
against the same interface ([`stream/source.ts`](src/lib/worldview/stream/source.ts)) and
return it from `createStreamSource()`.

## Streaming event schema

All event types are defined in [`src/lib/worldview/types.ts`](src/lib/worldview/types.ts)
(mirrored by `backend/app/schema.py`). Every event carries a `queryRunId`.

| `type`               | payload (key fields)                                                   | drives                                |
| -------------------- | ---------------------------------------------------------------------- | ------------------------------------- |
| `query_started`      | `query`, `queryType` (`descriptive`\|`policy`), `mode`, `provider`     | run identity + answer mode            |
| `status`             | `ticker`, `phase`, `counts`, `progress` (0–1)                          | ticker + progress bar                 |
| `region_defined`     | `regionId`, `name`, `justification`, `districtIds`                     | region names                          |
| `cluster_defined`    | `clusterId`, `label`, `summary`, `representativePosts`, `regionId`     | legend, column colours                |
| `region_resolved`    | `regionId`, `clusterId`, `volume`, `confidence`, `method`              | region fills, 3D columns              |
| `deflection`         | `clusterA/B`, `level`, `unitA/B`, `point`                              | deflection panel + map arcs           |
| `answer_chunk`       | `segment` (`{ text, kind?, clusterId?, regionId?, citations? }`)       | overview + per-region persona replies |
| `research_document`  | `document` (`{ id, url, title, domain, snippet }`)                     | numbered sources                      |
| `divergence_region`  | similarity, noise floor, points only-with / only-without / reframed    | Divergence tab                        |
| `divergence_summary` | reply-similarity matrix, cross-region similarity, t-SNE points         | Divergence tab                        |
| `divergence_models`  | per region: how far two models' replies agree, each model's divergence | Divergence tab (across models)        |
| `done` / `error`     | `counts` / `message`                                                   | terminal state / reconnect            |

## Architecture

```
backend/app/
  karnataka.py              — regions, place lexicon, persona builder
  graph/build.py            — source → research → resolve_regions → cluster → aggregate
                              → deflect → synthesize → answer_regions → divergence
  graph/nodes/              — one module per stage
src/lib/worldview/
  types.ts / store.ts       — event schema + Zustand run store (applyEvent reducer)
  karnataka.ts              — region ids, names, validated colours, camera
  selectors.ts / palette.ts — legend grouping, split-region metric, colours
  stream/                   — mock (replays stream/demoRun.json) ↔ SSE swap
src/components/
  dashboard/map/            — deck.gl map: Karnataka regions (Story) / India districts (Data)
  dashboard/                — query bar, answer, legend, region, deflection, history panels
  divergence/               — Divergence tab: scores, point diffs, heatmap, t-SNE
scripts/
  build-demo-run.mjs        — rebuilds the offline demo from an SSE capture
  build-state-boundaries.mjs — dissolves districts → india-states.geojson (turf, dev-only)
```

**SSR safety.** deck.gl / mapbox-gl (which need `window`/WebGL) are `lazy`-imported and
only mounted on the client after `useEffect`, wrapped in an error boundary. The server
renders just the dark backdrop, so there is no `window is not defined` crash and no map
code in the SSR path.

**Regenerating the offline demo.** Capture a real run and rebuild the fixture:
`curl -sN "http://localhost:8001/api/worldview/stream?q=...&mode=medium" > run.sse && node scripts/build-demo-run.mjs run.sse`.

## Scripts

```sh
npm run dev       # dev server (SSR)
npm run build     # production build
npm run lint      # eslint
npm run format    # prettier --write
```

---

This project was built with [Lovable](https://lovable.dev). Commits pushed to the connected
branch sync back into the Lovable editor, so keep the branch in a working state and avoid
rewriting published history.
