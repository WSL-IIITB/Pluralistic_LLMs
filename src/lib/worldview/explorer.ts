/**
 * Dashboard-level UI state shared between the left column (tabs, persona
 * explorer) and the right-half map: which tab is open, which region/district
 * the map is focused on, and which persona is being explored.
 *
 * Kept separate from the run store (store.ts) because none of this comes from
 * the analysis stream and none of it should be wiped by starting a new run.
 */

import { create } from "zustand";

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
  /** Region the map is zoomed to (set directly, or implied by a district). */
  regionId: string | null;
  /** District the map is zoomed to; implies `regionId`. */
  districtId: string | null;
  /** Which tab the district sheet shows. */
  districtTab: DistrictSheetTab;
  /** Persona currently open in the Personas tab. */
  persona: { regionId: string; personaId: string } | null;

  setTab(tab: DashboardTab): void;
  focusRegion(regionId: string): void;
  /** Zoom to a district; its sheet opens on `tab` (default: what's on the ground). */
  focusDistrict(districtId: string, regionId: string, tab?: DistrictSheetTab): void;
  setDistrictTab(tab: DistrictSheetTab): void;
  /** Zoom back out to all of Karnataka. */
  resetFocus(): void;
  selectPersona(regionId: string, personaId: string): void;
}

export const useExplorerStore = create<ExplorerState>((set) => ({
  tab: "Map",
  regionId: null,
  districtId: null,
  districtTab: "reasons",
  persona: null,

  setTab: (tab) => set({ tab }),
  focusRegion: (regionId) => set({ regionId, districtId: null }),
  focusDistrict: (districtId, regionId, tab = "reasons") =>
    set({ districtId, regionId, districtTab: tab }),
  setDistrictTab: (districtTab) => set({ districtTab }),
  resetFocus: () => set({ regionId: null, districtId: null }),
  selectPersona: (regionId, personaId) =>
    set({ persona: { regionId, personaId }, regionId, districtId: null }),
}));
