/** Conversation state for the Ask tab. Lives outside the component so it survives tab switches. */

import { create } from "zustand";

import {
  CHAT_URL,
  ChatError,
  REFUSAL,
  checkAnswer,
  streamChat,
  type AnswerChecks,
  type ChatTurn,
} from "./chat";
import type { KnowledgePack } from "./knowledgePack";
import { routeContext } from "./knowledgeRouter";

const PASS_KEY = "wv.chat.passphrase";
const MAX_HISTORY = 5; // earlier turns sent along with the new question (the Worker allows 6 in total)

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  status: "streaming" | "done" | "error" | "stopped";
  /** Source ids that were in the context for this answer. */
  sourceIds: string[];
  checks?: AnswerChecks;
  /** True when the model gave the fixed "not covered by this research" reply. */
  refused?: boolean;
  error?: string;
}

export type ChatNotice =
  | { kind: "locked"; message: string }
  | { kind: "rate_limited"; message: string; retryAt: number }
  | { kind: "offline" | "down" | "too_large" | "error"; message: string };

interface ChatStore {
  messages: ChatMessage[];
  busy: boolean;
  passphrase: string | null;
  notice: ChatNotice | null;
  lastQuestion: string | null;
  setPassphrase(p: string): void;
  lock(): void;
  clear(): void;
  stop(): void;
  send(
    question: string,
    pack: KnowledgePack,
    focus: { districtId?: string | null; regionId?: string | null },
  ): Promise<void>;
}

function readPass(): string | null {
  try {
    return window.sessionStorage.getItem(PASS_KEY);
  } catch {
    return null;
  }
}
function writePass(p: string | null) {
  try {
    if (p) window.sessionStorage.setItem(PASS_KEY, p);
    else window.sessionStorage.removeItem(PASS_KEY);
  } catch {
    /* storage unavailable: the passphrase just won't survive a reload */
  }
}

let controller: AbortController | null = null;
let counter = 0;
const nextId = () => `m${Date.now().toString(36)}${(counter++).toString(36)}`;

export const useChatStore = create<ChatStore>((set, get) => ({
  messages: [],
  busy: false,
  passphrase: typeof window === "undefined" ? null : readPass(),
  notice: null,
  lastQuestion: null,

  setPassphrase: (p) => {
    const clean = p.trim();
    writePass(clean || null);
    set({ passphrase: clean || null, notice: null });
  },
  lock: () => {
    writePass(null);
    set({ passphrase: null });
  },
  clear: () => {
    controller?.abort();
    set({ messages: [], busy: false, notice: null, lastQuestion: null });
  },
  stop: () => controller?.abort(),

  send: async (question, pack, focus) => {
    const q = question.trim();
    const { busy, passphrase, messages } = get();
    if (!q || busy || !CHAT_URL) return;
    if (!passphrase) {
      set({ notice: { kind: "locked", message: "Enter the team passphrase to ask a question." } });
      return;
    }

    // Earlier finished turns + this question. The router looks at the last two user turns.
    const history: ChatTurn[] = messages
      .filter((m) => m.status === "done" && m.content.trim())
      .slice(-MAX_HISTORY)
      .map((m) => ({ role: m.role, content: m.content }));
    const turns: ChatTurn[] = [...history, { role: "user", content: q }];
    const routed = routeContext(pack, turns, { focus });

    const user: ChatMessage = {
      id: nextId(),
      role: "user",
      content: q,
      status: "done",
      sourceIds: [],
    };
    const reply: ChatMessage = {
      id: nextId(),
      role: "assistant",
      content: "",
      status: "streaming",
      sourceIds: routed.sourceIds,
    };
    set({ messages: [...messages, user, reply], busy: true, notice: null, lastQuestion: q });

    const patch = (p: Partial<ChatMessage>) =>
      set((s) => ({ messages: s.messages.map((m) => (m.id === reply.id ? { ...m, ...p } : m)) }));

    controller = new AbortController();
    try {
      const text = await streamChat({
        url: CHAT_URL,
        passphrase,
        context: routed.context,
        messages: turns,
        signal: controller.signal,
        onDelta: (piece) =>
          set((s) => ({
            messages: s.messages.map((m) =>
              m.id === reply.id ? { ...m, content: m.content + piece } : m,
            ),
          })),
      });
      const refused = text.trim().replace(/^"|"$/g, "") === REFUSAL;
      patch({
        status: "done",
        content: text.trim(),
        refused,
        checks: refused
          ? { unknownIds: [], unseenNumbers: [] }
          : checkAnswer(text, routed.sourceIds, routed.context),
      });
    } catch (err) {
      if (err instanceof DOMException && err.name === "AbortError") {
        patch({ status: "stopped" });
      } else if (err instanceof ChatError) {
        patch({ status: "error", error: err.message });
        if (err.code === "unauthorized") {
          writePass(null);
          set({
            passphrase: null,
            notice: {
              kind: "locked",
              message: "That passphrase wasn't accepted. Please try again.",
            },
          });
        } else if (err.code === "rate_limited") {
          set({
            notice: {
              kind: "rate_limited",
              message: "Too many questions — please wait a moment.",
              retryAt: Date.now() + (err.retryAfter ?? 60) * 1000,
            },
          });
        } else if (err.code === "offline") {
          set({
            notice: {
              kind: "offline",
              message: "Can't reach the chat service. Check your connection and try again.",
            },
          });
        } else if (err.code === "too_large") {
          set({ notice: { kind: "too_large", message: err.message } });
        } else if (err.code === "upstream_unavailable") {
          set({
            notice: {
              kind: "down",
              message: "The model is unavailable right now. Please try again shortly.",
            },
          });
        } else {
          set({ notice: { kind: "error", message: err.message } });
        }
      } else {
        patch({ status: "error", error: "Something went wrong." });
        set({ notice: { kind: "error", message: "Something went wrong. Please try again." } });
      }
    } finally {
      controller = null;
      set({ busy: false });
    }
  },
}));
