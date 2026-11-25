/**
 * Dashboard-level UI state shared between the left column (tabs, persona
 * explorer) and the right-half map: which tab is open, which region/district
 * the map is focused on, and which persona is being explored.
 *
 * Kept separate from the run store (store.ts) because none of this comes from
 * the analysis stream and none of it should be wiped by starting a new run.
 */

import { create } from "zustand";

import { curatedDistrictId } from "./personaLibrary";
import type { StudyTopic } from "./stunting";

export const DASHBOARD_TABS = [
  "Map",
  "Ask",
  "Personas",
  "Divergence",
  "UIDAI / NITI",
  "Data",
  "History",
] as const;
export type DashboardTab = (typeof DASHBOARD_TABS)[number];

/** The tabs of the district sheet on the map. */
export type DistrictSheetTab = "reasons" | "compare" | "numbers" | "media";

export interface ExplorerState {
  tab: DashboardTab;
  /** Which study the data views show: secondary-school dropout or under-5 stunting. Personas are shared. */
  topic: StudyTopic;
  /** Region the map is zoomed to (set directly, or implied by a district). */
  regionId: string | null;
  /** District the map is zoomed to; implies `regionId`. */
  districtId: string | null;
  /** Which tab the district sheet shows. */
  districtTab: DistrictSheetTab;
  /** Curated regional persona last chosen (kept for older callers; see `libraryPersonaId`). */
  persona: { regionId: string; personaId: string } | null;
  /** Persona-library persona open in the Personas tab (district-level; see personaLibrary.ts). */
  libraryPersonaId: string | null;

  setTab(tab: DashboardTab): void;
  setTopic(topic: StudyTopic): void;
  focusRegion(regionId: string): void;
  /** Zoom to a district; its sheet opens on `tab` (default: what's on the ground). */
  focusDistrict(districtId: string, regionId: string, tab?: DistrictSheetTab): void;
  setDistrictTab(tab: DistrictSheetTab): void;
  /** Zoom back out to all of Karnataka. */
  resetFocus(): void;
  /** Open a curated regional persona (male/female of a region). */
  selectPersona(regionId: string, personaId: string): void;
  /** Open any library persona; the map zooms to its district. */
  selectLibraryPersona(id: string, districtId: string, regionId: string): void;
}

export const useExplorerStore = create<ExplorerState>((set) => ({
  tab: "Map",
  topic: "dropout",
  regionId: null,
  districtId: null,
  districtTab: "reasons",
  persona: null,
  libraryPersonaId: null,

  setTab: (tab) => set({ tab }),
  setTopic: (topic) => set({ topic }),
  focusRegion: (regionId) => set({ regionId, districtId: null }),
  focusDistrict: (districtId, regionId, tab = "reasons") =>
    set({ districtId, regionId, districtTab: tab }),
  setDistrictTab: (districtTab) => set({ districtTab }),
  resetFocus: () => set({ regionId: null, districtId: null }),
  selectPersona: (regionId, personaId) => {
    const districtId = curatedDistrictId(regionId, personaId);
    set({
      persona: { regionId, personaId },
      libraryPersonaId: districtId ? `${districtId}-${personaId}` : null,
      regionId,
      districtId,
    });
  },
  selectLibraryPersona: (id, districtId, regionId) =>
    set({ libraryPersonaId: id, districtId, regionId }),
}));
