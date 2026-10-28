/**
 * The Ask tab: a chat that answers questions about the study using ONLY the dashboard's own
 * hardcoded research (the knowledge pack). Answers stream from the Worker; every cited source is a
 * chip you can open, every district or region name is a chip that moves the map, and anything the
 * model cites or states that is not in the text it was given is flagged rather than trusted.
 */

import { Lock, RotateCcw, Send, Square, Trash2 } from "lucide-react";
import { Fragment, useEffect, useMemo, useRef, useState, type ReactNode } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useExplorerStore } from "@/lib/worldview";
import { CHAT_URL } from "@/lib/worldview/chat";
import { useChatStore, type ChatMessage } from "@/lib/worldview/chatStore";
import { loadKnowledgePack, type KnowledgePack } from "@/lib/worldview/knowledgePack";

const SUGGESTIONS = [
  "What are the main reasons students leave school across Karnataka?",
  "Which region has the highest average dropout rate?",
  "What does the research say about Kalaburagi?",
  "Where is the evidence thinnest?",
  "What did the UIDAI/NITI check find?",
  "How do the personas' answers differ from a generic answer?",
];

const escapeRe = (s: string) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

/** Turns `[S12]`, **bold**, and district/region names in an answer into chips and emphasis. */
function useRenderer(pack: KnowledgePack | null) {
  const focusDistrict = useExplorerStore((s) => s.focusDistrict);
  const focusRegion = useExplorerStore((s) => s.focusRegion);

  return useMemo(() => {
    const sources = new Map((pack?.sources ?? []).map((s) => [s.id, s]));
    const entities = new Map<
      string,
      { kind: "district" | "region"; id: string; regionId: string }
    >();
    for (const d of pack?.index.districts ?? [])
      for (const a of [d.name.toLowerCase(), ...d.aliases])
        if (!entities.has(a)) entities.set(a, { kind: "district", id: d.id, regionId: d.regionId });
    for (const r of pack?.index.regions ?? [])
      for (const a of r.aliases)
        if (!entities.has(a)) entities.set(a, { kind: "region", id: r.id, regionId: r.id });
    // An alias shared by several districts (e.g. plain "Bengaluru" -> Urban or Rural) is ambiguous, and in prose
    // usually means the city or a destination, so it is left as text rather than linked to one of them.
    const owners = new Map<string, Set<string>>();
    for (const d of pack?.index.districts ?? [])
      for (const a of [d.name.toLowerCase(), ...d.aliases])
        (owners.get(a) ?? owners.set(a, new Set()).get(a)!).add(d.id);
    const names = [...entities.keys()]
      .filter((n) => (owners.get(n)?.size ?? 0) <= 1)
      .sort((a, b) => b.length - a.length);
    const re = new RegExp(
      `\\[(S\\d+)\\]|\\*\\*(.+?)\\*\\*|(?<![A-Za-z])(${names.map(escapeRe).join("|") || "$^"})(?![A-Za-z])`,
      "gi",
    );

    function inline(text: string, known: string[], key: string): ReactNode[] {
      const out: ReactNode[] = [];
      let last = 0;
      let n = 0;
      for (const m of text.matchAll(re)) {
        const at = m.index ?? 0;
        if (at > last) out.push(text.slice(last, at));
        const k = `${key}-${n++}`;
        if (m[1]) {
          const id = m[1];
          const src = sources.get(id);
          const ok = known.includes(id) && !!src;
          out.push(
            ok ? (
              <a
                key={k}
                href={src!.url}
                target="_blank"
                rel="noopener noreferrer"
                title={`${src!.title} — ${src!.outlet}${src!.date ? `, ${src!.date}` : ""}`}
                className="mx-0.5 inline-block rounded bg-secondary px-1.5 align-baseline text-[10px] leading-4 tabular-nums text-muted-foreground no-underline transition-colors hover:text-foreground"
              >
                {id.slice(1)}
              </a>
            ) : (
              <span
                key={k}
                title="This source was not among the sources the model was given — treat the claim as unverified."
                className="mx-0.5 inline-block rounded bg-red-500/20 px-1.5 align-baseline text-[10px] leading-4 text-red-700 dark:text-red-300"
              >
                ?
              </span>
            ),
          );
        } else if (m[2]) {
          out.push(<b key={k}>{inline(m[2], known, k)}</b>);
        } else if (m[3]) {
          const e = entities.get(m[3].toLowerCase());
          out.push(
            e ? (
              <button
                key={k}
                type="button"
                onClick={() =>
                  e.kind === "district" ? focusDistrict(e.id, e.regionId) : focusRegion(e.id)
                }
                title="Show on the map"
                className="font-medium text-primary underline decoration-dotted underline-offset-2 hover:decoration-solid"
              >
                {m[0]}
              </button>
            ) : (
              m[0]
            ),
          );
        }
        last = at + m[0].length;
      }
      if (last < text.length) out.push(text.slice(last));
      return out;
    }

    return function render(rawText: string, known: string[]): ReactNode {
      // The default scope tag, and any section name the model wrongly wrote as a "citation", are noise.
      const text = rawText
        .replace(/\s*\((?:DISTRICT|GENERAL)\)/g, "")
        .replace(
          /\s*\[(?:DIGEST|CAVEATS|UIDAI|ANALYSIS|PERSONAS|REGION|DISTRICT|SYNTHESIS|GENERAL|STATEWIDE|REGIONAL|PERSONA|SOURCES)[^\]]*\]/g,
          "",
        );
      const blocks: ReactNode[] = [];
      let list: string[] = [];
      const flush = () => {
        if (!list.length) return;
        const items = list;
        list = [];
        blocks.push(
          <ul key={`ul${blocks.length}`} className="my-1.5 list-disc space-y-1 pl-5">
            {items.map((it, i) => (
              <li key={i}>{inline(it, known, `li${blocks.length}-${i}`)}</li>
            ))}
          </ul>,
        );
      };
      text.split("\n").forEach((line, i) => {
        const bullet = line.match(/^\s*[-•*]\s+(.*)$/);
        if (bullet) {
          list.push(bullet[1]!);
        } else {
          flush();
          if (line.trim())
            blocks.push(
              <p key={`p${i}`} className="my-1.5">
                {inline(line, known, `p${i}`)}
              </p>,
            );
        }
      });
      flush();
      return <Fragment>{blocks}</Fragment>;
    };
  }, [pack, focusDistrict, focusRegion]);
}

