/**
 * The stunting topic (second study, beside dropout): NITI's PROVISIONAL prescriptive model for under-5 stunting in
 * Karnataka, district by district -- GET /api/stunting, or public/data/niti-stunting.json on the static site
 * (built by backend/app/stunting.py from the team's Tableau workbook).
 */

import { useEffect, useState } from "react";
import { create } from "zustand";

import { cachedJson } from "./api";

export interface StuntingFactorInfo {
  name: string;
  column: string;
  bucket: string;
  coefficient: number;
  pearson: number | null;
  directionMatch: string;
  better: "higher" | "lower";
  short: string;
  measures: string;
  karnataka: { min: number; median: number; max: number };
}

export interface StuntingDistrictFactor {
  name: string;
  bucket: string;
  value: number;
  /** Value the model prescribes for this factor's share of the target cut (0-100). */
  prescribed: number;
  /** |prescribed - value| as % of today's value. */
  change: number | null;
  /** This factor's share of the cut, in %. */
  share: number;
  /** The unclamped prescription fell outside 0-100%. */
  atLimit: boolean;
  /** Rank among Karnataka's districts, 1 = best in the direction the model links to less stunting. */
  rank: number;
}

export interface StuntingDistrict {
  area: string;
  districtId: string;
  stunting: number | null;
  target: number | null;
  rankHighest?: number;
  /** Sorted by change, largest first (the dashboard's order). */
  factors: StuntingDistrictFactor[];
}

export interface StuntingModel {
  version: number;
  topic: "stunting";
  outcome: { name: string; short: string; unit: string; better: "lower" };
  source: {
    file: string;
    from: string;
    dataset: string;
    provisional: boolean;
    karnatakaDistricts: number;
    withData: number;
    missing: string[];
  };
  method: {
    model: string;
    target: string;
    allocation: string;
    prescribed: string;
    caveat: string;
    reduceBy: number;
    intercept: number;
    confidence: number | null;
  };
  factors: StuntingFactorInfo[];
  statewide: {
    mean: number | null;
    median: number | null;
    highest: { districtId: string; value: number } | null;
    lowest: { districtId: string; value: number } | null;
  };
  districts: Record<string, StuntingDistrict>;
}

const load = cachedJson<StuntingModel>("/api/stunting");

/** The stunting model; undefined while loading, null if it could not be loaded. */
export function useStunting(): StuntingModel | null | undefined {
  const [data, setData] = useState<StuntingModel | null | undefined>(undefined);
  useEffect(() => {
    let alive = true;
    void load().then((d) => alive && setData(d));
    return () => {
      alive = false;
    };
  }, []);
  return data;
}

export const STUDY_TOPICS = [
  { id: "dropout", label: "Dropout", long: "Secondary-school dropout" },
  { id: "stunting", label: "Stunting", long: "Under-5 stunting" },
] as const;
export type StudyTopic = (typeof STUDY_TOPICS)[number]["id"];

/** The question a stunting pipeline run asks (the Map-tab analysis: personas, sources, Divergence, Data). */
export const STUNTING_QUERY = "reasons for child stunting in Karnataka";

// ── Recomputing the model at any target (the workbook's "Reduce … stunted" and bucket-priority controls) ──

export interface StuntingSettings {
  /** Target cut, 0.05-0.5 (the workbook's default 0.20). */
  reduceBy: number;
  /** Bucket to prioritise, or null for equal allocation. */
  priorityBucket: string | null;
  /** Share of the cut the prioritised bucket takes (the workbook's "Assign Bucket Priority", default 0.5). */
  priorityWeight: number;
  set(p: Partial<Omit<StuntingSettings, "set">>): void;
}

export const useStuntingSettings = create<StuntingSettings>((set) => ({
  reduceBy: 0.2,
  priorityBucket: null,
  priorityWeight: 0.5,
  set: (p) => set(p),
}));

/**
 * One district's prescriptions at the given settings -- the workbook's "Prescribed" field:
 *   prescribed = clamp(value + (bucket weight / factors in bucket) x (target - current) / coefficient, 0, 100)
 * with equal bucket weights, or (Custom Priority) the chosen bucket taking `priorityWeight` and the others sharing
 * the rest equally. Sorted by change, largest first. Same result as backend/app/stunting.py at the defaults.
 */
export function prescribe(
  model: StuntingModel,
  district: StuntingDistrict,
  s: Pick<StuntingSettings, "reduceBy" | "priorityBucket" | "priorityWeight">,
): { target: number | null; factors: StuntingDistrictFactor[] } {
  if (district.stunting == null) return { target: null, factors: [] };
  const info = Object.fromEntries(model.factors.map((f) => [f.name, f]));
  const buckets = [...new Set(district.factors.map((f) => f.bucket))];
  const perBucket = Object.fromEntries(
    buckets.map((b) => [b, district.factors.filter((f) => f.bucket === b).length]),
  );
  const prioritised =
    s.priorityBucket && buckets.includes(s.priorityBucket) ? s.priorityBucket : null;
  const weight = (b: string) =>
    !prioritised
      ? 1 / buckets.length
      : b === prioritised
        ? s.priorityWeight
        : (1 - s.priorityWeight) / Math.max(1, buckets.length - 1);
  const target = district.stunting * (1 - s.reduceBy);
  const factors = district.factors.map((f) => {
    const coef = info[f.name]?.coefficient ?? 0;
    const share = weight(f.bucket) / perBucket[f.bucket]!;
    const raw =
      Math.abs(coef) < 1e-5 ? f.value : f.value + (share * (target - district.stunting!)) / coef;
    const prescribed = Math.min(100, Math.max(0, raw));
    return {
      ...f,
      prescribed: Math.round(prescribed * 100) / 100,
      change:
        Math.abs(f.value) < 1e-6
          ? null
          : Math.round((Math.abs(prescribed - f.value) / f.value) * 1000) / 10,
      share: Math.round(share * 10000) / 100,
      atLimit: raw < 0 || raw > 100,
    };
  });
  factors.sort((a, b) => (b.change ?? 0) - (a.change ?? 0));
  return { target: Math.round(target * 100) / 100, factors };
}
