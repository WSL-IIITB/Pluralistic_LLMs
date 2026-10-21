/**
 * POST /chat -- the only route a browser may call.
 *
 * The dashboard (a static GitHub Pages site) sends `{context, messages}`: `context` is the slice of the
 * hardcoded knowledge pack relevant to the question, `messages` the conversation so far. This Worker:
 *   1. allows only the configured origins (CORS + a server-side check),
 *   2. rate-limits per IP (before auth, so guessing the passphrase is throttled too),
 *   3. checks the team passphrase in constant time,
 *   4. validates and caps the request (size, turns, lengths) and drops every other field,
 *   5. prepends the server-held rules ("answer only from the context, cite, refuse otherwise") --
 *      the browser never supplies or can alter them,
 *   6. streams Gemma's reply back unchanged (OpenAI-style SSE).
 * Secrets (CHAT_PASSPHRASE, GEMMA_UPSTREAM_URL) exist only as Worker secrets.
 */

import rules from "./chatRules.json";

export interface RateLimiter {
  limit(options: { key: string }): Promise<{ success: boolean }>;
}

export interface ChatEnv {
  CHAT_PASSPHRASE?: string;
  GEMMA_UPSTREAM_URL?: string;
  GEMMA_MODEL?: string;
  /** Optional bearer token for the model server (Worker secret). */
  GEMMA_API_KEY?: string;
  /** Comma-separated exact origins (scheme + host [+ port], no path), e.g. https://org.github.io */
  ALLOWED_ORIGINS?: string;
  CHAT_LIMITER?: RateLimiter;
}

const MAX_BODY_BYTES = 120_000;
const MAX_CONTEXT_CHARS = 80_000;
const MAX_TURNS = 6;
const MAX_USER_CHARS = 1_000;
const MAX_ASSISTANT_CHARS = 4_000;
const MAX_OUTPUT_TOKENS = 700;
const UPSTREAM_FIRST_BYTE_MS = 60_000;
const DEFAULT_MODEL = "Firworks/gemma-4-26B-A4B-it-fp8";

const SYSTEM_PROMPT = rules.system.replace("{{REFUSAL}}", `"${rules.refusal}"`);

function allowedOrigins(env: ChatEnv): string[] {
  return (env.ALLOWED_ORIGINS ?? "")
    .split(",")
    .map((o) => o.trim().replace(/\/$/, ""))
    .filter(Boolean);
}

/** The request's Origin if it is on the allow-list, else null (null also when there is no Origin header). */
function matchedOrigin(request: Request, env: ChatEnv): string | null {
  const origin = request.headers.get("origin");
  return origin && allowedOrigins(env).includes(origin) ? origin : null;
}

function corsHeaders(origin: string | null): Headers {
  const h = new Headers({ vary: "Origin" });
  if (origin) {
    h.set("access-control-allow-origin", origin);
    h.set("access-control-allow-methods", "POST, OPTIONS");
    h.set("access-control-allow-headers", "authorization, content-type");
    h.set("access-control-max-age", "86400");
  }
  return h;
}

function fail(status: number, code: string, message: string, origin: string | null, extra?: Record<string, string>): Response {
  const headers = corsHeaders(origin);
  headers.set("content-type", "application/json");
  headers.set("cache-control", "no-store");
  for (const [k, v] of Object.entries(extra ?? {})) headers.set(k, v);
  return new Response(JSON.stringify({ error: { code, message } }), { status, headers });
}

/** Constant-time string comparison: hash both sides to equal length, then timingSafeEqual. */
export async function safeEqual(a: string, b: string): Promise<boolean> {
  const enc = new TextEncoder();
  const [ha, hb] = await Promise.all([
    crypto.subtle.digest("SHA-256", enc.encode(a)),
    crypto.subtle.digest("SHA-256", enc.encode(b)),
  ]);
  return (crypto.subtle as unknown as { timingSafeEqual(x: ArrayBuffer, y: ArrayBuffer): boolean }).timingSafeEqual(ha, hb);
}

interface Turn {
  role: "user" | "assistant";
  content: string;
}

/** Returns the validated request, or a message describing what is wrong. Unknown fields are dropped. */
function validate(body: unknown): { context: string; messages: Turn[] } | string {
  if (!body || typeof body !== "object") return "Body must be a JSON object.";
  const { context, messages } = body as { context?: unknown; messages?: unknown };
  if (typeof context !== "string" || !context.trim()) return "`context` must be a non-empty string.";
  if (context.length > MAX_CONTEXT_CHARS) return `\`context\` is longer than ${MAX_CONTEXT_CHARS} characters.`;
  if (!Array.isArray(messages) || messages.length === 0) return "`messages` must be a non-empty array.";
  if (messages.length > MAX_TURNS) return `At most ${MAX_TURNS} messages are accepted.`;
  const clean: Turn[] = [];
  for (const m of messages) {
    if (!m || typeof m !== "object") return "Each message must be an object.";
    const { role, content } = m as { role?: unknown; content?: unknown };
    if (role !== "user" && role !== "assistant") return "Message role must be 'user' or 'assistant'.";
    if (typeof content !== "string" || !content.trim()) return "Message content must be a non-empty string.";
    const cap = role === "user" ? MAX_USER_CHARS : MAX_ASSISTANT_CHARS;
    if (content.length > cap) return `A ${role} message is longer than ${cap} characters.`;
    clean.push({ role, content });
  }
  if (clean[clean.length - 1]!.role !== "user") return "The last message must be from the user.";
  return { context, messages: clean };
}

