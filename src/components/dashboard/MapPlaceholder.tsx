/**
 * Static stand-in for the future interactive 3D map of India.
 * No map SDK is loaded — replace the inner content when wiring deck.gl/Mapbox.
 */
export function MapPlaceholder() {
  return (
    <div className="absolute inset-0 overflow-hidden bg-background">
      {/* faint grid graticule */}
      <div
        aria-hidden
        className="absolute inset-0 opacity-[0.35]"
        style={{
          backgroundImage:
            "linear-gradient(to right, oklch(1 0 0 / 4%) 1px, transparent 1px), linear-gradient(to bottom, oklch(1 0 0 / 4%) 1px, transparent 1px)",
          backgroundSize: "72px 72px",
        }}
      />
      {/* warm horizon glow */}
      <div
        aria-hidden
        className="absolute inset-0"
        style={{
          background:
            "radial-gradient(60% 50% at 50% 55%, oklch(0.78 0.16 65 / 7%), transparent 70%)",
        }}
      />

      <svg
        aria-hidden
        viewBox="0 0 200 240"
        className="absolute top-1/2 left-1/2 h-[78vh] -translate-x-1/2 -translate-y-1/2 opacity-[0.14]"
      >
        <path
          d="M62 22 L92 14 L120 26 L142 20 L156 36 L150 58 L162 72 L152 96 L138 108 L132 132 L118 168 L104 208 L92 226 L82 200 L70 168 L52 140 L40 112 L28 88 L34 66 L48 52 L44 34 Z"
          fill="oklch(0.78 0.16 65 / 10%)"
          stroke="oklch(0.8 0.05 70 / 55%)"
          strokeWidth="0.8"
        />
      </svg>

      <p className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 text-[11px] tracking-[0.3em] text-muted-foreground/40 uppercase">
        3D map of India renders here
      </p>

      <div className="absolute bottom-3 left-3 rounded-md border border-panel-border bg-panel px-2 py-1 text-[10px] text-muted-foreground/70 backdrop-blur-sm">
        © Mapbox · © OpenStreetMap
      </div>
      <div className="absolute right-3 bottom-3 rounded-md border border-panel-border bg-panel px-2 py-1 text-[10px] tracking-wide text-muted-foreground/70 uppercase backdrop-blur-sm">
        State view
      </div>
    </div>
  );
}
