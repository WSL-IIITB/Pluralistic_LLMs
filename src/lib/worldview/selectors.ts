/**
 * Pure derived-data selectors over the store's accumulated data. Kept separate
 * from the store so they're trivially testable and don't re-run unless their
 * inputs change.
 */

import { regionShortName } from "./karnataka";
import type {
  ClusterDatum,
  ClusterId,
  RegionDatum,
  RegionId,
  RegionStatsDatum,
  RGBAColor,
} from "./types";

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
      regionName: regions[regionId]?.name ?? regionShortName(regionId),
      clusters: list,
      totalPostCount: list.reduce((sum, c) => sum + c.postCount, 0),
    });
  }
  groups.sort((a, b) => b.totalPostCount - a.totalPostCount);
  return groups;
}

/** Shannon entropy of a region's cluster-volume mix, normalised 0–1 (0 = one viewpoint). */
export function regionEntropy(stats: RegionStatsDatum): number {
  const vols = Object.values(stats.clusterVolumes).filter((v) => v > 0);
  const total = vols.reduce((a, b) => a + b, 0);
  if (vols.length < 2 || total === 0) return 0;
  let h = 0;
  for (const v of vols) {
    const p = v / total;
    h -= p * Math.log2(p);
  }
  return h / Math.log2(vols.length);
}

/** Regions whose viewpoints genuinely disagree, for the "split regions" outline. */
export function splitRegionIds(
  regionStats: Record<RegionId, RegionStatsDatum>,
  { minEntropy = 0.5, minClusters = 2, minVolume = 3 } = {},
): Set<RegionId> {
  const out = new Set<RegionId>();
  for (const stats of Object.values(regionStats)) {
    const clusters = Object.values(stats.clusterVolumes).filter((v) => v > 0).length;
    if (
      clusters >= minClusters &&
      stats.volume >= minVolume &&
      regionEntropy(stats) >= minEntropy
    ) {
      out.add(stats.regionId);
    }
  }
  return out;
}
