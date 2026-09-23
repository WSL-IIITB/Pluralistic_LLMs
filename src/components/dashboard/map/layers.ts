/**
 * Builds the deck.gl layer stack. Imported only by DeckMap, so all deck.gl code
 * stays in the client-only chunk. Two modes share the India landmass/state
 * backdrop:
 *
 *  Story View (Karnataka persona regions), bottom → top:
 *    district hairlines (faint context) → region fills (dominant viewpoint,
 *    or the region's identity colour before data) → region borders →
 *    split-region glow → selection outline → deflection arcs →
 *    viewpoint columns (one per cluster, ringed round the region) → labels
 *
 *  Data View: the unchanged India-wide numeric district choropleth.
 */

import { ArcLayer, ColumnLayer, GeoJsonLayer, TextLayer } from "@deck.gl/layers";
import type { Layer } from "@deck.gl/core";
import type { Feature, FeatureCollection } from "geojson";

import {
  clusterColor,
  confidenceAlpha,
  COLUMN_ELEVATION_SCALE,
  regionColor,
  withAlpha,
  type ClusterDatum,
  type ClusterId,
  type DeflectionDatum,
  type DistrictId,
  type LayerToggles,
  type RegionId,
  type RegionStatsDatum,
  type RGBAColor,
  type Selection,
  type ViewTier,
} from "@/lib/worldview";
import type { DistrictFeatureProps, DistrictGeo } from "@/lib/worldview/geo/districts";
import type { StateFeatureCollection } from "@/lib/worldview/geo/states";
import { interventionColor, numericColor, type NumericDomain } from "@/lib/dataview/palette";
import type { DataViewColorMode } from "@/lib/dataview/store";
import type { RegionFeature, RegionFeatureCollection } from "./useRegionGeo";

export interface DataViewLayerParams {
  active: boolean;
  colorMode: DataViewColorMode;
  values: Record<DistrictId, number>;
  domain: NumericDomain;
}

export interface BuildLayersParams {
  geo: DistrictGeo;
  tier: ViewTier;
  stateGeo: StateFeatureCollection | null;
  regionGeo: RegionFeatureCollection | null;
  regionStats: Record<RegionId, RegionStatsDatum>;
  clusters: Record<ClusterId, ClusterDatum>;
  splitRegions: Set<RegionId>;
  toggles: LayerToggles;
  selection: Selection;
  hoveredClusterId: ClusterId | null;
  deflections: DeflectionDatum[];
  deflectionPair: { a: ClusterId | null; b: ClusterId | null };
  /** Precomputed by `computeColumnPositions`, memoized on [regionStats, regionGeo]. */
  columnPositions: Map<ClusterId, ColumnDatum>;
  dataView?: DataViewLayerParams;
}

export interface ColumnDatum {
  clusterId: ClusterId;
  regionId: RegionId;
  position: [number, number];
  volume: number;
  confidence: RegionStatsDatum["confidence"];
}

interface ArcDatum {
  source: [number, number];
  target: [number, number];
  colorA: RGBAColor;
  colorB: RGBAColor;
  highlight: boolean;
}

const LANDMASS_BASE_RGBA: RGBAColor = [42, 39, 36, 215];
const STATE_BORDER_RGBA: RGBAColor = [232, 218, 195, 205];
const STATE_BORDER_WIDTH_PX = 1.6;
const REGION_BORDER_RGBA: RGBAColor = [244, 238, 226, 235];
const KARNATAKA_STATE_CODE = "29";
/** Degrees — ring radius the per-cluster columns sit on around a region's label point. */
const COLUMN_RING_DEG = 0.28;
const REGION_COLUMN_RADIUS_METERS = 9000;

const districtProps = (f: Feature): DistrictFeatureProps =>
  f.properties as unknown as DistrictFeatureProps;

/**
 * One column per (region, cluster), ringed around the region's label point so
 * a region's competing viewpoints stand side by side. Memoize on
 * [regionStats, regionGeo] — this must not rerun on hover.
 */
