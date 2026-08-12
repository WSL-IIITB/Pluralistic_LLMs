/**
 * Client-only deck.gl map. Lazy-loaded by WorldviewMap so none of this — deck.gl,
 * mapbox-gl, or the mapbox CSS — is ever imported during SSR.
 *
 * Renders extruded 3D viewpoint columns over India, a subtle district choropleth
 * floor, deflection arcs, split-state highlights, and (optionally) a Mapbox dark
 * basemap when VITE_MAPBOX_TOKEN is set. With no token it draws on the dark
 * canvas alone — fully functional, just without street-level context.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import DeckGL from "@deck.gl/react";
import {
  AmbientLight,
  DirectionalLight,
  FlyToInterpolator,
  LightingEffect,
  WebMercatorViewport,
  type PickingInfo,
  type ViewStateChangeParameters,
} from "@deck.gl/core";
import Map from "react-map-gl/mapbox";
import "mapbox-gl/dist/mapbox-gl.css";

import {
  computeStateDiversity,
  INDIA_VIEW,
  splitStateCodes,
  useWorldviewStore,
  viewTierForZoom,
  ZOOM_TIERS,
  type ClusterId,
  type MapViewState,
  type ViewTier,
} from "@/lib/worldview";
import type { BBox, DistrictGeo } from "@/lib/worldview/geo/districts";
import { buildLayers, computeRepresentativeCentroids } from "./layers";
import { useStateGeo } from "./useStateGeo";

interface DeckMapProps {
  geo: DistrictGeo;
  mapboxToken: string | null;
  onViewTierChange: (tier: ViewTier) => void;
}

type ViewState = MapViewState & {
  transitionDuration?: number;
  transitionInterpolator?: FlyToInterpolator;
};

interface PickedDistrict {
  districtId: string;
  stateCode: string;
}

const MAP_STYLE = "mapbox://styles/mapbox/dark-v11";

const HTML_ESCAPES: Record<string, string> = {
  "&": "&amp;",
  "<": "&lt;",
  ">": "&gt;",
  '"': "&quot;",
  "'": "&#39;",
};

/** Escapes text interpolated into the tooltip's `html`; names/labels may originate from an LLM backend. */
function escapeHtml(input: string): string {
  return input.replace(/[&<>"']/g, (ch) => HTML_ESCAPES[ch] ?? ch);
}

function pickDistrict(info: PickingInfo): PickedDistrict | null {
  const o = info.object as unknown;
  if (!o || typeof o !== "object") return null;
  if ("districtId" in o && "stateCode" in o) {
    const c = o as { districtId: string; stateCode: string };
    return { districtId: c.districtId, stateCode: c.stateCode };
  }
  if ("properties" in o) {
    const p = (o as { properties?: { districtId?: string; stateCode?: string } }).properties;
    if (p?.districtId && p?.stateCode) return { districtId: p.districtId, stateCode: p.stateCode };
  }
  return null;
}

export default function DeckMap({ geo, mapboxToken, onViewTierChange }: DeckMapProps) {
  const [viewState, setViewState] = useState<ViewState>(INDIA_VIEW);
  const sizeRef = useRef<{ width: number; height: number }>({ width: 1280, height: 800 });
  const tierRef = useRef<ViewTier>(viewTierForZoom(INDIA_VIEW.zoom));

  // Store slices (each change re-renders the map, which is what we want live).
  const districts = useWorldviewStore((s) => s.districts);
  const clusters = useWorldviewStore((s) => s.clusters);
  const deflections = useWorldviewStore((s) => s.deflections);
  const toggles = useWorldviewStore((s) => s.layers);
  const selection = useWorldviewStore((s) => s.selection);
  const hoveredClusterId = useWorldviewStore((s) => s.hoveredClusterId);
  const deflectionPair = useWorldviewStore((s) => s.deflectionPair);

  const stateGeo = useStateGeo();
  const tier = viewTierForZoom(viewState.zoom);

  const stateDiversity = useMemo(() => computeStateDiversity(districts), [districts]);
  const splitStates = useMemo(() => splitStateCodes(stateDiversity), [stateDiversity]);
  // Deliberately keyed only on [districts, geo] -- NOT hoveredClusterId/
  // selection/deflectionPair, which `layers` below also depends on. Hoisted
  // out of buildLayers() specifically so hovering a Legend/Deflection row
  // doesn't re-scan every district per cluster on each hover event; see
  // computeRepresentativeCentroids's doc comment in layers.ts.
  const representativeCentroids = useMemo(
    () => computeRepresentativeCentroids(districts, geo),
    [districts, geo],
  );

  const layers = useMemo(
    () =>
      buildLayers({
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
      }),
    [
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
    ],
  );

  const effects = useMemo(() => {
    const ambient = new AmbientLight({ color: [255, 245, 230], intensity: 1.5 });
    const key = new DirectionalLight({
      color: [255, 235, 210],
      intensity: 1.1,
      direction: [-1, -3, -1],
    });
    const fill = new DirectionalLight({
      color: [180, 190, 220],
      intensity: 0.5,
      direction: [2, 1, -1],
    });
    return [new LightingEffect({ ambient, key, fill })];
  }, []);

  const reportTier = useCallback(
    (zoom: number) => {
      const tier = viewTierForZoom(zoom);
      if (tier !== tierRef.current) {
        tierRef.current = tier;
        onViewTierChange(tier);
      }
    },
    [onViewTierChange],
  );

  useEffect(() => reportTier(viewState.zoom), [reportTier, viewState.zoom]);

  const flyToBBox = useCallback((bbox: BBox, fallbackZoom: number) => {
    const { width, height } = sizeRef.current;
    let longitude = (bbox[0] + bbox[2]) / 2;
    let latitude = (bbox[1] + bbox[3]) / 2;
    let zoom = fallbackZoom;
    try {
      const vp = new WebMercatorViewport({ width, height });
      const fit = vp.fitBounds(
        [
          [bbox[0], bbox[1]],
          [bbox[2], bbox[3]],
        ],
        { padding: 120 },
      );
      longitude = fit.longitude;
      latitude = fit.latitude;
      zoom = Math.min(fit.zoom, 8.5);
    } catch {
      /* keep centroid fallback */
    }
    setViewState((prev) => ({
      ...prev,
      longitude,
      latitude,
      zoom,
      pitch: 48,
      transitionDuration: 1100,
      transitionInterpolator: new FlyToInterpolator(),
    }));
  }, []);

  const handleClick = useCallback(
    (info: PickingInfo) => {
      const picked = pickDistrict(info);
      const store = useWorldviewStore.getState();
      if (!picked) {
        store.clearSelection();
        return;
      }
      const atCountry = viewState.zoom < ZOOM_TIERS.country;
      if (atCountry) {
        store.select({ kind: "state", id: picked.stateCode });
        const st = geo.states[picked.stateCode];
        if (st) flyToBBox(st.bbox, 5.6);
      } else {
        store.select({ kind: "district", id: picked.districtId });
        const d = geo.districts[picked.districtId];
        if (d) {
          setViewState((prev) => ({
            ...prev,
            longitude: d.centroid[0],
            latitude: d.centroid[1],
            zoom: Math.max(prev.zoom, 7.4),
            pitch: 52,
            transitionDuration: 900,
            transitionInterpolator: new FlyToInterpolator(),
          }));
        }
      }
    },
    [geo, viewState.zoom, flyToBBox],
  );

  const getTooltip = useCallback(
    (info: PickingInfo): { html: string; style: Record<string, string> } | null => {
      const picked = pickDistrict(info);
      if (!picked) return null;
      const store = useWorldviewStore.getState();
      const d = store.districts[picked.districtId];
      const loaded = geo.districts[picked.districtId];
      const name = loaded?.name ?? picked.districtId;
      const stateName = loaded?.stateName ?? "";
      const clusterId: ClusterId | null = d?.clusterId ?? null;
      const label = clusterId ? (store.clusters[clusterId]?.label ?? clusterId) : "no data yet";
      const conf = d ? d.confidence : "—";
      const vol = d ? d.volume : 0;
      return {
        html: `<div style="font-weight:600">${escapeHtml(name)}</div>
               <div style="opacity:.7">${escapeHtml(stateName)}</div>
               <div style="margin-top:4px">${escapeHtml(label)}</div>
               <div style="opacity:.7">confidence: ${escapeHtml(conf)}${vol ? ` · ${vol} posts` : ""}</div>`,
        style: {
          background: "rgba(20,20,24,0.92)",
          color: "#f4f2ee",
          fontSize: "11px",
          padding: "8px 10px",
          borderRadius: "8px",
          border: "1px solid rgba(255,255,255,0.1)",
          boxShadow: "0 12px 30px -12px rgba(0,0,0,0.8)",
        },
      };
    },
    [geo],
  );

  return (
    <DeckGL
      viewState={viewState}
      controller={{ dragRotate: true, touchRotate: true }}
      layers={layers}
      effects={effects}
      onViewStateChange={(params: ViewStateChangeParameters) => {
        const vs = params.viewState as ViewState;
        setViewState(vs);
        reportTier(vs.zoom);
      }}
      onResize={(size: { width: number; height: number }) => {
        sizeRef.current = size;
      }}
      onClick={handleClick}
      getTooltip={getTooltip}
      getCursor={({ isDragging, isHovering }) =>
        isDragging ? "grabbing" : isHovering ? "pointer" : "grab"
      }
      style={{ position: "absolute", inset: "0" }}
    >
      {mapboxToken ? (
        <Map
          reuseMaps
          mapStyle={MAP_STYLE}
          mapboxAccessToken={mapboxToken}
          attributionControl={false}
        />
      ) : null}
    </DeckGL>
  );
}
