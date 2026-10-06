/**
 * Client-only deck.gl map. Lazy-loaded by WorldviewMap so none of this — deck.gl,
 * mapbox-gl, or the mapbox CSS — is ever imported during SSR.
 *
 * A flat view of Karnataka's six persona regions. The user cannot pan, zoom or
 * rotate; the camera only moves programmatically — it frames all of Karnataka,
 * or flies to the region / district chosen by a click (or from the panels),
 * leaving room at the bottom for the detail sheet. Esc or a click on empty map
 * zooms back out. Optional Mapbox dark basemap when VITE_MAPBOX_TOKEN is set.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import DeckGL from "@deck.gl/react";
import { FlyToInterpolator, WebMercatorViewport, type PickingInfo } from "@deck.gl/core";
import Map from "react-map-gl/mapbox";
import "mapbox-gl/dist/mapbox-gl.css";

import { KARNATAKA_VIEW, regionShortName, useExplorerStore, type MapViewState } from "@/lib/worldview";
import type { BBox, DistrictFeatureProps, DistrictGeo } from "@/lib/worldview/geo/districts";
import { buildLayers } from "./layers";
import { useRegionGeo } from "./useRegionGeo";
import { useStateGeo } from "./useStateGeo";

interface DeckMapProps {
  geo: DistrictGeo;
  mapboxToken: string | null;
}

type ViewState = MapViewState & {
  transitionDuration?: number;
  transitionInterpolator?: FlyToInterpolator;
};

const MAP_STYLE = "mapbox://styles/mapbox/dark-v11";

const KARNATAKA_BOUNDS: BBox = [74.0, 11.5, 78.6, 18.5];
const FALLBACK_VIEW: ViewState = { ...KARNATAKA_VIEW, pitch: 0, bearing: 0 };
/** Share of the map's height kept clear at the bottom for the detail sheet when something is focused. */
const SHEET_FRACTION = 0.46;
/** Top inset: room for the region pills overlaid on the map (they wrap to two rows when narrow). */
const topInset = (width: number) => (width < 640 ? 82 : 52);

const NO_INTERACTION = {
  dragPan: false,
  dragRotate: false,
  scrollZoom: false,
  touchZoom: false,
  touchRotate: false,
  doubleClickZoom: false,
  keyboard: false,
} as const;

function frame(bbox: BBox, width: number, height: number, focused: boolean, maxZoom: number): ViewState {
  const bottom = focused ? Math.round(height * SHEET_FRACTION) : 24;
  try {
    const fit = new WebMercatorViewport({ width, height }).fitBounds(
      [
        [bbox[0], bbox[1]],
        [bbox[2], bbox[3]],
      ],
      { padding: { top: topInset(width), bottom, left: 28, right: 28 }, maxZoom },
    );
    return { longitude: fit.longitude, latitude: fit.latitude, zoom: fit.zoom, pitch: 0, bearing: 0 };
  } catch {
    return FALLBACK_VIEW;
  }
}

const escapeHtml = (s: string) => s.replace(/[&<>"']/g, (c) => `&#${c.charCodeAt(0)};`);

export default function DeckMap({ geo, mapboxToken }: DeckMapProps) {
  const stateGeo = useStateGeo();
  const regionGeo = useRegionGeo();

  const regionId = useExplorerStore((s) => s.regionId);
  const districtId = useExplorerStore((s) => s.districtId);

  const districtToRegion = useMemo(() => {
    const out: Record<string, string> = {};
    for (const f of regionGeo?.features ?? []) {
      for (const id of f.properties.districtIds) out[id] = f.properties.regionId;
    }
    return out;
  }, [regionGeo]);

  const layers = useMemo(
    () => buildLayers({ geo, stateGeo, regionGeo, districtToRegion, regionId, districtId }),
    [geo, stateGeo, regionGeo, districtToRegion, regionId, districtId],
  );

  // ── Camera ────────────────────────────────────────────────────────────────
  const [size, setSize] = useState<{ width: number; height: number } | null>(null);
  const [viewState, setViewState] = useState<ViewState>(FALLBACK_VIEW);
  const lastFocusKey = useRef<string>("");

  useEffect(() => {
    if (!size) return;
    let bbox: BBox = KARNATAKA_BOUNDS;
    let maxZoom = 12;
    if (districtId) {
      bbox = geo.districts[districtId]?.bbox ?? bbox;
      maxZoom = 9.2;
    } else if (regionId) {
      bbox = regionGeo?.features.find((f) => f.properties.regionId === regionId)?.properties.bbox ?? bbox;
      maxZoom = 8;
    }
    const next = frame(bbox, size.width, size.height, !!(districtId || regionId), maxZoom);
    const focusKey = `${regionId ?? ""}|${districtId ?? ""}`;
    const focusChanged = focusKey !== lastFocusKey.current && lastFocusKey.current !== "";
    lastFocusKey.current = focusKey;
    setViewState(
      focusChanged
        ? { ...next, transitionDuration: 900, transitionInterpolator: new FlyToInterpolator() }
        : next,
    );
  }, [size, regionId, districtId, geo, regionGeo]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") useExplorerStore.getState().resetFocus();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  // ── Interaction ───────────────────────────────────────────────────────────
  const pickedDistrict = (info: PickingInfo): DistrictFeatureProps | null => {
    const props = (info.object as { properties?: Partial<DistrictFeatureProps> } | null)?.properties;
    return props?.districtId ? (props as DistrictFeatureProps) : null;
  };

  const handleClick = useCallback(
    (info: PickingInfo) => {
      const d = pickedDistrict(info);
      const store = useExplorerStore.getState();
      if (!d) {
        store.resetFocus();
        return;
      }
      const rid = districtToRegion[d.districtId];
      if (rid) store.focusDistrict(d.districtId, rid);
    },
    [districtToRegion],
  );

  const getTooltip = useCallback(
    (info: PickingInfo) => {
      const d = pickedDistrict(info);
      if (!d) return null;
      const rid = districtToRegion[d.districtId];
      return {
        html: `<div style="font-weight:600">${escapeHtml(d.districtName)}</div><div style="opacity:.7">${escapeHtml(regionShortName(rid))}</div>`,
        style: {
          background: "rgba(20,20,24,0.92)",
          color: "#f4f2ee",
          fontSize: "11px",
          padding: "7px 10px",
          borderRadius: "8px",
          border: "1px solid rgba(255,255,255,0.1)",
        },
      };
    },
    [districtToRegion],
  );

  return (
    <DeckGL
      viewState={viewState}
      controller={NO_INTERACTION}
      layers={layers}
      onResize={({ width, height }: { width: number; height: number }) => {
        if (width > 0 && height > 0) setSize({ width, height });
      }}
      onClick={handleClick}
      getTooltip={getTooltip}
      getCursor={({ isHovering }) => (isHovering ? "pointer" : "default")}
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