export function computeColumnPositions(
  regionStats: Record<RegionId, RegionStatsDatum>,
  regionGeo: RegionFeatureCollection | null,
): Map<ClusterId, ColumnDatum> {
  const out = new Map<ClusterId, ColumnDatum>();
  if (!regionGeo) return out;
  for (const feature of regionGeo.features) {
    const { regionId, labelPoint } = feature.properties;
    const stats = regionStats[regionId];
    if (!stats) continue;
    const entries = Object.entries(stats.clusterVolumes)
      .filter(([, v]) => v > 0)
      .sort((a, b) => b[1] - a[1]);
    entries.forEach(([clusterId, volume], i) => {
      const angle = (2 * Math.PI * i) / entries.length - Math.PI / 2;
      const r = entries.length > 1 ? COLUMN_RING_DEG : 0;
      out.set(clusterId, {
        clusterId,
        regionId,
        position: [labelPoint[0] + r * Math.cos(angle), labelPoint[1] + r * Math.sin(angle)],
        volume,
        confidence: stats.confidence,
      });
    });
  }
  return out;
}

function regionFill(
  f: RegionFeature,
  regionStats: Record<RegionId, RegionStatsDatum>,
  clusters: Record<ClusterId, ClusterDatum>,
  selection: Selection,
): RGBAColor {
  const { regionId } = f.properties;
  const stats = regionStats[regionId];
  const selected = selection.kind === "region" && selection.id === regionId;
  if (stats?.clusterId) {
    return withAlpha(clusterColor(clusters, stats.clusterId), selected ? 175 : 125);
  }
  return withAlpha(regionColor(regionId), selected ? 110 : 60);
}

export function buildLayers(params: BuildLayersParams): Layer[] {
  const { geo, stateGeo, dataView, tier } = params;
  const layers: Layer[] = [];

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

  if (dataView?.active) {
    layers.push(
      new GeoJsonLayer({
        id: "district-base",
        data: geo.featureCollection as unknown as FeatureCollection,
        stroked: tier !== "Country view",
        lineWidthUnits: "pixels",
        getLineWidth: 0.5,
        getLineColor: [255, 255, 255, 28],
        filled: true,
        pickable: true,
        getFillColor: (f: Feature): RGBAColor => {
          const value = dataView.values[districtProps(f).districtId];
          if (value === undefined) return [0, 0, 0, 0];
          const rgb =
            dataView.colorMode === "dropoutRate"
              ? numericColor(value, dataView.domain)
              : interventionColor(value);
          return withAlpha(rgb, 150);
        },
        updateTriggers: {
          stroked: [tier],
          getFillColor: [dataView.colorMode, dataView.values, dataView.domain],
        },
      }),
    );
    pushStateBorders(layers, stateGeo);
    return layers;
  }

  pushStateBorders(layers, stateGeo);
  layers.push(...buildRegionLayers(params));
  return layers;
}

