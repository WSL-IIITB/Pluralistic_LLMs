/**
 * The "Key findings" summary for the stunting topic -- the counterpart of keyFindings.ts for dropout.
 *
 * The wording is authored here once; every number is computed from the NITI stunting model, the media research and
 * the saved stunting run when the page renders, so the summary follows the target slider and cannot drift from the
 * panels below it. Nothing in this file is a literal statistic.
 */

import type { PersonaSummary } from "./aggregate";
import { KARNATAKA_REGIONS } from "./karnataka";
import type { KeyFinding } from "./keyFindings";
import { prescribe, type StuntingModel, type StuntingSettings } from "./stunting";
import {
  STUNTING_CATEGORY_LABEL,
  type StuntingCategory,
  type StuntingResearch,
} from "./stuntingResearch";

const pct = (x: number, digits = 0) => `${(x * 100).toFixed(digits)}%`;
const lower = (s: string) => s.charAt(0).toLowerCase() + s.slice(1);
const shortName = (s: string) => s.split(" (")[0]!;

function joinList(items: string[]): string {
  if (items.length <= 1) return items.join("");
  return `${items.slice(0, -1).join(", ")} and ${items[items.length - 1]}`;
}

/** A strong-evidence reason in one district whose detail contains `needle`, if the research still has it. */
function strongReason(
  research: Record<string, StuntingResearch>,
  districtId: string,
  needle: string,
) {
  const f = research[districtId];
  const r = f?.reasons.find(
    (x) => x.evidence === "strong" && x.detail.toLowerCase().includes(needle.toLowerCase()),
  );
  return f && r ? { f, r } : null;
}

export interface StuntingKeyFindingsInput {
  model: StuntingModel;
  research: Record<string, StuntingResearch>;
  settings: Pick<StuntingSettings, "reduceBy" | "priorityBucket" | "priorityWeight">;
  persona: PersonaSummary | null;
}

