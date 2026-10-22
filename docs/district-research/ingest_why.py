"""
Ingest the "why is this factor dominant here?" deep-research responses (prompts/why-*.md) and VERIFY them.

    python3 ingest_why.py responses/why-1-chatgpt.md [more files ...]          # dry run: verification report
    python3 ingest_why.py responses/why-*.md --write                            # merge into district_research/<id>.json

Each district block carries `dominantFactorWhy` entries (one per factor row) with a verdict, an explanation
and proof items. Before anything is stored, every proof item is checked against the page it cites:

  * the page must open (unreachable / redirect-host sources are dropped);
  * scope "district" proof must come from a page that names the district (or a known alias);
  * every number in the claim must appear on at least one cited page;
  * a quote that is not on the page is removed (the claim stays only if the rest checks out).

Verdicts are then made consistent with what survived: "supported" needs surviving district proof
(otherwise it becomes "partly" if general proof survives, else "no-evidence"); "partly" needs any
surviving proof (else "no-evidence"). Everything dropped or downgraded is written to `notes`.
The result is stored under `dominantFactorWhy` in the district's research file, with its own
source list (ids are local to that block, not shared with the file's main `sources`).
"""

from __future__ import annotations

import json
import os
import re
import sys
import urllib.request
from urllib.parse import urlparse

from build_converted import ALIASES, CACHE, OUTLETS, page_meta, page_text
from build_prompts import NAMES
from ingest_responses import BAD_HOSTS, BLOCK, OUT

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
DISTRICTS = os.path.join(ROOT, "public", "data", "districts.json")
VERDICTS = {"supported", "partly", "not-supported", "no-evidence"}
SOURCE_TYPES = {"news", "government", "ngo", "research", "data"}
NUM = re.compile(r"(?<![\w.])\d+(?:\.\d+)?(?![\w])")


BROWSER_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"


def fetch(url: str) -> str:
    """Page body as text ("" if it cannot be opened). Binary PDFs come back as their raw bytes decoded loosely, so
    their text is unreadable: quotes/numbers/district names cannot be confirmed on them and those proof items drop."""
    os.makedirs(CACHE, exist_ok=True)
    path = os.path.join(CACHE, "why_" + re.sub(r"\W+", "_", url)[-140:])
    if os.path.isfile(path):
        return open(path, encoding="utf-8", errors="ignore").read()
    try:
        req = urllib.request.Request(url, headers={"User-Agent": BROWSER_UA, "Accept-Language": "en"})
        body = urllib.request.urlopen(req, timeout=30).read(2_000_000).decode("utf-8", "ignore")
    except Exception:  # noqa: BLE001
        body = ""
    open(path, "w", encoding="utf-8").write(body)
    return body


def aliases_for(did: str) -> list[str]:
    base = NAMES[did].split(" (")[0]
    for key, vals in ALIASES.items():
        if key.split(" (")[0] == base:
            return vals
    return [base.lower()]


def parse(path: str) -> dict[str, dict]:
    text = re.sub(r"```(?:json)?", "", open(path, encoding="utf-8").read())
    out: dict[str, dict] = {}
    for did, body in BLOCK.findall(text):
        try:
            out[did] = json.loads(body)
        except json.JSONDecodeError as exc:
            print(f"  ! {did}: JSON error: {exc}")
    return out


def numbers_in(text: str) -> set[str]:
    return {n for n in NUM.findall(re.sub(r"(?<=\d),(?=\d)", "", text)) if len(n.replace(".", "")) >= 2}


