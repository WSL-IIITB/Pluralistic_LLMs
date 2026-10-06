/**
 * Public surface of the Worldview data layer — one import for the UI.
 */

export * from "./types";
export * from "./palette";
export * from "./selectors";
export {
  useWorldviewStore,
  type WorldviewStore,
  type RunState,
  type StatusSnapshot,
  type LayerToggles,
  type Selection,
  type RunSnapshot,
  type SavedRunData,
} from "./store";
export { useQueryStream, type QueryStreamApi, type RunOptions } from "./useQueryStream";
export { STREAM_SOURCE } from "./stream";
export { saveRun, listSavedRuns, fetchSavedRun, deleteSavedRun } from "./runHistory";
export * from "./karnataka";
export * from "./explorer";
export { STATIC_DATA, assetUrl } from "./api";
export { useDistrictProfiles, type DistrictProfile, type DistrictNitiFactor } from "./districtProfiles";
export { usePersonaProfile, type PersonaProfile } from "./personaProfiles";
export { personaCard, type PersonaCard, type PersonaCardTopic } from "./personaCards";
export * from "./districtResearch";
export { loadDefaultRun } from "./defaultRun";
export { CATEGORY_LABEL, CATEGORY_EMOJI } from "./reasonCategories";