function pushStateBorders(layers: Layer[], stateGeo: StateFeatureCollection | null) {
  if (!stateGeo || stateGeo.features.length === 0) return;
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

function buildRegionLayers(params: BuildLayersParams): Layer[] {
  const {
    geo,
    regionGeo,
    regionStats,
    clusters,
    splitRegions,
    toggles,
    selection,
    hoveredClusterId,
    deflections,
    deflectionPair,
    columnPositions,
  } = params;
  const layers: Layer[] = [];
  if (!regionGeo) return layers;

  const karnatakaDistricts = geo.featureCollection.features.filter(
    (f) => f.properties.stateCode === KARNATAKA_STATE_CODE,
  );
  layers.push(
    new GeoJsonLayer({
      id: "karnataka-district-hairlines",
      data: {
        type: "FeatureCollection",
        features: karnatakaDistricts,
      } as unknown as FeatureCollection,
      stroked: true,
      filled: false,
      getLineColor: [255, 255, 255, 26],
      lineWidthUnits: "pixels",
      getLineWidth: 0.6,
      parameters: { depthCompare: "always" },
    }),
  );

  layers.push(
    new GeoJsonLayer({
      id: "region-fill",
      data: regionGeo as unknown as FeatureCollection,
      stroked: false,
      filled: true,
      pickable: true,
      getFillColor: (f: Feature) =>
        regionFill(f as RegionFeature, regionStats, clusters, selection),
      updateTriggers: { getFillColor: [regionStats, clusters, selection] },
    }),
  );

  layers.push(
    new GeoJsonLayer({
      id: "region-borders",
      data: regionGeo as unknown as FeatureCollection,
      stroked: true,
      filled: false,
      getLineColor: REGION_BORDER_RGBA,
      lineWidthUnits: "pixels",
      getLineWidth: 1.8,
      lineJointRounded: true,
      parameters: { depthCompare: "always" },
    }),
  );

  const highlighted = regionGeo.features.filter(
    (f) =>
      (toggles.splitRegions && splitRegions.has(f.properties.regionId)) ||
      (selection.kind === "region" && selection.id === f.properties.regionId),
  );
  if (highlighted.length > 0) {
    layers.push(
      new GeoJsonLayer({
        id: "region-highlight",
        data: { type: "FeatureCollection", features: highlighted } as unknown as FeatureCollection,
        stroked: true,
        filled: false,
        getLineColor: (f: Feature): RGBAColor =>
          selection.kind === "region" && selection.id === (f as RegionFeature).properties.regionId
            ? [255, 255, 255, 240]
            : [249, 183, 63, 220],
        lineWidthUnits: "pixels",
        getLineWidth: 3.2,
        lineJointRounded: true,
        parameters: { depthCompare: "always" },
        updateTriggers: { getLineColor: [selection] },
      }),
    );
  }

  const pairMatches = (d: DeflectionDatum): boolean => {
    const { a, b } = deflectionPair;
    if (!a || !b) return false;
    return (d.clusterA === a && d.clusterB === b) || (d.clusterA === b && d.clusterB === a);
  };
  const arcData: ArcDatum[] = [];
  for (const d of toggles.links ? deflections : deflections.filter(pairMatches)) {
    const s = columnPositions.get(d.clusterA);
    const t = columnPositions.get(d.clusterB);
    if (!s || !t) continue;
    arcData.push({
      source: s.position,
      target: t.position,
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
        getSourceColor: (d) => withAlpha(d.colorA, d.highlight ? 235 : 120),
        getTargetColor: (d) => withAlpha(d.colorB, d.highlight ? 235 : 120),
        getWidth: (d) => (d.highlight ? 3.2 : 1.5),
        getHeight: 0.4,
        parameters: { depthCompare: "always" },
      }),
    );
  }

  if (toggles.columns && columnPositions.size > 0) {
    const columnColor = (d: ColumnDatum): RGBAColor => {
      let alpha = confidenceAlpha(d.confidence);
      if (hoveredClusterId && d.clusterId !== hoveredClusterId) alpha = Math.round(alpha * 0.22);
      if (selection.kind === "region" && selection.id === d.regionId) alpha = 255;
      return withAlpha(clusterColor(clusters, d.clusterId), alpha);
    };
    layers.push(
      new ColumnLayer<ColumnDatum>({
        id: "viewpoint-columns",
        data: [...columnPositions.values()],
        diskResolution: 6,
        radius: REGION_COLUMN_RADIUS_METERS,
        radiusUnits: "meters",
        extruded: true,
        pickable: true,
        elevationScale: COLUMN_ELEVATION_SCALE * 2.2,
        getPosition: (d) => d.position,
        getElevation: (d) => d.volume,
        getFillColor: columnColor,
        material: { ambient: 0.55, diffuse: 0.6, shininess: 24, specularColor: [50, 50, 55] },
        updateTriggers: { getFillColor: [hoveredClusterId, selection, clusters] },
      }),
    );
  }

  layers.push(
    new TextLayer<RegionFeature>({
      id: "region-labels",
      data: regionGeo.features,
      getPosition: (f) => [f.properties.labelPoint[0], f.properties.labelPoint[1] - 0.42],
      getText: (f) => f.properties.shortName,
      getSize: 13,
      getColor: [244, 240, 232, 240],
      fontFamily: "Inter, system-ui, sans-serif",
      fontWeight: 600,
      background: true,
      getBackgroundColor: [20, 20, 24, 190],
      backgroundPadding: [6, 3],
      characterSet: "auto",
      parameters: { depthCompare: "always" },
    }),
  );

  return layers;
}