function Bubble({ m, render }: { m: ChatMessage; render: (t: string, k: string[]) => ReactNode }) {
  if (m.role === "user") {
    return (
      <div className="flex justify-end">
        <p className="max-w-[85%] rounded-2xl rounded-br-md bg-primary/90 px-3.5 py-2 text-[13px] leading-snug text-primary-foreground">
          {m.content}
        </p>
      </div>
    );
  }
  const waiting = m.status === "streaming" && !m.content;
  return (
    <div className="flex">
      <div
        className={
          "max-w-[92%] rounded-2xl rounded-bl-md border border-panel-border px-3.5 py-2.5 text-[13px] leading-relaxed " +
          (m.refused
            ? "bg-secondary/20 text-muted-foreground"
            : "bg-secondary/40 text-foreground/90")
        }
      >
        {waiting ? (
          <span className="inline-flex gap-1 py-1" aria-label="Thinking">
            <span className="size-1.5 animate-bounce rounded-full bg-muted-foreground/60 [animation-delay:-0.3s]" />
            <span className="size-1.5 animate-bounce rounded-full bg-muted-foreground/60 [animation-delay:-0.15s]" />
            <span className="size-1.5 animate-bounce rounded-full bg-muted-foreground/60" />
          </span>
        ) : m.status === "error" && !m.content ? (
          <span className="text-red-700 dark:text-red-300">{m.error ?? "That didn't work."}</span>
        ) : (
          <>
            {render(m.content, m.sourceIds)}
            {m.status === "streaming" && (
              <span
                className="ml-0.5 inline-block h-3.5 w-1.5 animate-pulse bg-foreground/60 align-middle"
                aria-hidden
              />
            )}
            {m.status === "stopped" && (
              <p className="mt-1 text-[11px] text-muted-foreground/90">Stopped.</p>
            )}
          </>
        )}
        {m.status === "done" && m.checks && m.checks.unseenNumbers.length > 0 && (
          <p className="mt-2 rounded-md bg-amber-500/10 px-2 py-1 text-[11px] leading-snug text-amber-800 dark:text-amber-300/90">
            Some figures here ({m.checks.unseenNumbers.slice(0, 4).join(", ")}) were not found in
            the research text the model was given — check the sources.
          </p>
        )}
        {m.status === "done" && m.checks && m.checks.unknownIds.length > 0 && (
          <p className="mt-2 rounded-md bg-red-500/10 px-2 py-1 text-[11px] leading-snug text-red-700 dark:text-red-300/90">
            This answer cites a source that wasn&apos;t provided to the model (marked ?). Treat that
            claim as unverified.
          </p>
        )}
        {m.refused && (
          <p className="mt-1.5 text-[11px] text-muted-foreground/90">
            Try asking about a district or region, why students leave school, the UIDAI/NITI check,
            or the personas.
          </p>
        )}
      </div>
    </div>
  );
}

