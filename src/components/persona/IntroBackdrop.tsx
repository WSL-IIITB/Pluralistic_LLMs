/**
 * The animated setting behind a persona's intro "video": five simple SVG landscapes (fields, city, dry plains,
 * coast, hills and forest) with drifting clouds and a sun that follows the story — morning at the greeting, across
 * the sky through the day, dusk and then night for "what keeps me up at night". Like a video, it looks the same in
 * the light and dark themes. Looping motion is switched off under prefers-reduced-motion (src/styles.css).
 */

import type { PersonaIntro } from "@/lib/worldview";

/** 0 = dawn, 0.5 = noon, 1 = dusk; `night` 0..1 fades the sky to night. */
export interface SkyPhase {
  sun: number;
  night: number;
}

const W = 1600;
const H = 900;

function Cloud({ y, scale, dur, delay }: { y: number; scale: number; dur: number; delay: number }) {
  return (
    <g
      className="intro-loop"
      style={{ animation: `intro-cloud ${dur}s linear ${delay}s infinite` }}
      opacity={0.85}
    >
      <g transform={`translate(0 ${y}) scale(${scale})`} fill="#ffffff">
        <ellipse cx={60} cy={30} rx={60} ry={26} />
        <ellipse cx={120} cy={22} rx={54} ry={30} />
        <ellipse cx={175} cy={34} rx={46} ry={22} />
      </g>
    </g>
  );
}

function Sway({
  x,
  y,
  h,
  color,
  delay,
}: {
  x: number;
  y: number;
  h: number;
  color: string;
  delay: number;
}) {
  return (
    <g
      className="intro-loop"
      style={{
        animation: `intro-sway ${3 + (delay % 2)}s ease-in-out ${delay}s infinite`,
        transformBox: "fill-box",
        transformOrigin: "50% 100%",
      }}
    >
      <path
        d={`M${x} ${y} q -6 ${-h * 0.5} 0 ${-h} M${x} ${y} q 10 ${-h * 0.45} 16 ${-h * 0.85} M${x} ${y} q -12 ${-h * 0.4} -18 ${-h * 0.8}`}
        stroke={color}
        strokeWidth={5}
        fill="none"
        strokeLinecap="round"
      />
    </g>
  );
}

function Fields() {
  const stalks = Array.from({ length: 26 }, (_, i) => i);
  return (
    <g>
      <path d={`M0 560 Q 300 500 650 545 T 1600 520 V ${H} H 0 Z`} fill="#9cc77a" />
      <path d={`M0 640 Q 400 600 800 630 T 1600 610 V ${H} H 0 Z`} fill="#7fb35d" />
      {Array.from({ length: 7 }, (_, i) => (
        <path
          key={i}
          d={`M${-200 + i * 300} ${H} L ${560 + i * 90} 640`}
          stroke="#6a9c4c"
          strokeWidth={10}
          opacity={0.5}
        />
      ))}
      {stalks.map((i) => (
        <Sway
          key={i}
          x={40 + i * 62}
          y={H - 20 - (i % 3) * 30}
          h={90 + (i % 4) * 14}
          color="#4f8a3a"
          delay={(i % 5) * 0.4}
        />
      ))}
    </g>
  );
}

