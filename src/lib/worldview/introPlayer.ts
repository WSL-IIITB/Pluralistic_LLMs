/**
 * Playback for the persona intro "video" (src/components/persona/PersonaIntro.tsx).
 *
 * The intro is a script of short lines ("beats"). Each line is spoken with the viewer's own browser voice (Web
 * Speech API), one utterance per line, which keeps clear of Chrome's cut-off on long utterances. When muted, or when
 * the browser has no voice, each line is timed from its length instead, so captions alone still play through.
 * Pausing cancels the speech and resuming replays the current line: speechSynthesis.pause() is unreliable across
 * browsers. A run token makes callbacks from a cancelled utterance ignore themselves.
 *
 * When a persona has recorded clips (public/audio/personas/manifest.json, made with ElevenLabs by
 * scripts/split_persona_audio.py), those play instead, one clip per line through a single reused audio element; the
 * browser voice stays as the fallback if a clip cannot play. Recorded clips pause and resume mid-line.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { assetUrl } from "./api";
import type { PersonaIntroLine } from "./personaCards";

/** Recorded clips for one persona: one per script line, in order. */
export interface PersonaAudio {
  voiceName: string;
  clips: { url: string; ms: number }[];
}

interface AudioManifest {
  model: string;
  voices: Record<string, { voice: string; name: string }>;
  clips: Record<string, { file: string; ms: number; chars: number }[]>;
}

let manifestLoad: Promise<AudioManifest | null> | null = null;

/** The recorded clips for "region/persona", or null when there are none (the browser voice is used instead). */
export function usePersonaAudio(key: string, lineCount: number): PersonaAudio | null {
  const [manifest, setManifest] = useState<AudioManifest | null>(null);
  useEffect(() => {
    let alive = true;
    manifestLoad ??= fetch(assetUrl("audio/personas/manifest.json"))
      .then((r) => (r.ok ? (r.json() as Promise<AudioManifest>) : null))
      .catch(() => null);
    void manifestLoad.then((m) => alive && setManifest(m));
    return () => {
      alive = false;
    };
  }, []);
  return useMemo(() => {
    const clips = manifest?.clips[key];
    if (!clips || clips.length !== lineCount) return null; // stale recordings never play against a changed script
    return {
      voiceName: manifest!.voices[key]?.name ?? "",
      clips: clips.map((c) => ({ url: assetUrl(`audio/personas/${c.file}`), ms: c.ms })),
    };
  }, [manifest, key, lineCount]);
}

export type IntroStatus = "poster" | "playing" | "paused" | "ended";

const VOICE_KEY = "wv.introVoice";
const GAP_MS = 350;
const RATE = 0.98;
// Voice names that say which gender they are (macOS, Windows, Android and Chrome voices for Indian/British English).
const MALE = /\b(rishi|aman|ravi|prabhat|hemant|daniel|arthur|male)\b/i;
const FEMALE =
  /\b(tara|veena|lekha|heera|neerja|isha|kajal|swara|female|samantha|karen|moira|serena|kate)\b/i;

export function speechSupported(): boolean {
  return (
    typeof window !== "undefined" &&
    "speechSynthesis" in window &&
    typeof SpeechSynthesisUtterance !== "undefined"
  );
}

/** The browser's English voices; the list arrives asynchronously in most browsers. */
export function useVoices(): SpeechSynthesisVoice[] {
  const [voices, setVoices] = useState<SpeechSynthesisVoice[]>([]);
  useEffect(() => {
    if (!speechSupported()) return;
    const synth = window.speechSynthesis;
    const load = () => setVoices(synth.getVoices().filter((v) => /^en/i.test(v.lang)));
    load();
    synth.addEventListener("voiceschanged", load);
    return () => synth.removeEventListener("voiceschanged", load);
  }, []);
  return voices;
}

const langOf = (v: SpeechSynthesisVoice) => v.lang.replace("_", "-").toLowerCase();

/** Prefer a voice of the persona's gender, Indian English first, then British, then any English; failing that, a
 * voice that is not of the other gender; failing that, any voice with its pitch nudged. */
