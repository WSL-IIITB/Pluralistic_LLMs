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
