"""
Generate the persona intro voice clips with ElevenLabs: one MP3 per script line, for all 12 personas.

    ELEVENLABS_API_KEY=... python3 scripts/generate_persona_audio.py              # generate what is missing
    ELEVENLABS_API_KEY=... python3 scripts/generate_persona_audio.py --only old-mysuru/male --limit 1
    python3 scripts/generate_persona_audio.py --manifest                          # rebuild the manifest only

Input : src/lib/worldview/personaCards/*.json (intro.lines; `say` is spoken when present, else `text`)
        scripts/persona_voices.json (model, output format, voice settings, one Indian-English voice per persona)
Output: public/audio/personas/<region>-<persona>-<nn>.mp3
        public/audio/personas/manifest.json  {model, voices{key: {voice, name}}, clips{key: [{file, ms, chars}]}}

The key is read from the environment and never written anywhere. Existing clips are never regenerated (delete a
file to redo it), so a rerun costs nothing. Lines of one persona are stitched (previous_request_ids) so the voice
stays consistent from clip to clip. Each request's character cost is logged; the run stops on the first error.
"""

from __future__ import annotations

import glob
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
CARDS = os.path.join(ROOT, "src", "lib", "worldview", "personaCards")
CONFIG = os.path.join(ROOT, "scripts", "persona_voices.json")
OUT = os.path.join(ROOT, "public", "audio", "personas")
LOG = os.path.join(OUT, "generation-log.json")
API = "https://api.elevenlabs.io/v1/text-to-speech/{voice}?output_format={fmt}"


def personas() -> dict[str, list[str]]:
    """'region/persona' -> spoken lines, in script order."""
    out = {}
    for path in sorted(glob.glob(os.path.join(CARDS, "*.json"))):
        rid = os.path.basename(path)[:-5]
        for pid, card in json.load(open(path, encoding="utf-8")).items():
            out[f"{rid}/{pid}"] = [ln.get("say") or ln["text"] for ln in card["intro"]["lines"]]
    return out


def clip_name(key: str, i: int) -> str:
    return f"{key.replace('/', '-')}-{i + 1:02d}.mp3"


FFMPEG = os.environ.get("FFMPEG", "ffmpeg")  # any ffmpeg with libmp3lame (e.g. the one imageio-ffmpeg ships)


def duration_ms(path: str) -> int:
    err = subprocess.run([FFMPEG, "-hide_banner", "-i", path], capture_output=True, text=True).stderr
    m = re.search(r"Duration: (\d+):(\d+):([\d.]+)", err)
    if not m:
        raise RuntimeError(f"could not read the duration of {path}")
    h, mi, s = m.groups()
    return round((int(h) * 3600 + int(mi) * 60 + float(s)) * 1000)


def speak(key: str, text: str, cfg: dict, voice: str, previous: list[str]) -> tuple[bytes, dict]:
    body = {"text": text, "model_id": cfg["model"], "language_code": "en", "voice_settings": cfg["voice_settings"]}
    if previous:
        body["previous_request_ids"] = previous[-3:]
    req = urllib.request.Request(API.format(voice=voice, fmt=cfg["output_format"]), data=json.dumps(body).encode(),
                                 headers={"xi-api-key": key, "Content-Type": "application/json", "Accept": "audio/mpeg"})
    with urllib.request.urlopen(req, timeout=120) as resp:
        return resp.read(), {k.lower(): v for k, v in resp.headers.items()}


def write_manifest(cfg: dict, scripts: dict[str, list[str]]) -> dict:
    manifest = {"model": cfg["model"], "format": cfg["output_format"], "voices": {}, "clips": {}}
    for key, lines in scripts.items():
        files = [os.path.join(OUT, clip_name(key, i)) for i in range(len(lines))]
        if not all(os.path.isfile(f) for f in files):
            continue  # only personas whose every line exists are played from audio
        v = cfg["voices"][key]
        manifest["voices"][key] = {"voice": v["voice_id"], "name": v["name"]}
        manifest["clips"][key] = [{"file": os.path.basename(f), "ms": duration_ms(f), "chars": len(t)} for f, t in zip(files, lines)]
    with open(os.path.join(OUT, "manifest.json"), "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=1, ensure_ascii=False)
    return manifest


def main() -> int:
    cfg = json.load(open(CONFIG, encoding="utf-8"))
    scripts = personas()
    os.makedirs(OUT, exist_ok=True)
    if "--manifest" in sys.argv:
        m = write_manifest(cfg, scripts)
        print(f"manifest: {len(m['clips'])} personas with complete audio")
        return 0
    key = os.environ.get("ELEVENLABS_API_KEY", "").strip()
    if not key:
        print("set ELEVENLABS_API_KEY in the environment")
        return 2
    only = sys.argv[sys.argv.index("--only") + 1] if "--only" in sys.argv else None
    limit = int(sys.argv[sys.argv.index("--limit") + 1]) if "--limit" in sys.argv else None
    log = json.load(open(LOG, encoding="utf-8")) if os.path.isfile(LOG) else []
    made = 0
    spent = 0.0
    for pkey, lines in scripts.items():
        if only and pkey != only:
            continue
        voice = cfg["voices"][pkey]["voice_id"]
        previous: list[str] = [e["request_id"] for e in log if e["persona"] == pkey and e.get("request_id")]
        for i, text in enumerate(lines):
            path = os.path.join(OUT, clip_name(pkey, i))
            if os.path.isfile(path):
                continue
            if limit is not None and made >= limit:
                break
            try:
                audio, headers = speak(key, text, cfg, voice, previous)
            except urllib.error.HTTPError as exc:
                print(f"STOP {pkey} line {i + 1}: HTTP {exc.code} {exc.read().decode('utf-8', 'ignore')[:300]}")
                json.dump(log, open(LOG, "w", encoding="utf-8"), indent=1)
                return 1
            if len(audio) < 2000:
                print(f"STOP {pkey} line {i + 1}: suspiciously small response ({len(audio)} bytes)")
                return 1
            with open(path, "wb") as fh:
                fh.write(audio)
            cost = headers.get("character-cost") or headers.get("x-character-count") or ""
            rid = headers.get("request-id", "")
            previous.append(rid) if rid else None
            spent += float(cost) if cost.replace(".", "", 1).isdigit() else 0
            log.append({"persona": pkey, "line": i + 1, "file": os.path.basename(path), "chars": len(text),
                        "cost": cost, "request_id": rid, "bytes": len(audio), "ms": duration_ms(path)})
            made += 1
            print(f"ok  {os.path.basename(path)}  {len(text)} chars  cost {cost or '?'}  {log[-1]['ms'] / 1000:.1f}s")
            time.sleep(0.3)
    json.dump(log, open(LOG, "w", encoding="utf-8"), indent=1)
    m = write_manifest(cfg, scripts)
    print(f"\nmade {made} clip(s), reported cost {spent:g}; manifest has {len(m['clips'])} complete personas")
    return 0


if __name__ == "__main__":
    sys.exit(main())
