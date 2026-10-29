/**
 * Decides which parts of the knowledge pack go into one chat request.
 *
 * Gemma's window is 32k tokens and the whole pack is ~44k, so every request carries the always-on
 * caveats + digest plus only the sections the question touches (districts / regions / UIDAI-NITI /
 * persona analysis). This is deterministic context fitting, not a search feature: it matches names
 * and a few keywords, nothing else. Kept dependency-free (type imports only) so the eval script can
 * run the exact same code under Node.
 */

import type { KnowledgePack } from "./knowledgePack.ts";

export interface ChatTurn {
  role: "user" | "assistant";
  content: string;
}

export interface RouteResult {
  /** Text to send as `context`. */
  context: string;
  /** Source ids ("S12") that appear in the context -- the only ids an answer may cite. */
  sourceIds: string[];
  /** Section names included, in order (for debugging / the eval report). */
  included: string[];
  tokenEstimate: number;
}

export interface RouteOptions {
  /** What the user is looking at on the map right now. */
  focus?: { districtId?: string | null; regionId?: string | null };
  /** Token budget for the context (default 12,000). */
  maxTokens?: number;
}

const UIDAI =
  /\b(uidai|niti|aayog|dominant factors?|sanitation|english[- ]medium|protected well|official (data|statistics)|statistical)\b/;
// "news vs data": the question sets what the news reports against what the official data shows.
const NEWS = /\b(news|media|articles?|stories|story|headlines?|reports?|reported|reporting)\b/;
const DATA =
  /\b(data|uidai|niti|dominant|statistics?|statistical|official|english[- ]medium|medium of instruction)\b/;
const RECONCILE = /\b(reconcil\w*|differ\w*|mismatch\w*|contradict\w*|versus|vs)\b/;
const ANALYSIS =
  /\b(persona|personas|generic answer|similarity|divergen\w*|story mode|consolidated|region[- ]first|composite)\b/;
const PERSONAS = /\b(persona|personas|composite|puttaswamy|manjula|character|characters)\b/;
const REGIONAL_FOLLOWUP =
  /\b(region|regional|neighbou?rs?|neighbou?ring|nearby|other districts|compare|comparison|similar|across)\b/;
const DEICTIC = /\b(this district|this region|here|there|this one|the selected|it)\b/;
const MAX_DISTRICTS = 6;
const MAX_REGIONS = 3;

const tokens = (s: string) => Math.ceil(s.length / 4);
const norm = (s: string) =>
  ` ${s
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, " ")
    .trim()} `;

interface Mention {
  kind: "district" | "region";
  id: string;
  pos: number;
}

/** Longest-match-first scan so "Bengaluru Rural" is not also read as "Bengaluru". */
export function findMentions(pack: KnowledgePack, text: string): Mention[] {
  let masked = norm(text);
  const aliases: { kind: Mention["kind"]; id: string; alias: string }[] = [];
  for (const d of pack.index.districts)
    for (const a of d.aliases) aliases.push({ kind: "district", id: d.id, alias: norm(a).trim() });
  for (const r of pack.index.regions)
    for (const a of r.aliases) aliases.push({ kind: "region", id: r.id, alias: norm(a).trim() });
  aliases.sort((a, b) => b.alias.length - a.alias.length);

  const found: Mention[] = [];
  for (const { kind, id, alias } of aliases) {
    if (!alias) continue;
    const needle = ` ${alias} `;
    let from = 0;
    for (;;) {
      const at = masked.indexOf(needle, from);
      if (at < 0) break;
      found.push({ kind, id, pos: at });
      masked = masked.slice(0, at) + " ".repeat(needle.length) + masked.slice(at + needle.length);
      from = at + needle.length;
    }
  }
  return found.sort((a, b) => a.pos - b.pos);
}

