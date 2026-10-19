/**
 * Aggregates across all 30 district research files (and the saved persona analysis) into the
 * numbers the dashboard shows. Pure functions + one hook, shared by the Overview panel and the
 * Key findings summary so the two can never disagree.
 */

import { useEffect, useState } from "react";

import {
  fetchAllDistrictResearch,
  type DistrictResearch,
  type ReasonCategory,
} from "./districtResearch";
import { KARNATAKA_REGIONS } from "./karnataka";
import type { DistrictProfile } from "./districtProfiles";
import type { PersonaSimilarityRegion } from "./types";

export type ResearchMap = Record<string, DistrictResearch>;

export const EVIDENCE_WEIGHT = { strong: 3, moderate: 2, thin: 1 } as const;

export interface StrongFinding {
  district: string;
  id: string;
  regionId: string;
  factor: string;
  category: ReasonCategory;
  detail: string;
}

export interface ResearchAggregate {
  /** Districts researched. */
  n: number;
  /** Reason categories, most widespread first. `districts` = how many districts document it. */
  categories: { category: ReasonCategory; districts: number; score: number }[];
  /** regionId -> category -> evidence-weighted score. */
  regionCats: Record<string, Record<string, number>>;
  strong: StrongFinding[];
  /** UIDAI/NITI factor verdict tallies per method. */
  verdicts: Record<"state" | "district", Record<string, number>>;
  sources: number;
  outlets: number;
  headlines: number;
  coverage: Record<string, number>;
}

export function aggregateResearch(research: ResearchMap): ResearchAggregate {
  const districts = Object.values(research);
  const catDistricts: Record<string, Set<string>> = {};
  const catScore: Record<string, number> = {};
  const regionCats: Record<string, Record<string, number>> = {};
  const strong: StrongFinding[] = [];

  for (const d of districts) {
    for (const r of d.reasons) {
      (catDistricts[r.category] ??= new Set()).add(d.districtId);
      catScore[r.category] = (catScore[r.category] ?? 0) + EVIDENCE_WEIGHT[r.evidence];
      const rc = (regionCats[d.regionId] ??= {});
      rc[r.category] = (rc[r.category] ?? 0) + EVIDENCE_WEIGHT[r.evidence];
      if (r.evidence === "strong")
        strong.push({
          district: d.name,
          id: d.districtId,
          regionId: d.regionId,
          factor: r.factor,
          category: r.category,
          detail: r.detail,
        });
    }
  }
  const categories = Object.keys(catDistricts)
    .map((c) => ({
      category: c as ReasonCategory,
      districts: catDistricts[c]!.size,
      score: catScore[c] ?? 0,
    }))
    .sort((a, b) => b.districts - a.districts || b.score - a.score);

  const verdicts: ResearchAggregate["verdicts"] = { state: {}, district: {} };
  for (const d of districts)
    for (const c of d.officialFactorCheck ?? [])
      verdicts[c.method][c.verdict] = (verdicts[c.method][c.verdict] ?? 0) + 1;

  const urls = new Set<string>();
  const outlets = new Set<string>();
  let headlines = 0;
  for (const d of districts) {
    headlines += d.headlines.length;
    for (const s of d.sources) {
      urls.add(s.url);
      outlets.add(s.outlet);
    }
  }
  const coverage: Record<string, number> = { moderate: 0, thin: 0, rich: 0 };
  for (const d of districts) coverage[d.coverage] = (coverage[d.coverage] ?? 0) + 1;

  return {
    n: districts.length,
    categories,
    regionCats,
    strong,
    verdicts,
    sources: urls.size,
    outlets: outlets.size,
    headlines,
    coverage,
  };
}

/** Average casefile dropout rate and district count per region. */
export function regionRatesFrom(
  byId: Record<string, DistrictProfile>,
): Record<string, { avg: number | null; n: number }> {
  const out: Record<string, { avg: number | null; n: number }> = {};
  for (const r of KARNATAKA_REGIONS) {
    const inRegion = Object.values(byId).filter((d) => d.regionId === r.id);
    const rates = inRegion
      .map((d) => d.dropoutRate)
      .filter((x): x is number => typeof x === "number");
    out[r.id] = {
      avg: rates.length ? rates.reduce((a, b) => a + b, 0) / rates.length : null,
      n: inRegion.length,
    };
  }
  return out;
}

export interface PersonaSummary {
  /** Mean over regions of the average male/female similarity to the generic answer (0-1). */
  averageMatch: number;
  /** Highest minus lowest regional match (0-1). */
  regionalSpread: number;
  /** Mean absolute male-female difference (0-1). */
  genderGap: number;
  lowest: { regionId: string; regionName: string; match: number } | null;
  highest: { regionId: string; regionName: string; match: number } | null;
}

/** Summary of the saved persona-similarity run; null if it has no usable regions. */
export function summarisePersonaSimilarity(
  rows: Record<string, PersonaSimilarityRegion>,
): PersonaSummary | null {
  const ok = Object.values(rows).filter(
    (r) => r.status === "ok" && r.maleSimilarity !== undefined && r.femaleSimilarity !== undefined,
  );
  if (!ok.length) return null;
  const matches = ok.map((r) => ({
    regionId: r.regionId,
    regionName: r.regionName,
    match: ((r.maleSimilarity ?? 0) + (r.femaleSimilarity ?? 0)) / 2,
  }));
  const sorted = [...matches].sort((a, b) => a.match - b.match);
  const gaps = ok.map((r) => Math.abs((r.maleSimilarity ?? 0) - (r.femaleSimilarity ?? 0)));
  return {
    averageMatch: matches.reduce((s, m) => s + m.match, 0) / matches.length,
    regionalSpread: sorted[sorted.length - 1]!.match - sorted[0]!.match,
    genderGap: gaps.reduce((s, g) => s + g, 0) / gaps.length,
    lowest: sorted[0] ?? null,
    highest: sorted[sorted.length - 1] ?? null,
  };
}

/** Loads every district's research once (re-used by whichever component asks first). */
export function useAllResearch(): ResearchMap | null {
  const [data, setData] = useState<ResearchMap | null>(null);
  useEffect(() => {
    let alive = true;
    void fetchAllDistrictResearch().then((r) => alive && setData(r));
    return () => {
      alive = false;
    };
  }, []);
  return data;
}

/** Looks up one key fact by district id and a fragment of its label; undefined if absent. */
export function keyFact(
  research: ResearchMap,
  districtId: string,
  labelIncludes: string,
): { label: string; value: string } | undefined {
  return research[districtId]?.keyFacts.find((f) =>
    f.label.toLowerCase().includes(labelIncludes.toLowerCase()),
  );
}
