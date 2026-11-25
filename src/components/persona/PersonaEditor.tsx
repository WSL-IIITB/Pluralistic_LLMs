/**
 * Create or fine-tune a persona: place them (region -> district -> taluk/town), fix any traits,
 * generate a draft from the district's region brief, then edit the text and save it as your own.
 * Fine-tuning an existing persona starts from its traits (re-create) or its text (edit directly);
 * the original is never overwritten -- a fine-tuned copy is saved as a new "custom" persona.
 */

import { Loader2, RefreshCw, Save, Sparkles, Trash2, X } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";

import {
  deleteCustomPersona,
  generatePersona,
  KARNATAKA_REGIONS,
  LIBRARY_LIVE,
  personaCard,
  rebuildCard,
  rgbaCss,
  saveCustomPersona,
  usePersonaLibrary,
  type Gender,
  type GenerateTraits,
  type LibraryPersona,
} from "@/lib/worldview";

const FIELD =
  "w-full rounded-lg border border-panel-border bg-background/60 px-3 py-1.5 text-[12.5px] text-foreground outline-none focus:border-foreground/40";

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block min-w-0">
      <span className="mb-1 block text-[10px] font-medium tracking-wide text-muted-foreground uppercase">
        {label}
      </span>
      {children}
    </label>
  );
}

/** Traits to start a re-creation from: what the persona's card (or saved traits) says. */
function traitsOf(p: LibraryPersona | null): GenerateTraits {
  if (!p) return {};
  const card =
    p.card ?? (p.curatedRef ? personaCard(p.curatedRef.regionId, p.curatedRef.personaId) : null);
  return {
    name: card?.name?.startsWith("The ") ? "" : (card?.name ?? p.traits?.["name"] ?? ""),
    age: card?.ageLabel ?? p.traits?.["age"] ?? "",
    occupation: card?.role ?? p.traits?.["occupation"] ?? "",
    community: card?.community ?? p.traits?.["community"] ?? "",
    taluk: card?.place ?? p.place ?? "",
    notes: "",
  };
}

