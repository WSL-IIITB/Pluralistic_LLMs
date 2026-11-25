/**
 * The persona library: one man and one woman per Karnataka district, independent of the
 * dropout study (backend/app/persona_library.py). Curated personas are the 12 researched
 * regional ones placed in their own district; the rest are generated, or made by a user.
 *
 * With a backend: GET /api/persona-library (summaries) and /api/persona-library/<id>.
 * On the static site: public/data/persona-library.json (everything, read-only).
 */

import { create } from "zustand";

import { apiUrl, assetUrl, STATIC_DATA } from "./api";
import type { PersonaCard } from "./personaCards";

export type PersonaSource = "curated" | "generated" | "custom" | "draft";
export type Gender = "male" | "female";

export interface LibraryDistrict {
  districtId: string;
  name: string;
  regionId: string;
}

export interface LibraryPersonaSummary {
  id: string;
  source: PersonaSource;
  districtId: string;
  districtName: string;
  regionId: string;
  gender: Gender;
  name: string;
  role: string | null;
  place: string | null;
  emoji: string | null;
  curatedRef: { regionId: string; personaId: string } | null;
  basedOn: string | null;
  createdAt: string | null;
  version: string;
}

export interface LibraryPersona {
  id: string;
  source: PersonaSource;
  districtId: string;
  districtName: string;
  regionId: string;
  gender: Gender;
  name: string;
  place?: string;
  definition: string;
  topics: { key: string; label: string; profile: string }[];
  /** Display card; null for curated personas, whose card lives in personaCards/. */
  card: PersonaCard | null;
  curatedRef?: { regionId: string; personaId: string } | null;
  traits?: Record<string, string>;
  basedOn?: string | null;
  provider?: string | null;
  createdAt?: string;
  version?: string;
}

export interface AskAnswer {
  answer: string;
  points: string[];
}

export interface AskResult {
  question: string;
  personaId: string;
  personaVersion: string;
  evidence: { used: boolean; district: string | null; topic?: "dropout" | "stunting" };
  generic: AskAnswer;
  persona: AskAnswer;
  similarity: number | null;
  onlyWithPersona: string[];
  onlyWithout: string[];
  provider: string;
}

/** Generating, saving and asking need the backend; the static site only shows the library. */
export const LIBRARY_LIVE = !STATIC_DATA;

/** The library id of a curated regional persona (it lives in the district its card names). */
const CURATED_DISTRICT: Record<string, string> = {
  "old-mysuru/male": "29-573",
  "old-mysuru/female": "29-572",
  "bayaluseeme/male": "29-566",
  "bayaluseeme/female": "29-582",
  "karavali/male": "29-563",
  "karavali/female": "29-569",
  "malnad/male": "29-570",
  "malnad/female": "29-576",
  "kitturu-karnataka/male": "29-555",
  "kitturu-karnataka/female": "29-557",
  "kalyana-karnataka/male": "29-579",
  "kalyana-karnataka/female": "29-565",
};

export function curatedLibraryId(regionId: string, personaId: string): string | null {
  const d = CURATED_DISTRICT[`${regionId}/${personaId}`];
  return d ? `${d}-${personaId}` : null;
}

export function curatedDistrictId(regionId: string, personaId: string): string | null {
  return CURATED_DISTRICT[`${regionId}/${personaId}`] ?? null;
}

// ── Loading ──────────────────────────────────────────────────────────────────

interface LibraryState {
  status: "idle" | "loading" | "ready" | "error";
  districts: LibraryDistrict[];
  personas: LibraryPersonaSummary[];
  /** Full records already fetched (all of them on the static site). */
  full: Record<string, LibraryPersona>;
  load(force?: boolean): Promise<void>;
  fetchPersona(id: string): Promise<LibraryPersona | null>;
}

async function getJson<T>(url: string, init?: RequestInit): Promise<T> {
  const r = await fetch(url, init);
  if (!r.ok) {
    let detail = `${r.status} ${r.statusText}`;
    try {
      const body = (await r.json()) as { detail?: string };
      if (body.detail) detail = body.detail;
    } catch {
      /* not JSON */
    }
    throw new Error(detail);
  }
  return (await r.json()) as T;
}

