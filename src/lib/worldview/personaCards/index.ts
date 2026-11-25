/** Typed access to the hand-distilled persona cards (see SCHEMA.md). */

export interface PersonaCardTopic {
  key: string;
  label: string;
  emoji: string;
  headline: string;
  points: string[];
  stat?: { value: string; label: string };
}

export interface PersonaFactorEffects {
  /** District this persona lives in (e.g. "29-573"); used to look up its dominant-factor rows and research. */
  districtId: string;
  /** One line per `schoolPressures` item, same order: what that pressure does to this household. */
  pressures: string[];
  /** If-then line for the state-level factor (household sanitation). */
  sanitation: string;
  /** Line for the district-level factor, anchored in what the card itself shows. */
  district: string;
}

/** How the persona's district's NITI prescriptive profile reaches this household (see SCHEMA.md). */
export interface PersonaDataLens {
  /** The NITI workbook row (area) the persona lives in, e.g. "Belagavi Chikkodi". */
  area: string;
  /** One line per top-3 change for that area, in the model's order (feasible ranking). */
  changes: { factor: string; effect: string }[];
  /** The factor where the area ranks lowest in Karnataka (not already in the top 3). */
  lag: { factor: string; effect: string };
}

export type IntroScene =
  "hello" | "household" | "day" | "world" | "school" | "district" | "worries" | "outro";

/** One narrated line of the persona's intro "video" (see SCHEMA.md and scripts/check_persona_intros.py). */
export interface PersonaIntroLine {
  scene: IntroScene;
  /** Caption shown on screen. */
  text: string;
  /** What the voice says, when it differs from the caption (numbers, acronyms). */
  say?: string;
  /** Indices of the card items this line brings on screen (household / dayInLife / schoolPressures / worries;
   * for "district", the dataLens changes, 3 = the lag factor). */
  show?: number[];
  /** Topic whose headline and stat the "world" scene shows. */
  topic?: string;
}

export interface PersonaIntro {
  backdrop: "fields" | "city" | "dry-plains" | "coast" | "hills-forest";
  lines: PersonaIntroLine[];
}

export interface PersonaCard {
  name: string;
  ageLabel: string;
  emoji: string;
  role: string;
  place: string;
  community: string;
  tagline: string;
  household: { who: string; emoji: string }[];
  vitals: { label: string; value: string }[];
  dayInLife: { when: string; emoji: string; text: string }[];
  topics: PersonaCardTopic[];
  worries: string[];
  /** First-person script for the animated self-introduction (see SCHEMA.md). */
  intro?: PersonaIntro;
}

/**
 * The dropout study's view of a curated persona's household -- kept OUT of the persona card
 * (studyLens/<region>.json) so the persona stays a person, independent of any study question.
 * The Personas tab shows it as a separate, labelled "study lens" section.
 */
export interface PersonaStudyLens {
  /** What could pull/push this household's children out of secondary school (an interpretation). */
  schoolPressures: { emoji: string; label: string; detail: string }[];
  /** How each listed pressure and the region's dominant factors would reach this persona (see SCHEMA.md). */
  factorEffects?: PersonaFactorEffects;
  /** The persona's district through the NITI prescriptive model (see SCHEMA.md). */
  dataLens?: PersonaDataLens;
}

type RegionCards = Record<string, PersonaCard>;

const modules = import.meta.glob<RegionCards>("./*.json", { eager: true, import: "default" });

const BY_REGION: Record<string, RegionCards> = {};
for (const [path, cards] of Object.entries(modules)) {
  const regionId = path.replace("./", "").replace(".json", "");
  BY_REGION[regionId] = cards;
}

export function personaCard(regionId: string, personaId: string): PersonaCard | null {
  return BY_REGION[regionId]?.[personaId] ?? null;
}

const lensModules = import.meta.glob<Record<string, PersonaStudyLens>>("./studyLens/*.json", {
  eager: true,
  import: "default",
});
const LENS_BY_REGION: Record<string, Record<string, PersonaStudyLens>> = {};
for (const [path, lenses] of Object.entries(lensModules)) {
  LENS_BY_REGION[path.replace("./studyLens/", "").replace(".json", "")] = lenses;
}

/** The study's lens on a curated persona (school pressures, factor effects, NITI data lens), or null. */
export function studyLens(regionId: string, personaId: string): PersonaStudyLens | null {
  return LENS_BY_REGION[regionId]?.[personaId] ?? null;
}

/** The stunting study's reading of a curated persona's household (stuntingLens/<region>.json) -- not the persona. */
export interface PersonaStuntingLens {
  districtId: string;
  /** The district has no figures in the stunting workbook. */
  noData?: boolean;
  underFive?: string;
  /** The district's top three prescribed factors (default 20% target), and how each could reach this household. */
  changes?: { factor: string; effect: string }[];
}

const stuntingModules = import.meta.glob<Record<string, PersonaStuntingLens>>(
  "./stuntingLens/*.json",
  {
    eager: true,
    import: "default",
  },
);
const STUNTING_BY_REGION: Record<string, Record<string, PersonaStuntingLens>> = {};
for (const [path, lenses] of Object.entries(stuntingModules)) {
  STUNTING_BY_REGION[path.replace("./stuntingLens/", "").replace(".json", "")] = lenses;
}

export function stuntingLens(regionId: string, personaId: string): PersonaStuntingLens | null {
  return STUNTING_BY_REGION[regionId]?.[personaId] ?? null;
}
