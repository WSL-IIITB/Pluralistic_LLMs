# India Worldview Explorer

Build the front-end UI shell for a data-visualization dashboard called "Pluralistic India — Worldview Explorer." This is UI ONLY: no real functionality, no data fetching, no API calls, no backend, no map library. Use hardcoded placeholder/mock content everywhere. A separate engineer will wire up all functionality later, so build clean, well-named, easily-extendable React components.

TECH: React + TypeScript + Tailwind CSS + shadcn/ui. Dark theme. Do not install mapping libraries — the map is a static placeholder for now (see below).

OVERALL AESTHETIC (very important — match this mood):

A dark, cartographic, "data-instrument" look inspired by the Manhattan Population Explorer / Uber deck.gl dashboards. Full-bleed dark charcoal background (#0d0d0f to #1a1a1d). Floating semi-transparent panels with subtle borders (rgba white ~8% borders, panel bg ~#16161a at 85% opacity, backdrop-blur). Clean sans-serif (Inter). Restrained, technical, elegant — lots of dark negative space, small uppercase labels, thin rules. Warm accent palette for data (ambers/oranges through reds), cool neutral greys for chrome.

LAYOUT (full-screen, map fills the entire viewport behind floating panels):

1. TOP BAR (fixed, full width, ~56px, dark, thin bottom border):

   - Left: product title "Pluralistic India" in medium weight, with a small subtitle "Worldview Explorer".

   - Center: tab navigation with 4 tabs — "Map", "Deflections", "Answer", "About". "Map" active by default (active tab has a subtle filled pill background).

   - Right: a small circular "info" icon button.

2. QUERY BAR (floating, top-center just below the top bar, prominent):

   - A wide search input with placeholder text "Enter a topic — e.g. Diwali, or 'high-school dropouts: where should government intervene?'"

   - A primary "Explore" button to its right (amber accent).

   - Directly under it, a thin status ticker line showing mock live status text: "Collected 1,240 posts · resolved 380 to districts · found 5 viewpoint clusters · analyzing deflections…" with a subtle animated pulse dot. This is static mock text, just style it to look live.

3. MAP PLACEHOLDER (fills the whole background behind the panels):

   - A dark full-viewport container representing where an interactive 3D map of India will go.

   - Put a faint centered label "3D map of India renders here" in low-opacity text, and optionally a very subtle dark topographic/grid texture or a faint SVG silhouette of India outline. Keep it dark and unobtrusive — it must read as "map area," not a finished map.

   - Add a small "mapbox"-style attribution chip bottom-left and a zoom-level indicator chip bottom-right reading "State view" (mock).

4. LEFT FLOATING PANEL — "Consolidated Answer" (top-left, ~380px wide, scrollable, floating with margin from edges):

   - Header: "Consolidated View" with a small "descriptive / policy" toggle badge.

   - Body: mock consolidated answer text about Diwali — 2–3 short paragraphs describing that Diwali is celebrated nationwide with shared rituals (lamps, sweets, family) but that regions commemorate different underlying events, then a short bulleted list of regional viewpoints (North: Rama's return to Ayodhya; South: Krishna defeating Narakasura; East/Bengal: Kali Puja; West/Gujarat: new-year & Lakshmi; Sikh: Bandi Chhor Divas; Jain: Mahavira's nirvana). Use placeholder text, clearly attributed by region.

   - Each viewpoint bullet has a small colored dot matching the legend palette.

5. RIGHT FLOATING PANEL — Legend + Layers (top-right, ~260px wide):

   - Section "Viewpoint Clusters": a vertical list of 6 mock clusters each with a colored swatch and label (use a categorical warm palette: amber, orange, red, rose, gold, coral). Labels: "Rama / Ayodhya", "Krishna / Narakasura", "Kali Puja", "New Year / Lakshmi", "Bandi Chhor Divas", "Mahavira Nirvana".

   - Section "Data Confidence": three swatches — "High" (solid), "Low" (semi-transparent), "No data → state fallback" (hatched/greyed pattern).

   - Section "Layers": a checklist (shadcn checkboxes, all checked) — "Show 3D columns", "Show deflection links", "Highlight split states". These are visual only, no behavior needed.

6. BOTTOM BAR — Collection Progress (floating bottom-center, ~560px wide):

   - A labeled progress bar at ~70% fill labeled "Live collection".

   - To its right, a secondary "Go deeper" button (outline style) and a small note "sampling bounded — extend for more coverage".

7. DEFLECTION PANEL (build it but hidden by default — show it as a bottom drawer/card that appears when the "Deflections" tab is active):

   - Two dropdown selectors labeled "Region A" and "Region B" (mock options: North, South, East, West, Sikh, Jain).

   - Below: a card showing a mock deflection: A = "Rama / Ayodhya", B = "Krishna / Narakasura", with a one-line "Point of deflection: which divine figure and which liberation event is being commemorated," and a small tag "level: inter-region".

STATE (minimal, UI-only):

- Tab switching should work (switch which panel/content is visible) — that's the only interactivity. Everything else is static mock data. No data logic, no fetching, no map SDK.

Make it responsive enough to look good on a laptop screen (1440px). Prioritize matching the dark, floating-panel, cartographic aesthetic above all else. Structure components cleanly: TopBar, QueryBar, MapPlaceholder, ConsolidatedPanel, LegendPanel, ProgressBar, DeflectionPanel.

This project was built with [Lovable](https://lovable.dev).

## Build with Lovable

Continue developing this project in the [Lovable editor](https://lovable.dev/projects/87235be6-ff58-4173-b56c-51692cde5023).

- **Ship faster**: describe what you want to build and Lovable handles the code.
- **Stay in sync**: every change made in Lovable is committed straight to this repository.
- **Full ownership**: this code is yours. Push to `main` on GitHub and your changes sync back into Lovable, ready for your next prompt.

## Development

Prefer working locally? You need Node.js and npm — [install with nvm](https://github.com/nvm-sh/nvm#installing-and-updating).

```sh
git clone <this-repository-url>
cd <repository-name>
npm i
npm run dev
```