export function AskPanel() {
  const [pack, setPack] = useState<KnowledgePack | null>(null);
  const [packFailed, setPackFailed] = useState(false);
  const [draft, setDraft] = useState("");
  const [passDraft, setPassDraft] = useState("");
  const [now, setNow] = useState(() => Date.now());
  const {
    messages,
    busy,
    passphrase,
    notice,
    lastQuestion,
    send,
    stop,
    clear,
    setPassphrase,
    lock,
  } = useChatStore();
  const districtId = useExplorerStore((s) => s.districtId);
  const regionId = useExplorerStore((s) => s.regionId);
  const render = useRenderer(pack);
  const scroller = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    let alive = true;
    void loadKnowledgePack().then((p) => {
      if (!alive) return;
      if (p) setPack(p);
      else setPackFailed(true);
    });
    return () => {
      alive = false;
    };
  }, []);

  // Keep the newest text in view while an answer streams.
  useEffect(() => {
    scroller.current?.scrollTo({ top: scroller.current.scrollHeight });
  }, [messages]);

  // Countdown for the rate-limit notice.
  const retryAt = notice?.kind === "rate_limited" ? notice.retryAt : 0;
  useEffect(() => {
    if (!retryAt) return;
    const t = setInterval(() => setNow(Date.now()), 500);
    return () => clearInterval(t);
  }, [retryAt]);
  const waitSeconds = retryAt ? Math.max(0, Math.ceil((retryAt - now) / 1000)) : 0;

  // Return focus to the box when an answer finishes.
  useEffect(() => {
    if (!busy) inputRef.current?.focus();
  }, [busy]);

  const ask = (q: string) => {
    if (!pack) return;
    setDraft("");
    void send(q, pack, { districtId, regionId });
  };
  // A question queued from another tab (an Ask button): sent as soon as the chat is unlocked and idle.
  const pending = useChatStore((s) => s.pending);
  const takePending = useChatStore((s) => s.takePending);
  useEffect(() => {
    if (!pending || !pack || busy || !passphrase) return;
    const q = takePending();
    if (q) void send(q, pack, { districtId, regionId });
  }, [pending, pack, busy, passphrase, takePending, send, districtId, regionId]);

  const lastAnswer = [...messages]
    .reverse()
    .find((m) => m.role === "assistant" && m.status === "done");
  const builtOn = pack
    ? new Date(pack.builtAt).toLocaleDateString("en-GB", {
        day: "numeric",
        month: "short",
        year: "numeric",
      })
    : "";

  return (
    <div className="panel-surface @container pointer-events-auto flex min-h-0 flex-1 flex-col overflow-hidden rounded-xl">
      <header className="flex items-start justify-between gap-3 border-b border-panel-border px-5 py-3.5">
        <div>
          <p className="label-micro">Ask the research</p>
          <h2 className="mt-1 text-[15px] font-semibold text-foreground">
            Questions about what we found
          </h2>
          <p className="mt-1 text-[12px] leading-relaxed text-muted-foreground">
            Answers come only from this dashboard&apos;s findings — nothing from the wider web.
          </p>
        </div>
        <div className="flex shrink-0 items-center gap-1">
          {passphrase && (
            <Button
              variant="ghost"
              size="sm"
              className="h-7 gap-1.5 px-2 text-[11px]"
              onClick={lock}
              title="Forget the passphrase on this device"
            >
              <Lock className="size-3" /> Lock
            </Button>
          )}
          {messages.length > 0 && (
            <Button
              variant="ghost"
              size="sm"
              className="h-7 gap-1.5 px-2 text-[11px]"
              onClick={clear}
              title="Clear the conversation"
            >
              <Trash2 className="size-3" /> Clear
            </Button>
          )}
        </div>
      </header>

      <div
        ref={scroller}
        className="min-h-0 flex-1 space-y-3 overflow-y-auto px-5 py-4 [&::-webkit-scrollbar]:w-1.5 [&::-webkit-scrollbar-thumb]:rounded-full [&::-webkit-scrollbar-thumb]:bg-border"
      >
        {!CHAT_URL ? (
          <div className="rounded-xl border border-dashed border-panel-border p-4 text-[12.5px] leading-relaxed text-muted-foreground">
            <p className="font-medium text-foreground">The chat isn&apos;t connected yet.</p>
            <p className="mt-1">
              It needs the small Cloudflare Worker that checks the team passphrase and talks to the
              model. Once it is deployed and its address is set as{" "}
              <code className="rounded bg-secondary px-1">VITE_CHAT_URL</code>, questions will work
              here. Setup steps are in{" "}
              <code className="rounded bg-secondary px-1">proxy/README.md</code>.
            </p>
          </div>
        ) : packFailed ? (
          <p className="text-[12.5px] text-red-700 dark:text-red-300">
            The research text could not be loaded. Please reload the page.
          </p>
        ) : !pack ? (
          <p className="py-8 text-center text-[13px] text-muted-foreground">
            Loading the research…
          </p>
        ) : messages.length === 0 ? (
          <div>
            <p className="text-[12.5px] leading-relaxed text-muted-foreground">
              Ask about a district or region, why students leave school, the UIDAI/NITI check, or
              the personas. Try one:
            </p>
            <div className="mt-3 flex flex-wrap gap-2">
              {SUGGESTIONS.map((s) => (
                <button
                  key={s}
                  type="button"
                  onClick={() => ask(s)}
                  disabled={busy}
                  className="rounded-full border border-panel-border bg-secondary/40 px-3 py-1.5 text-left text-[12px] text-foreground/85 transition-colors hover:bg-secondary disabled:opacity-50"
                >
                  {s}
                </button>
              ))}
            </div>
          </div>
        ) : (
          messages.map((m) => <Bubble key={m.id} m={m} render={render} />)
        )}
      </div>

      {/* Screen readers hear the finished answer once, not every streamed token. */}
      <div className="sr-only" aria-live="polite">
        {lastAnswer ? lastAnswer.content : ""}
      </div>

      {CHAT_URL && pack && (
        <footer className="space-y-2 border-t border-panel-border px-5 py-3">
          {notice && (
            <div
              role="status"
              className={
                "flex items-center justify-between gap-3 rounded-lg px-3 py-2 text-[12px] " +
                (notice.kind === "locked"
                  ? "bg-secondary/60 text-foreground/90"
                  : "bg-red-500/10 text-red-700 dark:text-red-300")
              }
            >
              <span>
                {notice.message}
                {notice.kind === "rate_limited" && waitSeconds > 0 && ` (${waitSeconds}s)`}
              </span>
              {lastQuestion &&
                notice.kind !== "locked" &&
                !(notice.kind === "rate_limited" && waitSeconds > 0) && (
                  <Button
                    variant="ghost"
                    size="sm"
                    className="h-6 gap-1 px-2 text-[11px]"
                    onClick={() => ask(lastQuestion)}
                    disabled={busy}
                  >
                    <RotateCcw className="size-3" /> Retry
                  </Button>
                )}
            </div>
          )}

          {!passphrase && pending && (
            <p className="mb-2 rounded-lg border border-panel-border bg-secondary/40 px-3 py-2 text-[12px] leading-snug text-foreground/90">
              <span className="font-medium">Ready to ask:</span> {pending}
              <span className="mt-1 block text-[11px] text-muted-foreground">
                Unlock with the team passphrase and it is sent straight away.
              </span>
            </p>
          )}
          {!passphrase ? (
            <form
              className="flex items-center gap-2"
              onSubmit={(e) => {
                e.preventDefault();
                if (passDraft.trim()) {
                  setPassphrase(passDraft);
                  setPassDraft("");
                }
              }}
            >
              <Input
                type="password"
                value={passDraft}
                onChange={(e) => setPassDraft(e.target.value)}
                placeholder="Team passphrase"
                aria-label="Team passphrase"
                autoComplete="off"
                className="h-9 flex-1 text-[13px]"
              />
              <Button
                type="submit"
                size="sm"
                className="h-9 px-4 text-xs font-semibold"
                disabled={!passDraft.trim()}
              >
                Unlock
              </Button>
            </form>
          ) : (
            <form
              className="flex items-center gap-2"
              onSubmit={(e) => {
                e.preventDefault();
                ask(draft);
              }}
            >
              <Input
                ref={inputRef}
                value={draft}
                onChange={(e) => setDraft(e.target.value)}
                placeholder="Ask about the research…"
                aria-label="Your question"
                maxLength={1000}
                disabled={busy}
                className="h-9 flex-1 text-[13px]"
              />
              {busy ? (
                <Button
                  type="button"
                  variant="secondary"
                  size="sm"
                  className="h-9 gap-1.5 px-3 text-xs font-semibold"
                  onClick={stop}
                >
                  <Square className="size-3 fill-current" /> Stop
                </Button>
              ) : (
                <Button
                  type="submit"
                  size="sm"
                  className="h-9 gap-1.5 px-4 text-xs font-semibold"
                  disabled={!draft.trim() || waitSeconds > 0}
                >
                  <Send className="size-3" /> Ask
                </Button>
              )}
            </form>
          )}
          <p className="text-[10.5px] leading-snug text-muted-foreground/90">
            AI-written from the research as of {builtOn}. Check the cited sources before relying on
            a figure.
          </p>
        </footer>
      )}
    </div>
  );
}