function City() {
  const blocks: [number, number, number][] = [
    [80, 380, 120],
    [220, 300, 90],
    [330, 420, 140],
    [500, 340, 100],
    [620, 260, 80],
    [720, 400, 130],
    [880, 320, 110],
    [1010, 430, 150],
    [1180, 290, 90],
    [1290, 380, 120],
    [1430, 330, 120],
  ];
  return (
    <g>
      {blocks.map(([x, top, w], i) => (
        <g key={i}>
          <rect x={x} y={top} width={w} height={H - top} fill={i % 2 ? "#8b96aa" : "#7a869c"} />
          {Array.from({ length: Math.floor((H - top - 160) / 50) }, (_, r) => (
            <rect
              key={r}
              x={x + 14}
              y={top + 20 + r * 50}
              width={w - 28}
              height={14}
              fill="#c9d3e2"
              opacity={0.55}
            />
          ))}
        </g>
      ))}
      <rect x={1080} y={180} width={40} height={260} fill="#6b7489" />
      {[0, 1, 2].map((i) => (
        <circle
          key={i}
          className="intro-loop"
          cx={1100}
          cy={170}
          r={28}
          fill="#dfe3ea"
          style={{ animation: `intro-rise 6s ease-out ${i * 2}s infinite` }}
        />
      ))}
      <rect x={0} y={760} width={W} height={140} fill="#5b6273" />
      <path d="M0 830 H 1600" stroke="#e8d27a" strokeWidth={8} strokeDasharray="60 50" />
    </g>
  );
}

function DryPlains() {
  return (
    <g>
      <path
        d="M0 520 L 220 430 L 420 500 L 640 410 L 900 490 L 1150 420 L 1400 480 L 1600 440 V 900 H 0 Z"
        fill="#c98f62"
        opacity={0.85}
      />
      <path d={`M0 600 Q 500 560 900 590 T 1600 570 V ${H} H 0 Z`} fill="#e0bb7a" />
      <path d={`M0 700 Q 400 670 900 690 T 1600 680 V ${H} H 0 Z`} fill="#d4a95f" />
      {Array.from({ length: 12 }, (_, i) => (
        <Sway
          key={i}
          x={70 + i * 135}
          y={H - 40 - (i % 3) * 50}
          h={50 + (i % 3) * 12}
          color="#7d6a3c"
          delay={(i % 4) * 0.6}
        />
      ))}
      <g transform="translate(1270 560)">
        <rect x={-6} y={-10} width={12} height={90} fill="#6e5532" />
        <ellipse cx={0} cy={-20} rx={80} ry={38} fill="#6f8f45" />
      </g>
    </g>
  );
}

function Coast() {
  const wave = (y: number, color: string, dur: number, op: number) => (
    <g
      className="intro-loop"
      style={{ animation: `intro-wave ${dur}s linear infinite` }}
      opacity={op}
    >
      <path
        d={`M0 ${y} ${Array.from({ length: 12 }, (_, i) => `q 50 -18 100 0 t 100 0`).join(" ")} V ${H} H 0 Z`}
        fill={color}
      />
    </g>
  );
  return (
    <g>
      <rect x={0} y={560} width={W} height={H - 560} fill="#3f8fc2" />
      {wave(600, "#5aa6d6", 9, 0.9)}
      {wave(680, "#3a83b8", 7, 0.9)}
      <g
        className="intro-loop"
        style={{
          animation: "intro-boat 4s ease-in-out infinite",
          transformBox: "fill-box",
          transformOrigin: "50% 100%",
        }}
      >
        <path d="M1050 620 h 200 l -40 50 h -120 Z" fill="#8a4b2a" />
        <rect x={1140} y={520} width={8} height={100} fill="#5a3a22" />
        <path d="M1148 525 l 70 70 h -70 Z" fill="#f3e9d2" />
      </g>
      <path d={`M0 790 Q 500 760 900 780 T 1600 770 V ${H} H 0 Z`} fill="#ecd9a8" />
      {wave(800, "#ffffff", 5, 0.35)}
    </g>
  );
}

function HillsForest() {
  return (
    <g>
      <path d="M0 470 Q 250 360 520 450 T 1050 420 T 1600 440 V 900 H 0 Z" fill="#6f9c78" />
      <path d="M0 560 Q 300 470 650 540 T 1250 520 T 1600 540 V 900 H 0 Z" fill="#4f8a5c" />
      <g
        className="intro-loop"
        style={{ animation: "intro-mist 40s linear infinite" }}
        opacity={0.5}
      >
        <rect x={-400} y={500} width={1400} height={50} rx={25} fill="#ffffff" />
        <rect x={700} y={580} width={1100} height={40} rx={20} fill="#ffffff" />
      </g>
      <path d="M0 660 Q 350 600 800 650 T 1600 630 V 900 H 0 Z" fill="#3c7449" />
      {Array.from({ length: 16 }, (_, i) => (
        <g key={i} transform={`translate(${30 + i * 102} ${700 + (i % 3) * 40})`}>
          <rect x={-5} y={0} width={10} height={60} fill="#4b3a26" />
          <path d="M0 -110 L 45 10 H -45 Z" fill={i % 2 ? "#2f6b3e" : "#285e36"} />
        </g>
      ))}
    </g>
  );
}

