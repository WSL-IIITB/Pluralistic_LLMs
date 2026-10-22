import json, re, sys, concurrent.futures
sys.path.insert(0, ".")
from ingest_why import fetch, aliases_for
from build_converted import page_text
from build_prompts import NAMES
r = json.load(open("../../public/data/districts-research.json"))
MARR = re.compile(r"child marriage|marriages?|married|wed(?:ding)?|bride|early marriage", re.I)
SCHOOL = re.compile(r"school|dropout|drop out|dropped out|education|student|class \d|sslc|girls? (?:leave|left|quit)", re.I)
def window_link(text):
    for m in re.finditer(r"child marriage|early marriage|marriages?\b|married", text):
        seg = text[max(0, m.start()-350): m.end()+350]
        if SCHOOL.search(seg): return True
    return False
jobs = {}
for did, d in r.items():
    for x in d["reasons"]:
        if MARR.search(x["factor"] + " " + x["detail"]):
            for sid in x["sources"]:
                s = next((s for s in d["sources"] if s["id"] == sid), None)
                if s: jobs[(did, s["url"])] = s
urls = sorted({u for _, u in jobs})
print(len(urls), "distinct pages to read", flush=True)
with concurrent.futures.ThreadPoolExecutor(8) as pool:
    texts = dict(zip(urls, pool.map(lambda u: page_text(fetch(u)), urls)))
rows = []
for did, d in sorted(r.items()):
    al = aliases_for(did)
    for x in d["reasons"]:
        if not MARR.search(x["factor"] + " " + x["detail"]): continue
        res = []
        for sid in x["sources"]:
            s = next((s for s in d["sources"] if s["id"] == sid), None)
            if not s: continue
            t = texts.get(s["url"], "")
            if not t: res.append(("unreachable", s["outlet"])); continue
            dist = any(a in t for a in al); mar = bool(MARR.search(t)); link = window_link(t)
            res.append(("DIRECT" if dist and mar and link else "district+marriage, no school link" if dist and mar else "district missing" if not dist else "marriage missing", s["outlet"]))
        best = "DIRECT" if any(a=="DIRECT" for a,_ in res) else ("unreachable" if res and all(a=="unreachable" for a,_ in res) else (sorted({a for a,_ in res})[0] if res else "no sources"))
        rows.append((did, d["name"], x["evidence"], x["factor"], best, res))
import collections
c = collections.Counter(b for *_, b, _ in rows)
print("\nmarriage-related reasons:", len(rows)); print(dict(c))
byd = collections.defaultdict(list)
for did, name, ev, f, best, res in rows: byd[name].append((ev, best))
good = [n for n, v in byd.items() if any(b == "DIRECT" for _, b in v)]
print("\ndistricts with at least one DIRECT page-verified marriage-and-school reason:", len(good), "of", len(byd))
print("districts with NO direct verification:", [(n, v) for n, v in byd.items() if n not in good])
json.dump([(a,b,c_,d,e,f) for a,b,c_,d,e,f in rows], open("/private/tmp/claude-501/-Users-viswanath-Desktop-ALL-PluralAI-dashboard/3c8240f7-355d-45f4-8bf9-434ea563a5eb/scratchpad/marriage_audit.json","w"), indent=1)
