/**
 * Builds the deck.gl layer stack from the store's live data + the district geo.
 * Imported only by DeckMap, so all deck.gl code stays in the client-only chunk.
 *
 * Layer stack (bottom → top):
 *   0. state-solid-backing — a solid, neutral, gap-free landmass so the country
 *      always reads as one continuous piece (never a translucent patchwork).
 *   1. district-base       — per-district choropleth fill; hairline strokes only
 *      render once zoomed past country view, to avoid a moiré/sparkle across
 *      hundreds of thin adjacent edges at the country tier.
 *   2. state-borders        — bold, always-visible state boundaries (dissolved,
 *      so no interior district seams leak through).
 *   3. split-states          — extra glow outline for contested states (toggle).
 *   4. selection-outline     — dissolved state or single-district outline.
 *   5. deflection-arcs       — links between co-occurring viewpoints (toggle).
 *   6. viewpoint-columns     — extruded 3D columns (toggle).
 */

import { ArcLayer, ColumnLayer, GeoJsonLayer } from "@deck.gl/layers";
import type { Layer } from "@deck.gl/core";
import type { Feature, FeatureCollection } from "geojson";

import {
  clusterColor,
  confidenceAlpha,
  COLUMN_ELEVATION_SCALE,
  COLUMN_RADIUS_METERS,
  withAlpha,
  type ClusterDatum,
  type ClusterId,
  type DeflectionDatum,
  type DistrictDatum,
  type DistrictId,
  type LayerToggles,
  type RGBAColor,
  type Selection,
  type StateCode,
  type StateDiversity,
  type ViewTier,
} from "@/lib/worldview";
import type { DistrictFeatureProps, DistrictGeo } from "@/lib/worldview/geo/districts";
import type { StateFeatureCollection } from "@/lib/worldview/geo/states";
import { interventionColor, numericColor, type NumericDomain } from "@/lib/dataview/palette";
import type { DataViewColorMode } from "@/lib/dataview/store";

export interface DataViewLayerParams {
  /** False (or this whole param omitted) falls through to the existing cluster-mode logic unchanged. */
  active: boolean;
  colorMode: DataViewColorMode;
  values: Record<DistrictId, number>;
  domain: NumericDomain;
}

export interface BuildLayersParams {
  geo: DistrictGeo;
  stateGeo: StateFeatureCollection | null;
  tier: ViewTier;
  districts: Record<DistrictId, DistrictDatum>;
  clusters: Record<ClusterId, ClusterDatum>;
  stateDiversity: Record<StateCode, StateDiversity>;
  splitStates: Set<StateCode>;
  toggles: LayerToggles;
  selection: Selection;
  hoveredClusterId: ClusterId | null;
  deflections: DeflectionDatum[];
  deflectionPair: { a: ClusterId | null; b: ClusterId | null };
  /** Precomputed by `computeRepresentativeCentroids`, memoized by the caller
   * on `[districts, geo]` — see that function's doc comment for why this
   * must not be recomputed here on every hover. */
  representativeCentroids: Map<ClusterId, [number, number]>;
  /** Data View's numeric choropleth mode — see {@link DataViewLayerParams}. Omitted/inactive for Story View. */
  dataView?: DataViewLayerParams;
}

interface ColumnDatum {
  districtId: DistrictId;
  stateCode: StateCode;
  clusterId: ClusterId;
  name: string;
  stateName: string;
  position: [number, number];
  volume: number;
  confidence: DistrictDatum["confidence"];
  isStateFallback: boolean;
}

interface ArcDatum {
  source: [number, number];
  target: [number, number];
  colorA: RGBAColor;
  colorB: RGBAColor;
  highlight: boolean;
}

/** Solid, gap-free backing tone — a touch warmer than the page background. */
const LANDMASS_BASE_RGBA: RGBAColor = [42, 39, 36, 215];
/** Bold, always-visible state boundary. */
const STATE_BORDER_RGBA: RGBAColor = [232, 218, 195, 205];
const STATE_BORDER_WIDTH_PX = 1.6;

const props = (f: Feature): DistrictFeatureProps => f.properties as unknown as DistrictFeatureProps;

/**
 * Highest-volume district centroid per dominant clusterId, ONE pass over
 * `districts` for every cluster at once. Callers should memoize this keyed
 * only on `[districts, geo]` (see DeckMap.tsx) and pass the result into
 * `buildLayers` — this must NOT be recomputed inside `buildLayers` itself,
 * since that function reruns on every hover/selection change and this
 * computation doesn't depend on either. At extrahigh's cluster-count scale
 * (~190 total), recomputing per-cluster-per-hover was a real, measured
 * regression (~30x more iterations per hover than at today's ≤6-cluster
 * scale) on a value that never actually changes on hover.
 */
