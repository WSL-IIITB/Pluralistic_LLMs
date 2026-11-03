"""
Split the persona voice recordings made on the ElevenLabs website into one clip per script line.

    python3 scripts/split_persona_audio.py <folder with the 12 downloads>      # check + write clips
    python3 scripts/split_persona_audio.py <folder> --dry-run                   # report only

Each download is one persona's whole intro (docs/elevenlabs/<region>-<persona>.txt), read with a
<break time="1.2s" /> between lines, saved as <region>-<persona>.mp3. This finds those pauses, cuts the recording at
them, and writes public/audio/personas/<region>-<persona>-<nn>.mp3 plus manifest.json for the intro player.

It refuses a recording unless it finds exactly one pause per line break, and it reports any clip whose length is
far off what its text should take (a sign of a misread, a skipped line, or a pause in the wrong place).
"""

from __future__ import annotations

import glob
import json
import os
import re
import statistics
import subprocess
import sys

from generate_persona_audio import CONFIG, FFMPEG, OUT, clip_name, duration_ms, personas, write_manifest

# (noise floor, minimum pause length): tried in order until the pause count matches the line count
DETECT = [(-40, 0.85), (-40, 0.7), (-35, 0.7), (-45, 0.6), (-35, 0.55)]
LEAD_IN = 0.06  # seconds kept before speech starts
TAIL = 0.18  # seconds kept after speech ends


def duration(path: str) -> float:
    return duration_ms(path) / 1000


def silences(path: str, noise: int, min_len: float) -> list[tuple[float, float]]:
    err = subprocess.run([FFMPEG, "-hide_banner", "-nostats", "-i", path, "-af", f"silencedetect=noise={noise}dB:d={min_len}",
                          "-f", "null", "-"], capture_output=True, text=True).stderr
    starts = [float(x) for x in re.findall(r"silence_start: (-?[\d.]+)", err)]
    ends = [float(x) for x in re.findall(r"silence_end: ([\d.]+)", err)]
    return list(zip(starts, ends))


def gaps_between_lines(path: str, n_lines: int) -> tuple[list[tuple[float, float]], str]:
    """The n_lines - 1 pauses separating the lines (leading/trailing silence ignored), or [] if none fit."""
    total = duration(path)
    for noise, min_len in DETECT:
        inner = [(s, e) for s, e in silences(path, noise, min_len) if s > 0.3 and e < total - 0.3]
        if len(inner) == n_lines - 1:
            return inner, f"{noise}dB/{min_len}s"
        if len(inner) > n_lines - 1:
            # more pauses than breaks: keep the longest ones (the 1.2 s breaks), in time order
            keep = sorted(sorted(inner, key=lambda g: g[1] - g[0], reverse=True)[: n_lines - 1])
            shortest_kept = min(e - s for s, e in keep)
            longest_dropped = max((e - s for s, e in inner if (s, e) not in keep), default=0)
            if shortest_kept - longest_dropped > 0.25:  # a clear margin, so the choice is not a guess
                return keep, f"{noise}dB/{min_len}s, kept the {n_lines - 1} longest of {len(inner)}"
    return [], ""


def speech_bounds(path: str) -> tuple[float, float]:
    """Start and end of speech in the whole file (to trim the first and last clip)."""
    total = duration(path)
    s = silences(path, -45, 0.15)
    start = s[0][1] if s and s[0][0] <= 0.05 else 0.0
    end = s[-1][0] if s and s[-1][1] >= total - 0.05 else total
    return start, end


def cut(src: str, dst: str, start: float, end: float, fmt_kbps: int) -> None:
    subprocess.run([FFMPEG, "-hide_banner", "-loglevel", "error", "-y", "-ss", f"{start:.3f}", "-to", f"{end:.3f}", "-i", src,
                    "-ac", "1", "-ar", "44100", "-c:a", "libmp3lame", "-b:a", f"{fmt_kbps}k", dst], check=True)


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not args:
        print(__doc__)
        return 2
    folder = os.path.expanduser(args[0])
    dry = "--dry-run" in sys.argv
    cfg = json.load(open(CONFIG, encoding="utf-8"))
    kbps = int(cfg["output_format"].rsplit("_", 1)[1])
    scripts = personas()
    os.makedirs(OUT, exist_ok=True)
    failed = 0
    for key, lines in scripts.items():
        src = os.path.join(folder, f"{key.replace('/', '-')}.mp3")
        if not os.path.isfile(src):
            matches = glob.glob(os.path.join(folder, f"{key.replace('/', '-')}*.mp3"))
            if not matches:
                print(f"--   {key}: no recording in {folder}")
                continue
            src = matches[0]
        gaps, how = gaps_between_lines(src, len(lines))
        if not gaps:
            n = len([g for g in silences(src, -40, 0.7)])
            print(f"FAIL {key}: expected {len(lines) - 1} pauses between {len(lines)} lines, could not find them cleanly "
                  f"(about {n} pauses at -40dB/0.7s). Check the recording read every <break> and every line.")
            failed += 1
            continue
        first, last = speech_bounds(src)
        bounds = []
        for i in range(len(lines)):
            start = first if i == 0 else gaps[i - 1][1]
            end = last if i == len(lines) - 1 else gaps[i][0]
            bounds.append((max(0.0, start - LEAD_IN), end + TAIL))
        # each clip's speaking rate should be close to the others; a far-off one means a misread or a misplaced cut
        rates = [len(t) / max(0.1, e - s) for t, (s, e) in zip(lines, bounds)]
        med = statistics.median(rates)
        odd = [i for i, r in enumerate(rates) if r > med * 1.6 or r < med / 1.6]
        status = "WARN" if odd else "ok  "
        print(f"{status} {key}: {len(lines)} clips ({how}), {duration(src):.1f}s total, ~{med:.1f} chars/s")
        for i in odd:
            s, e = bounds[i]
            print(f"       line {i + 1}: {e - s:.1f}s for {len(lines[i])} chars (rate {rates[i]:.1f}) -- listen to this one: {lines[i][:70]!r}")
        if dry:
            continue
        for i, (s, e) in enumerate(bounds):
            cut(src, os.path.join(OUT, clip_name(key, i)), s, e, kbps)
    if not dry:
        m = write_manifest(cfg, scripts)
        print(f"\nmanifest: {len(m['clips'])} personas with complete audio -> {os.path.relpath(OUT)}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