export function pickVoice(
  voices: SpeechSynthesisVoice[],
  gender: "male" | "female",
  savedName: string | null,
): { voice: SpeechSynthesisVoice | null; pitch: number } {
  const nudge = gender === "male" ? 0.85 : 1.1;
  const saved = savedName ? voices.find((v) => v.name === savedName) : undefined;
  if (saved) return { voice: saved, pitch: 1 };
  if (!voices.length) return { voice: null, pitch: nudge };
  const want = gender === "male" ? MALE : FEMALE;
  const avoid = gender === "male" ? FEMALE : MALE;
  const byLang = ["en-in", "en-gb", "en"].map((pref) =>
    voices.filter((v) => langOf(v).startsWith(pref)),
  );
  for (const pool of byLang) {
    const match = pool.find((v) => want.test(v.name));
    if (match) return { voice: match, pitch: 1 };
  }
  for (const pool of byLang) {
    const neutral = pool.find((v) => !avoid.test(v.name));
    if (neutral) return { voice: neutral, pitch: nudge };
  }
  return { voice: voices[0]!, pitch: nudge };
}

export function readSavedVoice(): string | null {
  try {
    return localStorage.getItem(VOICE_KEY);
  } catch {
    return null;
  }
}

export function saveVoice(name: string | null): void {
  try {
    if (name) localStorage.setItem(VOICE_KEY, name);
    else localStorage.removeItem(VOICE_KEY);
  } catch {
    // storage unavailable (private window, blocked site data): the choice just isn't remembered
  }
}

/** How long a line takes at a natural pace: about 2.6 words a second, never under 2.2 s. */
export function estimateMs(text: string): number {
  return Math.max(2200, (text.trim().split(/\s+/).length / 2.6) * 1000);
}

export interface IntroPlayer {
  status: IntroStatus;
  beat: number;
  /** True while the current line is being voiced (or, muted, while it is on screen). */
  speaking: boolean;
  /** 0..1 through the current line, from the clock (or the voice's word boundaries when it reports them). */
  progress: number;
  /** Estimated length of each line, ms. */
  durations: number[];
  play(): void;
  pause(): void;
  seek(beat: number): void;
}