export function routeContext(
  pack: KnowledgePack,
  messages: ChatTurn[],
  opts: RouteOptions = {},
): RouteResult {
  const budget = opts.maxTokens ?? 12_000;
  const userTurns = messages.filter((m) => m.role === "user");
  const text = userTurns
    .slice(-2)
    .map((m) => m.content)
    .join(" \n ");
  const lower = text.toLowerCase();

  let mentions = findMentions(pack, text);
  // A follow-up that names nothing ("why do you think so?") keeps talking about the place discussed most recently.
  if (!mentions.length) {
    for (const turn of userTurns.slice(-8, -2).reverse()) {
      mentions = findMentions(pack, turn.content);
      if (mentions.length) break;
    }
  }
  const districtIds: string[] = [];
  const regionIds: string[] = [];
  for (const m of mentions) {
    const list = m.kind === "district" ? districtIds : regionIds;
    if (!list.includes(m.id)) list.push(m.id);
  }
  // Nothing named: fall back to what the user is looking at, if the question points at it.
  const focus = opts.focus ?? {};
  if (!districtIds.length && !regionIds.length && DEICTIC.test(lower)) {
    if (focus.districtId) districtIds.push(focus.districtId);
    else if (focus.regionId) regionIds.push(focus.regionId);
  }

  // Priority order: earlier entries are kept when the budget is tight.
  const parts: { name: string; text: string }[] = [
    { name: "CAVEATS", text: pack.caveats },
    { name: "DIGEST", text: pack.digest },
  ];
  const optional: { name: string; text: string }[] = [];
  for (const id of districtIds.slice(0, MAX_DISTRICTS)) {
    const t = pack.districts[id];
    if (t) optional.push({ name: `DISTRICT ${id}`, text: t });
  }
  if (pack.newsVsData && DATA.test(lower) && (NEWS.test(lower) || RECONCILE.test(lower)))
    optional.push({ name: "NEWS VS DATA", text: pack.newsVsData });
  // "…the other districts in its region" after a district question: bring in that district's region section.
  if (REGIONAL_FOLLOWUP.test(lower)) {
    for (const id of districtIds.slice(0, 2)) {
      const rid = pack.index.districts.find((d) => d.id === id)?.regionId;
      if (rid && !regionIds.includes(rid)) regionIds.push(rid);
    }
  }
  for (const id of regionIds.slice(0, MAX_REGIONS)) {
    const t = pack.regions[id];
    if (t) optional.push({ name: `REGION ${id}`, text: t });
  }
  if (UIDAI.test(lower)) optional.push({ name: "UIDAI", text: pack.uidai });
  if (ANALYSIS.test(lower)) optional.push({ name: "ANALYSIS", text: pack.analysis });
  if (PERSONAS.test(lower)) optional.push({ name: "PERSONAS", text: pack.personas });

  let used = parts.reduce((s, p) => s + tokens(p.text), 0);
  const kept: typeof optional = [];
  for (const p of optional) {
    const t = tokens(p.text);
    if (used + t > budget && kept.length) continue; // always keep the first requested section
    kept.push(p);
    used += t;
  }
  parts.push(...kept);

  const body = parts.map((p) => `=== ${p.name} ===\n${p.text}`).join("\n\n");
  const ids = [...new Set([...body.matchAll(/\[(S\d+)\]/g)].map((m) => m[1]!))].sort(
    (a, b) => Number(a.slice(1)) - Number(b.slice(1)),
  );
  const byId = new Map(pack.sources.map((s) => [s.id, s]));
  const sourceLines = ids.map((id) => {
    const s = byId.get(id);
    return s ? `${id}: ${s.title} — ${s.outlet}${s.date ? `, ${s.date}` : ""}` : id;
  });
  const context = `${body}\n\n=== SOURCES (cite only these ids) ===\n${sourceLines.join("\n")}`;
  return {
    context,
    sourceIds: ids,
    included: parts.map((p) => p.name),
    tokenEstimate: tokens(context),
  };
}
