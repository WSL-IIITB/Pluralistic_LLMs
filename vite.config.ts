// @lovable.dev/vite-tanstack-config already includes the following — do NOT add them manually
// or the app will break with duplicate plugins:
//   - TanStack devtools (dev-only, first), tanstackStart, viteReact, tailwindcss, tsConfigPaths,
//     nitro (build-only using cloudflare as a default target), VITE_* env injection, @ path alias,
//     React/TanStack dedupe, error logger plugins, and sandbox detection (port/host/strictPort).
// You can pass additional config via defineConfig({ vite: { ... }, etc... }) if needed.
import { defineConfig } from "@lovable.dev/vite-tanstack-config";

// GitHub Pages build (`npm run build:pages`, run by .github/workflows/pages.yml): a purely static
// single-page site with the data baked into public/data/. No server runtime, so nitro is off, and
// the site is served from /<repo>/ so asset URLs need that base. Every other build is unchanged.
const pages = process.env["GITHUB_PAGES"] === "1";

export default defineConfig(
  pages
    ? {
        nitro: false,
        vite: { base: process.env["PAGES_BASE"] ?? "/" },
        tanstackStart: {
          server: { entry: "server" },
          spa: { enabled: true, prerender: { outputPath: "/index.html", crawlLinks: false } },
        },
      }
    : {
        tanstackStart: {
          // Redirect TanStack Start's bundled server entry to src/server.ts (our SSR error wrapper).
          // nitro/vite builds from this
          server: { entry: "server" },
        },
      },
);