export async function handleChat(request: Request, env: ChatEnv): Promise<Response> {
  const origin = matchedOrigin(request, env);
  const hasOrigin = request.headers.get("origin") !== null;

  if (request.method === "OPTIONS") {
    // Preflight carries no credentials; answer it before auth. Without a matching origin the browser
    // simply gets no CORS headers and blocks the real request.
    return new Response(null, { status: 204, headers: corsHeaders(origin) });
  }
  if (request.method !== "POST") return fail(405, "method_not_allowed", "Use POST.", origin, { allow: "POST, OPTIONS" });
  if (hasOrigin && !origin) return fail(403, "forbidden_origin", "This origin is not allowed.", null);

  // Throttle first, per IP, so passphrase guessing is limited as much as normal use.
  if (!env.CHAT_LIMITER) console.log("chat: no rate limiter bound -- requests are NOT being throttled");
  if (env.CHAT_LIMITER) {
    const ip = request.headers.get("cf-connecting-ip") ?? "unknown";
    const { success } = await env.CHAT_LIMITER.limit({ key: `chat:${ip}` });
    console.log(`chat: rate limiter ${success ? "allowed" : "blocked"} a request (key ${ip === "unknown" ? "unknown" : "ip"})`);
    if (!success) return fail(429, "rate_limited", "Too many requests. Try again in a minute.", origin, { "retry-after": "60" });
  }

  const provided = (request.headers.get("authorization") ?? "").replace(/^Bearer\s+/i, "").trim();
  if (!env.CHAT_PASSPHRASE || !provided || !(await safeEqual(provided, env.CHAT_PASSPHRASE))) {
    console.log("chat: rejected request with invalid passphrase");
    return fail(401, "unauthorized", "Invalid or missing passphrase.", origin);
  }
  if (!env.GEMMA_UPSTREAM_URL) return fail(502, "upstream_unavailable", "The chat service is not configured.", origin);

  const declared = Number(request.headers.get("content-length") ?? "0");
  if (declared > MAX_BODY_BYTES) return fail(413, "too_large", "Request is too large.", origin);
  const raw = await request.text();
  if (raw.length > MAX_BODY_BYTES) return fail(413, "too_large", "Request is too large.", origin);
  let parsed: unknown;
  try {
    parsed = JSON.parse(raw);
  } catch {
    return fail(400, "bad_request", "Body is not valid JSON.", origin);
  }
  const checked = validate(parsed);
  if (typeof checked === "string") return fail(400, "bad_request", checked, origin);

  // Keep the client-supplied context from closing the delimiter the rules rely on.
  const context = checked.context.replaceAll("</CONTEXT>", "</ CONTEXT>").replaceAll("<CONTEXT>", "< CONTEXT>");
  const upstreamBody = {
    model: env.GEMMA_MODEL || DEFAULT_MODEL,
    temperature: 0,
    max_tokens: MAX_OUTPUT_TOKENS,
    stream: true,
    messages: [{ role: "system", content: `${SYSTEM_PROMPT}\n\n<CONTEXT>\n${context}\n</CONTEXT>` }, ...checked.messages],
  };

  const abort = new AbortController();
  const timer = setTimeout(() => abort.abort(), UPSTREAM_FIRST_BYTE_MS);
  let upstream: Response;
  try {
    upstream = await fetch(`${env.GEMMA_UPSTREAM_URL.replace(/\/$/, "")}/v1/chat/completions`, {
      method: "POST",
      headers: { "content-type": "application/json", authorization: `Bearer ${env.GEMMA_API_KEY || "not-needed"}` },
      body: JSON.stringify(upstreamBody),
      signal: abort.signal,
    });
  } catch (err) {
    const timedOut = err instanceof Error && err.name === "AbortError";
    console.log(`chat: upstream ${timedOut ? "timeout" : "error"}`);
    return fail(timedOut ? 504 : 502, "upstream_unavailable", "The model did not respond. Please try again.", origin);
  } finally {
    clearTimeout(timer); // only the wait for the first byte is bounded; the stream itself is not cut
  }
  if (!upstream.ok) {
    const detail = (await upstream.text().catch(() => "")).slice(0, 400);
    console.log(`chat: upstream status ${upstream.status} server=${upstream.headers.get("server") ?? "?"} type=${upstream.headers.get("content-type") ?? "?"} body=${detail.slice(0, 160).replace(/\s+/g, " ")}`);
    if (upstream.status === 400 && /context length|maximum context/i.test(detail))
      return fail(413, "too_large", "That question needed too much context. Try a narrower question.", origin);
    return fail(502, "upstream_unavailable", "The model is unavailable right now.", origin);
  }

  const headers = corsHeaders(origin);
  headers.set("content-type", "text/event-stream; charset=utf-8");
  headers.set("cache-control", "no-store");
  headers.set("x-accel-buffering", "no");
  return new Response(upstream.body, { status: 200, headers });
}
