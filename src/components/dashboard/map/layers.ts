/**
 * Builds the deck.gl layer stack for the Karnataka map. Imported only by
 * DeckMap, so all deck.gl code stays in the client-only chunk.
 *
 * Bottom → top: India state backing → state borders → district fills (each
 * district takes its persona region's colour; pickable) → district outlines →
 * region borders → labels (region names overview; district names once zoomed).
 */

import { GeoJsonLayer, TextLayer } from "@deck.gl/layers";
import type { Layer } from "@deck.gl/core";
import type { Feature, FeatureCollection } from "geojson";

import type { Theme } from "@/lib/theme";
import { regionColor, withAlpha, type RGBAColor } from "@/lib/worldview";
import type { DistrictFeatureProps, DistrictGeo } from "@/lib/worldview/geo/districts";
import type { StateFeatureCollection } from "@/lib/worldview/geo/states";
import type { RegionFeature, RegionFeatureCollection } from "./useRegionGeo";

export interface BuildLayersParams {
  geo: DistrictGeo;
  stateGeo: StateFeatureCollection | null;
  regionGeo: RegionFeatureCollection | null;
  /** district id -> persona region id */
  districtToRegion: Record<string, string>;
  regionId: string | null;
  districtId: string | null;
  theme: Theme;
}

interface MapPalette {
  landmassBase: RGBAColor;
  otherStateFill: RGBAColor;
  otherStateBorder: RGBAColor;
  stateBorder: RGBAColor;
  halo: RGBAColor;
  regionBorder: RGBAColor;
  regionBorderDim: RGBAColor;
  districtHighlight: RGBAColor;
  outlineSelected: RGBAColor;
  outline: RGBAColor;
  outlineDim: RGBAColor;
  /** district fill alphas: selected / in focus / out of focus */
  fillAlpha: readonly [number, number, number];
  labelText: RGBAColor;
  labelBg: RGBAColor;
  labelBgDistrict: RGBAColor;
}

const PALETTES: Record<Theme, MapPalette> = {
  dark: {
    landmassBase: [42, 39, 36, 225],
    otherStateFill: [42, 39, 36, 55],
    otherStateBorder: [232, 218, 195, 42],
    stateBorder: [232, 218, 195, 205],
    halo: [255, 236, 200, 38],
    regionBorder: [244, 238, 226, 235],
    regionBorderDim: [244, 238, 226, 70],
    districtHighlight: [255, 255, 255, 60],
    outlineSelected: [255, 255, 255, 255],
    outline: [255, 255, 255, 85],
    outlineDim: [255, 255, 255, 24],
    fillAlpha: [240, 150, 38],
    labelText: [244, 240, 232, 240],
    labelBg: [20, 20, 24, 190],
    labelBgDistrict: [20, 20, 24, 170],
  },
  light: {
    landmassBase: [255, 253, 248, 240],
    otherStateFill: [120, 112, 100, 26],
    otherStateBorder: [90, 80, 65, 45],
    stateBorder: [60, 52, 42, 200],
    halo: [90, 70, 40, 30],
    regionBorder: [45, 40, 34, 225],
    regionBorderDim: [45, 40, 34, 60],
    districtHighlight: [0, 0, 0, 45],
    outlineSelected: [30, 25, 20, 255],
    outline: [255, 255, 255, 200],
    outlineDim: [255, 255, 255, 70],
    fillAlpha: [245, 195, 60],
    labelText: [30, 28, 26, 245],
    labelBg: [255, 255, 255, 220],
    labelBgDistrict: [255, 255, 255, 205],
  },
};
const KARNATAKA_STATE_CODE = "29";

const districtProps = (f: Feature): DistrictFeatureProps =>
  f.properties as unknown as DistrictFeatureProps;

