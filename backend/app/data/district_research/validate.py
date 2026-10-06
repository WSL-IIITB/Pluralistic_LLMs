"""
Validate district_research/*.json against SCHEMA.md and (optionally) check that
every cited URL still resolves.

    python3 validate.py              # schema checks only
    python3 validate.py --urls       # also HEAD/GET every source URL
"""

from __future__ import annotations

import concurrent.futures
import glob
import json
import os
import sys
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
CATEGORIES = {"economic", "migration", "school-infrastructure", "social-norms", "gender", "health", "governance", "other"}
SOURCE_TYPES = {"news", "government", "ngo", "research", "data"}


def check_file(path: str) -> list[str]:
    problems: list[str] = []
    d = json.load(open(path, encoding="utf-8"))
    for key in ("districtId", "name", "regionId", "headline", "summary", "reasons", "keyFacts", "headlines", "responses", "sources", "coverage", "gaps"):
        if key not in d:
            problems.append(f"missing {key}")
    if problems:
        return problems
    if os.path.basename(path)[:-5] != d["districtId"]:
        problems.append("filename != districtId")
    n = len(d["sources"])
    ids = [s.get("id") for s in d["sources"]]
    if ids != list(range(1, n + 1)):
        problems.append("source ids are not 1..n")
    urls = {s.get("url") for s in d["sources"]}
    for s in d["sources"]:
        if not str(s.get("url", "")).startswith("http"):
            problems.append(f"bad source url {s.get('url')!r}")
        if s.get("type") not in SOURCE_TYPES:
            problems.append(f"bad source type {s.get('type')!r}")
    for group in ("reasons", "keyFacts", "responses"):
        for item in d[group]:
            for sid in item.get("sources", []):
                if not isinstance(sid, int) or not 1 <= sid <= n:
                    problems.append(f"{group}: source index {sid} out of range")
    for r in d["reasons"]:
        if r.get("category") not in CATEGORIES:
            problems.append(f"bad category {r.get('category')!r}")
        if r.get("evidence") not in {"strong", "moderate", "thin"}:
            problems.append(f"bad evidence {r.get('evidence')!r}")
        if not r.get("sources"):
            problems.append(f"reason {r.get('factor')!r} has no sources")
    for h in d["headlines"]:
        if h.get("url") not in urls:
            problems.append(f"headline url not in sources: {h.get('url')}")
    if not 1 <= len(d["reasons"]) <= 9:
        problems.append(f"{len(d['reasons'])} reasons (want 1-9)")
    for chk in d.get("officialFactorCheck", []):
        if chk.get("verdict") not in {"supports", "contradicts", "unclear", "no-evidence"}:
            problems.append(f"bad verdict {chk.get('verdict')!r}")
        if chk.get("method") not in {"state", "district"}:
            problems.append(f"bad method {chk.get('method')!r}")
    if d["coverage"] not in {"rich", "moderate", "thin"}:
        problems.append(f"bad coverage {d['coverage']!r}")
    return problems


def url_status(url: str) -> tuple[str, int | str]:
    headers = {"User-Agent": "Mozilla/5.0 (research-link-check)"}
    for method in ("HEAD", "GET"):
        try:
            req = urllib.request.Request(url, method=method, headers=headers)
            with urllib.request.urlopen(req, timeout=15) as resp:
                return url, resp.status
        except urllib.error.HTTPError as exc:
            if method == "HEAD" and exc.code in (403, 405, 400):
                continue
            return url, exc.code
        except Exception as exc:  # noqa: BLE001
            if method == "HEAD":
                continue
            return url, type(exc).__name__
    return url, "error"


def main() -> int:
    files = sorted(glob.glob(os.path.join(HERE, "29-*.json")))
    bad = 0
    all_urls: dict[str, str] = {}
    for f in files:
        probs = check_file(f)
        name = os.path.basename(f)
        d = json.load(open(f, encoding="utf-8"))
        status = "ok " if not probs else "BAD"
        print(f"{status} {name:12} {d.get('name','?'):28} cov={d.get('coverage','?'):8} reasons={len(d.get('reasons',[]))} sources={len(d.get('sources',[]))}")
        for p in probs:
            print("      -", p)
        bad += bool(probs)
        for s in d.get("sources", []):
            all_urls[s["url"]] = name
    print(f"\n{len(files)} files, {bad} with problems, {len(all_urls)} unique source urls")
    if "--urls" in sys.argv:
        with concurrent.futures.ThreadPoolExecutor(max_workers=12) as pool:
            results = list(pool.map(url_status, all_urls))
        dead = [(u, c) for u, c in results if not (isinstance(c, int) and c < 400)]
        for u, c in dead:
            print(f"  {c}  {u}  ({all_urls[u]})")
        print(f"{len(dead)} of {len(results)} urls did not return a success status (403/paywalls are common for news sites)")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
