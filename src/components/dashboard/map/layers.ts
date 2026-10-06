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
}

const LANDMASS_BASE_RGBA: RGBAColor = [42, 39, 36, 225];
const OTHER_STATE_FILL_RGBA: RGBAColor = [42, 39, 36, 55];
const OTHER_STATE_BORDER_RGBA: RGBAColor = [232, 218, 195, 42];
const STATE_BORDER_RGBA: RGBAColor = [232, 218, 195, 205];
const REGION_BORDER_RGBA: RGBAColor = [244, 238, 226, 235];
const KARNATAKA_STATE_CODE = "29";

const districtProps = (f: Feature): DistrictFeatureProps => f.properties as unknown as DistrictFeatureProps;

export function buildLayers({
  geo,
  stateGeo,
  regionGeo,
  districtToRegion,
  regionId,
  districtId,
}: BuildLayersParams): Layer[] {
  const layers: Layer[] = [];

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
        getFillColor: (f: Feature): RGBAColor => (isKarnataka(f) ? LANDMASS_BASE_RGBA : OTHER_STATE_FILL_RGBA),
        parameters: { depthCompare: "always" },
      }),
      new GeoJsonLayer({
        id: "state-borders",
        data: stateGeo as unknown as FeatureCollection,
        stroked: true,
        filled: false,
        getLineColor: (f: Feature): RGBAColor => (isKarnataka(f) ? STATE_BORDER_RGBA : OTHER_STATE_BORDER_RGBA),
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
        getLineColor: [255, 236, 200, 38],
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
      highlightColor: [255, 255, 255, 60],
      getFillColor: (f: Feature): RGBAColor => {
        const id = districtProps(f).districtId;
        const base = regionColor(districtToRegion[id] ?? "");
        if (id === districtId) return withAlpha(base, 240);
        return withAlpha(base, inFocus(id) ? 150 : 38);
      },
      updateTriggers: { getFillColor: [regionId, districtId, districtToRegion] },
    }),
    new GeoJsonLayer({
      id: "district-outlines",
      data: districtCollection,
      stroked: true,
      filled: false,
      lineWidthUnits: "pixels",
      getLineWidth: (f: Feature) => (districtProps(f).districtId === districtId ? 2.6 : 0.7),
      getLineColor: (f: Feature): RGBAColor =>
        districtProps(f).districtId === districtId ? [255, 255, 255, 255] : [255, 255, 255, inFocus(districtProps(f).districtId) ? 85 : 24],
      updateTriggers: { getLineWidth: [districtId], getLineColor: [regionId, districtId] },
      parameters: { depthCompare: "always" },
    }),
    new GeoJsonLayer({
      id: "region-borders",
      data: regionGeo as unknown as FeatureCollection,
      stroked: true,
      filled: false,
      getLineColor: (f: Feature): RGBAColor => {
        const id = (f as RegionFeature).properties.regionId;
        return !regionId || id === regionId ? REGION_BORDER_RGBA : [244, 238, 226, 70];
      },
      lineWidthUnits: "pixels",
      getLineWidth: 1.8,
      lineJointRounded: true,
      parameters: { depthCompare: "always" },
      updateTriggers: { getLineColor: [regionId] },
    }),
  );

  const labelStyle = {
    getColor: [244, 240, 232, 240] as RGBAColor,
    fontFamily: "Inter, system-ui, sans-serif",
    fontWeight: 600,
    background: true,
    getBackgroundColor: [20, 20, 24, 190] as RGBAColor,
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
        getBackgroundColor: [20, 20, 24, 170],
      }),
    );
  }

  return layers;
}
