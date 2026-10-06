/**
 * Draggable divider between the left column and the map. The split is a
 * fraction of the window width (so it survives window resizes), clamped so
 * neither side gets unusably small, and remembered in localStorage.
 *
 * The line itself fades out towards the top and bottom, and the map's left edge
 * dissolves into the page (see MapEdgeFade) — there is no hard seam.
 */

import { useCallback, useEffect, useRef, useState } from "react";

const STORAGE_KEY = "wv.split";
const DEFAULT_SPLIT = 0.5;
const MIN_LEFT_PX = 360;
const MIN_RIGHT_PX = 320;

function clampSplit(fraction: number): number {
  const w = typeof window === "undefined" ? 1440 : window.innerWidth;
  const lo = Math.min(0.9, MIN_LEFT_PX / w);
  const hi = Math.max(lo, 1 - MIN_RIGHT_PX / w);
  return Math.min(hi, Math.max(lo, fraction));
}

function readStored(): number {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    const n = raw ? Number(raw) : NaN;
    return Number.isFinite(n) ? clampSplit(n) : DEFAULT_SPLIT;
  } catch {
    return DEFAULT_SPLIT;
  }
}

/** Left column width as a fraction of the window, with setters for the handle. */
export function useSplit() {
  const [split, setSplitState] = useState(DEFAULT_SPLIT);
  const [dragging, setDragging] = useState(false);

  // Read the stored value after mount so SSR and first client render agree.
  useEffect(() => setSplitState(readStored()), []);
  useEffect(() => {
    const onResize = () => setSplitState((s) => clampSplit(s));
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, []);

  const setSplit = useCallback((fraction: number, persist = false) => {
    const next = clampSplit(fraction);
    setSplitState(next);
    if (persist) {
      try {
        window.localStorage.setItem(STORAGE_KEY, String(next));
      } catch {
        /* storage unavailable — the split just won't be remembered */
      }
    }
  }, []);

  return { split, setSplit, dragging, setDragging };
}

interface SplitHandleProps {
  split: number;
  setSplit: (fraction: number, persist?: boolean) => void;
  dragging: boolean;
  setDragging: (dragging: boolean) => void;
}

export function SplitHandle({ split, setSplit, dragging, setDragging }: SplitHandleProps) {
  const ref = useRef<HTMLDivElement>(null);

  const onPointerDown = (e: React.PointerEvent) => {
    e.preventDefault();
    ref.current?.setPointerCapture(e.pointerId);
    setDragging(true);
  };
  const onPointerMove = (e: React.PointerEvent) => {
    if (dragging) setSplit(e.clientX / window.innerWidth);
  };
  const onPointerUp = (e: React.PointerEvent) => {
    if (!dragging) return;
    ref.current?.releasePointerCapture(e.pointerId);
    setDragging(false);
    setSplit(e.clientX / window.innerWidth, true);
  };
  const onKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "ArrowLeft") setSplit(split - 0.02, true);
    else if (e.key === "ArrowRight") setSplit(split + 0.02, true);
    else if (e.key === "Home" || e.key === "Enter") setSplit(DEFAULT_SPLIT, true);
    else return;
    e.preventDefault();
  };

  return (
    <div
      ref={ref}
      role="separator"
      aria-orientation="vertical"
      aria-label="Resize panels — drag, or use the arrow keys"
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={Math.round(split * 100)}
      tabIndex={0}
      onPointerDown={onPointerDown}
      onPointerMove={onPointerMove}
      onPointerUp={onPointerUp}
      onPointerCancel={onPointerUp}
      onKeyDown={onKeyDown}
      onDoubleClick={() => setSplit(DEFAULT_SPLIT, true)}
      className="group absolute inset-y-0 z-40 w-4 -translate-x-1/2 cursor-col-resize touch-none outline-none"
      style={{ left: `${split * 100}%` }}
    >
      {/* the line — fades to nothing at both ends */}
      <div
        className={
          "pointer-events-none absolute inset-y-14 left-1/2 w-px -translate-x-1/2 bg-gradient-to-b from-transparent to-transparent transition-all duration-200 " +
          (dragging
            ? "via-primary/70"
            : "via-foreground/20 group-hover:via-foreground/45 group-focus-visible:via-primary/70")
        }
      />
      {/* grip, shown on hover / focus / drag */}
      <div
        className={
          "pointer-events-none absolute top-1/2 left-1/2 flex h-10 w-3 -translate-x-1/2 -translate-y-1/2 flex-col items-center justify-center gap-1 rounded-full border border-panel-border bg-panel backdrop-blur-md transition-opacity duration-200 " +
          (dragging ? "opacity-100" : "opacity-0 group-hover:opacity-100 group-focus-visible:opacity-100")
        }
        aria-hidden
      >
        <span className="size-0.5 rounded-full bg-muted-foreground" />
        <span className="size-0.5 rounded-full bg-muted-foreground" />
        <span className="size-0.5 rounded-full bg-muted-foreground" />
      </div>
    </div>
  );
}
