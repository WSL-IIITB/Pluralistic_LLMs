"""
Ingest the web sources found for each district's NITI "top three changes" and VERIFY them.

    python3 ingest_prescriptive.py <research.json> [more ...]            # dry run: verification report
    python3 ingest_prescriptive.py <research.json> [more ...] --write    # merge into district_research/<id>.json

Each input (one per region, from the search pass) lists, per district, the top three changes the NITI prescriptive
model ranks highest (public/data/niti-prescriptive.json, feasible ranking) and, for each, findings
{claim, quote, url, title, outlet, date, scope: district|state, stance: gap|progress|context}. Before anything is
stored, every finding is re-checked against the page it cites, exactly as the "why dominant" answers are:

  * the page must open (redirect/aggregator hosts and pages that cannot be fetched are dropped);
  * scope "district" needs a page that names the district (or a known alias);
  * every number in the claim must appear on the page;
  * the quote must appear on the page, or it is removed (the claim stays only if the rest checks out).

The result goes under `prescriptiveEvidence` in the district's research file, with its own source list (ids local to
that block). public/data/districts-research.json is rebuilt from the files, the same way the API serves them.
"""

from __future__ import annotations

import glob
import json
import os
import re
import sys
import urllib.request
from urllib.parse import urlparse

from build_converted import CACHE, OUTLETS, page_meta, page_text
from ingest_responses import BAD_HOSTS, OUT
from ingest_why import BROWSER_UA, aliases_for, numbers_in

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
PRESCRIPTIVE = os.path.join(ROOT, "public", "data", "niti-prescriptive.json")
STATIC = os.path.join(ROOT, "public", "data", "districts-research.json")
STANCES = {"gap", "progress", "context"}
MAX_FINDINGS = 4


def fetch(url: str) -> str:
    """Page body as text ("" if it cannot be opened), cached next to the other research fetches."""
    os.makedirs(CACHE, exist_ok=True)
    path = os.path.join(CACHE, "pre_" + re.sub(r"\W+", "_", url)[-140:])
    if os.path.isfile(path):
        return open(path, encoding="utf-8", errors="ignore").read()
    try:
        req = urllib.request.Request(url, headers={"User-Agent": BROWSER_UA, "Accept-Language": "en"})
        body = urllib.request.urlopen(req, timeout=30).read(3_000_000).decode("utf-8", "ignore")
    except Exception:  # noqa: BLE001
        body = ""
    open(path, "w", encoding="utf-8").write(body)
    return body


def norm(s: str) -> str:
    s = s.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    s = s.replace("–", "-").replace("—", "-").replace("\xa0", " ")
    return " ".join(s.split()).lower()


def source_type(host: str) -> str:
    if host.endswith((".gov.in", ".nic.in")) or "udise" in host:
        return "government"
    if "osaat" in host or host.endswith(".org"):
        return "ngo"
    if "zenodo" in host or "researchgate" in host or host.endswith(".ac.in"):
        return "research"
    return "news"


def load(paths: list[str]) -> dict[str, dict[str, list[dict]]]:
    """district id -> factor -> {summary, findings[]} merged across the input files."""
    out: dict[str, dict[str, dict]] = {}
    for path in paths:
        data = json.load(open(path, encoding="utf-8"))
        for d in data.get("districts", []):
            for ch in d.get("changes", []):
                slot = out.setdefault(d["districtId"], {}).setdefault(ch["factor"], {"summary": "", "findings": []})
                if ch.get("summary") and not slot["summary"]:
                    slot["summary"] = ch["summary"].strip()
                slot["findings"].extend(ch.get("findings", []))
    return out


