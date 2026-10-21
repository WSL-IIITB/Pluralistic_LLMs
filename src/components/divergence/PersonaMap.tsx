/**
 * 2-D map of every persona answer: for each region, the generic answer (no persona) and the
 * man's and woman's answers (with persona). Points that sit close together say similar things.
 * The layout is precomputed (scripts/build_persona_map.py) from sentence embeddings of the
 * replies, projected with t-SNE or classical MDS — see the reading note rendered below.
 */

import { useMemo, useState } from "react";

import {
  KARNATAKA_REGIONS,
  regionColor,
  regionShortName,
  rgbaCss,
  useWorldviewStore,
  type PersonaMapPoint,
  type RegionId,
} from "@/lib/worldview";

type Method = "tsne" | "mds";

const METHODS: { id: Method; label: string; note: string }[] = [
  {
    id: "tsne",
    label: "t-SNE",
    note: "t-SNE keeps close neighbours together and can stretch the gaps between groups.",
  },
  {
    id: "mds",
    label: "MDS",
    note: "MDS keeps overall distances more faithfully, so far-apart answers really are different.",
  },
];

const CONDITION_LABEL: Record<PersonaMapPoint["condition"], string> = {
  baseline: "Generic answer (no persona)",
  male: "Man's answer (with persona)",
  female: "Woman's answer (with persona)",
};

const W = 440;
const H = 380;
const PAD = 30;

function Marker({
  condition,
  x,
  y,
  color,
  active,
}: {
  condition: PersonaMapPoint["condition"];
  x: number;
  y: number;
  color: string;
  active: boolean;
}) {
  const stroke = "var(--card)";
  if (condition === "baseline") {
    // hollow ring = the answer without a persona
    return (
      <circle
        cx={x}
        cy={y}
        r={active ? 10 : 8.5}
        fill="var(--card)"
        stroke={color}
        strokeWidth={3}
      />
    );
  }
  if (condition === "male") {
    const r = active ? 10.5 : 9;
    return (
      <polygon
        points={`${x},${y - r} ${x + r * 0.95},${y + r * 0.7} ${x - r * 0.95},${y + r * 0.7}`}
        fill={color}
        stroke={stroke}
        strokeWidth={1.5}
        strokeLinejoin="round"
      />
    );
  }
  return (
    <circle cx={x} cy={y} r={active ? 8.5 : 7} fill={color} stroke={stroke} strokeWidth={1.5} />
  );
}

