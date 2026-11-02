/**
 * A persona introduces itself: an animated, voiced "video" built live from the persona card. A short first-person
 * script (card.intro, checked by scripts/check_persona_intros.py) plays line by line over an animated setting, with
 * the card's own household, day, pressures, district numbers and worries appearing as they are mentioned. The voice
 * is the viewer's browser voice; captions always work, muted or not, and a transcript is one click away.
 */

import {
  Captions,
  ChevronDown,
  Pause,
  Play,
  RotateCcw,
  SkipBack,
  SkipForward,
  Volume2,
  VolumeX,
} from "lucide-react";
import { useMemo, useState } from "react";

import {
  formatFactorValue,
  rgbaCss,
  useNitiPrescriptive,
  type IntroScene,
  type PersonaCard,
  type RGBAColor,
} from "@/lib/worldview";
import {
  pickVoice,
  readSavedVoice,
  saveVoice,
  speechSupported,
  useIntroPlayer,
  useVoices,
} from "@/lib/worldview/introPlayer";

import { IntroBackdrop, type SkyPhase } from "./IntroBackdrop";

const SCENE_LABEL: Record<IntroScene, string> = {
  hello: "Hello",
  household: "Family",
  day: "My day",
  world: "My world",
  school: "School",
  district: "My district",
  worries: "Worries",
  outro: "Bye",
};

