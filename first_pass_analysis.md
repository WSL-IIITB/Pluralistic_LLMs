# First-Pass Analysis — Pluralistic India / Worldview Explorer

## 1. What This Application Does & Who It's For

A **real-time data dashboard** that visualises how different regions of India hold **different viewpoints on a shared topic**. It's a research/policy tool — not a consumer product.

**How it works:**
1. User types a topic (e.g. "Diwali", "high-school dropouts: where should government intervene?")
2. A **LangGraph agent backend** (Python, FastAPI) kicks off a pipeline: source social-media posts (Reddit + YouTube + government research docs) → geo-resolve each post to an Indian **district** → cluster posts into distinct **viewpoints** → find **points of deflection** between viewpoints → synthesise a **consolidated answer**
3. Results stream via **SSE** to a React frontend that progressively builds a **3D map** (deck.gl columns over India) + side panels (legend, deflection analysis, consolidated answer)

**Who it's for:** Researchers, policy analysts, or anyone studying regional opinion diversity across India. The "policy" answer mode suggests government/NGO use cases.

**Key capability:** Ships with a **full offline mock demo** (Diwali topic) — no backend, no API keys, no Mapbox token needed.

---

## 2. Files to Read First (Ranked by Importance)

| # | File | Why |
|---|------|-----|
| 1 | [`types.ts`](file:///c:/Users/saket/Downloads/Pluralistic_LLMs/src/lib/worldview/types.ts) | **The single source of truth.** Every data type, every streaming event, every domain concept is defined here. Reading this tells you the entire data model and streaming protocol in ~500 lines. |
| 2 | [`store.ts`](file:///c:/Users/saket/Downloads/Pluralistic_LLMs/src/lib/worldview/store.ts) | **The brain.** 610-line Zustand store that accumulates streamed events into renderable state. Contains the `applyEvent` reducer, "Go deeper" merge logic, and the full shape of what the UI reads. |
| 3 | [`index.tsx`](file:///c:/Users/saket/Downloads/Pluralistic_LLMs/src/routes/index.tsx) (route) | **The page.** Single-route app — this file composes all panels (QueryBar, Map, Legend, Deflection, ConsolidatedPanel) and defines the layout. Shows how everything wires together. |
| 4 | [`stream/config.ts`](file:///c:/Users/saket/Downloads/Pluralistic_LLMs/src/lib/worldview/stream/config.ts) | **The one toggle.** `mock` ↔ `sse` swap. Tiny file but critical for understanding how the app decides where data comes from. |
| 5 | [`useQueryStream.ts`](file:///c:/Users/saket/Downloads/Pluralistic_LLMs/src/lib/worldview/useQueryStream.ts) | **The hook.** How the UI triggers a run, cancels, retries, and wires SSE events into the store. The bridge between user action and data flow. |
| 6 | [`DeckMap.tsx`](file:///c:/Users/saket/Downloads/Pluralistic_LLMs/src/components/dashboard/map/DeckMap.tsx) | **The visual centrepiece.** Client-only deck.gl + react-map-gl. Shows 3D columns, arcs, choropleth — the most complex rendering code. |
| 7 | [`backend/app/main.py`](file:///c:/Users/saket/Downloads/Pluralistic_LLMs/backend/app/main.py) | **Backend entry point.** FastAPI app with SSE streaming endpoint. Shows the API contract the frontend consumes. |
| 8 | [`vite.config.ts`](file:///c:/Users/saket/Downloads/Pluralistic_LLMs/vite.config.ts) | **Build system.** Uses `@lovable.dev/vite-tanstack-config` which bundles TanStack Start, Nitro (Cloudflare), Tailwind, React — a LOT is hidden behind this one import. Important to know what you can't configure. |

---

## 3. Commands to Run Locally

### Frontend (mock mode — works with zero config)

```sh
# From project root
npm install
npm run dev
```

This starts a Vite dev server with SSR (TanStack Start + Nitro). The offline Diwali demo auto-plays on load.

### Backend (optional — only needed for real data)

```sh
# From backend/
pip install -r requirements.txt
# Copy and fill in backend/.env.example → backend/.env
python -m app.main
```

> [!WARNING]
> **Unclear from code alone:**
> - The backend's `requirements.txt` lists dependencies but doesn't specify a Python version. Given LangGraph + FastAPI + async patterns, **Python 3.10+** is a safe bet, but not stated.
> - The backend needs API keys (Azure/OpenAI/Ollama) configured in `backend/.env` — see [`backend/.env.example`](file:///c:/Users/saket/Downloads/Pluralistic_LLMs/backend/.env.example) for the full list.
> - There's also a [`proxy/`](file:///c:/Users/saket/Downloads/Pluralistic_LLMs/proxy) directory (Cloudflare Worker for endpoint-masking). Its relationship to local dev is unclear — likely only needed for deployed environments.

### To wire frontend → backend (still local)

Either set env vars:
```
VITE_WORLDVIEW_STREAM=sse
VITE_WORLDVIEW_API_URL=http://localhost:8000/api/worldview/stream
```

Or edit one line in [`stream/config.ts`](file:///c:/Users/saket/Downloads/Pluralistic_LLMs/src/lib/worldview/stream/config.ts):
```ts
const DEFAULT_SOURCE: SourceKind = "sse"; // was "mock"
```

---

## Things That Are Unclear

| Item | What's unclear |
|------|---------------|
| **`@lovable.dev/vite-tanstack-config`** | This package does _a lot_ (Nitro, Tailwind, React, TanStack, path aliases, dedupe, port config). Its internals are opaque — no source in the repo. If something breaks in the build pipeline, debugging will require reading that package's source on npm. |
| **`bun.lock` vs `package-lock.json`** | Both exist. `bunfig.toml` also exists. Unclear if the canonical package manager is **npm** or **bun**. README says `npm install` but both lockfiles are committed. |
| **Data View feature** | There's a [`src/components/dataview/`](file:///c:/Users/saket/Downloads/Pluralistic_LLMs/src/components/dataview) directory and env vars for it (`VITE_DATAVIEW_*`), but the route tree only has one route (`/`). How is Data View accessed? Likely a tab/panel within the same page, but unclear without reading more. |
| **`nitro` as devDependency** | `"nitro": "3.0.260603-beta"` — a **beta** version pinned in devDependencies. Could be a source of instability. |