export function PersonaMap() {
  const map = useWorldviewStore((s) => s.personaSimilarityMap);
  const [method, setMethod] = useState<Method>("tsne");
  const [region, setRegion] = useState<RegionId | null>(null);
  const [hover, setHover] = useState<number | null>(null);

  const layout = useMemo(() => {
    if (!map) return null;
    const xs = map.points.map((p) => p[method][0]);
    const ys = map.points.map((p) => p[method][1]);
    const [x0, x1] = [Math.min(...xs), Math.max(...xs)];
    const [y0, y1] = [Math.min(...ys), Math.max(...ys)];
    const scale = Math.min((W - 2 * PAD) / (x1 - x0 || 1), (H - 2 * PAD) / (y1 - y0 || 1));
    const ox = (W - (x1 - x0) * scale) / 2;
    const oy = (H - (y1 - y0) * scale) / 2;
    return map.points.map((p) => ({
      p,
      x: ox + (p[method][0] - x0) * scale,
      y: H - (oy + (p[method][1] - y0) * scale),
    }));
  }, [map, method]);

  if (!map || !layout) return null;

  const shown = (rid: string): boolean => !region || rid === region;
  const hovered = hover != null ? layout[hover] : null;
  const regionsPresent = KARNATAKA_REGIONS.filter((r) =>
    map.points.some((p) => p.regionId === r.id),
  );
  const methodNote = METHODS.find((m) => m.id === method)?.note;

  return (
    <section
      aria-label="Persona answer map"
      className="mb-4 rounded-lg border border-panel-border px-3.5 py-3.5"
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="label-micro">Persona map</p>
          <h3 className="mt-1 text-[13.5px] font-semibold text-foreground">
            How alike are the answers, with and without a persona?
          </h3>
          <p className="mt-1 max-w-[620px] text-[12px] leading-relaxed text-muted-foreground">
            Each point is one answer to the same question. Points that sit close together say
            similar things. Look at how far each region&apos;s man and woman drift from that
            region&apos;s own generic answer (the ring), and which regions cluster together.
          </p>
        </div>
        <div
          role="group"
          aria-label="Projection method"
          className="flex shrink-0 rounded-full border border-panel-border p-0.5"
        >
          {METHODS.map((m) => (
            <button
              key={m.id}
              type="button"
              aria-pressed={method === m.id}
              onClick={() => setMethod(m.id)}
              className={
                "rounded-full px-3 py-1 text-[11px] font-medium transition-colors " +
                (method === m.id
                  ? "bg-secondary text-foreground"
                  : "text-muted-foreground hover:text-foreground")
              }
            >
              {m.label}
            </button>
          ))}
        </div>
      </div>

      <div className="mt-3 flex flex-wrap gap-1.5" role="group" aria-label="Filter by region">
        <button
          type="button"
          aria-pressed={region == null}
          onClick={() => setRegion(null)}
          className={
            "rounded-full border px-2.5 py-1 text-[11px] transition-colors " +
            (region == null
              ? "border-foreground/30 bg-secondary text-foreground"
              : "border-panel-border text-muted-foreground hover:text-foreground")
          }
        >
          All regions
        </button>
        {regionsPresent.map((r) => (
          <button
            key={r.id}
            type="button"
            aria-pressed={region === r.id}
            onClick={() => setRegion(region === r.id ? null : r.id)}
            className={
              "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[11px] transition-colors " +
              (region === r.id
                ? "border-foreground/30 bg-secondary text-foreground"
                : "border-panel-border text-muted-foreground hover:text-foreground")
            }
          >
            <span
              className="size-2 rounded-full"
              style={{ backgroundColor: rgbaCss(r.color) }}
              aria-hidden
            />
            {r.shortName}
          </button>
        ))}
      </div>

      <div className="relative mt-3">
        <svg
          viewBox={`0 0 ${W} ${H}`}
          role="img"
          aria-label="Scatter plot placing each persona answer in two dimensions by similarity of meaning"
          className="block h-auto w-full rounded-md bg-secondary/40"
        >
          {/* each region's generic answer joined to its two persona answers */}
          {regionsPresent.map((r) => {
            const base = layout.find((l) => l.p.regionId === r.id && l.p.condition === "baseline");
            if (!base || !shown(r.id)) return null;
            return layout
              .filter((l) => l.p.regionId === r.id && l.p.condition !== "baseline")
              .map((l) => (
                <line
                  key={`${r.id}-${l.p.condition}`}
                  x1={base.x}
                  y1={base.y}
                  x2={l.x}
                  y2={l.y}
                  stroke={rgbaCss(r.color, 0.55)}
                  strokeWidth={1.6}
                  strokeDasharray="4 3"
                />
              ));
          })}
          {layout.map((l, i) => {
            const color = rgbaCss(regionColor(l.p.regionId));
            const visible = shown(l.p.regionId);
            const label = `${regionShortName(l.p.regionId)}: ${CONDITION_LABEL[l.p.condition]}`;
            return (
              <g
                key={i}
                tabIndex={visible ? 0 : -1}
                role="img"
                aria-label={label}
                opacity={visible ? 1 : 0.12}
                onMouseEnter={() => visible && setHover(i)}
                onMouseLeave={() => setHover(null)}
                onFocus={() => setHover(i)}
                onBlur={() => setHover(null)}
                className="cursor-pointer outline-none [&:focus-visible_*]:stroke-foreground"
              >
                <circle cx={l.x} cy={l.y} r={16} fill="transparent" />
                <Marker
                  condition={l.p.condition}
                  x={l.x}
                  y={l.y}
                  color={color}
                  active={hover === i}
                />
              </g>
            );
          })}
        </svg>

        {hovered && (
          <div
            role="status"
            className="pointer-events-none absolute z-10 w-[240px] rounded-lg border border-panel-border bg-card px-3 py-2 text-[11.5px] leading-snug shadow-lg"
            style={{
              left: `${Math.min(Math.max((hovered.x / W) * 100, 22), 78)}%`,
              top: `${(hovered.y / H) * 100}%`,
              transform:
                hovered.y / H > 0.55
                  ? "translate(-50%, calc(-100% - 14px))"
                  : "translate(-50%, 14px)",
            }}
          >
            <p className="font-semibold text-foreground">
              {regionShortName(hovered.p.regionId)} · {CONDITION_LABEL[hovered.p.condition]}
            </p>
            <p className="mt-1 text-muted-foreground">{hovered.p.text}</p>
          </div>
        )}
      </div>

      <div className="mt-2.5 flex flex-wrap items-center gap-x-4 gap-y-1 text-[11px] text-muted-foreground">
        <span className="inline-flex items-center gap-1.5">
          <svg width="14" height="14" viewBox="0 0 14 14" aria-hidden>
            <circle
              cx="7"
              cy="7"
              r="5"
              fill="var(--card)"
              stroke="currentColor"
              strokeWidth="2.4"
            />
          </svg>
          Without persona
        </span>
        <span className="inline-flex items-center gap-1.5">
          <svg width="14" height="14" viewBox="0 0 14 14" aria-hidden>
            <polygon points="7,1.5 13,12 1,12" fill="currentColor" />
          </svg>
          Man
        </span>
        <span className="inline-flex items-center gap-1.5">
          <svg width="14" height="14" viewBox="0 0 14 14" aria-hidden>
            <circle cx="7" cy="7" r="5.5" fill="currentColor" />
          </svg>
          Woman
        </span>
        <span>Colour = region (as on the map). Dashed line joins a region&apos;s answers.</span>
      </div>
      <p className="mt-1.5 text-[10.5px] leading-snug text-muted-foreground">
        {methodNote} Eighteen answers squeezed into two dimensions, so treat distances as
        approximate. Built from {map.embeddingModel} sentence embeddings; hover or focus a point to
        read the answer.
      </p>
    </section>
  );
}
