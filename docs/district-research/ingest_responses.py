"""
Parse the ChatGPT / Gemini deep-research outputs and merge them into
backend/app/data/district_research/<districtId>.json.

    python3 ingest_responses.py responses/chatgpt.md responses/gemini.md            # dry run: parse + report only
    python3 ingest_responses.py responses/chatgpt.md responses/gemini.md --write    # merge into the district files

Each response must contain blocks of the form
    === DISTRICT 29-577 | Mysuru | BEGIN ===  { json }  === DISTRICT 29-577 | Mysuru | END ===

Merge policy (new deep-research result wins, old pass is kept where it adds something):
  - the new file is the base; its sources keep their ids;
  - old sources whose URL is not in the new file are appended with fresh ids;
  - old reasons / keyFacts / responses / headlines that the new file does not already have
    (matched on factor / label / text / url) are appended with their source ids remapped;
  - coverage is the better of the two; gaps and officialFactorCheck come from the new file.
Redirect/aggregator URLs are dropped (with any claim that rested only on them).
Run district_research/validate.py afterwards.
"""

from __future__ import annotations

import json
import os
import re
import sys
from urllib.parse import urlparse

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.abspath(os.path.join(HERE, "..", "..", "backend", "app", "data", "district_research"))
BLOCK = re.compile(r"=== DISTRICT (29-\d{3}) \|[^\n]*BEGIN ===\s*(.*?)\s*=== DISTRICT \1 \|[^\n]*END ===", re.S)
BAD_HOSTS = ("vertexaisearch.cloud.google.com", "google.com", "news.google.com", "bing.com", "bing.net", "duckduckgo.com")
RANK = {"thin": 0, "moderate": 1, "rich": 2}


def parse(path: str) -> dict[str, dict]:
    text = open(path, encoding="utf-8").read()
    text = re.sub(r"```(?:json)?", "", text)
    out: dict[str, dict] = {}
    for did, body in BLOCK.findall(text):
        try:
            out[did] = json.loads(body)
        except json.JSONDecodeError as exc:
            print(f"  ! {did}: JSON error: {exc}")
    return out


def clean_urls(d: dict) -> dict:
    """Drop sources on redirector/aggregator hosts and anything resting only on them."""
    bad = {s["id"] for s in d.get("sources", []) if urlparse(s["url"]).netloc.lower().removeprefix("www.") in BAD_HOSTS}
    if not bad:
        return d
    keep = [s for s in d["sources"] if s["id"] not in bad]
    remap = {s["id"]: i + 1 for i, s in enumerate(keep)}
    for s in keep:
        s["id"] = remap[s["id"]]
    for group in ("reasons", "keyFacts", "responses", "officialFactorCheck"):
        kept = []
        for item in d.get(group, []):
            ids = [remap[i] for i in item.get("sources", []) if i in remap]
            if ids or group == "officialFactorCheck":
                item["sources"] = ids
                kept.append(item)
        d[group] = kept
    urls = {s["url"] for s in keep}
    d["headlines"] = [h for h in d.get("headlines", []) if h["url"] in urls]
    d["sources"] = keep
    d["gaps"] = (d.get("gaps", "") + f" {len(bad)} redirect/aggregator source(s) were dropped.").strip()
    return d


def merge(new: dict, old: dict | None) -> dict:
    new = clean_urls(new)
    if not old:
        return new
    by_url = {s["url"]: s["id"] for s in new["sources"]}
    remap: dict[int, int] = {}
    for s in old["sources"]:
        if s["url"] in by_url:
            remap[s["id"]] = by_url[s["url"]]
        else:
            nid = len(new["sources"]) + 1
            new["sources"].append({**s, "id": nid})
            by_url[s["url"]] = nid
            remap[s["id"]] = nid
    norm = lambda t: re.sub(r"\W+", " ", t.lower()).strip()  # noqa: E731
    for group, key in (("reasons", "factor"), ("keyFacts", "label"), ("responses", "text")):
        have = {norm(x[key]) for x in new[group]}
        for x in old[group]:
            if norm(x[key]) not in have:
                new[group].append({**x, "sources": [remap[i] for i in x["sources"] if i in remap]})
    have_urls = {h["url"] for h in new["headlines"]}
    new["headlines"] += [h for h in old["headlines"] if h["url"] not in have_urls]
    new["headlines"].sort(key=lambda h: h.get("date", ""), reverse=True)
    new["headlines"] = new["headlines"][:12]
    strength = {"strong": 0, "moderate": 1, "thin": 2}
    new["reasons"] = new["reasons"][:2] + sorted(new["reasons"][2:], key=lambda r: strength.get(r["evidence"], 3))
    new["reasons"] = new["reasons"][:8]
    if RANK.get(old.get("coverage"), 0) > RANK.get(new.get("coverage"), 0):
        new["coverage"] = old["coverage"]
    # a merged file holds more sources than either half alone
    if new["coverage"] == "thin" and len(new["sources"]) >= 8 and len(new["reasons"]) >= 4:
        new["coverage"] = "moderate"
    new["gaps"] = (new.get("gaps", "") + " " + old.get("gaps", "")).strip()[:900]
    return new


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    write = "--write" in sys.argv
    if not args:
        print(__doc__)
        return 2
    found: dict[str, dict] = {}
    for path in args:
        if os.path.isdir(path):  # a folder of already-structured <districtId>.json files
            got = {}
            for name in sorted(os.listdir(path)):
                if re.fullmatch(r"29-\d{3}\.json", name):
                    got[name[:-5]] = json.load(open(os.path.join(path, name), encoding="utf-8"))
        else:
            got = parse(path)
        print(f"{path}: {len(got)} district blocks")
        found.update(got)
    for did, new in sorted(found.items()):
        old_path = os.path.join(OUT, f"{did}.json")
        old = json.load(open(old_path, encoding="utf-8")) if os.path.isfile(old_path) else None
        merged = merge(new, old)
        print(f"  {did} {merged.get('name','?'):28} sources {len(old['sources']) if old else 0} -> {len(merged['sources'])}  "
              f"reasons {len(merged['reasons'])}  headlines {len(merged['headlines'])}  cov={merged['coverage']}")
        if write:
            json.dump(merged, open(old_path, "w", encoding="utf-8"), indent=2, ensure_ascii=False)
    print("wrote files" if write else "dry run -- pass --write to merge")
    missing = sorted({f"29-{n}" for n in range(555, 585)} - set(found))
    if missing:
        print("not in these responses:", ", ".join(missing))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
