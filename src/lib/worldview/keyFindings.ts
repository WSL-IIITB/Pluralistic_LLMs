/**
 * The "Key findings" summary shown at the top of the dashboard.
 *
 * The wording is authored here once; every number is computed from the research data
 * (aggregate.ts) when the page renders, so the summary cannot drift from the panels below it
 * when the research changes. Nothing in this file is a literal statistic.
 */

import {
  keyFact,
  type PersonaSummary,
  type ResearchAggregate,
  type ResearchMap,
} from "./aggregate";
import { CATEGORY_LABEL } from "./reasonCategories";
import type { DistrictProfile } from "./districtProfiles";
import { KARNATAKA_REGIONS } from "./karnataka";

export interface KeyFinding {
  id: string;
  /** Bold lead-in. */
  lead: string;
  text: string;
  /** Optional click target that moves the map / opens a tab. */
  action?:
    | { kind: "region"; regionId: string; label: string }
    | { kind: "district"; districtId: string; regionId: string; label: string }
    | { kind: "tab"; tab: "Divergence" | "Data" | "Personas"; label: string };
}

const pct = (x: number, digits = 0) => `${(x * 100).toFixed(digits)}%`;
const points = (x: number) => `${Math.round(x * 100)} percentage points`;
const lower = (s: string) => s.charAt(0).toLowerCase() + s.slice(1);

function joinList(items: string[]): string {
  if (items.length <= 1) return items.join("");
  return `${items.slice(0, -1).join(", ")} and ${items[items.length - 1]}`;
}

export interface KeyFindingsInput {
  agg: ResearchAggregate;
  research: ResearchMap;
  /** Average casefile dropout rate per region (see regionRatesFrom). */
  regionRates: Record<string, { avg: number | null; n: number }>;
  persona: PersonaSummary | null;
  /** Casefile dropout rates per district id. */
  byId: Record<string, DistrictProfile>;
}

