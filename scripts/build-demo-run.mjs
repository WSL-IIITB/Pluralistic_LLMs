// Builds src/lib/worldview/stream/demoRun.json (the offline demo's replay)
// from a raw SSE capture of a real run, e.g.:
//   curl -sN "http://localhost:8001/api/worldview/stream?q=high%20school%20dropouts&mode=medium" > run.sse
//   node scripts/build-demo-run.mjs run.sse
import { readFileSync, writeFileSync } from "node:fs";

const [, , input] = process.argv;
if (!input) {
  console.error("usage: node scripts/build-demo-run.mjs <capture.sse>");
  process.exit(1);
}

const events = readFileSync(input, "utf8")
  .split("\n")
  .filter((line) => line.startsWith("data:"))
  .map((line) => JSON.parse(line.slice(5)))
  .map(({ queryRunId: _id, t: _t, ...rest }) => rest);

const started = events.find((e) => e.type === "query_started");
if (!started || events.at(-1)?.type !== "done") {
  console.error("capture must contain a query_started event and end with done");
  process.exit(1);
}

const out = new URL("../src/lib/worldview/stream/demoRun.json", import.meta.url);
writeFileSync(out, JSON.stringify({ query: started.query, events }));
console.log(`wrote ${events.length} events for “${started.query}”`);
