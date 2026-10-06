/**
 * DataViewPanels — Data View's top-level router, rendered by routes/index.tsx
 * when the "Data" tab is active.
 *
 * Currently just mounts `KarnatakaPersonaSimilarity.tsx` (Karnataka Story
 * Mode's male/female-persona-vs-baseline similarity scores and t-SNE; reads
 * the Karnataka worldview store). The India-wide "Verdict" and
 * "Intervention & Budget" pages (`DataViewVerdict.tsx` /
 * `DataViewIntervention.tsx`, backed by `lib/dataview/store.ts` +
 * `useDataViewBootstrap`) are intentionally not rendered here for now --
 * left in place, not deleted, in case they're wanted again later. Restoring
 * them means bringing back the page toggle (Verdict / Intervention & Budget /
 * Persona Similarity) this file rendered before this simplification.
 */

import { KarnatakaPersonaSimilarity } from "./KarnatakaPersonaSimilarity";

export function DataViewPanels() {
  return <KarnatakaPersonaSimilarity />;
}
