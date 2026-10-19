"""
Ask Gemma every eval question under the SAME rules the Worker uses and grade the answers.

    node scripts/chat_eval/build_contexts.mjs          # real router -> contexts.json
    cd backend && .venv/bin/python ../scripts/chat_eval/run_eval.py [--only id,id] [--show]

Uses the backend's configured Gemma client (address never printed). Checks per answer:
  * every cited [S#] exists in the context that was sent        (hard)
  * out-of-scope questions get EXACTLY the refusal sentence      (hard)
  * answerable questions are not refused                         (hard)
  * `include` regexes all match, `exclude` regexes none          (hard)
  * digits (3+ digits / decimals) in the answer that never appear in the context   (soft warning)
Pass bar: >= all-but-2 questions pass, 100% valid citations, 100% correct refusals.
Results -> scripts/chat_eval/results.json
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(ROOT, "backend"))

from app.config import get_settings  # noqa: E402
from app.connectors.llm import RemoteGemmaLLMClient  # noqa: E402

RULES = json.load(open(os.path.join(ROOT, "proxy", "src", "chatRules.json"), encoding="utf-8"))
REFUSAL = RULES["refusal"]
SYSTEM = RULES["system"].replace("{{REFUSAL}}", f'"{REFUSAL}"')


def build_messages(context: str, question: str) -> list[dict]:
    return [
        {"role": "system", "content": f"{SYSTEM}\n\n<CONTEXT>\n{context}\n</CONTEXT>"},
        {"role": "user", "content": question},
    ]


async def main() -> int:
    questions = {q["id"]: q for q in json.load(open(os.path.join(HERE, "questions.json"), encoding="utf-8"))}
    contexts = {c["id"]: c for c in json.load(open(os.path.join(HERE, "contexts.json"), encoding="utf-8"))}
    only = None
    if "--only" in sys.argv:
        only = set(sys.argv[sys.argv.index("--only") + 1].split(","))
    llm = RemoteGemmaLLMClient(get_settings())
    sem = asyncio.Semaphore(3)

    async def one(qid: str) -> dict:
        q, c = questions[qid], contexts[qid]
        async with sem:
            try:
                resp = await llm.client.chat.completions.create(
                    model=llm._model, temperature=0.0, max_tokens=700,
                    messages=build_messages(c["context"], q["question"]), timeout=120,
                )
                answer = (resp.choices[0].message.content or "").strip()
            except Exception as exc:  # noqa: BLE001
                return {"id": qid, "category": q["category"], "answer": "", "error": f"{type(exc).__name__}", "fails": ["request failed"], "warns": []}
        fails, warns = [], []
        cited = set(re.findall(r"\[(S\d+)\]", answer))
        bad = sorted(cited - set(c["sourceIds"]))
        if bad:
            fails.append(f"cites ids not in context: {bad}")
        if re.search(r"\[(DIGEST|CAVEATS|UIDAI|ANALYSIS|PERSONAS|REGION|DISTRICT)", answer):
            warns.append("cites a section name instead of a source id")
        is_refusal = answer.strip().strip('"') == REFUSAL
        if q.get("refuse"):
            if not is_refusal:
                fails.append("should have refused (out of scope) but answered")
        else:
            if is_refusal and not q.get("allowRefusal"):
                fails.append("refused an answerable question")
            for pat in ([] if is_refusal and q.get("allowRefusal") else q.get("include", [])):
                if not re.search(pat, answer, re.I):
                    fails.append(f"missing /{pat}/")
            for pat in q.get("exclude", []):
                if re.search(pat, answer, re.I):
                    fails.append(f"contains forbidden /{pat}/")
            ctx_digits = set(re.findall(r"\d[\d,]*\.?\d*", c["context"].replace(",", "")))
            for num in re.findall(r"\d[\d,]*\.?\d*", answer):
                plain = num.replace(",", "").rstrip(".")
                if len(plain.replace(".", "")) < 3 and "." not in plain:
                    continue  # ignore small counts / years-in-words noise
                if plain not in ctx_digits:
                    warns.append(f"number {num} not in context")
            if not cited and not is_refusal:
                warns.append("no citations")
        return {"id": qid, "category": q["category"], "question": q["question"], "answer": answer,
                "citations": sorted(cited), "refused": is_refusal, "fails": fails, "warns": warns, "tokens": c["tokenEstimate"]}

    ids = [i for i in questions if (not only or i in only)]
    results = await asyncio.gather(*[one(i) for i in ids])
    passed = sum(1 for r in results if not r["fails"])
    bad_cites = sum(1 for r in results if any("cites ids" in f for f in r["fails"]))
    bad_refusals = sum(1 for r in results if any("refus" in f for f in r["fails"]))
    show = "--show" in sys.argv
    for r in results:
        mark = "PASS" if not r["fails"] else "FAIL"
        print(f"{mark}  {r['id']:<32} [{r['category']}]")
        for f in r["fails"]:
            print(f"        x {f}")
        for w in r["warns"]:
            print(f"        ! {w}")
        if show or r["fails"]:
            print("        > " + r["answer"].replace("\n", "\n          ")[:700])
    print(f"\n{passed}/{len(results)} passed | invalid-citation answers: {bad_cites} | wrong refusals: {bad_refusals}")
    ok = passed >= len(results) - 2 and bad_cites == 0 and bad_refusals == 0
    print("EVAL " + ("PASSED" if ok else "NOT PASSED") + " (bar: all but 2 pass, 100% valid citations, 100% correct refusals)")
    json.dump(results, open(os.path.join(HERE, "results.json"), "w"), indent=1, ensure_ascii=False)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
