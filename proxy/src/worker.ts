/**
 * Authenticated reverse proxy in front of two internal, otherwise-unauthenticated
 * model endpoints (self-hosted Gemma, Claude via Azure AI Foundry). Real upstream
 * addresses and credentials live only as Worker secrets (never in this source, never
 * in the repo) -- callers authenticate with one shared passphrase instead, which can
 * be rotated here at any time to revoke everyone's access at once. See ../README.md
 * for setup and rotation.
 */

export interface Env {
  SHARED_PASSPHRASE: string;
  GEMMA_UPSTREAM_URL: string;
  AZURE_ANTHROPIC_UPSTREAM_URL: string;
  AZURE_ANTHROPIC_API_KEY: string;
}

// Headers that must not be forwarded verbatim between hops (either they
// describe the wrong hop's connection, or forwarding a stale one -- notably
// content-length after we rewrite auth headers of a different byte length --
// would corrupt the request).
const HOP_BY_HOP = new Set([
  "connection",
  "keep-alive",
  "proxy-authenticate",
  "proxy-authorization",
  "te",
  "trailer",
  "transfer-encoding",
  "upgrade",
  "host",
  "content-length",
]);

function filteredHeaders(src: Headers): Headers {
  const out = new Headers();
  for (const [key, value] of src.entries()) {
    if (!HOP_BY_HOP.has(key.toLowerCase())) out.set(key, value);
  }
  return out;
}

function unauthorized(): Response {
  return new Response(JSON.stringify({ error: "Invalid or missing passphrase." }), {
    status: 401,
    headers: { "content-type": "application/json" },
  });
}

async function forward(request: Request, upstreamUrl: string, headers: Headers): Promise<Response> {
  const upstream = await fetch(upstreamUrl, {
    method: request.method,
    headers,
    // A GET/HEAD request has no body; passing null keeps fetch happy either way.
    body: request.method === "GET" || request.method === "HEAD" ? null : request.body,
    // Required by the Workers runtime whenever the request body is a stream.
    duplex: "half",
  } as RequestInit);
  return new Response(upstream.body, {
    status: upstream.status,
    statusText: upstream.statusText,
    headers: filteredHeaders(upstream.headers),
  });
}

/** Gemma path: OpenAI-compatible client sends its key as `Authorization: Bearer <key>`. */
async function proxyGemma(request: Request, env: Env, suffix: string): Promise<Response> {
  const authHeader = request.headers.get("authorization") ?? "";
  const provided = authHeader.replace(/^Bearer\s+/i, "").trim();
  if (!env.SHARED_PASSPHRASE || provided !== env.SHARED_PASSPHRASE) {
    console.log("gemma proxy: rejected request with invalid passphrase");
    return unauthorized();
  }
  if (!env.GEMMA_UPSTREAM_URL) {
    return new Response(JSON.stringify({ error: "Proxy misconfigured: GEMMA_UPSTREAM_URL not set." }), {
      status: 502,
      headers: { "content-type": "application/json" },
    });
  }
  const headers = filteredHeaders(request.headers);
  headers.set("authorization", "Bearer not-needed"); // real server takes no auth at all
  const upstreamUrl = env.GEMMA_UPSTREAM_URL.replace(/\/$/, "") + suffix;
  return forward(request, upstreamUrl, headers);
}

/** Claude (Azure AI Foundry) path: Anthropic's Foundry client sends its key as
 * BOTH `x-api-key` and `api-key` -- check either, since either could be set. */
async function proxyClaude(request: Request, env: Env, suffix: string): Promise<Response> {
  const provided = request.headers.get("x-api-key") ?? request.headers.get("api-key") ?? "";
  if (!env.SHARED_PASSPHRASE || provided !== env.SHARED_PASSPHRASE) {
    console.log("claude proxy: rejected request with invalid passphrase");
    return unauthorized();
  }
  if (!env.AZURE_ANTHROPIC_UPSTREAM_URL || !env.AZURE_ANTHROPIC_API_KEY) {
    return new Response(
      JSON.stringify({ error: "Proxy misconfigured: AZURE_ANTHROPIC_UPSTREAM_URL/API_KEY not set." }),
      { status: 502, headers: { "content-type": "application/json" } },
    );
  }
  const headers = filteredHeaders(request.headers);
  headers.set("x-api-key", env.AZURE_ANTHROPIC_API_KEY);
  headers.set("api-key", env.AZURE_ANTHROPIC_API_KEY);
  const upstreamUrl = env.AZURE_ANTHROPIC_UPSTREAM_URL.replace(/\/$/, "") + suffix;
  return forward(request, upstreamUrl, headers);
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    // Unauthenticated on purpose -- reveals nothing, just confirms the proxy itself is up.
    if (url.pathname === "/" || url.pathname === "/health") {
      return new Response("ok", { status: 200 });
    }
    if (url.pathname.startsWith("/gemma")) {
      return proxyGemma(request, env, url.pathname.slice("/gemma".length) + url.search);
    }
    if (url.pathname.startsWith("/claude")) {
      return proxyClaude(request, env, url.pathname.slice("/claude".length) + url.search);
    }
    return new Response("Not found", { status: 404 });
  },
};