function clock(ms: number): string {
  const s = Math.max(0, Math.round(ms / 1000));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

/** Where the sun is (and how dark it is) for each scene: morning greeting, the day, dusk and night for worries. */
function skyFor(scene: IntroScene | "poster", dayShare: number): SkyPhase {
  switch (scene) {
    case "poster":
    case "hello":
      return { sun: 0.15, night: 0 };
    case "household":
      return { sun: 0.25, night: 0 };
    case "day":
      return { sun: 0.3 + 0.4 * dayShare, night: 0 };
    case "world":
      return { sun: 0.72, night: 0 };
    case "school":
      return { sun: 0.8, night: 0.1 };
    case "district":
      return { sun: 0.86, night: 0.3 };
    case "worries":
      return { sun: 0.95, night: 0.75 };
    case "outro":
      return { sun: 0.95, night: 1 };
  }
}

function Chip({
  children,
  fresh,
  color,
}: {
  children: React.ReactNode;
  fresh: boolean;
  color: RGBAColor;
}) {
  return (
    <span
      className={
        "intro-t-sm inline-flex items-center gap-[0.5em] rounded-full border bg-white/90 px-[0.8em] py-[0.35em] font-medium text-slate-900 shadow-sm transition-all duration-500 animate-in fade-in zoom-in-90 " +
        (fresh ? "scale-105" : "opacity-80")
      }
      style={{ borderColor: fresh ? rgbaCss(color) : "transparent" }}
    >
      {children}
    </span>
  );
}

export function PersonaIntro({
  card,
  personaId,
  color,
  regionName,
  districtId,
  onExplore,
}: {
  card: PersonaCard;
  personaId: string;
  color: RGBAColor;
  regionName: string;
  districtId?: string | undefined;
  onExplore: () => void;
}) {
  const intro = card.intro!;
  const lines = intro.lines;
  const voices = useVoices();
  const [savedVoice, setSavedVoice] = useState<string | null>(() => readSavedVoice());
  const [muted, setMuted] = useState(false);
  const [cc, setCc] = useState(true);
  const [showTranscript, setShowTranscript] = useState(false);
  const gender = personaId === "female" ? "female" : "male";
  const { voice, pitch } = pickVoice(voices, gender, savedVoice);
  const canSpeak = speechSupported() && !!voice;
  const player = useIntroPlayer(lines, { voice, pitch, muted: muted || !canSpeak });
  const nitiData = useNitiPrescriptive();

  const poster = player.status === "poster";
  const line = lines[player.beat]!;
  const scene: IntroScene | "poster" = poster ? "poster" : line.scene;

  // Items brought on screen so far within the current scene, and the ones this line just added.
  const { shown, fresh, dayShare } = useMemo(() => {
    const out = new Set<number>();
    let start = player.beat;
    while (start > 0 && lines[start - 1]!.scene === line.scene) start -= 1;
    for (let i = start; i <= player.beat; i++) for (const j of lines[i]!.show ?? []) out.add(j);
    const dayLines = lines.filter((l) => l.scene === "day").length;
    const dayDone = lines.slice(0, player.beat + 1).filter((l) => l.scene === "day").length;
    return {
      shown: [...out],
      fresh: new Set(line.show ?? []),
      dayShare: dayLines ? dayDone / dayLines : 0,
    };
  }, [lines, line, player.beat]);

  const sky = skyFor(scene, dayShare);
  const total = player.durations.reduce((a, b) => a + b, 0);
  const elapsed =
    player.status === "ended"
      ? total
      : player.durations.slice(0, player.beat).reduce((a, b) => a + b, 0) +
        (poster ? 0 : player.progress * (player.durations[player.beat] ?? 0));
  const chapters = useMemo(() => {
    const out: { scene: IntroScene; first: number; last: number; ms: number }[] = [];
    lines.forEach((l, i) => {
      const prev = out[out.length - 1];
      if (prev && prev.scene === l.scene) {
        prev.last = i;
        prev.ms += player.durations[i]!;
      } else out.push({ scene: l.scene, first: i, last: i, ms: player.durations[i]! });
    });
    return out;
  }, [lines, player.durations]);

  const district = districtId && nitiData ? nitiData.districts[districtId] : undefined;
  const area = district?.areas.find((a) => a.area === card.dataLens?.area);
  const factorInfo = useMemo(
    () => Object.fromEntries((nitiData?.factors ?? []).map((f) => [f.name, f])),
    [nitiData],
  );
  const topic = card.topics.find((t) => t.key === line.topic);

  const captionCut = Math.round(player.progress * line.text.length);
  const toggle = () => (player.status === "playing" ? player.pause() : player.play());

  function panel() {
    if (scene === "poster" || scene === "hello")
      return (
        <div className="space-y-[0.5em] rounded-xl bg-white/85 p-[0.9em] shadow-sm backdrop-blur-sm animate-in fade-in slide-in-from-right-4 duration-500">
          <p className="intro-t-xs font-medium tracking-wide text-slate-600 uppercase">
            {regionName} · composite persona
          </p>
          <p className="intro-t-xl leading-tight font-semibold text-slate-900">{card.name}</p>
          <p className="intro-t-md text-slate-800">
            {card.ageLabel} · {card.role}
          </p>
          <p className="intro-t-sm text-slate-700">
            {card.place}
            {card.community ? ` · ${card.community}` : ""}
          </p>
          {scene === "poster" && (
            <p className="intro-t-sm leading-snug text-slate-700 italic">{card.tagline}</p>
          )}
        </div>
      );
    if (scene === "household")
      return (
        <div className="flex flex-wrap gap-[0.6em]">
          <Chip fresh={false} color={color}>
            <span>{card.emoji}</span>Me
          </Chip>
          {shown.map((i) => (
            <Chip key={i} fresh={fresh.has(i)} color={color}>
              <span>{card.household[i]!.emoji}</span>
              {card.household[i]!.who}
            </Chip>
          ))}
        </div>
      );
    if (scene === "day")
      return (
        <ol className="space-y-[0.6em]">
          {shown.slice(-3).map((i) => {
            const b = card.dayInLife[i]!;
            return (
              <li
                key={i}
                className={
                  "flex gap-[0.7em] rounded-xl bg-white/90 p-[0.7em] text-slate-900 shadow-sm transition-opacity duration-500 animate-in fade-in slide-in-from-right-4 " +
                  (fresh.has(i) ? "" : "opacity-70")
                }
              >
                <span className="intro-t-lg leading-none">{b.emoji}</span>
                <span>
                  <span
                    className="intro-t-xs block font-semibold tracking-wide uppercase"
                    style={{
                      color: rgbaCss([color[0] * 0.6, color[1] * 0.6, color[2] * 0.6, 255]),
                    }}
                  >
                    {b.when}
                  </span>
                  <span className="intro-t-sm leading-snug">{b.text}</span>
                </span>
              </li>
            );
          })}
        </ol>
      );
    if (scene === "world" && topic)
      return (
        <div
          key={topic.key}
          className="space-y-[0.6em] rounded-xl bg-white/90 p-[0.9em] text-slate-900 shadow-sm animate-in fade-in zoom-in-95 duration-500"
        >
          <p className="intro-t-md font-semibold leading-snug">
            {topic.emoji} {topic.headline}
          </p>
          {topic.stat && (
            <div className="flex items-baseline gap-[0.6em]">
              <span
                className="intro-t-xl font-bold tabular-nums"
                style={{ color: rgbaCss([color[0] * 0.6, color[1] * 0.6, color[2] * 0.6, 255]) }}
              >
                {topic.stat.value}
              </span>
              <span className="intro-t-xs leading-snug text-slate-700">{topic.stat.label}</span>
            </div>
          )}
        </div>
      );
    if (scene === "school")
      return (
        <div className="grid grid-cols-2 gap-[0.6em]">
          {shown.map((i) => {
            const p = card.schoolPressures[i]!;
            return (
              <div
                key={i}
                className={
                  "rounded-xl border-2 bg-white/90 p-[0.7em] text-slate-900 shadow-sm animate-in fade-in zoom-in-90 duration-500 " +
                  (fresh.has(i) ? "" : "opacity-75")
                }
                style={{ borderColor: fresh.has(i) ? rgbaCss(color) : "transparent" }}
              >
                <span className="intro-t-lg leading-none">{p.emoji}</span>
                <p className="intro-t-sm mt-[0.3em] font-semibold leading-tight">{p.label}</p>
              </div>
            );
          })}
        </div>
      );
    if (scene === "district" && card.dataLens)
      return (
        <div className="space-y-[0.6em] animate-in fade-in duration-500">
          <p className="intro-t-xs font-medium tracking-wide text-white uppercase [text-shadow:0_1px_3px_rgb(0_0_0/0.6)]">
            My district in numbers · NITI model
          </p>
          {area?.dropout2023_24 != null && (
            <p className="intro-t-sm inline-block rounded-lg bg-white/90 px-[0.7em] py-[0.35em] text-slate-900">
              Secondary dropout 2023-24{" "}
              <span className="font-bold tabular-nums">{area.dropout2023_24.toFixed(1)}%</span>
            </p>
          )}
          <div className="grid grid-cols-3 gap-[0.5em]">
            {card.dataLens.changes.map((c, i) => {
              const f = area?.factors.find((x) => x.name === c.factor);
              return (
                <div
                  key={c.factor}
                  className="rounded-xl bg-white/90 p-[0.6em] text-slate-900 shadow-sm animate-in fade-in slide-in-from-bottom-3 fill-mode-both"
                  style={{ animationDelay: `${i * 250}ms` }}
                >
                  <p className="intro-t-xs font-semibold text-slate-600 uppercase">
                    Change {i + 1}
                  </p>
                  <p className="intro-t-sm font-semibold leading-tight">
                    {factorInfo[c.factor]?.short ?? c.factor}
                  </p>
                  {f && (
                    <p className="intro-t-xs mt-[0.2em] tabular-nums text-slate-700">
                      {formatFactorValue(c.factor, f.value)} · #{f.rank} of 35
                    </p>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      );
    if (scene === "worries")
      return (
        <div className="flex flex-wrap gap-[0.6em]">
          {shown.map((i, k) => (
            <span
              key={i}
              className="intro-t-sm rounded-full bg-white/90 px-[0.8em] py-[0.4em] font-medium text-slate-900 shadow-sm animate-in fade-in slide-in-from-bottom-4 fill-mode-both"
              style={{ animationDelay: `${k * 350}ms` }}
            >
              {card.worries[i]}
            </span>
          ))}
        </div>
      );
    if (scene === "outro")
      return (
        <div className="space-y-[0.8em] rounded-xl bg-white/90 p-[0.9em] text-slate-900 shadow-sm animate-in fade-in duration-500">
          <p className="intro-t-md font-semibold">Thanks for meeting me.</p>
          <p className="intro-t-xs leading-snug text-slate-700">
            I&apos;m a composite persona built from public data, not a real person. My lines are
            written from my card and voiced by your browser.
          </p>
          <div className="flex flex-wrap gap-[0.5em]">
            <button
              type="button"
              onClick={() => player.seek(0)}
              className="intro-t-xs inline-flex items-center gap-[0.4em] rounded-full bg-slate-900 px-[0.9em] py-[0.45em] font-medium text-white"
            >
              <RotateCcw className="size-[1.1em]" aria-hidden /> Replay
            </button>
            <button
              type="button"
              onClick={onExplore}
              className="intro-t-xs rounded-full border border-slate-300 bg-white px-[0.9em] py-[0.45em] font-medium text-slate-900"
            >
              Explore my full card ↓
            </button>
          </div>
        </div>
      );
    return null;
  }

  return (
    <div className="space-y-2.5">
      <div
        className="intro-wrap rounded-2xl outline-none focus-visible:ring-2 focus-visible:ring-primary"
        tabIndex={0}
        role="region"
        aria-label={`Video introduction: ${card.name}`}
        onKeyDown={(e) => {
          if (e.target !== e.currentTarget) return;
          if (e.key === " ") {
            e.preventDefault();
            toggle();
          } else if (e.key === "ArrowRight") player.seek(player.beat + 1);
          else if (e.key === "ArrowLeft") player.seek(player.beat - 1);
        }}
      >
        <div className="intro-stage rounded-2xl border border-panel-border shadow-lg">
          <IntroBackdrop backdrop={intro.backdrop} phase={sky} />

          <span className="intro-t-xs absolute top-[3%] left-[3%] z-10 rounded-full bg-black/45 px-[0.8em] py-[0.3em] text-white">
            Composite persona · {canSpeak && !muted ? "voiced by your browser" : "captions"}
          </span>

          <div className="intro-avatar z-10">
            <div
              className="relative aspect-square w-full"
              style={{
                animation: player.speaking ? "intro-bob 1.1s ease-in-out infinite" : undefined,
              }}
            >
              {player.speaking &&
                [0, 1].map((i) => (
                  <span
                    key={i}
                    className="intro-loop absolute inset-0 rounded-full"
                    style={{
                      border: `3px solid ${rgbaCss(color)}`,
                      animation: `intro-pulse 1.6s ease-out ${i * 0.8}s infinite`,
                    }}
                    aria-hidden
                  />
                ))}
              <div
                className="intro-emoji flex size-full items-center justify-center rounded-full shadow-xl ring-[0.6cqw] leading-none"
                style={{
                  backgroundColor: rgbaCss([255, 255, 255, 255], 0.85),
                  ["--tw-ring-color" as string]: rgbaCss(color, 0.9),
                }}
                aria-hidden
              >
                {card.emoji}
              </div>
            </div>
          </div>

          <div key={`${scene}`} className="intro-panel z-10 overflow-hidden">
            {panel()}
          </div>

          {poster && (
            <button
              type="button"
              onClick={player.play}
              className="intro-t-md absolute bottom-[8%] left-1/2 z-20 inline-flex -translate-x-1/2 items-center gap-[0.6em] rounded-full whitespace-nowrap bg-slate-900/85 px-[1.3em] py-[0.7em] font-semibold text-white shadow-xl transition-transform hover:scale-105"
            >
              <Play className="size-[1.2em] fill-white" aria-hidden />
              Meet {card.name.replace(/^The /, "the ")}
              <span className="intro-t-xs font-normal text-white/80">
                ~{Math.max(1, Math.round(total / 60000))} min
              </span>
            </button>
          )}

          {!poster && cc && (
            <p
              className="intro-caption intro-t-md z-20 rounded-lg bg-black/65 px-[0.9em] py-[0.5em] text-center leading-snug text-white/70"
              aria-live={muted || !canSpeak ? "polite" : "off"}
            >
              <span className="text-white">{line.text.slice(0, captionCut)}</span>
              {line.text.slice(captionCut)}
            </p>
          )}
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <button
          type="button"
          onClick={toggle}
          aria-label={player.status === "playing" ? "Pause" : "Play"}
          className="flex size-8 items-center justify-center rounded-full bg-foreground text-background transition-opacity hover:opacity-90"
        >
          {player.status === "playing" ? (
            <Pause className="size-4" aria-hidden />
          ) : (
            <Play className="size-4" aria-hidden />
          )}
        </button>
        <button
          type="button"
          onClick={() => player.seek(player.beat - 1)}
          disabled={poster || player.beat === 0}
          aria-label="Previous line"
          className="flex size-7 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground disabled:opacity-40"
        >
          <SkipBack className="size-4" aria-hidden />
        </button>
        <button
          type="button"
          onClick={() => player.seek(player.beat + 1)}
          disabled={poster || player.status === "ended"}
          aria-label="Next line"
          className="flex size-7 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground disabled:opacity-40"
        >
          <SkipForward className="size-4" aria-hidden />
        </button>

        <div className="flex min-w-[180px] flex-1 gap-0.5" role="group" aria-label="Chapters">
          {chapters.map((c) => {
            const done = player.status === "ended" || (!poster && player.beat > c.last);
            const active = !poster && player.beat >= c.first && player.beat <= c.last;
            const before = active
              ? player.durations.slice(c.first, player.beat).reduce((a, b) => a + b, 0) +
                player.progress * player.durations[player.beat]!
              : 0;
            const fill = done ? 1 : active ? before / c.ms : 0;
            return (
              <button
                key={c.first}
                type="button"
                onClick={() => player.seek(c.first)}
                title={SCENE_LABEL[c.scene]}
                className="group flex flex-col gap-1 text-left"
                style={{ flexGrow: c.ms }}
              >
                <span className="h-1.5 w-full overflow-hidden rounded-full bg-secondary">
                  <span
                    className="block h-full rounded-full transition-[width] duration-100"
                    style={{ width: `${fill * 100}%`, backgroundColor: rgbaCss(color) }}
                  />
                </span>
                <span
                  className={
                    "truncate text-[9.5px] leading-none " +
                    (active ? "font-semibold text-foreground" : "invisible")
                  }
                >
                  {SCENE_LABEL[c.scene]}
                </span>
              </button>
            );
          })}
        </div>

        <span className="text-[11px] text-muted-foreground tabular-nums">
          {clock(elapsed)} / {clock(total)}
        </span>
        <button
          type="button"
          onClick={() => setMuted((m) => !m)}
          disabled={!canSpeak}
          aria-label={muted ? "Turn the voice on" : "Mute the voice"}
          title={canSpeak ? undefined : "No voice available in this browser: captions only"}
          className="flex size-7 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground disabled:opacity-40"
        >
          {muted || !canSpeak ? (
            <VolumeX className="size-4" aria-hidden />
          ) : (
            <Volume2 className="size-4" aria-hidden />
          )}
        </button>
        <button
          type="button"
          onClick={() => setCc((v) => !v)}
          aria-pressed={cc}
          aria-label="Captions"
          className={
            "flex size-7 items-center justify-center rounded-md transition-colors hover:bg-secondary " +
            (cc ? "text-foreground" : "text-muted-foreground")
          }
        >
          <Captions className="size-4" aria-hidden />
        </button>
        {voices.length > 0 && (
          <select
            value={voice?.name ?? ""}
            onChange={(e) => {
              saveVoice(e.target.value);
              setSavedVoice(e.target.value);
            }}
            aria-label="Voice"
            className="max-w-[150px] rounded-md border border-panel-border bg-card px-1.5 py-1 text-[11px] text-foreground"
          >
            {voices.map((v) => (
              <option key={v.name} value={v.name}>
                {v.name} ({v.lang})
              </option>
            ))}
          </select>
        )}
      </div>

      <div>
        <button
          type="button"
          onClick={() => setShowTranscript((v) => !v)}
          aria-expanded={showTranscript}
          className="label-micro flex items-center gap-1.5 transition-colors hover:text-foreground"
        >
          <ChevronDown
            className={`size-3 transition-transform ${showTranscript ? "" : "-rotate-90"}`}
            aria-hidden
          />
          Transcript
        </button>
        {showTranscript && (
          <ol className="mt-2 space-y-1 text-[12px] leading-snug text-muted-foreground animate-in fade-in duration-200">
            {lines.map((l, i) => (
              <li key={i}>
                <button
                  type="button"
                  onClick={() => player.seek(i)}
                  className={
                    "text-left hover:text-foreground " +
                    (!poster && i === player.beat ? "font-medium text-foreground" : "")
                  }
                >
                  {l.text}
                </button>
              </li>
            ))}
          </ol>
        )}
        <p className="mt-1.5 text-[10.5px] leading-snug text-muted-foreground">
          The lines are written from this persona&apos;s card (a composite built from public data)
          and spoken by your browser&apos;s own voice; the voice differs from device to device.
        </p>
      </div>
    </div>
  );
}
