# Model proxy

Authenticated reverse proxy in front of the two internal model endpoints (self-hosted
Gemma, Claude via Azure AI Foundry) this project can use. It exists so the **real**
addresses and credentials never appear in the `india-worldview-explorer` repo or reach
anyone who clones it — instead, everyone else goes through this proxy with one shared
passphrase that you control and can rotate at any time.

Runs on Cloudflare Workers (free tier is enough for this).

## One-time setup

```bash
cd proxy
npm install
npx wrangler login          # opens a browser tab — log in with/create a Cloudflare account
```

Set the four secrets (each prompts for a value — paste it and press enter; nothing is
echoed, and nothing here ever touches this repo):

```bash
npx wrangler secret put SHARED_PASSPHRASE
npx wrangler secret put GEMMA_UPSTREAM_URL
npx wrangler secret put AZURE_ANTHROPIC_UPSTREAM_URL
npx wrangler secret put AZURE_ANTHROPIC_API_KEY
```

- `SHARED_PASSPHRASE` — make up any long random string. This is the only thing lab
  members ever see.
- `GEMMA_UPSTREAM_URL` — the real Gemma server, e.g. `http://<ip>:<port>` (no trailing
  slash, no `/v1`).
- `AZURE_ANTHROPIC_UPSTREAM_URL` — the real value of `AZURE_ANTHROPIC_ENDPOINT` from
  your own `backend/.env`.
- `AZURE_ANTHROPIC_API_KEY` — the real value of `AZURE_ANTHROPIC_API_KEY` from your own
  `backend/.env`.

Deploy:

```bash
npm run deploy
```

This prints the Worker's URL, something like `https://worldview-model-proxy.<your-subdomain>.workers.dev`.

## What to give lab members

Just two things, however you'd normally share something like this with the lab (Slack
DM, verbally, etc.) — never commit these anywhere:

1. The Worker URL from `npm run deploy`.
2. The `SHARED_PASSPHRASE` value.

They put this in their own local `backend/.env` (already git-ignored):

```bash
REMOTE_GEMMA_BASE_URL=https://<your-worker-url>/gemma
REMOTE_GEMMA_API_KEY=<the shared passphrase>

AZURE_ANTHROPIC_ENDPOINT=https://<your-worker-url>/claude
AZURE_ANTHROPIC_API_KEY=<the shared passphrase>
AZURE_ANTHROPIC_DEPLOYMENT=claude-sonnet-4-5
```

That's it — their local backend never sees the real IP, the real Azure endpoint, or the
real Azure key. The proxy checks the passphrase and attaches the real credentials
server-side before forwarding.

## Rotating / revoking access

One shared passphrase for everyone means rotating it revokes it for everyone at once —
simplest thing that matches "I want to be able to cut this off anytime." To rotate
(you can also just ask for this in a future chat and it'll be run for you):

```bash
cd proxy
npx wrangler secret put SHARED_PASSPHRASE   # enter a new value
npm run deploy
```

Then share only the new value with whoever should still have access.

If the real upstream ever moves (like the Gemma server did on 2026-09-03), update it the
same way:

```bash
npx wrangler secret put GEMMA_UPSTREAM_URL
npm run deploy
```

## Checking for abuse

```bash
npm run tail
```

Streams live logs, including a line for every request rejected with a bad passphrase —
useful if you suspect the shared value leaked and want to confirm before rotating it.

## Troubleshooting: "Found both a user configuration file... and a deploy configuration file"

Building the *frontend* (`npm run build` at the repo root) generates its own
`../.wrangler/deploy/config.json` for its unrelated Cloudflare Pages/Workers deploy
target, which can confuse `wrangler deploy` run from here. `npm run deploy` and `npm run
dev` already pass `--config ./wrangler.toml` to avoid this; if you run `wrangler`
directly and hit this error, add that same flag (or delete the stray `../.wrangler/`
directory — it's just a build cache, safe to remove).

---

## The browser chat route: `POST /chat`

The dashboard's **Ask** tab (a static GitHub Pages site) talks to this Worker, which is the only route a browser
may call. It adds what a static page cannot do for itself: keep a passphrase secret, hold the "answer only from the
research" rules, and reach the model without exposing its address.

What it does, in order (see `src/chat.ts`):

1. **Origin allow-list + CORS** — only the origins in `ALLOWED_ORIGINS` (`wrangler.toml`) may call it from a browser.
   `/gemma` and `/claude` stay CORS-less on purpose: they are for the backend only.
2. **Per-IP rate limit** (Workers Rate Limiting binding `CHAT_LIMITER`, 10 requests/minute) — applied *before* the
   passphrase check, so guessing the passphrase is throttled as much as normal use. Use a long passphrase (16+ characters).
3. **Team passphrase** (`CHAT_PASSPHRASE`, compared in constant time). The user types it into the dashboard; it is kept
   in `sessionStorage` only and never appears in the page source or the bundle.
4. **Validation** — body ≤ 120 KB, ≤ 6 messages, user messages ≤ 1,000 characters, context ≤ 80,000 characters; every
   other field the client sends (model, system prompt, max_tokens, tools…) is dropped.
5. **Server-held rules** (`src/chatRules.json`) are prepended: answer only from the supplied context, cite `[S#]` ids,
   respect scope tags, refuse otherwise. The browser can't change them.
6. **Streams** Gemma's reply straight back (`text/event-stream`).

Errors are `{"error":{"code","message"}}`: 401 `unauthorized`, 400 `bad_request`, 403 `forbidden_origin`, 413 `too_large`,
429 `rate_limited` (+ `Retry-After`), 502/504 `upstream_unavailable`.

### One-time setup for the chat (about 10 minutes, in this folder)

```sh
npx wrangler login                        # skip if you already did this for the model proxy
npx wrangler secret put CHAT_PASSPHRASE   # the TEAM passphrase people type into the dashboard
npx wrangler secret put GEMMA_UPSTREAM_URL
npx wrangler secret put SHARED_PASSPHRASE # only if the backend uses /gemma or /claude through this Worker
npm run deploy                            # prints https://worldview-model-proxy.<you>.workers.dev
```

Then tell the dashboard where the Worker is — the URL is public, not a secret:

```sh
gh variable set CHAT_URL --body "https://worldview-model-proxy.<you>.workers.dev/chat"   # used by the Pages workflow
# local dev: put VITE_CHAT_URL=http://localhost:8787/chat in the repo's .env.local
```

Check it: no passphrase → 401; `curl -X OPTIONS -H "Origin: https://evil.example" …` returns no
`access-control-allow-origin`; 11 quick requests → 429. **Rotate** the team passphrase with
`npx wrangler secret put CHAT_PASSPHRASE` again — everyone must re-enter it. If the rate-limit binding is not
available on your Cloudflare plan, `wrangler deploy` will say so; remove the `[[ratelimits]]` block (the route then
runs without throttling) or move to a Durable Object limiter.

Add a new site's origin to `ALLOWED_ORIGINS` in `wrangler.toml` and redeploy before using the chat from it.