const SETTING: Record<PersonaIntro["backdrop"], () => React.ReactElement> = {
  fields: Fields,
  city: City,
  "dry-plains": DryPlains,
  coast: Coast,
  "hills-forest": HillsForest,
};

export function IntroBackdrop({
  backdrop,
  phase,
}: {
  backdrop: PersonaIntro["backdrop"];
  phase: SkyPhase;
}) {
  const Setting = SETTING[backdrop] ?? Fields;
  // Sun on an arc from the left horizon (0) over the top (0.5) to the right horizon (1).
  const sx = 160 + phase.sun * (W - 320);
  const sy = 460 - Math.sin(phase.sun * Math.PI) * 330;
  const dusk = Math.max(0, 1 - Math.abs(phase.night - 0.5) * 2); // peaks halfway to night
  return (
    <svg
      viewBox={`0 0 ${W} ${H}`}
      preserveAspectRatio="xMidYMid slice"
      className="absolute inset-0 h-full w-full"
      aria-hidden
    >
      <defs>
        <linearGradient id="intro-day" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#9fd4f0" />
          <stop offset="1" stopColor="#fdf1d6" />
        </linearGradient>
        <linearGradient id="intro-dusk" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#5b5ea6" />
          <stop offset="1" stopColor="#f2a65a" />
        </linearGradient>
        <linearGradient id="intro-night" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#0d1733" />
          <stop offset="1" stopColor="#2b3a67" />
        </linearGradient>
        <linearGradient id="intro-shade" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0.55" stopColor="#000" stopOpacity="0" />
          <stop offset="1" stopColor="#000" stopOpacity="0.45" />
        </linearGradient>
      </defs>
      <rect width={W} height={H} fill="url(#intro-day)" />
      <rect
        width={W}
        height={H}
        fill="url(#intro-dusk)"
        className="intro-fade"
        style={{ opacity: dusk }}
      />
      <rect
        width={W}
        height={H}
        fill="url(#intro-night)"
        className="intro-fade"
        style={{ opacity: phase.night > 0.5 ? (phase.night - 0.5) * 2 : 0 }}
      />
      <g className="intro-fade" style={{ opacity: phase.night > 0.6 ? 1 : 0 }}>
        {Array.from({ length: 40 }, (_, i) => (
          <circle
            key={i}
            cx={(i * 397) % W}
            cy={30 + ((i * 211) % 380)}
            r={i % 3 ? 2 : 3}
            fill="#fff"
            opacity={0.8}
          />
        ))}
      </g>
      <g className="intro-sun" style={{ transform: `translate(${sx}px, ${sy}px)` }}>
        <circle r={phase.night > 0.6 ? 46 : 64} fill={phase.night > 0.6 ? "#f4f1de" : "#ffd36e"} />
        {phase.night <= 0.6 && <circle r={96} fill="#ffd36e" opacity={0.25} />}
      </g>
      <Cloud y={110} scale={1.2} dur={70} delay={-10} />
      <Cloud y={200} scale={0.8} dur={95} delay={-50} />
      <Cloud y={60} scale={0.9} dur={120} delay={-80} />
      <Setting />
      <rect
        width={W}
        height={H}
        fill="#0d1733"
        className="intro-fade"
        style={{ opacity: phase.night * 0.45 }}
      />
      <rect width={W} height={H} fill="url(#intro-shade)" />
    </svg>
  );
}