def verify(did: str, block: dict, factor_rows: list[dict]) -> tuple[dict, list[str]]:
    notes: list[str] = []
    al = aliases_for(did)
    src_by_id = {s.get("id"): s for s in block.get("sources", [])}
    pages: dict[int, tuple[str, str]] = {}  # id -> (raw, text)
    for sid, s in src_by_id.items():
        url = str(s.get("url", ""))
        host = urlparse(url).netloc.lower().removeprefix("www.")
        if not url.startswith("http") or host in BAD_HOSTS:
            notes.append(f"source {sid} dropped: redirect/aggregator or bad URL ({host or url[:30]})")
            continue
        raw = fetch(url)
        if not raw:
            notes.append(f"source {sid} dropped: page could not be opened ({host})")
            continue
        pages[sid] = (raw, page_text(raw))

    wanted = {(f["method"], f["factor"]) for f in factor_rows}
    entries: list[dict] = []
    for e in block.get("dominantFactorWhy", []):
        key = (e.get("method"), e.get("factor"))
        label = f"{e.get('method')}/{str(e.get('factor'))[:40]}"
        if key not in wanted:
            notes.append(f"entry {label} dropped: not one of this district's factor rows")
            continue
        if e.get("verdict") not in VERDICTS:
            notes.append(f"entry {label}: bad verdict {e.get('verdict')!r} -> no-evidence")
            e["verdict"] = "no-evidence"
        proof: list[dict] = []
        for p in e.get("proof", []):
            ids = [i for i in p.get("sources", []) if i in pages]
            claim = str(p.get("claim", "")).strip()
            if not claim or not ids:
                notes.append(f"{label}: proof dropped (no openable source): {claim[:60]!r}")
                continue
            texts = [pages[i][1] for i in ids]
            scope = p.get("scope") if p.get("scope") in ("district", "general") else "general"
            if scope == "district" and not any(a in t for t in texts for a in al):
                notes.append(f"{label}: district proof dropped, cited page does not name the district: {claim[:60]!r}")
                continue
            missing = [n for n in numbers_in(claim) if not any(re.search(rf"(?<![\w.]){re.escape(n)}(?![\w])", t) for t in texts)]
            if missing:
                notes.append(f"{label}: proof dropped, number(s) {', '.join(sorted(missing))} not on the cited page: {claim[:60]!r}")
                continue
            quote = " ".join(str(p.get("quote", "")).split())
            if quote and quote.lower() not in " ".join(texts):
                notes.append(f"{label}: quote removed (not found on the page)")
                quote = ""
            proof.append({"scope": scope, "claim": claim, "quote": quote, "sources": ids})
        verdict = e["verdict"]
        has_local = any(p["scope"] == "district" for p in proof)
        if verdict == "supported" and not has_local:
            new = "partly" if proof else "no-evidence"
            notes.append(f"{label}: 'supported' -> '{new}' (no verified district-specific proof survived)")
            verdict = new
        elif verdict == "partly" and not proof:
            notes.append(f"{label}: 'partly' -> 'no-evidence' (no verified proof survived)")
            verdict = "no-evidence"
        entries.append(
            {
                "factor": e["factor"],
                "method": e["method"],
                "area": e.get("area", ""),
                "verdict": verdict,
                "why": str(e.get("why", "")).strip(),
                "mechanism": str(e.get("mechanism", "")).strip(),
                "proof": proof,
            }
        )
    found = {(x["method"], x["factor"]) for x in entries}
    for method, factor in sorted(wanted - found):
        notes.append(f"no entry returned for {method}/{factor[:40]}")

    # keep only the sources that surviving proof still cites, renumbered from 1
    used = sorted({i for x in entries for p in x["proof"] for i in p["sources"]})
    remap = {old: n + 1 for n, old in enumerate(used)}
    sources = []
    for old in used:
        s = src_by_id[old]
        raw = pages[old][0]
        host = urlparse(s["url"]).netloc.lower().removeprefix("www.")
        title, date = page_meta(raw, s.get("title", ""))
        sources.append(
            {
                "id": remap[old],
                "url": s["url"],
                "title": title or s.get("title", ""),
                "outlet": OUTLETS.get(host, s.get("outlet") or host),
                "date": date or str(s.get("date", ""))[:10],
                "type": s.get("type") if s.get("type") in SOURCE_TYPES else "news",
            }
        )
    for x in entries:
        for p in x["proof"]:
            p["sources"] = [remap[i] for i in p["sources"]]
    return (
        {
            "researchedOn": str(block.get("researchedOn", "")),
            "entries": entries,
            "sources": sources,
            "gaps": str(block.get("gaps", "")).strip(),
            "notes": notes,
        },
        notes,
    )


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    write = "--write" in sys.argv
    if not args:
        print(__doc__)
        return 2
    ctx = {d["districtId"]: d for d in json.load(open(DISTRICTS, encoding="utf-8"))["districts"]}
    found: dict[str, dict] = {}
    for path in args:
        got = parse(path)
        print(f"{path}: {len(got)} district blocks")
        found.update(got)
    tally = {"supported": 0, "partly": 0, "not-supported": 0, "no-evidence": 0}
    for did, block in sorted(found.items()):
        if did not in ctx:
            print(f"  ! {did}: unknown district id, skipped")
            continue
        result, notes = verify(did, block, ctx[did]["nitiFactors"])
        for e in result["entries"]:
            tally[e["verdict"]] += 1
        print(f"\n{did} {NAMES[did]}: {len(result['entries'])} factor entries, {len(result['sources'])} verified sources, {len(notes)} note(s)")
        for e in result["entries"]:
            print(f"   [{e['method']:8}] {e['verdict']:13} proof={len(e['proof'])}  {e['factor'][:55]}")
        for n in notes:
            print(f"     - {n}")
        if write:
            path = os.path.join(OUT, f"{did}.json")
            data = json.load(open(path, encoding="utf-8"))
            data["dominantFactorWhy"] = result
            json.dump(data, open(path, "w", encoding="utf-8"), indent=2, ensure_ascii=False)
    print(f"\nverdicts after verification: {tally}")
    print("wrote files" if write else "dry run -- pass --write to merge into district_research/")
    missing = sorted(set(NAMES) - set(found))
    if missing:
        print("not in these responses:", ", ".join(missing))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