export function PersonaEditor({
  districtId: initialDistrict,
  gender: initialGender,
  base,
  onSaved,
  onDeleted,
  onClose,
}: {
  districtId: string;
  gender: Gender;
  /** Persona being fine-tuned (null = create a new one). */
  base: LibraryPersona | null;
  onSaved: (p: LibraryPersona) => void;
  /** A custom persona was deleted (the panel moves off it). */
  onDeleted: () => void;
  onClose: () => void;
}) {
  const districts = usePersonaLibrary((s) => s.districts);
  const [districtId, setDistrictId] = useState(initialDistrict);
  const district = districts.find((d) => d.districtId === districtId);
  const [regionId, setRegionId] = useState(district?.regionId ?? KARNATAKA_REGIONS[0]!.id);
  const [gender, setGender] = useState<Gender>(initialGender);
  const [traits, setTraits] = useState<GenerateTraits>(() => traitsOf(base));
  const editingCustom = base?.source === "custom";
  // Editing a saved custom persona opens straight on its text.
  const [draft, setDraft] = useState<LibraryPersona | null>(() =>
    editingCustom ? structuredClone(base) : null,
  );
  const [busy, setBusy] = useState<null | "generate" | "card" | "save" | "delete">(null);
  const [error, setError] = useState<string | null>(null);
  const region = KARNATAKA_REGIONS.find((r) => r.id === regionId)!;
  const regionDistricts = useMemo(
    () => districts.filter((d) => d.regionId === regionId),
    [districts, regionId],
  );

  const root = useRef<HTMLDivElement>(null);
  useEffect(() => {
    root.current?.scrollIntoView({ behavior: "smooth", block: "start" });
  }, []);

  if (!LIBRARY_LIVE)
    return (
      <p className="rounded-xl border border-dashed border-panel-border px-4 py-3 text-[12px] text-muted-foreground">
        Creating personas needs the analysis backend; this published copy of the dashboard is
        read-only.
      </p>
    );

  const run = async (kind: NonNullable<typeof busy>, fn: () => Promise<void>) => {
    setBusy(kind);
    setError(null);
    try {
      await fn();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(null);
    }
  };

  const generate = () =>
    run("generate", async () => {
      const d = await generatePersona(districtId, gender, traits);
      setDraft({ ...d, basedOn: base?.id ?? null });
    });

  const editTextDirectly = () => {
    if (!base) return;
    const source =
      base.card ??
      (base.curatedRef ? personaCard(base.curatedRef.regionId, base.curatedRef.personaId) : null);
    // A curated card carries the recorded intro; a fine-tuned copy keeps only the person.
    let card: typeof source = null;
    if (source) {
      const { intro: _intro, ...rest } = structuredClone(source);
      card = rest;
    }
    setDraft({
      ...structuredClone(base),
      id: "draft",
      source: "draft",
      card,
      name: card?.name ?? base.name,
      place: base.place || card?.place || "",
      basedOn: base.id,
    });
  };

  const setTopic = (key: string, profile: string) =>
    setDraft(
      (d) => d && { ...d, topics: d.topics.map((t) => (t.key === key ? { ...t, profile } : t)) },
    );

  const save = () =>
    run("save", async () => {
      if (!draft) return;
      const card = draft.card
        ? { ...draft.card, name: draft.name, place: draft.place || draft.card.place }
        : null;
      const saved = await saveCustomPersona({ ...draft, districtId, gender, card });
      onSaved(saved);
    });

  return (
    <div
      ref={root}
      className="scroll-mt-4 space-y-4 rounded-2xl border p-4"
      style={{ borderColor: rgbaCss(region.color, 0.6), background: rgbaCss(region.color, 0.05) }}
    >
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="label-micro">
            {editingCustom
              ? "Edit your persona"
              : base
                ? "Fine-tune this persona"
                : "Create a persona"}
          </p>
          <p className="mt-1 text-[12px] leading-snug text-muted-foreground">
            {base && !editingCustom
              ? "Change where they live or any trait and re-create them, or edit their text directly. The original stays as it is; your version is saved as a new persona."
              : "Place a person in a district, fix any traits you care about, and let the model write the rest from the region's research brief. Review and edit before saving."}
          </p>
        </div>
        <button
          type="button"
          onClick={onClose}
          aria-label="Close"
          className="rounded-full p-1 text-muted-foreground hover:text-foreground"
        >
          <X className="size-4" />
        </button>
      </div>

      {!editingCustom && (
        <>
          <div className="grid gap-3 @xl:grid-cols-4">
            <Field label="Region">
              <select
                className={FIELD}
                value={regionId}
                onChange={(e) => {
                  setRegionId(e.target.value);
                  const first = districts.find((d) => d.regionId === e.target.value);
                  if (first) setDistrictId(first.districtId);
                }}
              >
                {KARNATAKA_REGIONS.map((r) => (
                  <option key={r.id} value={r.id}>
                    {r.shortName}
                  </option>
                ))}
              </select>
            </Field>
            <Field label="District">
              <select
                className={FIELD}
                value={districtId}
                onChange={(e) => setDistrictId(e.target.value)}
              >
                {regionDistricts.map((d) => (
                  <option key={d.districtId} value={d.districtId}>
                    {d.name}
                  </option>
                ))}
              </select>
            </Field>
            <Field label="Taluk / town / village">
              <input
                className={FIELD}
                value={traits.taluk ?? ""}
                placeholder="optional, e.g. Hunsur"
                onChange={(e) => setTraits({ ...traits, taluk: e.target.value })}
              />
            </Field>
            <Field label="Gender">
              <select
                className={FIELD}
                value={gender}
                onChange={(e) => setGender(e.target.value as Gender)}
              >
                <option value="male">Man</option>
                <option value="female">Woman</option>
              </select>
            </Field>
          </div>
          <div className="grid gap-3 @xl:grid-cols-4">
            <Field label="Name">
              <input
                className={FIELD}
                value={traits.name ?? ""}
                placeholder="optional"
                onChange={(e) => setTraits({ ...traits, name: e.target.value })}
              />
            </Field>
            <Field label="Age">
              <input
                className={FIELD}
                value={traits.age ?? ""}
                placeholder="optional"
                onChange={(e) => setTraits({ ...traits, age: e.target.value })}
              />
            </Field>
            <Field label="Occupation">
              <input
                className={FIELD}
                value={traits.occupation ?? ""}
                placeholder="optional"
                onChange={(e) => setTraits({ ...traits, occupation: e.target.value })}
              />
            </Field>
            <Field label="Community">
              <input
                className={FIELD}
                value={traits.community ?? ""}
                placeholder="optional"
                onChange={(e) => setTraits({ ...traits, community: e.target.value })}
              />
            </Field>
          </div>
          <Field label="Anything else about them">
            <textarea
              className={`${FIELD} min-h-[52px] resize-y`}
              value={traits.notes ?? ""}
              placeholder="optional, e.g. returned from Gulf work; runs a small kirana shop; first in family to go to college"
              onChange={(e) => setTraits({ ...traits, notes: e.target.value })}
            />
          </Field>
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              onClick={generate}
              disabled={!!busy}
              className="flex items-center gap-1.5 rounded-full px-4 py-2 text-[12px] font-medium text-foreground disabled:opacity-50"
              style={{ backgroundColor: rgbaCss(region.color, 0.35) }}
            >
              {busy === "generate" ? (
                <Loader2 className="size-3.5 animate-spin" />
              ) : (
                <Sparkles className="size-3.5" />
              )}
              {draft
                ? "Re-create from these traits"
                : base
                  ? "Re-create from these traits"
                  : "Generate persona"}
            </button>
            {base && !draft && (
              <button
                type="button"
                onClick={editTextDirectly}
                className="rounded-full border border-panel-border px-4 py-2 text-[12px] font-medium text-foreground hover:bg-secondary"
              >
                Edit their text directly
              </button>
            )}
          </div>
          {busy === "generate" && (
            <p className="text-[11.5px] text-muted-foreground">
              Writing the persona and distilling their card — about a minute…
            </p>
          )}
        </>
      )}

      {error && (
        <p className="rounded-xl border border-destructive/40 px-4 py-2.5 text-[12px] text-destructive">
          {error}
        </p>
      )}

      {draft && (
        <div className="space-y-3 border-t border-panel-border pt-4">
          <p className="label-micro">Review and edit</p>
          <div className="grid gap-3 @xl:grid-cols-2">
            <Field label="Name">
              <input
                className={FIELD}
                value={draft.name}
                onChange={(e) => setDraft({ ...draft, name: e.target.value })}
              />
            </Field>
            <Field label="Place">
              <input
                className={FIELD}
                value={draft.place ?? ""}
                onChange={(e) => setDraft({ ...draft, place: e.target.value })}
              />
            </Field>
          </div>
          <Field label="Who they are">
            <textarea
              className={`${FIELD} min-h-[60px] resize-y`}
              value={draft.definition}
              onChange={(e) => setDraft({ ...draft, definition: e.target.value })}
            />
          </Field>
          {draft.topics.map((t) => (
            <Field key={t.key} label={t.label}>
              <textarea
                className={`${FIELD} min-h-[110px] resize-y leading-relaxed`}
                value={t.profile}
                onChange={(e) => setTopic(t.key, e.target.value)}
              />
            </Field>
          ))}
          <div className="flex flex-wrap items-center gap-2">
            <button
              type="button"
              onClick={save}
              disabled={!!busy}
              className="flex items-center gap-1.5 rounded-full px-4 py-2 text-[12px] font-medium text-foreground disabled:opacity-50"
              style={{ backgroundColor: rgbaCss(region.color, 0.35) }}
            >
              {busy === "save" ? (
                <Loader2 className="size-3.5 animate-spin" />
              ) : (
                <Save className="size-3.5" />
              )}
              {editingCustom ? "Save changes" : "Save as my persona"}
            </button>
            <button
              type="button"
              disabled={!!busy}
              onClick={() =>
                run("card", async () => {
                  const card = await rebuildCard({ ...draft, districtId, gender });
                  setDraft({ ...draft, card });
                })
              }
              className="flex items-center gap-1.5 rounded-full border border-panel-border px-4 py-2 text-[12px] font-medium text-foreground hover:bg-secondary disabled:opacity-50"
            >
              {busy === "card" ? (
                <Loader2 className="size-3.5 animate-spin" />
              ) : (
                <RefreshCw className="size-3.5" />
              )}
              Rebuild card from this text
            </button>
            {editingCustom && (
              <button
                type="button"
                disabled={!!busy}
                onClick={() =>
                  run("delete", async () => {
                    if (!window.confirm(`Delete ${draft.name}? This cannot be undone.`)) return;
                    await deleteCustomPersona(draft.id);
                    onDeleted();
                  })
                }
                className="ml-auto flex items-center gap-1.5 rounded-full px-3 py-2 text-[12px] text-destructive hover:bg-destructive/10 disabled:opacity-50"
              >
                <Trash2 className="size-3.5" /> Delete
              </button>
            )}
          </div>
          <p className="text-[10.5px] leading-snug text-muted-foreground">
            The card (household, day in life, topic highlights) is distilled from the text. After
            editing the text, rebuild it so they match.
          </p>
        </div>
      )}
    </div>
  );
}