export function buildKeyFindings({
  agg,
  research,
  regionRates,
  persona,
  byId,
}: KeyFindingsInput): KeyFinding[] {
  const out: KeyFinding[] = [];
  const regionName = (id: string) => KARNATAKA_REGIONS.find((r) => r.id === id)?.shortName ?? id;

  // 1. Reach and how solid it is.
  out.push({
    id: "reach",
    lead: "What we looked at.",
    text:
      `${agg.n} Karnataka districts in ${KARNATAKA_REGIONS.length} regions, using ${agg.sources} sources from ` +
      `${agg.outlets} outlets (${agg.headlines} news items, plus government and NGO reports). ` +
      `Evidence is ${agg.coverage["moderate"] ?? 0} districts at moderate coverage and ` +
      `${agg.coverage["thin"] ?? 0} thin — every figure was checked against the page it cites.`,
  });

  // 2. What drives dropout.
  const top = agg.categories.slice(0, 4);
  if (top.length) {
    out.push({
      id: "drivers",
      lead: "Why students leave.",
      text:
        `The reasons that recur across the state are ` +
        joinList(
          top.map(
            (c) => `${lower(CATEGORY_LABEL[c.category])} (${c.districts} of ${agg.n} districts)`,
          ),
        ) +
        `. Money and work at home, early marriage of girls, and gaps in schooling itself (exams, staffing, ` +
        `tracking children) show up almost everywhere; migration and local customs matter in specific places.`,
    });
  }

  // 3. Regional pattern.
  const rated = KARNATAKA_REGIONS.filter((r) => regionRates[r.id]?.avg != null)
    .map((r) => ({ id: r.id, name: r.shortName, avg: regionRates[r.id]!.avg! }))
    .sort((a, b) => a.avg - b.avg);
  if (rated.length >= 2) {
    const lo = rated[0]!;
    const hi = rated[rated.length - 1]!;
    const topOf = (id: string) => {
      const best = Object.entries(agg.regionCats[id] ?? {})
        .filter(([cat]) => cat !== "other")
        .sort((a, b) => b[1] - a[1])[0];
      return best ? lower(CATEGORY_LABEL[best[0] as keyof typeof CATEGORY_LABEL] ?? best[0]) : null;
    };
    const veryLow = Object.values(byId)
      .filter((d) => typeof d.dropoutRate === "number" && d.dropoutRate < 3)
      .map((d) => research[d.districtId]?.name)
      .filter((n): n is string => !!n);
    out.push({
      id: "regions",
      lead: "It is not one story.",
      text:
        `Average dropout rates in the casefile run from ${lo.avg.toFixed(1)}% in ${lo.name} to ` +
        `${hi.avg.toFixed(1)}% in ${hi.name}. ` +
        (topOf(hi.id) && topOf(hi.id) === topOf(lo.id)
          ? `The most-documented reason is the same in both: ${topOf(hi.id)}.`
          : `The most-documented reason in ${hi.name} is ${topOf(hi.id) ?? "mixed"}; in ${lo.name} it is ${topOf(lo.id) ?? "mixed"}.`) +
        (veryLow.length
          ? ` The casefile's lowest rates (${joinList(veryLow)}) are not explained by any source we found.`
          : ""),
      action: { kind: "region", regionId: hi.id, label: `See ${hi.name}` },
    });
  }

  // 4. Best-evidenced examples, pulled from the data rather than typed in.
  const oosc = keyFact(research, "29-579", "rural-development survey");
  const raichur = keyFact(research, "29-559", "rescued");
  const bits: string[] = [];
  if (oosc)
    bits.push(`in Kalaburagi two departments counted out-of-school children as ${oosc.value}`);
  if (raichur)
    bits.push(
      `Raichur reported ${raichur.value} child labourers rescued from cotton fields in a year`,
    );
  if (bits.length) {
    out.push({
      id: "examples",
      lead: "What the strongest evidence looks like.",
      text:
        `${bits[0]!.charAt(0).toUpperCase() + bits[0]!.slice(1)}${bits[1] ? `; ${bits[1]}` : ""}. ` +
        `Official counts and on-the-ground reports often disagree, which is itself a finding.`,
      ...(oosc
        ? {
            action: {
              kind: "district" as const,
              districtId: "29-579",
              regionId: research["29-579"]!.regionId,
              label: "See Kalaburagi",
            },
          }
        : {}),
    });
  }

  // 5. UIDAI / NITI factors.
  const rows = (["state", "district"] as const).flatMap((m) => Object.entries(agg.verdicts[m]));
  const total = rows.reduce((s, [, n]) => s + n, 0);
  if (total) {
    const sum = (v: string) => rows.filter(([k]) => k === v).reduce((s, [, n]) => s + n, 0);
    out.push({
      id: "official",
      lead: "The statistical factors.",
      text:
        `UIDAI/NITI name one dominant factor per district (household sanitation statewide; school-level factors ` +
        `district by district). We tested those ${total} claims against local evidence: ${sum("no-evidence")} ` +
        `found nothing either way, ${sum("unclear")} were unclear, ${sum("supports")} supported and ` +
        `${sum("contradicts")} contradicted. Silence means these are not what reporters and officials discuss — ` +
        `not that they don't matter.`,
      action: { kind: "tab", tab: "Divergence", label: "Story vs UIDAI/NITI" },
    });
  }

  // 6. Persona analysis (from the saved run).
  if (persona) {
    out.push({
      id: "persona",
      lead: "One answer does not fit all regions.",
      text:
        `Answers written in a region's own voice match a generic Karnataka answer only ${pct(persona.averageMatch)} ` +
        `on average` +
        (persona.lowest && persona.highest
          ? `, from ${pct(persona.lowest.match)} (${regionName(persona.lowest.regionId)}) to ` +
            `${pct(persona.highest.match)} (${regionName(persona.highest.regionId)})`
          : "") +
        `. A man's and a woman's voice in the same region differ by only ${points(persona.genderGap)} on average, ` +
        `so region matters more than gender here.`,
      action: { kind: "tab", tab: "Data", label: "See the comparison" },
    });
  }

  // 7. How to read all this.
  out.push({
    id: "caveats",
    lead: "Read with care.",
    text:
      `This maps the evidence we could find; it is not a measurement. Some figures are statewide or regional, ` +
      `not district. SSLC pass rates are not dropout rates, and 2025 and 2026 results are not comparable. ` +
      `The personas are composites, not real people. ${agg.coverage["thin"] ?? 0} districts have thin coverage.`,
  });

  return out;
}
