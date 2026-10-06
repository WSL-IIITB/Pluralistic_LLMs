/** Typed access to the hand-distilled persona cards (see SCHEMA.md). */

export interface PersonaCardTopic {
  key: string;
  label: string;
  emoji: string;
  headline: string;
  points: string[];
  stat?: { value: string; label: string };
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
