/**
 * Background profiles of each Karnataka district from District Mocha (https://district-mocha.netlify.app/), an
 * outside, AI-assisted development dashboard: baseline figures, strengths, challenges, opportunities, goals,
 * programmes, industries and role-based actions. GET /api/district-mocha, or public/data/district-mocha.json on the
 * static site; imported by scripts/import_district_mocha.py. Context only -- not this study's research, and not
 * checked by it.
 */

import { useEffect, useState } from "react";

import { cachedJson } from "./api";

export interface MochaProfile {
  name: string;
  tagline: string;
  region: string;
  url: string;
  baseline: { label: string; value: string; year: string; note: string }[];
  strengths: { title: string; detail: string }[];
  challenges: { title: string; detail: string }[];
  opportunities: { title: string; detail: string }[];
  goals: { target: string; detail: string }[];
  programmes: { name: string; status: string }[];
  industriesTitle?: string;
  industries: { name: string; priority: string; stats: string; note: string }[];
  roles: { role: string; action: string }[];
  linked: { kind: string; name: string; summary: string; url: string }[];
}

export interface MochaDistrict extends MochaProfile {
  districtId: string;
  /** Other District Mocha pages that share this district's map polygon (Vijayanagara, under Ballari). */
  also?: MochaProfile[];
}

export interface DistrictMochaData {
  source: { name: string; url: string; about: string; importedOn: string; scrapedOn?: string };
  districts: Record<string, MochaDistrict>;
}

const load = cachedJson<DistrictMochaData>("/api/district-mocha");

/** All district profiles; undefined while loading, null if unavailable. */
export function useDistrictMocha(): DistrictMochaData | null | undefined {
  const [data, setData] = useState<DistrictMochaData | null | undefined>(undefined);
  useEffect(() => {
    let alive = true;
    void load().then((d) => alive && setData(d));
    return () => {
      alive = false;
    };
  }, []);
  return data;
}
