/**
 * News vs data: the news research and the UIDAI/NITI dominant-factor data side by side, with the reasons they
 * name different factors. Built by scripts/build_news_vs_data.py into public/data/news-vs-data.json (counts and
 * templated sentences only; no model-written text).
 */

import { useEffect, useState } from "react";

import { assetUrl } from "./api";

type Verdicts = Record<string, number>;

export interface NewsCategoryCount {
  category: string;
  label: string;
  districts: number;
  reasons: number;
  strong: number;
  moderate: number;
  thin: number;
}

export interface NewsVsDataStatewide {
  districts: number;
  lead: string;
  news: {
    categories: NewsCategoryCount[];
    childLabour: {
      districts: string[];
      reasons: number;
      strong: number;
      moderate: number;
      thin: number;
    };
    childMarriageDistricts: number;
    headlines: { total: number; childLabour: number; childMarriage: number; language: number };
    touchingLanguage: {
      districtId: string;
      name: string;
      family: string;
      factor: string;
      evidence: string;
    }[];
    touchingLanguageDistricts: string[];
  };
  data: {
    methods: Record<"state" | "district", string>;
    stateFactors: { factor: string; rows: number }[];
    districtFactors: { factor: string; rows: number }[];
    karnatakaWorkbookRows: number;
    national: {
      rows: number;
      topDistrictFactor: string;
      topDistrictFactorRows: number;
      topDistrictFactorRank: number;
      stateFactorNames: string[];
      districtFactorNames: string[];
      socialFactors: string[];
    };
  };
  found: {
    check: Record<"state" | "district", Verdicts>;
    why: Record<"state" | "district", Verdicts>;
    districtLevelProof: { district: number; general: number };
    generalClaims: string[];
  };
  differ: { title: string; text: string }[];
  connect: { text: string; untested: string };
}

export interface NewsVsDataDistrict {
  name: string;
  regionId: string;
  coverage: string;
  news: {
    reasons: number;
    topCategories: string[];
    top: { factor: string; category: string; evidence: "strong" | "moderate" | "thin" }[];
    childLabour: boolean;
  };
  data: {
    method: "state" | "district";
    factor: string;
    short: string;
    area: string;
    value: number;
  }[];
  found: Record<
    "state" | "district",
    { check: string | null; why: string[]; districtProof: number; generalProof: number }
  >;
  touching: { family: string; factor: string; detail: string; evidence: string }[];
  differ: string[];
}

export interface NewsVsData {
  version: number;
  statewide: NewsVsDataStatewide;
  districts: Record<string, NewsVsDataDistrict>;
}

let inflight: Promise<NewsVsData | null> | null = null;

function load(): Promise<NewsVsData | null> {
  inflight ??= fetch(assetUrl("data/news-vs-data.json"))
    .then((r) => (r.ok ? (r.json() as Promise<NewsVsData>) : null))
    .catch(() => null)
    .then((d) => {
      if (d === null) inflight = null; // retry on the next mount
      return d;
    });
  return inflight;
}

/** `undefined` while loading, `null` if the file could not be read. */
export function useNewsVsData(): NewsVsData | null | undefined {
  const [data, setData] = useState<NewsVsData | null | undefined>(undefined);
  useEffect(() => {
    let alive = true;
    void load().then((d) => alive && setData(d));
    return () => {
      alive = false;
    };
  }, []);
  return data;
}
