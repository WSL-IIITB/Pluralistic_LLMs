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
