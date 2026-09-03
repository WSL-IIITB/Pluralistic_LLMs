/**
 * Pure derived-data selectors over the store's accumulated data. Kept separate
 * from the store so they're trivially testable and don't re-run unless their
 * inputs change.
 */

import type {
  ClusterDatum,
  ClusterId,
  DistrictDatum,
  DistrictId,
  RegionDatum,
  RegionId,
  RGBAColor,
  StateCode,
} from "./types";

export interface StateDiversity {
  stateCode: StateCode;
  /** Shannon entropy of the state's cluster-volume distribution, normalised 0–1. */
  entropy: number;
  /** How many distinct clusters appear anywhere in the state. */
  clustersPresent: number;
  totalVolume: number;
  dominantClusterId: ClusterId | null;
  /** Per-cluster volume totals across the state's districts. */
  clusterVolumes: Record<ClusterId, number>;
}

/** Ordered legend entries (clusters in the order they were first defined). */
export function legendClusters(
  clusters: Record<ClusterId, ClusterDatum>,
  order: readonly ClusterId[],
): ClusterDatum[] {
  const out: ClusterDatum[] = [];
  for (const id of order) {
    const c = clusters[id];
    if (c) out.push(c);
  }
  return out;
}

/** Look up a cluster colour by id, with a neutral fallback. */
export function clusterColor(
  clusters: Record<ClusterId, ClusterDatum>,
  id: ClusterId | null | undefined,
): RGBAColor {
  if (!id) return [130, 130, 140];
  return clusters[id]?.color ?? [130, 130, 140];
}

export interface LegendGroup {
  stateCode: StateCode;
  clusters: ClusterDatum[];
  totalPostCount: number;
}

/**
 * Legend entries grouped by state — extrahigh mode only. Clusters with no
 * resolvable `stateCode` (basic/medium/high's global clusters) are excluded
 * entirely; callers should fall back to the flat `legendClusters()` list
 * when no cluster in the run has a `stateCode` at all (i.e.
 * `!items.some((c) => c.stateCode != null)`), which is the normal case for
 * every mode except extrahigh. Groups are sorted by total post count
 * descending so the most-discussed states surface without scrolling.
 */
export function legendGroups(
  clusters: Record<ClusterId, ClusterDatum>,
  order: readonly ClusterId[],
): LegendGroup[] {
  const byState = new Map<StateCode, ClusterDatum[]>();
  for (const id of order) {
    const c = clusters[id];
    if (!c || !c.stateCode) continue;
    const list = byState.get(c.stateCode);
    if (list) list.push(c);
    else byState.set(c.stateCode, [c]);
  }

  const groups: LegendGroup[] = [];
  for (const [stateCode, list] of byState) {
    groups.push({
      stateCode,
      clusters: list,
      totalPostCount: list.reduce((sum, c) => sum + c.postCount, 0),
    });
  }
  groups.sort((a, b) => b.totalPostCount - a.totalPostCount);
  return groups;
}

export interface LegendGroupByRegion {
  regionId: RegionId;
  /** Resolved directly from `RegionDatum` (unlike `LegendGroup.stateCode`,
   *  which callers must resolve to a display name via external geo data — a
   *  region's name is agent-generated per run, so there's no static lookup
   *  to defer to; it's already known here). */
  regionName: string;
  clusters: ClusterDatum[];
  totalPostCount: number;
}

/**
 * Legend entries grouped by AGENT-INFERRED REGION — extrahigh mode only,
 * post region-inference (see infer_regions.py). The primary grouping for
 * extrahigh's Legend/Deflection panels, replacing `legendGroups()` (state)
 * above as of the region-inference redesign — kept alongside, not replacing,
 * `legendGroups()` itself, since a district's own state is still a
 * meaningful secondary fact even when regions are the primary lens (a region
 * can span several states). Clusters with no resolvable `regionId` (older
 * saved runs predating region-inference, or basic/medium/high's global
 * clusters) are excluded entirely; callers should fall back to
 * `legendGroups()` when no cluster in the run has a `regionId` at all.
 * Groups are sorted by total post count descending, same as `legendGroups()`.
 */
export function legendGroupsByRegion(
  clusters: Record<ClusterId, ClusterDatum>,
  order: readonly ClusterId[],
  regions: Record<RegionId, RegionDatum>,
): LegendGroupByRegion[] {
  const byRegion = new Map<RegionId, ClusterDatum[]>();
  for (const id of order) {
    const c = clusters[id];
    if (!c || !c.regionId) continue;
    const list = byRegion.get(c.regionId);
    if (list) list.push(c);
    else byRegion.set(c.regionId, [c]);
  }

  const groups: LegendGroupByRegion[] = [];
  for (const [regionId, list] of byRegion) {
    groups.push({
      regionId,
      regionName: regions[regionId]?.name ?? regionId,
      clusters: list,
      totalPostCount: list.reduce((sum, c) => sum + c.postCount, 0),
    });
  }
  groups.sort((a, b) => b.totalPostCount - a.totalPostCount);
  return groups;
}

/**
 * Intra-state cluster diversity for every state that has resolved districts.
 * `entropy` is normalised so a single-viewpoint state → 0 and a maximally split
 * state → 1.
 */
export function computeStateDiversity(
  districts: Record<DistrictId, DistrictDatum>,
): Record<StateCode, StateDiversity> {
  const byState: Record<StateCode, Record<ClusterId, number>> = {};

  for (const id of Object.keys(districts)) {
    const d = districts[id];
    if (!d) continue;
    const bucket = (byState[d.stateCode] ??= {});
    const volumes = d.clusterVolumes ?? (d.clusterId ? { [d.clusterId]: d.volume } : {});
    for (const cid of Object.keys(volumes)) {
      bucket[cid] = (bucket[cid] ?? 0) + (volumes[cid] ?? 0);
    }
  }

  const result: Record<StateCode, StateDiversity> = {};
  for (const stateCode of Object.keys(byState)) {
    const volumes = byState[stateCode] ?? {};
    const ids = Object.keys(volumes);
    let total = 0;
    let dominantClusterId: ClusterId | null = null;
    let dominantVol = -Infinity;
    for (const cid of ids) {
      const v = volumes[cid] ?? 0;
      total += v;
      if (v > dominantVol) {
        dominantVol = v;
        dominantClusterId = cid;
      }
    }

    let entropy = 0;
    if (total > 0) {
      for (const cid of ids) {
        const p = (volumes[cid] ?? 0) / total;
        if (p > 0) entropy -= p * Math.log2(p);
      }
    }
    const k = ids.filter((cid) => (volumes[cid] ?? 0) > 0).length;
    const normalised = k > 1 ? entropy / Math.log2(k) : 0;

    result[stateCode] = {
      stateCode,
      entropy: normalised,
      clustersPresent: k,
      totalVolume: total,
      dominantClusterId,
      clusterVolumes: volumes,
    };
  }
  return result;
}

export interface SplitStateOptions {
  minEntropy?: number;
  minClusters?: number;
  minVolume?: number;
}

/** States whose districts genuinely disagree, for the "split states" highlight. */
export function splitStateCodes(
  diversity: Record<StateCode, StateDiversity>,
  { minEntropy = 0.5, minClusters = 2, minVolume = 3 }: SplitStateOptions = {},
): Set<StateCode> {
  const out = new Set<StateCode>();
  for (const code of Object.keys(diversity)) {
    const d = diversity[code];
    if (!d) continue;
    if (d.clustersPresent >= minClusters && d.entropy >= minEntropy && d.totalVolume >= minVolume) {
      out.add(code);
    }
  }
  return out;
}
