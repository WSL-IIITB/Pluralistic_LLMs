/** The full UIDAI/NITI dominant-factor workbooks (all India), from public/data/niti-factors.json. */

import { useEffect, useState } from "react";

import { assetUrl } from "./api";

export interface NitiRow {
  state: string;
  district: string;
  /** State-level method: the factor ranked highest for the state, and this district's value for it. */
  stateFactor: string;
  stateValue: number;
  /** District-level method: the factor selected for this district, and its fitted weight. */
  districtFactor: string | null;
  districtValue: number | null;
}

export interface NitiFactorOnlyRow {
  state: string;
  factor: string;
  value: number | null;
}

export interface NitiData {
  source: {
    files: string[];
    rows: number;
    states: number;
    unpaired: number;
    factorOnlyRows: { state: number; district: number };
  };
  methods: Record<"state" | "district", string>;
  rows: NitiRow[];
  factorOnlyRows: Record<"state" | "district", NitiFactorOnlyRow[]>;
}

let inflight: Promise<NitiData | null> | null = null;

function load(): Promise<NitiData | null> {
  inflight ??= fetch(assetUrl("data/niti-factors.json"))
    .then((r) => (r.ok ? (r.json() as Promise<NitiData>) : null))
    .catch(() => null)
    .then((d) => {
      if (d === null) inflight = null; // retry on the next mount
      return d;
    });
  return inflight;
}

/** `undefined` while loading, `null` if the file could not be read. */
export function useNitiData(): NitiData | null | undefined {
  const [data, setData] = useState<NitiData | null | undefined>(undefined);
  useEffect(() => {
    let alive = true;
    void load().then((d) => alive && setData(d));
    return () => {
      alive = false;
    };
  }, []);
  return data;
}

const SHORT: Record<string, string> = {
  "% Population Living in Households with Improved Sanitation": "Household sanitation",
  "% Schools with instruction medium 1 (English)": "English-medium schools",
  "% Schools with Functional Protected Well": "Schools with a protected well",
};

/** A shorter label for the factors that recur in Karnataka; other factors keep their workbook name. */
export function shortFactor(name: string): string {
  return SHORT[name] ?? name;
}