export function buildStuntingKeyFindings({
  model,
  research,
  settings,
  persona,
}: StuntingKeyFindingsInput): KeyFinding[] {
  const out: KeyFinding[] = [];
  const files = Object.values(research);
  const n = files.length;
  const info = Object.fromEntries(model.factors.map((f) => [f.name, f]));
  const regionOf = (id: string) => research[id]?.regionId ?? null;
  const regionName = (id: string) => KARNATAKA_REGIONS.find((r) => r.id === id)?.shortName ?? id;
  const name = (id: string) => shortName(research[id]?.name ?? model.districts[id]?.area ?? id);
  const withData = Object.values(model.districts).filter((d) => d.stunting != null);

  // 1. Reach and how solid it is.
  const cov = { rich: 0, moderate: 0, thin: 0 };
  files.forEach((f) => (cov[f.coverage] += 1));
  const sources = files.reduce((a, f) => a + f.sources.length, 0);
  out.push({
    id: "reach",
    lead: "What we looked at.",
    text:
      `Under-5 stunting (NFHS-6) for ${withData.length} of Karnataka's ${model.source.karnatakaDistricts} districts, ` +
      `with the NITI team's model of ${model.factors.length} factors behind it, and media and official reports for ` +
      `${n} districts from ${sources} sources. Coverage is ${cov.rich + cov.moderate} districts moderate or better ` +
      `and ${cov.thin} thin — every number in a claim was checked against the page it cites.`,
  });

  // 2. How much stunting, and where.
  const rated = KARNATAKA_REGIONS.map((r) => {
    const v = withData.filter((d) => regionOf(d.districtId) === r.id).map((d) => d.stunting!);
    return {
      id: r.id,
      name: r.shortName,
      avg: v.length ? v.reduce((a, b) => a + b, 0) / v.length : null,
    };
  })
    .filter((r): r is { id: string; name: string; avg: number } => r.avg != null)
    .sort((a, b) => a.avg - b.avg);
  const hi = model.statewide.highest;
  const lo = model.statewide.lowest;
  if (hi && lo && rated.length >= 2) {
    const top = rated[rated.length - 1]!;
    const bottom = rated[0]!;
    const ratio = hi.value / lo.value;
    out.push({
      id: "where",
      lead: "Where children are stunted.",
      text:
        `About ${Math.round(model.statewide.mean ?? 0)} in 100 children under five are stunted in the average ` +
        `district, but it ranges from ${hi.value.toFixed(1)}% in ${name(hi.districtId)} to ${lo.value.toFixed(1)}% ` +
        `in ${name(lo.districtId)} — ${ratio >= 2 ? `${ratio.toFixed(1)} times as high` : "a wide gap"}. ` +
        `${top.name} averages ${top.avg.toFixed(1)}%, ${bottom.name} ${bottom.avg.toFixed(1)}%.`,
      action: { kind: "region", regionId: top.id, label: `See ${top.name}` },
    });
  }

  // 3. What the news says drives it.
  const catDistricts = new Map<StuntingCategory, Set<string>>();
  for (const f of files)
    for (const r of f.reasons) {
      if (r.category === "other") continue;
      (
        catDistricts.get(r.category) ?? catDistricts.set(r.category, new Set()).get(r.category)!
      ).add(f.districtId);
    }
  const cats = [...catDistricts.entries()].sort((a, b) => b[1].size - a[1].size).slice(0, 4);
  if (cats.length) {
    out.push({
      id: "drivers",
      lead: "Why children are stunted, in the news.",
      text:
        `The reasons that recur across the state are ` +
        joinList(
          cats.map(
            ([c, ds]) => `${lower(STUNTING_CATEGORY_LABEL[c])} (${ds.size} of ${n} districts)`,
          ),
        ) +
        `. Anaemic, undernourished mothers — often married and pregnant young — and households too poor to feed ` +
        `children well come up again and again; anganwadis and referrals that miss children are the main ` +
        `service gap reported.`,
    });
  }

  // 4. What the model asks for, at the chosen target.
  const top: Record<string, number> = {};
  let atLimit = 0;
  let cells = 0;
  for (const d of withData) {
    const { factors } = prescribe(model, d, settings);
    if (factors[0]) top[factors[0].name] = (top[factors[0].name] ?? 0) + 1;
    atLimit += factors.filter((f) => f.atLimit).length;
    cells += factors.length;
  }
  const leaders = Object.entries(top).sort((a, b) => b[1] - a[1]);
  if (leaders.length) {
    const [first, k] = leaders[0]!;
    const second = leaders[1];
    out.push({
      id: "model",
      lead: "What the data model asks for.",
      text:
        `To cut stunting by ${Math.round(settings.reduceBy * 100)}%, the factor that would have to move furthest ` +
        `is ${lower(info[first]?.short ?? first)} in ${k} of ${withData.length} districts` +
        (second ? `, then ${lower(info[second[0]]?.short ?? second[0])} in ${second[1]}` : "") +
        `. ` +
        (atLimit
          ? `${atLimit} of ${cells} factor targets hit the 0–100% limit, so some factors cannot deliver their ` +
            `share on their own.`
          : `Every factor target stays within 0–100%.`) +
        ` Move the target slider below to see how this changes.`,
    });
  }

  // 5. News vs data: is there local evidence for the model's top factors?
  const why = new Map<string, { supported: number; partly: number; none: number }>();
  for (const f of files)
    for (const w of f.modelFactorWhy) {
      const t = why.get(w.factor) ?? { supported: 0, partly: 0, none: 0 };
      if (w.verdict === "supported") t.supported += 1;
      else if (w.verdict === "partly") t.partly += 1;
      else t.none += 1;
      why.set(w.factor, t);
    }
  if (why.size) {
    const tot = [...why.values()].reduce(
      (a, t) => ({ s: a.s + t.supported, p: a.p + t.partly, x: a.x + t.none }),
      { s: 0, p: 0, x: 0 },
    );
    const silent = [...why.entries()]
      .filter(([, t]) => t.supported + t.partly === 0 && t.none >= 3)
      .map(([f]) => lower(info[f]?.short ?? f));
    const best = [...why.entries()].sort((a, b) => b[1].supported - a[1].supported)[0];
    out.push({
      id: "official",
      lead: "News vs data.",
      text:
        `We checked the model's top three factors in each district against local reporting: ` +
        `${tot.s} had local evidence, ${tot.p} partly and ${tot.x} none. ` +
        (best && best[1].supported
          ? `The best supported is ${lower(info[best[0]]?.short ?? best[0])} (${best[1].supported} districts). `
          : "") +
        (silent.length
          ? `Nobody reports on ${joinList(silent)} as a cause of stunting, though the model leans on it. `
          : "") +
        `Silence means it is not what reporters and officials discuss — not that it doesn't matter.`,
      action: { kind: "tab", tab: "Divergence", label: "Story vs data" },
    });
  }

  // 6. Best-evidenced examples, pulled from the research rather than typed in.
  const yadgir = strongReason(research, "29-580", "screened");
  const raichur = strongReason(research, "29-559", "anaemi");
  const bits: string[] = [];
  if (raichur) bits.push(`in ${name("29-559")}, ${lower(raichur.r.detail.replace(/\.$/, ""))}`);
  if (yadgir) bits.push(`in ${name("29-580")}, ${lower(yadgir.r.detail.replace(/\.$/, ""))}`);
  if (bits.length) {
    const target = raichur ?? yadgir!;
    out.push({
      id: "examples",
      lead: "What the strongest evidence looks like.",
      text:
        `${bits[0]!.charAt(0).toUpperCase() + bits[0]!.slice(1)}${bits[1] ? `; ${bits[1]}` : ""}. ` +
        `The problem is well documented; getting care and food to these mothers and children is where it breaks down.`,
      action: {
        kind: "district",
        districtId: target.f.districtId,
        regionId: target.f.regionId,
        label: `See ${name(target.f.districtId)}`,
      },
    });
  }

  // 7. Persona analysis (from the saved stunting run).
  if (persona) {
    out.push({
      id: "persona",
      lead: "One answer does not fit all regions.",
      text:
        `Answers written in a region's own voice match a generic Karnataka answer ${pct(persona.averageMatch)} ` +
        `on average` +
        (persona.lowest && persona.highest
          ? `, from ${pct(persona.lowest.match)} (${regionName(persona.lowest.regionId)}) to ` +
            `${pct(persona.highest.match)} (${regionName(persona.highest.regionId)})`
          : "") +
        `. A man's and a woman's voice in the same region differ by ${Math.round(persona.genderGap * 100)} ` +
        `percentage points on average.`,
      action: { kind: "tab", tab: "Data", label: "See the comparison" },
    });
  }

  // 8. How to read all this.
  out.push({
    id: "caveats",
    lead: "Read with care.",
    text:
      `The model is a correlation across districts, not proof that changing a factor would change stunting. ` +
      `Some news figures are from NFHS-5 while the model uses NFHS-6, so they can differ for the same district` +
      (model.source.missing.length
        ? `; the workbook has no figures for ${joinList(model.source.missing)}`
        : "") +
      `. The personas are composites, not real people. ${cov.thin} districts have thin coverage.`,
  });

  return out;
}
