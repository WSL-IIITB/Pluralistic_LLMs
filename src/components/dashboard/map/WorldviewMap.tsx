/**
 * WorldviewMap — the real 3D map, replacing the old MapPlaceholder.
 *
 * Design contract:
 *  • The dark backdrop (grid graticule + warm horizon glow) and the corner chips
 *    are preserved from the original placeholder, so the cartographic aesthetic
 *    is identical.
 *  • deck.gl / mapbox are loaded ONLY on the client, ONLY after mount, via a
 *    lazy import wrapped in an error boundary. On the server (and if WebGL or the
 *    map libs fail), we render just the backdrop + a hint — never a crash.
 *  • The district GeoJSON is fetched lazily; if it's missing the map degrades to
 *    the backdrop while the rest of the dashboard (stream, panels) keeps working.
 */

import { Component, lazy, Suspense, useEffect, useState, type ReactNode } from "react";

import { viewTierForZoom, INDIA_VIEW, type ViewTier } from "@/lib/worldview";
import { useDistrictGeo } from "./useDistrictGeo";

const DeckMap = lazy(() => import("./DeckMap"));

function readMapboxToken(): string | null {
  const env = (import.meta.env ?? {}) as Record<string, string | undefined>;
  const token = env["VITE_MAPBOX_TOKEN"];
  return token && token.trim().length > 0 ? token.trim() : null;
}

// ── Backdrop (always rendered; identical to the original placeholder) ──────────
function MapBackdrop() {
  return (
    <>
      <div
        aria-hidden
        className="absolute inset-0 opacity-[0.35]"
        style={{
          backgroundImage:
            "linear-gradient(to right, oklch(1 0 0 / 4%) 1px, transparent 1px), linear-gradient(to bottom, oklch(1 0 0 / 4%) 1px, transparent 1px)",
          backgroundSize: "72px 72px",
        }}
      />
      <div
        aria-hidden
        className="absolute inset-0"
        style={{
          background:
            "radial-gradient(60% 50% at 50% 55%, oklch(0.78 0.16 65 / 7%), transparent 70%)",
        }}
      />
    </>
  );
}

// ── Faint India hint, shown only when no live map is drawn yet ──────────────────
function MapEmptyHint({ label }: { label: string }) {
  return (
    <>
      <svg
        aria-hidden
        viewBox="0 0 200 240"
        className="absolute top-1/2 left-1/2 h-[78vh] -translate-x-1/2 -translate-y-1/2 opacity-[0.12]"
      >
        <path
          d="M62 22 L92 14 L120 26 L142 20 L156 36 L150 58 L162 72 L152 96 L138 108 L132 132 L118 168 L104 208 L92 226 L82 200 L70 168 L52 140 L40 112 L28 88 L34 66 L48 52 L44 34 Z"
          fill="oklch(0.78 0.16 65 / 10%)"
          stroke="oklch(0.8 0.05 70 / 55%)"
          strokeWidth="0.8"
        />
      </svg>
      <p className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 text-[11px] tracking-[0.3em] text-muted-foreground/40 uppercase">
        {label}
      </p>
    </>
  );
}

// ── Error boundary so a WebGL / map-lib failure degrades to the backdrop ────────
class MapErrorBoundary extends Component<
  { children: ReactNode; onError: () => void },
  { failed: boolean }
> {
  override state = { failed: false };
  static getDerivedStateFromError() {
    return { failed: true };
  }
  override componentDidCatch() {
    this.props.onError();
  }
  override render() {
    if (this.state.failed) return null;
    return this.props.children;
  }
}

// ── Client-only map subtree (geo load + deck) ──────────────────────────────────
function ClientMap({
  onViewTierChange,
  dataViewActive,
}: {
  onViewTierChange: (tier: ViewTier) => void;
  dataViewActive: boolean;
}) {
  const { geo, status } = useDistrictGeo();
  const [failed, setFailed] = useState(false);
  const token = readMapboxToken();

  if (failed) return <MapEmptyHint label="map unavailable — showing data only" />;
  if (status === "loading") return null;
  if (status === "missing" || !geo)
    return (
      <MapEmptyHint label="district boundaries not found — drop geo/india-districts.geojson" />
    );

  return (
    <MapErrorBoundary onError={() => setFailed(true)}>
      <Suspense fallback={null}>
        <DeckMap
          geo={geo}
          mapboxToken={token}
          onViewTierChange={onViewTierChange}
          dataViewActive={dataViewActive}
        />
      </Suspense>
    </MapErrorBoundary>
  );
}

interface WorldviewMapProps {
  /** True when the "Data" tab is active — see routes/index.tsx. Threaded down
   * to DeckMap; defaults to false so every existing Story View caller is unaffected. */
  dataViewActive?: boolean;
}

export function WorldviewMap({ dataViewActive = false }: WorldviewMapProps) {
  const [mounted, setMounted] = useState(false);
  const [tier, setTier] = useState<ViewTier>(viewTierForZoom(INDIA_VIEW.zoom));

  useEffect(() => setMounted(true), []);

  return (
    <div className="absolute inset-0 overflow-hidden bg-background">
      <MapBackdrop />

      {mounted ? (
        <ClientMap onViewTierChange={setTier} dataViewActive={dataViewActive} />
      ) : (
        <MapEmptyHint label="3D map of India" />
      )}

      <div className="pointer-events-none absolute bottom-3 left-3 rounded-md border border-panel-border bg-panel px-2 py-1 text-[10px] text-muted-foreground/70 backdrop-blur-sm">
        © Mapbox · © OpenStreetMap
      </div>
      <div className="pointer-events-none absolute right-3 bottom-3 rounded-md border border-panel-border bg-panel px-2 py-1 text-[10px] tracking-wide text-muted-foreground/70 uppercase backdrop-blur-sm">
        {tier}
      </div>
    </div>
  );
}
