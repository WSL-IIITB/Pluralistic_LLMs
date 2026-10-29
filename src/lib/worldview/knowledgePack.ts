/** Types and loader for the hardcoded knowledge pack (public/data/knowledge-pack.json). */

import { assetUrl } from "./api";

export interface PackSource {
  /** Global id as written in the pack text, e.g. "S12". */
  id: string;
  title: string;
  outlet: string;
  date: string;
  type: string;
  url: string;
}

export interface KnowledgePack {
  version: number;
  builtAt: string;
  sourceHash: string;
  stats: {
    districts: number;
    sources: number;
    outlets: number;
    headlines: number;
    coverage: Record<string, number>;
  };
  sources: PackSource[];
  index: {
    districts: { id: string; name: string; regionId: string; aliases: string[] }[];
    regions: { id: string; name: string; aliases: string[] }[];
  };
  /** Always sent. */
  caveats: string;
  digest: string;
  /** Sent only when a question touches them (see knowledgeRouter.ts). */
  regions: Record<string, string>;
  districts: Record<string, string>;
  uidai: string;
  /** Why the news research and the UIDAI/NITI data name different main factors. */
  newsVsData: string;
  analysis: string;
  personas: string;
  tokenEstimate: Record<string, number>;
}

let inflight: Promise<KnowledgePack | null> | null = null;

/** The pack, fetched once; null if it can't be loaded. Always re-validated by the browser cache. */
export function loadKnowledgePack(): Promise<KnowledgePack | null> {
  inflight ??= fetch(assetUrl("data/knowledge-pack.json"))
    .then((r) => (r.ok ? (r.json() as Promise<KnowledgePack>) : null))
    .catch(() => null);
  return inflight;
}