def verify(did: str, changes: dict[str, dict], wanted: list[str]) -> tuple[dict, list[str]]:
    notes: list[str] = []
    al = aliases_for(did)
    pages: dict[str, tuple[str, str]] = {}  # url -> (raw, normalised text)
    sources: list[dict] = []
    sid_by_url: dict[str, int] = {}
    out_changes = []
    for factor in wanted:
        slot = changes.get(factor, {"summary": "", "findings": []})
        kept: list[dict] = []
        for f in slot["findings"]:
            url = str(f.get("url", "")).strip()
            claim = " ".join(str(f.get("claim", "")).split())
            label = f"{factor[:34]} | {claim[:50]!r}"
            host = urlparse(url).netloc.lower().removeprefix("www.")
            if not url.startswith("http") or host in BAD_HOSTS:
                notes.append(f"{label}: dropped, redirect/aggregator or bad URL ({host or url[:30]})")
                continue
            if url not in pages:
                raw = fetch(url)
                pages[url] = (raw, norm(page_text(raw)) if raw else "")
            raw, text = pages[url]
            if not text:
                notes.append(f"{label}: dropped, page could not be opened ({host})")
                continue
            scope = f.get("scope") if f.get("scope") in ("district", "state") else "state"
            if scope == "district" and not any(a in text for a in al):
                notes.append(f"{label}: dropped, page does not name the district")
                continue
            missing = [n for n in numbers_in(claim) if not re.search(rf"(?<![\w.]){re.escape(n)}(?![\w])", text.replace(",", ""))]
            if missing:
                notes.append(f"{label}: dropped, number(s) {', '.join(sorted(missing))} not on the page")
                continue
            quote = " ".join(str(f.get("quote", "")).split())
            if quote and norm(quote) not in text:
                notes.append(f"{label}: quote removed (not found on the page)")
                quote = ""
            if url not in sid_by_url:
                sid_by_url[url] = len(sources) + 1
                title, date = page_meta(raw, str(f.get("title", "")))
                sources.append({
                    "id": sid_by_url[url], "url": url, "title": (title or f.get("title") or "")[:200],
                    "outlet": OUTLETS.get(host, f.get("outlet") or host),
                    "date": date or str(f.get("date", ""))[:10], "type": source_type(host),
                })
            if any(k["claim"] == claim and k["sources"] == [sid_by_url[url]] for k in kept):
                continue
            kept.append({"claim": claim, "quote": quote, "scope": scope,
                         "stance": f.get("stance") if f.get("stance") in STANCES else "context",
                         "sources": [sid_by_url[url]]})
        # district findings first, then gaps before progress before context
        kept.sort(key=lambda k: (k["scope"] != "district", ["gap", "progress", "context"].index(k["stance"])))
        out_changes.append({"factor": factor, "summary": slot["summary"] if kept else "", "findings": kept[:MAX_FINDINGS]})
    used = {i for c in out_changes for k in c["findings"] for i in k["sources"]}
    remap = {old: n + 1 for n, old in enumerate(sorted(used))}
    for c in out_changes:
        for k in c["findings"]:
            k["sources"] = [remap[i] for i in k["sources"]]
    sources = [{**s, "id": remap[s["id"]]} for s in sources if s["id"] in used]
    return {"researchedOn": "2026-11-03", "ranking": "feasible", "changes": out_changes, "sources": sources, "notes": notes}, notes


def top_three(did: str, data: dict) -> list[str]:
    """The district's top three changes: the highest feasible contribution across its NITI rows (areas)."""
    best: dict[str, float] = {}
    for a in data["districts"][did]["areas"]:
        for f in a["factors"]:
            best[f["name"]] = max(best.get(f["name"], -1), f["feasible"]["contribution"])
    return [n for n, _ in sorted(best.items(), key=lambda kv: -kv[1])[:3]]


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    write = "--write" in sys.argv
    if not args:
        print(__doc__)
        return 2
    niti = json.load(open(PRESCRIPTIVE, encoding="utf-8"))
    found = load(args)
    totals = {"in": 0, "kept": 0, "district": 0}
    for did in sorted(niti["districts"]):
        wanted = top_three(did, niti)
        changes = found.get(did, {})
        result, notes = verify(did, changes, wanted)
        n_in = sum(len(changes.get(f, {}).get("findings", [])) for f in wanted)
        n_kept = sum(len(c["findings"]) for c in result["changes"])
        totals["in"] += n_in
        totals["kept"] += n_kept
        totals["district"] += sum(1 for c in result["changes"] for k in c["findings"] if k["scope"] == "district")
        print(f"\n{did} {niti['districts'][did]['name']}: {n_kept}/{n_in} findings kept, {len(result['sources'])} sources")
        for c in result["changes"]:
            print(f"   {c['factor'][:50]:50} {len(c['findings'])} kept")
        for n in notes:
            print(f"     - {n}")
        if write:
            path = os.path.join(OUT, f"{did}.json")
            data = json.load(open(path, encoding="utf-8"))
            data["prescriptiveEvidence"] = result
            json.dump(data, open(path, "w", encoding="utf-8"), indent=2, ensure_ascii=False)
    print(f"\nkept {totals['kept']} of {totals['in']} findings ({totals['district']} about the district itself)")
    if write:
        merged = {}
        for path in sorted(glob.glob(os.path.join(OUT, "29-*.json"))):
            merged[os.path.basename(path)[:-5]] = json.load(open(path, encoding="utf-8"))
        with open(STATIC, "w", encoding="utf-8") as fh:
            json.dump(merged, fh, ensure_ascii=False, separators=(",", ":"))
        print(f"wrote district files and {os.path.relpath(STATIC, ROOT)}")
    else:
        print("dry run -- pass --write to merge into district_research/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
