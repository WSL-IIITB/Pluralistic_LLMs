"""
Build the human-evaluation item set for the persona responses.

    cd backend && .venv/bin/python ../scripts/build_eval_items.py

Reads  public/data/default-run.json   (the saved run the dashboard opens on: the question, each
                                       persona's reply, and the no-persona baseline reply per region)
       backend persona files          (persona text -> the exact persona prompt the model was given)
       src/lib/worldview/personaCards (name / role / place / community, for display)
Writes docs/human-eval/persona_eval_items.csv   (one row per persona response -- reference sheet)
       public/evaluate/items.json               (what the evaluation form loads; no long prompts)

The persona prompt is REBUILT from the current persona files (the run did not store it). Its short
hash (`persona_version`) is recorded so a response can be traced to the exact persona text.
"""

from __future__ import annotations

import csv
import json
import os
import re
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "backend"))

from app.karnataka import build_persona_prompt, persona_regions, persona_version  # noqa: E402

RUN = json.load(open(os.path.join(ROOT, "public/data/default-run.json"), encoding="utf-8"))
PERSONAS = {(p["regionId"], p["personaId"]): p for p in json.load(open(os.path.join(ROOT, "public/data/personas.json"), encoding="utf-8"))}

# The instruction block appended to every persona prompt when the reply was generated
# (backend/app/connectors/llm.py, OpenAILLMClient.answer_for_region). {region_name} is filled per row.
TASK_INSTRUCTIONS = (
    "You answer a user's question about Karnataka, India, for ONE region: {region_name}. "
    "Ground the reply in the supplied evidence: `research_documents` (mainstream and "
    "official web sources gathered for this region -- {{id, title, domain, snippet}}), "
    "`viewpoint_clusters` (what is being said about the topic in this region on social "
    "media and in the news -- label, summary, postCount, sources), and `deflections` "
    "(points where this region's viewpoints disagree). If the evidence is thin, say less "
    "rather than inventing.\n\n"
    "REQUIRED STRUCTURE, in this order:\n"
    "1. EXACTLY ONE `tldr` segment: the region's one-sentence answer (max ~30 words).\n"
    "2. TWO to FOUR `recommendation` segments: the core of the reply, one sentence each "
    "(max ~40 words) -- concrete actions for policy questions, distinct positions for "
    "descriptive ones.\n"
    "3. Evidence, keeping the two source types SEPARATE: zero to two `body` segments "
    "that begin 'Official & mainstream sources:' and draw ONLY on research_documents "
    "(attach their ids as `citations`), then zero to two `body` segments that begin "
    "'Social media:' and draw ONLY on viewpoint_clusters (never cite these).\n\n"
    'Respond with JSON: {{"segments": [{{"text": str, "kind": "tldr"|"recommendation"|'
    '"body", "clusterId": str (optional), "citations": int[] (optional)}}]}}. PLAIN TEXT '
    "ONLY: no markdown, no URLs, no source names inline -- use `citations`. Only cite ids "
    "present in research_documents. Do not restate the region's name as a label; the UI "
    "already shows it."
)
USER_MESSAGE_NOTE = (
    "JSON with: query, query_type, region, research_documents (id/title/domain/snippet gathered for "
    "that region), viewpoint_clusters (the region's social/news viewpoint clusters) and deflections."
)

REGION_NAME = {r["id"]: r["name"] for r in persona_regions()}
REGION_SHORT = {r["id"]: r["short_name"] for r in persona_regions()}


def card(region_id: str, persona_id: str) -> dict:
    path = os.path.join(ROOT, "src/lib/worldview/personaCards", f"{region_id}.json")
    return json.load(open(path, encoding="utf-8"))[persona_id]


_CITATION = re.compile(r"\s*\[\d+(?:\s*,\s*\d+)*\]")


def clean(text: str) -> str:
    """Drop inline source-number markers like "[12, 29]" -- they point at a source list the
    evaluator is not shown, so they would only confuse."""
    return _CITATION.sub("", text).strip()


