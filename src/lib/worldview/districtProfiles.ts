/** Per-district facts from GET /api/karnataka/districts (static data, no LLM). */

import { useEffect, useState } from "react";

import { cachedJson } from "./api";

export interface DistrictNitiFactor {
  /** Row label as it appears in the workbook (a sub-area for split districts). */
  area: string;
  factor: string;
  value: number;
  method: "state" | "district";
}

export interface DistrictProfile {
  districtId: string;
  regionId: string;
  /** Secondary dropout rate (%) from the LKI-SSM casefile; null if the district has only sub-area rows. */
  dropoutRate: number | null;
  subAreas: { name: string; dropoutRate: number }[];
  nitiFactors: DistrictNitiFactor[];
}

interface Payload {
  districts: DistrictProfile[];
  methods: Record<"state" | "district", string>;
}

const load = cachedJson<Payload>("/api/karnataka/districts");

export function useDistrictProfiles(): {
  byId: Record<string, DistrictProfile>;
  methods: Payload["methods"] | null;
  ready: boolean;
} {
  const [data, setData] = useState<Payload | null>(null);
  const [ready, setReady] = useState(false);
  useEffect(() => {
    let alive = true;
    void load().then((p) => {
      if (!alive) return;
      setData(p);
      setReady(true);
    });
    return () => {
      alive = false;
    };
  }, []);
  const byId: Record<string, DistrictProfile> = {};
  for (const d of data?.districts ?? []) byId[d.districtId] = d;
  return { byId, methods: data?.methods ?? null, ready };
}
