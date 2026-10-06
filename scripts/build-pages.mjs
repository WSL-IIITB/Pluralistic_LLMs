// Builds the static GitHub Pages site into dist/client.
//
//   npm run build:pages                       # served from /<repo>/ (PAGES_BASE defaults to it)
//   PAGES_BASE=/ npm run build:pages          # served from a domain root
//
// Needs public/data/ (python3 scripts/export_static_data.py) to be committed first.
import { execSync } from "node:child_process";
import { copyFileSync, existsSync, writeFileSync } from "node:fs";

const repo = process.env.GITHUB_REPOSITORY?.split("/")[1] ?? "india-worldview-explorer";
const base = process.env.PAGES_BASE ?? `/${repo}/`;

if (!existsSync("public/data/default-run.json")) {
  console.error("public/data/ is missing -- run: python3 scripts/export_static_data.py");
  process.exit(1);
}

execSync("npx vite build", {
  stdio: "inherit",
  env: { ...process.env, GITHUB_PAGES: "1", PAGES_BASE: base, VITE_STATIC_DATA: "1" },
});

// Single-page app: unknown paths fall back to the app, and Pages should not run Jekyll over it.
const out = "dist/client";
if (!existsSync(`${out}/index.html`)) {
  console.error(`${out}/index.html was not produced -- the prerender step failed`);
  process.exit(1);
}
copyFileSync(`${out}/index.html`, `${out}/404.html`);
writeFileSync(`${out}/.nojekyll`, "");
console.log(`static site ready in ${out} (base ${base})`);
