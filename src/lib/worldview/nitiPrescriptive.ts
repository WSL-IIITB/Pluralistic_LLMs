/**
 * The NITI team's prescriptive model for Karnataka (public/data/niti-prescriptive.json, built by
 * scripts/export_niti_prescriptive.py from their Tableau workbook): 18 school and household factors per district,
 * each with a fitted line across Karnataka's districts, and the "top changes" the model ranks highest.
 * Two rankings are kept apart: "niti" (exactly as the workbook computes it) and "feasible" (the same formula with
 * percentages capped at 100%).
 */

import { useEffect, useState } from "react";

import { assetUrl } from "./api";

export type Ranking = "feasible" | "niti";

export interface PrescriptiveFactorInfo {
  name: string;
  column: string;
  bucket: string;
  slope: number;
  intercept: number;
  pearson: number;
  directionMatch: string;
  short: string;
  better: "higher" | "lower";
  measures: string;
  why: string;
  change: string;
  karnataka: { min: number; median: number; max: number };
}

export interface PrescriptiveFactor {
  name: string;
  value: number;
  /** The fitted line's predicted dropout at this value. */
  predicted: number;
  /** Rank among Karnataka's rows, 1 = best in the direction the model links to lower dropout. */
  rank: number;
  niti: { target: number; sensitivity: number | null; contribution: number };
  feasible: { target: number; sensitivity: number | null; contribution: number };
  /** The published 10% step pushes this percentage past 100% (or below 0%). */
  pastLimit: boolean;
}

export interface PrescriptiveArea {
  area: string;
  districtId: string;
  dropout2023_24: number | null;
  dropout2024_25: number | null;
  /** Sorted by feasible contribution, highest first. */
  factors: PrescriptiveFactor[];
  topFeasible: string[];
  topNiti: string[];
}

export interface NitiPrescriptive {
  version: number;
  source: {
    file: string;
    from: string;
    dataset: string;
    karnatakaRows: number;
    factorsPerDistrict: number;
  };
  method: Record<
    "model" | "sensitivity" | "contribution" | "niti" | "feasible" | "step" | "caveat",
    string
  >;
  factors: PrescriptiveFactorInfo[];
  statewide: {
    topFeasible: Record<string, number>;
    topNiti: Record<string, number>;
    pastLimitRows: number;
  };
  districts: Record<string, { name: string; areas: PrescriptiveArea[] }>;
}

let inflight: Promise<NitiPrescriptive | null> | null = null;

function load(): Promise<NitiPrescriptive | null> {
  inflight ??= fetch(assetUrl("data/niti-prescriptive.json"))
    .then((r) => (r.ok ? (r.json() as Promise<NitiPrescriptive>) : null))
    .catch(() => null)
    .then((d) => {
      if (d === null) inflight = null; // retry on the next mount
      return d;
    });
  return inflight;
}

/** `undefined` while loading, `null` if the file could not be read. */
export function useNitiPrescriptive(): NitiPrescriptive | null | undefined {
  const [data, setData] = useState<NitiPrescriptive | null | undefined>(undefined);
  useEffect(() => {
    let alive = true;
    void load().then((d) => alive && setData(d));
    return () => {
      alive = false;
    };
  }, []);
  return data;
}

/** "2.4" for a percentage indicator, as published; teachers per 100 students keeps one decimal too. */
export function formatFactorValue(name: string, v: number): string {
  return name === "Teachers per 100 students" ? v.toFixed(1) : `${v.toFixed(1)}%`;
}
