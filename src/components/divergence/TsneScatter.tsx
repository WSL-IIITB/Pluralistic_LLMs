/**
 * t-SNE scatter of every extracted point. Region = colour AND shape (4 regions
 * sit in the CVD warn band, so colour never carries identity alone); condition
 * = filled (persona) vs hollow (no persona). Each point has a 24px hit target.
 */

import { useMemo, useState } from "react";

import {
  KARNATAKA_REGIONS,
  regionColor,
  regionShortName,
  rgbaCss,
  type DivergenceEmbeddingPoint,
  type RegionId,
} from "@/lib/worldview";

const W = 560;
const H = 360;
const PAD = 18;

type Shape = "circle" | "square" | "triangle" | "diamond";
const SHAPES: Record<RegionId, Shape> = {
  "mysuru-bengaluru": "circle",
  "north-karnataka": "square",
  karavali: "triangle",
  malnad: "diamond",
};

function Marker({
  shape,
  x,
  y,
  color,
  filled,
}: {
  shape: Shape;
  x: number;
  y: number;
  color: string;
  filled: boolean;
}) {
  const r = 5;
  const common = {
    fill: filled ? color : "var(--background)",
    stroke: filled ? "var(--background)" : color,
    strokeWidth: 2,
  };
  if (shape === "square")
    return <rect x={x - r} y={y - r} width={2 * r} height={2 * r} rx={1} {...common} />;
  if (shape === "triangle")
    return (
      <polygon
        points={`${x},${y - r - 1} ${x + r + 1},${y + r} ${x - r - 1},${y + r}`}
        {...common}
      />
    );
  if (shape === "diamond")
    return (
      <polygon
        points={`${x},${y - r - 1} ${x + r + 1},${y} ${x},${y + r + 1} ${x - r - 1},${y}`}
        {...common}
      />
    );
  return <circle cx={x} cy={y} r={r} {...common} />;
}

export function TsneScatter({ points }: { points: DivergenceEmbeddingPoint[] }) {
  const [hover, setHover] = useState<number | null>(null);

  const scaled = useMemo(() => {
    if (points.length === 0) return [];
    const xs = points.map((p) => p.x);
    const ys = points.map((p) => p.y);
    const [x0, x1] = [Math.min(...xs), Math.max(...xs)];
    const [y0, y1] = [Math.min(...ys), Math.max(...ys)];
    const sx = (v: number) => PAD + ((v - x0) / (x1 - x0 || 1)) * (W - 2 * PAD);
    const sy = (v: number) => PAD + ((v - y0) / (y1 - y0 || 1)) * (H - 2 * PAD);
    return points.map((p) => ({ ...p, px: sx(p.x), py: sy(p.y) }));
  }, [points]);

  if (points.length === 0) {
    return (
      <p className="mt-3 text-[12px] text-muted-foreground/70">
        Too few points this run to project.
      </p>
    );
  }

  const hovered = hover !== null ? scaled[hover] : undefined;

  return (
    <div className="mt-2">
      <Legend />
      <div className="relative">
        <svg
          viewBox={`0 0 ${W} ${H}`}
          className="w-full"
          role="img"
          aria-label="t-SNE projection of reply points"
        >
          <rect
            x={0.5}
            y={0.5}
            width={W - 1}
            height={H - 1}
            fill="none"
            stroke="var(--border)"
            strokeWidth={1}
            rx={6}
          />
          {scaled.map((p, i) => (
            <g key={i}>
              <Marker
                shape={SHAPES[p.regionId] ?? "circle"}
                x={p.px}
                y={p.py}
                color={rgbaCss(regionColor(p.regionId))}
                filled={p.condition === "persona"}
              />
              <circle
                cx={p.px}
                cy={p.py}
                r={12}
                fill="transparent"
                tabIndex={0}
                onPointerEnter={() => setHover(i)}
                onPointerLeave={() => setHover(null)}
                onFocus={() => setHover(i)}
                onBlur={() => setHover(null)}
                aria-label={`${regionShortName(p.regionId)}, ${p.condition === "persona" ? "with persona" : "without persona"}: ${p.text}`}
              />
              {hover === i && (
                <circle
                  cx={p.px}
                  cy={p.py}
                  r={9}
                  fill="none"
                  stroke="var(--foreground)"
                  strokeWidth={1.5}
                />
              )}
            </g>
          ))}
        </svg>
        {hovered && (
          <div
            className="pointer-events-none absolute z-10 max-w-[280px] rounded-lg border border-panel-border bg-background/95 px-2.5 py-2 text-[11px] shadow-xl"
            style={{
              left: `${(hovered.px / W) * 100}%`,
              top: `${(hovered.py / H) * 100}%`,
              transform: `translate(${hovered.px > W / 2 ? "-105%" : "5%"}, -50%)`,
            }}
          >
            <p className="leading-snug text-foreground">{hovered.text}</p>
            <p className="mt-1 flex items-center gap-1.5 text-muted-foreground">
              <span
                className="inline-block h-[2px] w-3"
                style={{ backgroundColor: rgbaCss(regionColor(hovered.regionId)) }}
              />
              {regionShortName(hovered.regionId)} ·{" "}
              {hovered.condition === "persona" ? "with persona" : "without persona"}
            </p>
          </div>
        )}
      </div>
    </div>
  );
}

function Legend() {
  return (
    <div className="mb-1.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-[10.5px] text-muted-foreground">
      {KARNATAKA_REGIONS.map((r) => (
        <span key={r.id} className="flex items-center gap-1">
          <svg width={14} height={14} viewBox="0 0 14 14" aria-hidden>
            <Marker shape={SHAPES[r.id] ?? "circle"} x={7} y={7} color={rgbaCss(r.color)} filled />
          </svg>
          {r.shortName}
        </span>
      ))}
      <span className="flex items-center gap-1">
        <svg width={14} height={14} viewBox="0 0 14 14" aria-hidden>
          <circle cx={7} cy={7} r={5} fill="var(--muted-foreground)" />
        </svg>
        with persona
      </span>
      <span className="flex items-center gap-1">
        <svg width={14} height={14} viewBox="0 0 14 14" aria-hidden>
          <circle
            cx={7}
            cy={7}
            r={4.5}
            fill="none"
            stroke="var(--muted-foreground)"
            strokeWidth={2}
          />
        </svg>
        without
      </span>
    </div>
  );
}