export function computeRepresentativeCentroids(
  districts: Record<DistrictId, DistrictDatum>,
  geo: DistrictGeo,
): Map<ClusterId, [number, number]> {
  const best = new Map<ClusterId, { vol: number; centroid: [number, number] }>();
  for (const id of Object.keys(districts)) {
    const d = districts[id];
    if (!d || !d.clusterId) continue;
    const loaded = geo.districts[id];
    if (!loaded) continue;
    const existing = best.get(d.clusterId);
    if (!existing || d.volume > existing.vol) {
      best.set(d.clusterId, { vol: d.volume, centroid: loaded.centroid });
    }
  }
  const out = new Map<ClusterId, [number, number]>();
  for (const [cid, v] of best) out.set(cid, v.centroid);
  return out;
}

export function buildLayers(params: BuildLayersParams): Layer[] {
  const {
    geo,
    stateGeo,
    tier,
    districts,
    clusters,
    stateDiversity,
    splitStates,
    toggles,
    selection,
    hoveredClusterId,
    deflections,
    deflectionPair,
    representativeCentroids,
    dataView,
  } = params;

  const layers: Layer[] = [];

  // District identity/version signal for updateTriggers (changes every event).
  const districtsSig = districts;
  const clustersSig = clusters;
  const stateAggColor = (stateCode: StateCode): RGBAColor => {
    const agg = stateDiversity[stateCode];
    return clusterColor(clusters, agg?.dominantClusterId);
  };

  // ── 0. Solid landmass backing (no gaps, always one continuous piece) ─────────
  if (stateGeo && stateGeo.features.length > 0) {
    layers.push(
      new GeoJsonLayer({
        id: "state-solid-backing",
        data: stateGeo as unknown as FeatureCollection,
        stroked: false,
        filled: true,
        getFillColor: LANDMASS_BASE_RGBA,
        parameters: { depthCompare: "always" },
      }),
    );
  }

  // ── 1. Base district polygons (choropleth fill; hairlines only past country zoom)
  const showDistrictHairlines = tier !== "Country view";
  layers.push(
    new GeoJsonLayer({
      id: "district-base",
      data: geo.featureCollection as unknown as FeatureCollection,
      stroked: showDistrictHairlines,
      filled: true,
      extruded: false,
      pickable: true,
      lineWidthUnits: "pixels",
      getLineWidth: 0.5,
      lineWidthMinPixels: 0.4,
      getLineColor: [255, 255, 255, 28],
      getFillColor: (f: Feature): RGBAColor => {
        const p = props(f);

        // Data View's numeric choropleth mode takes over entirely when active —
        // falls through to the untouched cluster-mode logic below otherwise.
        if (dataView?.active) {
          const value = dataView.values[p.districtId];
          if (value === undefined) return [0, 0, 0, 0];
          const rgb =
            dataView.colorMode === "dropoutRate"
              ? numericColor(value, dataView.domain)
              : interventionColor(value);
          return withAlpha(rgb, 150);
        }

        const d = districts[p.districtId];
        if (d && d.clusterId) {
          if (d.isStateFallback) return withAlpha(stateAggColor(p.stateCode), 70);
          return withAlpha(clusterColor(clusters, d.clusterId), 150);
        }
        const agg = stateDiversity[p.stateCode];
        if (agg?.dominantClusterId)
          return withAlpha(clusterColor(clusters, agg.dominantClusterId), 55);
        // No data at all: let the solid landmass backing show through cleanly.
        return [0, 0, 0, 0];
      },
      updateTriggers: {
        stroked: [tier],
        getFillColor: [
          districtsSig,
          clustersSig,
          stateDiversity,
          dataView?.active,
          dataView?.colorMode,
          dataView?.values,
          dataView?.domain,
        ],
      },
    }),
  );

  // ── 2. Bold, always-visible state borders (dissolved — no interior seams) ────
  if (stateGeo && stateGeo.features.length > 0) {
    layers.push(
      new GeoJsonLayer({
        id: "state-borders",
        data: stateGeo as unknown as FeatureCollection,
        stroked: true,
        filled: false,
        getLineColor: STATE_BORDER_RGBA,
        lineWidthUnits: "pixels",
        getLineWidth: STATE_BORDER_WIDTH_PX,
        lineWidthMinPixels: 1.2,
        lineJointRounded: true,
        parameters: { depthCompare: "always" },
      }),
    );
  }

  // ── 3. Split-state highlight (contested states get an extra glow) ────────────
  if (toggles.splitStates && splitStates.size > 0) {
    const splitFeatures = stateGeo
      ? stateGeo.features.filter((f) => splitStates.has(f.properties.stateCode))
      : geo.featureCollection.features.filter((f) => splitStates.has(f.properties.stateCode));
    layers.push(
      new GeoJsonLayer({
        id: "split-states",
        data: {
          type: "FeatureCollection",
          features: splitFeatures,
        } as unknown as FeatureCollection,
        stroked: true,
        filled: false,
        getLineColor: [249, 183, 63, 220],
        lineWidthUnits: "pixels",
        getLineWidth: STATE_BORDER_WIDTH_PX + 1.4,
        lineWidthMinPixels: 2,
        lineJointRounded: true,
        parameters: { depthCompare: "always" },
      }),
    );
  }

  // ── 4. Selection outline (dissolved state, or a single district) ─────────────
  if (selection.kind) {
    const selFeatures =
      selection.kind === "state" && stateGeo
        ? stateGeo.features.filter((f) => f.properties.stateCode === selection.id)
        : geo.featureCollection.features.filter((f) =>
            selection.kind === "district"
              ? f.properties.districtId === selection.id
              : f.properties.stateCode === selection.id,
          );
    if (selFeatures.length > 0) {
      layers.push(
        new GeoJsonLayer({
          id: "selection-outline",
          data: {
            type: "FeatureCollection",
            features: selFeatures,
          } as unknown as FeatureCollection,
          stroked: true,
          filled: false,
          getLineColor: [255, 255, 255, 230],
          lineWidthUnits: "pixels",
          getLineWidth: 2.2,
          lineWidthMinPixels: 1.8,
          lineJointRounded: true,
          parameters: { depthCompare: "always" },
        }),
      );
    }
  }

  // ── 5. Deflection arcs ───────────────────────────────────────────────────────
  const pairMatches = (d: DeflectionDatum): boolean => {
    const { a, b } = deflectionPair;
    if (!a || !b) return false;
    return (d.clusterA === a && d.clusterB === b) || (d.clusterA === b && d.clusterB === a);
  };
  const arcSource = toggles.links ? deflections : deflections.filter(pairMatches);
  const arcData: ArcDatum[] = [];
  for (const d of arcSource) {
    const s = representativeCentroids.get(d.clusterA) ?? null;
    const t = representativeCentroids.get(d.clusterB) ?? null;
    if (!s || !t) continue;
    arcData.push({
      source: s,
      target: t,
      colorA: clusterColor(clusters, d.clusterA),
      colorB: clusterColor(clusters, d.clusterB),
      highlight: pairMatches(d),
    });
  }
  if (arcData.length > 0) {
    layers.push(
      new ArcLayer<ArcDatum>({
        id: "deflection-arcs",
        data: arcData,
        getSourcePosition: (d) => d.source,
        getTargetPosition: (d) => d.target,
        getSourceColor: (d) => withAlpha(d.colorA, d.highlight ? 235 : 110),
        getTargetColor: (d) => withAlpha(d.colorB, d.highlight ? 235 : 110),
        getWidth: (d) => (d.highlight ? 3 : 1.3),
        getHeight: 0.5,
        greatCircle: false,
        parameters: { depthCompare: "always" },
      }),
    );
  }

  // ── 6. Extruded 3D columns (height = volume, colour = cluster) ────────────────
  if (toggles.columns) {
    const columnData: ColumnDatum[] = [];
    for (const id of Object.keys(districts)) {
      const d = districts[id];
      if (!d || !d.clusterId || d.volume <= 0) continue;
      const loaded = geo.districts[id];
      if (!loaded) continue;
      columnData.push({
        districtId: id,
        stateCode: d.stateCode,
        clusterId: d.clusterId,
        name: loaded.name,
        stateName: loaded.stateName,
        position: loaded.centroid,
        volume: d.volume,
        confidence: d.confidence,
        isStateFallback: d.isStateFallback,
      });
    }

    const columnColor = (d: ColumnDatum): RGBAColor => {
      const base = clusterColor(clusters, d.clusterId);
      let alpha = confidenceAlpha(d.confidence);
      if (hoveredClusterId && d.clusterId !== hoveredClusterId) alpha = Math.round(alpha * 0.22);
      const isSelected =
        (selection.kind === "district" && selection.id === d.districtId) ||
        (selection.kind === "state" && selection.id === d.stateCode);
      if (isSelected) alpha = 255;
      return withAlpha(base, alpha);
    };

    layers.push(
      new ColumnLayer<ColumnDatum>({
        id: "viewpoint-columns",
        data: columnData,
        diskResolution: 6,
        radius: COLUMN_RADIUS_METERS,
        radiusUnits: "meters",
        extruded: true,
        pickable: true,
        elevationScale: COLUMN_ELEVATION_SCALE,
        getPosition: (d) => d.position,
        getElevation: (d) => d.volume,
        getFillColor: columnColor,
        material: { ambient: 0.55, diffuse: 0.6, shininess: 24, specularColor: [50, 50, 55] },
        updateTriggers: {
          getFillColor: [hoveredClusterId, selection, clustersSig],
          getElevation: [districtsSig],
        },
      }),
    );
  }

  return layers;
}
