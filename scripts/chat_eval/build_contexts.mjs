// Runs the REAL router (src/lib/worldview/knowledgeRouter.ts) over every eval question and writes
// scripts/chat_eval/contexts.json for run_eval.py. Needs Node >= 22.18 (runs .ts directly).
import { readFileSync, writeFileSync } from "node:fs";
import { routeContext } from "../../src/lib/worldview/knowledgeRouter.ts";

const here = new URL(".", import.meta.url);
const pack = JSON.parse(readFileSync(new URL("../../public/data/knowledge-pack.json", here), "utf8"));
const questions = JSON.parse(readFileSync(new URL("questions.json", here), "utf8"));

const out = questions.map((q) => {
  const r = routeContext(pack, [{ role: "user", content: q.question }], { focus: q.focus });
  return { id: q.id, context: r.context, sourceIds: r.sourceIds, included: r.included, tokenEstimate: r.tokenEstimate };
});
writeFileSync(new URL("contexts.json", here), JSON.stringify(out));
for (const o of out) console.log(`${o.id.padEnd(34)} ~${String(o.tokenEstimate).padStart(5)} tok  ${o.included.join(", ")}`);
console.log(`\n${out.length} contexts; largest ~${Math.max(...out.map((o) => o.tokenEstimate))} tokens (budget 12,000; Gemma window 32,768)`);
