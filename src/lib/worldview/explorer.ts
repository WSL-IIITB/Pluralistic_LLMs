/**
 * Dashboard-level UI state shared between the left column (tabs, persona
 * explorer) and the right-half map: which tab is open, which region/district
 * the map is focused on, and which persona is being explored.
 *
 * Kept separate from the run store (store.ts) because none of this comes from
 * the analysis stream and none of it should be wiped by starting a new run.
 */

import { create } from "zustand";

export const DASHBOARD_TABS = ["Map", "Personas", "Divergence", "Data", "History"] as const;
export type DashboardTab = (typeof DASHBOARD_TABS)[number];

export interface ExplorerState {
  tab: DashboardTab;
  /** Region the map is zoomed to (set directly, or implied by a district). */
  regionId: string | null;
  /** District the map is zoomed to; implies `regionId`. */
  districtId: string | null;
  /** Persona currently open in the Personas tab. */
  persona: { regionId: string; personaId: string } | null;

  setTab(tab: DashboardTab): void;
  focusRegion(regionId: string): void;
  focusDistrict(districtId: string, regionId: string): void;
  /** Zoom back out to all of Karnataka. */
  resetFocus(): void;
  selectPersona(regionId: string, personaId: string): void;
}

export const useExplorerStore = create<ExplorerState>((set) => ({
  tab: "Map",
  regionId: null,
  districtId: null,
  persona: null,

  setTab: (tab) => set({ tab }),
  focusRegion: (regionId) => set({ regionId, districtId: null }),
  focusDistrict: (districtId, regionId) => set({ districtId, regionId }),
  resetFocus: () => set({ regionId: null, districtId: null }),
  selectPersona: (regionId, personaId) =>
    set({ persona: { regionId, personaId }, regionId, districtId: null }),
}));
