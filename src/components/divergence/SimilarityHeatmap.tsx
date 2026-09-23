/**
 * Reply-similarity heatmap: rows/columns are every region's reply under each
 * condition. One-hue sequential ramp (dark mode: low = dark, high = light),
 * scaled over the off-diagonal values; the diagonal (self = 1) is neutral.
 * Values live in the hover tooltip and the Table view — never only in colour.
 */

import { useState } from "react";

import { regionColor, rgbaCss, type DivergenceSummary } from "@/lib/worldview";

// Reference sequential blue ramp, dark-mode order (700 -> 100).
const RAMP = [
  "#0d366b",
  "#104281",
  "#184f95",
  "#1c5cab",
  "#256abf",
  "#2a78d6",
  "#3987e5",
  "#5598e7",
  "#6da7ec",
  "#86b6ef",
  "#9ec5f4",
  "#b7d3f6",
  "#cde2fb",
];

function rampColor(t: number): string {
  const i = Math.round(Math.max(0, Math.min(1, t)) * (RAMP.length - 1));
  return RAMP[i] ?? RAMP[0]!;
}

export function SimilarityHeatmap({ summary }: { summary: DivergenceSummary }) {
  const [hover, setHover] = useState<{ i: number; j: number } | null>(null);
  const n = summary.labels.length;
  const off = summary.matrix.flatMap((row, i) => row.filter((_, j) => j !== i));
  const lo = off.length ? Math.min(...off) : 0;
  const hi = off.length ? Math.max(...off) : 1;
  const cell = 26;
  const labelW = 132;
  const w = labelW + n * (cell + 2);
  const h = n * (cell + 2) + 28;

  const label = (i: number) => {
    const l = summary.labels[i];
    return l ? `${l.regionName}${l.condition === "persona" ? "" : " · no persona"}` : "";
  };
  const hv = hover ? summary.matrix[hover.i]?.[hover.j] : undefined;

  return (
    <div className="mt-3">
      <div className="relative overflow-x-auto">
        <svg
          viewBox={`0 0 ${w} ${h}`}
          style={{ width: "100%", maxWidth: w }}
          role="img"
          aria-label="Reply similarity heatmap"
        >
          {summary.labels.map((l, i) => (
            <g key={`row-${i}`}>
              <rect
                x={1}
                y={i * (cell + 2) + cell / 2 - 4}
                width={8}
                height={8}
                rx={1.5}
                fill={l.condition === "persona" ? rgbaCss(regionColor(l.regionId)) : "none"}
                stroke={rgbaCss(regionColor(l.regionId))}
                strokeWidth={l.condition === "persona" ? 0 : 1.5}
              />
              <text
                x={14}
                y={i * (cell + 2) + cell / 2 + 3.5}
                fontSize={10}
                fill="var(--muted-foreground)"
              >
                {label(i)}
              </text>
            </g>
          ))}
          {summary.matrix.map((row, i) =>
            row.map((v, j) => {
              const diag = i === j;
              const hovered = hover?.i === i && hover.j === j;
              return (
                <rect
                  key={`${i}-${j}`}
                  x={labelW + j * (cell + 2)}
                  y={i * (cell + 2)}
                  width={cell}
                  height={cell}
                  rx={3}
                  fill={diag ? "var(--border)" : rampColor((v - lo) / (hi - lo || 1))}
                  stroke={hovered ? "var(--foreground)" : "none"}
                  strokeWidth={1.5}
                  tabIndex={0}
                  onPointerEnter={() => setHover({ i, j })}
                  onPointerLeave={() => setHover(null)}
                  onFocus={() => setHover({ i, j })}
                  onBlur={() => setHover(null)}
                  aria-label={`${label(i)} vs ${label(j)}: ${v.toFixed(2)}`}
                />
              );
            }),
          )}
          <text x={labelW} y={n * (cell + 2) + 16} fontSize={10} fill="var(--muted-foreground)">
            less alike {lo.toFixed(2)}
          </text>
          <text
            x={w}
            y={n * (cell + 2) + 16}
            fontSize={10}
            fill="var(--muted-foreground)"
            textAnchor="end"
          >
            {hi.toFixed(2)} more alike
          </text>
        </svg>
        {hover && hv !== undefined && (
          <div className="pointer-events-none absolute top-0 right-0 max-w-[240px] rounded-lg border border-panel-border bg-background/95 px-2.5 py-2 text-[11px] shadow-xl">
            <p className="text-[14px] font-semibold text-foreground">{hv.toFixed(3)}</p>
            <p className="text-muted-foreground">{label(hover.i)}</p>
            <p className="text-muted-foreground">vs {label(hover.j)}</p>
          </div>
        )}
      </div>
      <p className="mt-1 text-[10.5px] text-muted-foreground/70">
        Row key: filled = with persona, hollow = without (same as the t-SNE).
      </p>
    </div>
  );
}