def reply_text(region_id: str, persona_id: str) -> tuple[str, str]:
    """(tl;dr, full reply as readable plain text) from the run's answer segments."""
    segs = [s for s in RUN["answer"] if s.get("regionId") == region_id and s.get("personaId") == persona_id]
    tldr = next((s["text"] for s in segs if s.get("kind") == "tldr"), "")
    recs = [s["text"] for s in segs if s.get("kind") == "recommendation"]
    body = [s["text"] for s in segs if s.get("kind") not in ("tldr", "recommendation")]
    parts = [tldr] if tldr else []
    parts += [f"{i}. {t}" for i, t in enumerate(recs, 1)]
    parts += body
    return clean(tldr), clean("\n\n".join(parts))


def main() -> None:
    rows, items = [], []
    for region_id in REGION_NAME:
        baseline = clean((RUN["personaSimilarity"].get(region_id) or {}).get("baselineReply", ""))
        for persona_id in ("male", "female"):
            c = card(region_id, persona_id)
            p = PERSONAS[(region_id, persona_id)]
            tldr, response = reply_text(region_id, persona_id)
            persona_prompt = build_persona_prompt(region_id, persona_id)
            item_id = f"{region_id}-{persona_id}"
            rows.append(
                {
                    "item_id": item_id,
                    "region_id": region_id,
                    "region_name": REGION_NAME[region_id],
                    "persona_gender": persona_id,
                    "persona_label": c["name"],
                    "persona_age": c["ageLabel"],
                    "persona_role": c["role"],
                    "persona_place": c["place"],
                    "persona_community": c["community"],
                    "persona_tagline": c["tagline"],
                    "persona_description": p["definition"],
                    "persona_version": persona_version(region_id, persona_id),
                    "query": RUN["query"],
                    "persona_prompt": persona_prompt,
                    "task_instructions": TASK_INSTRUCTIONS.format(region_name=REGION_NAME[region_id]),
                    "user_message": USER_MESSAGE_NOTE,
                    "response_tldr": tldr,
                    "response": response,
                    "baseline_response_no_persona": baseline,
                    "model_provider": RUN["provider"],
                    "reasoning_mode": RUN["mode"],
                    "run_id": RUN["id"],
                }
            )
            items.append(
                {
                    "itemId": item_id,
                    "regionId": region_id,
                    "regionName": REGION_SHORT[region_id],
                    "personaGender": persona_id,
                    "persona": {
                        "emoji": c["emoji"], "label": c["name"], "age": c["ageLabel"], "role": c["role"], "place": c["place"],
                        "community": c["community"], "tagline": c["tagline"], "description": p["definition"],
                    },
                    "personaVersion": persona_version(region_id, persona_id),
                    "query": RUN["query"],
                    "response": response,
                    "baseline": baseline,
                }
            )

    csv_path = os.path.join(ROOT, "docs/human-eval/persona_eval_items.csv")
    with open(csv_path, "w", newline="", encoding="utf-8-sig") as fh:  # BOM so Excel/Sheets read UTF-8
        w = csv.DictWriter(fh, fieldnames=list(rows[0]), quoting=csv.QUOTE_ALL)
        w.writeheader()
        w.writerows(rows)
    json_path = os.path.join(ROOT, "public/evaluate/items.json")
    json.dump({"query": RUN["query"], "runId": RUN["id"], "items": items}, open(json_path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    longest = max(len(r["persona_prompt"]) for r in rows)
    print(f"{len(rows)} rows -> {os.path.relpath(csv_path, ROOT)} ({os.path.getsize(csv_path) // 1024} KB)")
    print(f"{len(items)} items -> {os.path.relpath(json_path, ROOT)} ({os.path.getsize(json_path) // 1024} KB)")
    print(f"longest persona_prompt: {longest} characters (Google Sheets cell limit is 50,000)")


if __name__ == "__main__":
    main()
