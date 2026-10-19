/**
 * Client for the Worker's POST /chat route: streams the reply and checks it against what was sent.
 *
 * The page never talks to the model directly -- it sends `{context, messages}` to the Worker (see
 * proxy/src/chat.ts), which holds the passphrase check and the "answer only from the context" rules.
 */

import rules from "../../../proxy/src/chatRules.json";

/** Public URL of the Worker's /chat route (VITE_CHAT_URL). Null until the Worker is deployed. */
export const CHAT_URL: string | null =
  (((import.meta.env ?? {}) as Record<string, string | undefined>)["VITE_CHAT_URL"] ?? "").trim() ||
  null;

/** The exact sentence the model is told to reply with when a question is out of scope. */
export const REFUSAL: string = rules.refusal;

export type ChatErrorCode =
  | "unauthorized"
  | "rate_limited"
  | "too_large"
  | "bad_request"
  | "forbidden_origin"
  | "upstream_unavailable"
  | "offline"
  | "unknown";

export class ChatError extends Error {
  constructor(
    readonly code: ChatErrorCode,
    message: string,
    /** Seconds to wait, for `rate_limited`. */
    readonly retryAfter?: number,
  ) {
    super(message);
  }
}

export interface ChatTurn {
  role: "user" | "assistant";
  content: string;
}

export interface StreamOptions {
  url: string;
  passphrase: string;
  context: string;
  messages: ChatTurn[];
  signal?: AbortSignal;
  /** Called with each new piece of text. */
  onDelta: (text: string) => void;
}

/** Sends one question and streams the answer; resolves with the full text. Throws ChatError. */
export async function streamChat(opts: StreamOptions): Promise<string> {
  let res: Response;
  try {
    res = await fetch(opts.url, {
      method: "POST",
      headers: { "content-type": "application/json", authorization: `Bearer ${opts.passphrase}` },
      body: JSON.stringify({ context: opts.context, messages: opts.messages }),
      ...(opts.signal ? { signal: opts.signal } : {}),
    });
  } catch (err) {
    if (err instanceof DOMException && err.name === "AbortError") throw err;
    throw new ChatError("offline", "Can't reach the chat service.");
  }

  if (!res.ok) {
    let code: ChatErrorCode = "unknown";
    let message = `The chat service returned an error (${res.status}).`;
    try {
      const body = (await res.json()) as { error?: { code?: string; message?: string } };
      if (body.error?.code) code = body.error.code as ChatErrorCode;
      if (body.error?.message) message = body.error.message;
    } catch {
      /* non-JSON error body: keep the generic message */
    }
    const retry = Number(res.headers.get("retry-after"));
    throw new ChatError(code, message, Number.isFinite(retry) && retry > 0 ? retry : undefined);
  }
  if (!res.body) throw new ChatError("unknown", "The chat service sent an empty reply.");

  // Server-sent events: `data: {"choices":[{"delta":{"content":"…"}}]}` lines, ending with `data: [DONE]`.
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let full = "";
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let cut: number;
    while ((cut = buffer.indexOf("\n\n")) >= 0) {
      const event = buffer.slice(0, cut);
      buffer = buffer.slice(cut + 2);
      for (const line of event.split("\n")) {
        if (!line.startsWith("data:")) continue;
        const data = line.slice(5).trim();
        if (!data || data === "[DONE]") continue;
        try {
          const piece = (JSON.parse(data) as { choices?: { delta?: { content?: string } }[] })
            .choices?.[0]?.delta?.content;
          if (piece) {
            full += piece;
            opts.onDelta(piece);
          }
        } catch {
          /* ignore a malformed event */
        }
      }
    }
  }
  return full;
}

export interface AnswerChecks {
  /** Cited ids ("S29") that were not in the context sent -- the model made them up. */
  unknownIds: string[];
  /** Figures in the answer that appear nowhere in the context sent. */
  unseenNumbers: string[];
}

/** Compares an answer with the context it was given. Pure; used by the UI and the tests. */
export function checkAnswer(answer: string, sourceIds: string[], context: string): AnswerChecks {
  const cited = [...new Set([...answer.matchAll(/\[(S\d+)\]/g)].map((m) => m[1]!))];
  const unknownIds = cited.filter((id) => !sourceIds.includes(id));
  const seen = new Set(context.replaceAll(",", "").match(/\d[\d.]*\d|\d/g) ?? []);
  const body = answer.replace(/\[S\d+\]/g, " ");
  const unseenNumbers: string[] = [];
  for (const raw of body.match(/\d[\d,]*\.?\d*/g) ?? []) {
    const plain = raw.replaceAll(",", "").replace(/\.$/, "");
    const digits = plain.replace(".", "");
    if (digits.length < 3 && !plain.includes(".")) continue; // small counts are noise
    if (!seen.has(plain) && !unseenNumbers.includes(raw)) unseenNumbers.push(raw);
  }
  return { unknownIds, unseenNumbers };
}