export function useIntroPlayer(
  lines: PersonaIntroLine[],
  opts: {
    voice: SpeechSynthesisVoice | null;
    pitch: number;
    muted: boolean;
    audio?: PersonaAudio | null;
  },
): IntroPlayer {
  const [status, setStatus] = useState<IntroStatus>("poster");
  const [beat, setBeat] = useState(0);
  const [speaking, setSpeaking] = useState(false);
  const [progress, setProgress] = useState(0);
  const clips = opts.audio?.clips ?? null;
  const durations = useMemo(
    () => (clips ? clips.map((c) => c.ms) : lines.map((l) => estimateMs(l.say ?? l.text))),
    [lines, clips],
  );
  const audioEl = useRef<HTMLAudioElement | null>(null);
  const audioMode = useRef(false);

  const token = useRef(0);
  const timers = useRef<number[]>([]);
  const startedAt = useRef(0);
  const boundary = useRef<number | null>(null);
  const optsRef = useRef(opts);
  optsRef.current = opts;
  const statusRef = useRef(status);
  statusRef.current = status;
  const beatRef = useRef(beat);
  beatRef.current = beat;

  const stopAll = useCallback(() => {
    token.current += 1;
    for (const t of timers.current) window.clearTimeout(t);
    timers.current = [];
    if (speechSupported()) window.speechSynthesis.cancel();
    const a = audioEl.current;
    if (a) {
      a.onended = null;
      a.onerror = null;
      a.pause();
    }
    setSpeaking(false);
  }, []);

  /** Play clip i from where the audio element is (0 for a fresh line); returns false if it cannot play. */
  const playClip = useCallback((i: number, my: number, advance: () => void, fresh: boolean) => {
    const clip = optsRef.current.audio?.clips[i];
    if (!clip) return false;
    audioEl.current ??= new Audio();
    const a = audioEl.current;
    if (fresh || !a.src.endsWith(clip.url)) {
      a.src = clip.url;
      a.currentTime = 0;
    }
    a.onended = advance;
    a.onerror = advance;
    audioMode.current = true;
    setSpeaking(true);
    void a.play().catch(() => {
      // autoplay refused or the file failed: fall back to timing the caption
      if (token.current === my)
        timers.current.push(
          window.setTimeout(advance, Math.max(0, clip.ms - a.currentTime * 1000)),
        );
    });
    const next = optsRef.current.audio?.clips[i + 1];
    if (next) {
      const warm = new Audio();
      warm.preload = "auto";
      warm.src = next.url;
    }
    return true;
  }, []);

  const runRef = useRef<(i: number) => void>(() => {});
  runRef.current = (i: number) => {
    stopAll();
    const my = token.current;
    if (i >= lines.length) {
      setStatus("ended");
      setProgress(1);
      return;
    }
    setBeat(i);
    setProgress(0);
    boundary.current = null;
    startedAt.current = performance.now();
    const line = lines[i]!;
    const spoken = line.say ?? line.text;
    const est = durations[i]!;
    const advance = () => {
      if (token.current !== my) return;
      setSpeaking(false);
      timers.current.push(
        window.setTimeout(() => token.current === my && runRef.current(i + 1), GAP_MS),
      );
    };
    const { voice, pitch, muted } = optsRef.current;
    audioMode.current = false;
    if (!muted && optsRef.current.audio && playClip(i, my, advance, true)) {
      // recorded clip: `ended` advances, the progress clock reads the audio position
    } else if (!muted && speechSupported() && voice) {
      const u = new SpeechSynthesisUtterance(spoken);
      u.voice = voice;
      u.lang = voice.lang;
      u.pitch = pitch;
      u.rate = RATE;
      u.onstart = () => token.current === my && setSpeaking(true);
      u.onboundary = (e) => {
        // Map word boundaries onto the caption only when the caption is what is being said.
        if (token.current === my && !line.say) boundary.current = e.charIndex / spoken.length;
      };
      u.onend = advance;
      u.onerror = advance;
      window.speechSynthesis.speak(u);
      setSpeaking(true);
      // Some voices never fire `end`: move on anyway after a generous wait.
      timers.current.push(window.setTimeout(advance, est * 1.8 + 1500));
    } else {
      setSpeaking(true);
      timers.current.push(window.setTimeout(advance, est));
    }
  };

  // Progress clock for captions and the chapter bar (10 updates a second is plenty).
  useEffect(() => {
    if (status !== "playing") return;
    const id = window.setInterval(() => {
      const a = audioEl.current;
      if (audioMode.current && a && a.duration > 0) {
        setProgress(Math.min(1, a.currentTime / a.duration));
        return;
      }
      const t = (performance.now() - startedAt.current) / (durations[beatRef.current] ?? 1);
      setProgress(Math.min(1, Math.max(boundary.current ?? 0, t)));
    }, 100);
    return () => window.clearInterval(id);
  }, [status, durations]);

  const play = useCallback(() => {
    const s = statusRef.current;
    setStatus("playing");
    // a paused recorded clip carries on from where it stopped
    if (s === "paused" && audioMode.current && audioEl.current?.ended) {
      runRef.current(beatRef.current + 1); // paused just as the clip finished: go on to the next line
      return;
    }
    if (s === "paused" && audioMode.current && !optsRef.current.muted) {
      token.current += 1;
      const my = token.current;
      const i = beatRef.current;
      const advance = () => {
        if (token.current !== my) return;
        setSpeaking(false);
        timers.current.push(
          window.setTimeout(() => token.current === my && runRef.current(i + 1), GAP_MS),
        );
      };
      if (playClip(i, my, advance, false)) return;
    }
    runRef.current(s === "poster" || s === "ended" ? 0 : beatRef.current);
  }, [playClip]);
  const pause = useCallback(() => {
    stopAll();
    setStatus("paused");
  }, [stopAll]);
  const seek = useCallback((i: number) => {
    setStatus("playing");
    runRef.current(Math.max(0, i));
  }, []);

  // Muting, or picking another voice, restarts the current line in the new mode.
  useEffect(() => {
    if (statusRef.current === "playing") runRef.current(beatRef.current);
  }, [opts.muted, opts.voice, opts.audio]);

  // Stop when the page is hidden, and always on unmount (another persona, another tab).
  useEffect(() => {
    const onHide = () => {
      if (document.hidden && statusRef.current === "playing") pause();
    };
    document.addEventListener("visibilitychange", onHide);
    return () => {
      document.removeEventListener("visibilitychange", onHide);
      stopAll();
    };
  }, [pause, stopAll]);

  return { status, beat, speaking, progress, durations, play, pause, seek };
}