export function buildLayers({
  geo,
  stateGeo,
  regionGeo,
  districtToRegion,
  regionId,
  districtId,
  theme,
}: BuildLayersParams): Layer[] {
  const layers: Layer[] = [];
  const pal = PALETTES[theme];

  if (stateGeo && stateGeo.features.length > 0) {
    const isKarnataka = (f: unknown): boolean =>
      (f as { properties: { stateCode: string } }).properties.stateCode === KARNATAKA_STATE_CODE;
    const karnataka = {
      type: "FeatureCollection",
      features: stateGeo.features.filter(isKarnataka),
    } as unknown as FeatureCollection;
    layers.push(
      // Every other state is pushed far back so Karnataka alone reads as lit.
      new GeoJsonLayer({
        id: "state-solid-backing",
        data: stateGeo as unknown as FeatureCollection,
        stroked: false,
        filled: true,
        getFillColor: (f: Feature): RGBAColor =>
          isKarnataka(f) ? pal.landmassBase : pal.otherStateFill,
        updateTriggers: { getFillColor: [theme] },
        parameters: { depthCompare: "always" },
      }),
      new GeoJsonLayer({
        id: "state-borders",
        data: stateGeo as unknown as FeatureCollection,
        stroked: true,
        filled: false,
        getLineColor: (f: Feature): RGBAColor =>
          isKarnataka(f) ? pal.stateBorder : pal.otherStateBorder,
        updateTriggers: { getLineColor: [theme] },
        lineWidthUnits: "pixels",
        getLineWidth: (f: Feature) => (isKarnataka(f) ? 2 : 1),
        lineWidthMinPixels: 0.8,
        lineJointRounded: true,
        parameters: { depthCompare: "always" },
      }),
      // Soft halo around Karnataka's outline.
      new GeoJsonLayer({
        id: "karnataka-halo",
        data: karnataka,
        stroked: true,
        filled: false,
        getLineColor: pal.halo,
        updateTriggers: { getLineColor: [theme] },
        lineWidthUnits: "pixels",
        getLineWidth: 9,
        lineJointRounded: true,
        parameters: { depthCompare: "always" },
      }),
    );
  }

  if (!regionGeo) return layers;

  const karnatakaDistricts = geo.featureCollection.features.filter(
    (f) => f.properties.stateCode === KARNATAKA_STATE_CODE,
  );
  const districtCollection = {
    type: "FeatureCollection",
    features: karnatakaDistricts,
  } as unknown as FeatureCollection;

  const inFocus = (id: string): boolean => !regionId || districtToRegion[id] === regionId;

  layers.push(
    new GeoJsonLayer({
      id: "district-fill",
      data: districtCollection,
      stroked: false,
      filled: true,
      pickable: true,
      autoHighlight: true,
      highlightColor: pal.districtHighlight,
      getFillColor: (f: Feature): RGBAColor => {
        const id = districtProps(f).districtId;
        const base = regionColor(districtToRegion[id] ?? "");
        if (id === districtId) return withAlpha(base, pal.fillAlpha[0]);
        return withAlpha(base, inFocus(id) ? pal.fillAlpha[1] : pal.fillAlpha[2]);
      },
      updateTriggers: { getFillColor: [regionId, districtId, districtToRegion, theme] },
    }),
    new GeoJsonLayer({
      id: "district-outlines",
      data: districtCollection,
      stroked: true,
      filled: false,
      lineWidthUnits: "pixels",
      getLineWidth: (f: Feature) => (districtProps(f).districtId === districtId ? 2.6 : 0.7),
      getLineColor: (f: Feature): RGBAColor =>
        districtProps(f).districtId === districtId
          ? pal.outlineSelected
          : inFocus(districtProps(f).districtId)
            ? pal.outline
            : pal.outlineDim,
      updateTriggers: { getLineWidth: [districtId], getLineColor: [regionId, districtId, theme] },
      parameters: { depthCompare: "always" },
    }),
    new GeoJsonLayer({
      id: "region-borders",
      data: regionGeo as unknown as FeatureCollection,
      stroked: true,
      filled: false,
      getLineColor: (f: Feature): RGBAColor => {
        const id = (f as RegionFeature).properties.regionId;
        return !regionId || id === regionId ? pal.regionBorder : pal.regionBorderDim;
      },
      lineWidthUnits: "pixels",
      getLineWidth: 1.8,
      lineJointRounded: true,
      parameters: { depthCompare: "always" },
      updateTriggers: { getLineColor: [regionId, theme] },
    }),
  );

  const labelStyle = {
    getColor: pal.labelText,
    fontFamily: "Inter, system-ui, sans-serif",
    fontWeight: 600,
    background: true,
    getBackgroundColor: pal.labelBg,
    backgroundPadding: [6, 3] as [number, number],
    characterSet: "auto" as const,
    parameters: { depthCompare: "always" as const },
  };

  if (!regionId) {
    layers.push(
      new TextLayer<RegionFeature>({
        id: "region-labels",
        data: regionGeo.features,
        getPosition: (f) => f.properties.labelPoint,
        getText: (f) => f.properties.shortName,
        getSize: 13,
        ...labelStyle,
      }),
    );
  } else {
    const labelled = karnatakaDistricts.filter((f) => inFocus(districtProps(f).districtId));
    layers.push(
      new TextLayer<Feature>({
        id: "district-labels",
        data: labelled,
        getPosition: (f) => geo.districts[districtProps(f).districtId]?.centroid ?? [0, 0],
        getText: (f) => districtProps(f).districtName,
        getSize: 12,
        ...labelStyle,
        getBackgroundColor: pal.labelBgDistrict,
      }),
    );
  }

  return layers;
}