function summarise(p: LibraryPersona): LibraryPersonaSummary {
  return {
    id: p.id,
    source: p.source,
    districtId: p.districtId,
    districtName: p.districtName,
    regionId: p.regionId,
    gender: p.gender,
    name: p.card?.name ?? p.name,
    role: p.card?.role ?? null,
    place: p.card?.place ?? p.place ?? null,
    emoji: p.card?.emoji ?? null,
    curatedRef: p.curatedRef ?? null,
    basedOn: p.basedOn ?? null,
    createdAt: p.createdAt ?? null,
    version: p.version ?? "",
  };
}

export const usePersonaLibrary = create<LibraryState>((set, get) => ({
  status: "idle",
  districts: [],
  personas: [],
  full: {},

  async load(force = false) {
    if (!force && (get().status === "loading" || get().status === "ready")) return;
    set({ status: "loading" });
    const fromSnapshot = async () => {
      const d = await getJson<{ districts: LibraryDistrict[]; personas: LibraryPersona[] }>(
        assetUrl("data/persona-library.json"),
      );
      set({
        status: "ready",
        districts: d.districts,
        personas: d.personas.map(summarise),
        full: Object.fromEntries(d.personas.map((p) => [p.id, p])),
      });
    };
    try {
      if (STATIC_DATA) return await fromSnapshot();
      const d = await getJson<{ districts: LibraryDistrict[]; personas: LibraryPersonaSummary[] }>(
        apiUrl("/api/persona-library"),
      );
      set({ status: "ready", districts: d.districts, personas: d.personas });
    } catch {
      try {
        await fromSnapshot(); // backend down: fall back to the published snapshot
      } catch {
        set({ status: "error" });
      }
    }
  },

  async fetchPersona(id) {
    const cached = get().full[id];
    if (cached) return cached;
    if (STATIC_DATA) return null;
    try {
      const p = await getJson<LibraryPersona>(
        apiUrl(`/api/persona-library/${encodeURIComponent(id)}`),
      );
      set((s) => ({ full: { ...s.full, [id]: p } }));
      return p;
    } catch {
      return null;
    }
  },
}));

// ── Actions (backend only) ───────────────────────────────────────────────────

const json = (body: unknown, method = "POST"): RequestInit => ({
  method,
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});

export interface GenerateTraits {
  name?: string;
  age?: string;
  occupation?: string;
  community?: string;
  taluk?: string;
  notes?: string;
}

export function generatePersona(
  districtId: string,
  gender: Gender,
  traits: GenerateTraits,
): Promise<LibraryPersona> {
  const clean = Object.fromEntries(Object.entries(traits).filter(([, v]) => v && v.trim()));
  return getJson(
    apiUrl("/api/persona-library/generate"),
    json({ districtId, gender, traits: clean }),
  );
}

export function rebuildCard(persona: LibraryPersona): Promise<PersonaCard> {
  return getJson(apiUrl("/api/persona-library/card"), json({ persona }));
}

export async function saveCustomPersona(persona: LibraryPersona): Promise<LibraryPersona> {
  const editing = persona.source === "custom" && persona.id.startsWith("custom-");
  const saved = await getJson<LibraryPersona>(
    apiUrl(
      editing
        ? `/api/persona-library/custom/${encodeURIComponent(persona.id)}`
        : "/api/persona-library/custom",
    ),
    json(persona, editing ? "PUT" : "POST"),
  );
  usePersonaLibrary.setState((s) => ({ full: { ...s.full, [saved.id]: saved } }));
  await usePersonaLibrary.getState().load(true);
  return saved;
}

export async function deleteCustomPersona(id: string): Promise<void> {
  await getJson(apiUrl(`/api/persona-library/custom/${encodeURIComponent(id)}`), {
    method: "DELETE",
  });
  usePersonaLibrary.setState((s) => {
    const full = { ...s.full };
    delete full[id];
    return { full };
  });
  await usePersonaLibrary.getState().load(true);
}

export function askWithAndWithout(
  persona: LibraryPersona,
  question: string,
  useEvidence: boolean,
  topic: "dropout" | "stunting" = "dropout",
): Promise<AskResult> {
  const body =
    persona.source === "draft"
      ? { persona, question, useEvidence, topic }
      : { personaId: persona.id, question, useEvidence, topic };
  return getJson(apiUrl("/api/persona-library/ask"), json(body));
}
