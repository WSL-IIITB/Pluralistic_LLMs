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
  schoolPressures: { emoji: string; label: string; detail: string }[];
  worries: string[];
  /** How each listed pressure and the region's dominant factors would reach this persona (see SCHEMA.md). */
  factorEffects?: PersonaFactorEffects;
  /** The persona's district through the NITI prescriptive model (see SCHEMA.md). */
  dataLens?: PersonaDataLens;
  /** First-person script for the animated self-introduction (see SCHEMA.md). */
  intro?: PersonaIntro;
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
