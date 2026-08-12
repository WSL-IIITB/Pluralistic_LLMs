/**
 * Hand-authored narrative content for the mock runs: the viewpoint clusters,
 * the points of deflection, and the streamed consolidated answer — for both a
 * descriptive run (Diwali) and a policy run (dropout intervention).
 *
 * The district-level geography is generated separately (generatedDistricts.ts)
 * and shared by both runs; the policy run recolours it via POLICY_CLUSTER_REMAP.
 */

import { paletteColor } from "../palette";
import type { AnswerSegment, ClusterId, DeflectionLevel, RGBAColor, SamplePost } from "../types";

export interface ClusterSpec {
  id: ClusterId;
  label: string;
  color: RGBAColor;
  summary: string;
  posts: SamplePost[];
}

export interface DeflectionSpec {
  id: string;
  clusterA: ClusterId;
  clusterB: ClusterId;
  level: DeflectionLevel;
  unitA: string;
  unitB: string;
  point: string;
  confidence: "high" | "medium" | "low";
}

const post = (
  id: string,
  platform: SamplePost["platform"],
  paraphrase: string,
  clusterId: ClusterId,
): SamplePost => ({
  id,
  platform,
  paraphrase,
  clusterId,
});

// ─────────────────────────────────────────────────────────────────────────────
// Descriptive run — Diwali
// ─────────────────────────────────────────────────────────────────────────────

export const DIWALI_CLUSTERS: ClusterSpec[] = [
  {
    id: "rama",
    label: "Rama / Ayodhya",
    color: paletteColor(0),
    summary:
      "Diwali marks Rama's return to Ayodhya after defeating Ravana; lamps light his path home.",
    posts: [
      post(
        "r1",
        "reddit",
        "Grew up lighting diyas for Ram's return — that's the whole point of the lamps here.",
        "rama",
      ),
      post(
        "r2",
        "youtube",
        "Ramlila wrapped last night, today the whole street is lit for Ayodhya.",
        "rama",
      ),
    ],
  },
  {
    id: "krishna",
    label: "Krishna / Narakasura",
    color: paletteColor(1),
    summary:
      "Celebrates the night Krishna slew the demon Narakasura — kept as Naraka Chaturdashi in the South.",
    posts: [
      post(
        "k1",
        "reddit",
        "Down south we mark Naraka Chaturdashi — the oil bath at dawn is the real ritual.",
        "krishna",
      ),
      post(
        "k2",
        "youtube",
        "It's about Krishna ending Narakasura, not Rama — different story entirely here.",
        "krishna",
      ),
    ],
  },
  {
    id: "kali",
    label: "Kali Puja",
    color: paletteColor(2),
    summary: "In Bengal and the East the new-moon night honours the fierce goddess Kali.",
    posts: [
      post(
        "ka1",
        "reddit",
        "In Bengal this night is Kali Puja — the pandal matters more than the diyas.",
        "kali",
      ),
      post(
        "ka2",
        "youtube",
        "We do Kali puja through the night; the firecrackers are for her.",
        "kali",
      ),
    ],
  },
  {
    id: "lakshmi",
    label: "New Year / Lakshmi",
    color: paletteColor(3),
    summary:
      "In the West the festival opens the new year and invites Lakshmi's prosperity into the home.",
    posts: [
      post(
        "l1",
        "reddit",
        "For us it's Bestu Varas — new-year books opened, Lakshmi puja for the shop.",
        "lakshmi",
      ),
      post(
        "l2",
        "youtube",
        "Chopda pujan at the store today, then family — it's our financial new year.",
        "lakshmi",
      ),
    ],
  },
  {
    id: "bandi",
    label: "Bandi Chhor Divas",
    color: paletteColor(4),
    summary: "Sikhs mark Guru Hargobind's release from Gwalior Fort, freeing 52 princes with him.",
    posts: [
      post(
        "b1",
        "reddit",
        "At the Gurdwara it's Bandi Chhor Divas — Guru Hargobind's release, not Diwali per se.",
        "bandi",
      ),
      post(
        "b2",
        "youtube",
        "Golden Temple lit up tonight for Bandi Chhor — the lamps mean freedom.",
        "bandi",
      ),
    ],
  },
  {
    id: "mahavira",
    label: "Mahavira Nirvana",
    color: paletteColor(5),
    summary:
      "Jains commemorate Mahavira attaining nirvana (moksha) on this night; lamps mark the passing of his light.",
    posts: [
      post(
        "m1",
        "reddit",
        "For our Jain family the diyas are for Mahavira's nirvana — we keep it quiet.",
        "mahavira",
      ),
      post(
        "m2",
        "youtube",
        "Nirvana of Mahavir today — the lamps stand in for the knowledge he left.",
        "mahavira",
      ),
    ],
  },
];

export const DIWALI_DEFLECTIONS: DeflectionSpec[] = [
  {
    id: "def-rama-krishna",
    clusterA: "rama",
    clusterB: "krishna",
    level: "inter-region",
    unitA: "North",
    unitB: "South",
    point:
      "Which divine figure and which liberation event the lamps commemorate — Rama's return to Ayodhya, or Krishna's slaying of Narakasura.",
    confidence: "high",
  },
  {
    id: "def-kali-lakshmi",
    clusterA: "kali",
    clusterB: "lakshmi",
    level: "inter-region",
    unitA: "East · Bengal",
    unitB: "West · Gujarat",
    point:
      "Whether the new-moon night honours Kali's fierce power or invites Lakshmi's prosperity for the new year.",
    confidence: "high",
  },
  {
    id: "def-bandi-rama",
    clusterA: "bandi",
    clusterB: "rama",
    level: "inter-region",
    unitA: "Punjab · Sikh",
    unitB: "North · Hindu",
    point: "Whether the lamps mark Guru Hargobind's release (Bandi Chhor) or Rama's homecoming.",
    confidence: "medium",
  },
  {
    id: "def-lakshmi-mahavira",
    clusterA: "lakshmi",
    clusterB: "mahavira",
    level: "intra-state",
    unitA: "Gujarat · majority",
    unitB: "Gujarat · Jain",
    point:
      "Within the same towns, whether the new-year lamp is for Lakshmi's blessing or Mahavira's nirvana.",
    confidence: "medium",
  },
  {
    id: "def-krishna-mahavira",
    clusterA: "krishna",
    clusterB: "mahavira",
    level: "inter-state",
    unitA: "Karnataka",
    unitB: "Jain communities",
    point: "Whether the festival centres a Vaishnava victory or a Jain liberation.",
    confidence: "low",
  },
];

export const DIWALI_ANSWER: AnswerSegment[] = [
  { kind: "heading", text: "Diwali — one festival, many commemorations" },
  {
    kind: "body",
    text: "Across nearly every state the surface grammar is the same: rows of oil lamps, sweets exchanged between households, cleaned and decorated thresholds, and family gatherings that stretch over several nights.",
  },
  {
    kind: "body",
    text: "\n\nUnderneath that shared ritual layer, regions commemorate materially different events. The lamps mean different things depending on where a post was written, and the divine figure at the centre of the story shifts with geography and community.",
  },
  { kind: "heading", text: "Regional viewpoints" },
  {
    kind: "recommendation",
    region: "North",
    clusterId: "rama",
    text: "the return of Rama to Ayodhya after his victory over Ravana.",
  },
  {
    kind: "recommendation",
    region: "South",
    clusterId: "krishna",
    text: "Krishna's defeat of the demon Narakasura (Naraka Chaturdashi).",
  },
  {
    kind: "recommendation",
    region: "East · Bengal",
    clusterId: "kali",
    text: "the worship of Kali on the new-moon night.",
  },
  {
    kind: "recommendation",
    region: "West · Gujarat",
    clusterId: "lakshmi",
    text: "the new year and Lakshmi puja for prosperity.",
  },
  {
    kind: "recommendation",
    region: "Punjab · Sikh",
    clusterId: "bandi",
    text: "Bandi Chhor Divas — Guru Hargobind's release from Gwalior.",
  },
  {
    kind: "recommendation",
    region: "Jain",
    clusterId: "mahavira",
    text: "Mahavira's attainment of nirvana.",
  },
  {
    kind: "body",
    text: "\n\nWhere a district returned too few posts, the reading falls back to its parent state; those areas render dimmed on the map and should be read as provisional.",
  },
];

// ─────────────────────────────────────────────────────────────────────────────
// Policy run — high-school dropout intervention
// ─────────────────────────────────────────────────────────────────────────────

export const POLICY_CLUSTERS: ClusterSpec[] = [
  {
    id: "structural",
    label: "Economic pressure",
    color: paletteColor(0),
    summary: "Students leave to earn; household income need is the binding constraint.",
    posts: [
      post(
        "p-s1",
        "reddit",
        "Kids here drop after class 8 to work the fields or a shop — it's money, plain and simple.",
        "structural",
      ),
    ],
  },
  {
    id: "curriculum",
    label: "Curriculum relevance",
    color: paletteColor(1),
    summary: "Perceived low payoff of academics; demand for vocational tracks.",
    posts: [
      post(
        "p-c1",
        "youtube",
        "Nobody sees the point of the syllabus — give them a trade and they'd stay.",
        "curriculum",
      ),
    ],
  },
  {
    id: "safety",
    label: "Safety & gender",
    color: paletteColor(2),
    summary: "Girls leaving over distance, safety, and early marriage.",
    posts: [
      post(
        "p-sa1",
        "reddit",
        "Girls stop after the school across the river closed — parents won't risk the commute.",
        "safety",
      ),
    ],
  },
  {
    id: "migration",
    label: "Seasonal migration",
    color: paletteColor(3),
    summary: "Families migrate for work; children drop mid-year and don't re-enrol.",
    posts: [
      post(
        "p-mi1",
        "youtube",
        "We move for the cane-cutting season, so the kids just miss half the year and quit.",
        "migration",
      ),
    ],
  },
  {
    id: "language",
    label: "Language barrier",
    color: paletteColor(4),
    summary: "Medium-of-instruction mismatch with the home language.",
    posts: [
      post(
        "p-la1",
        "reddit",
        "Instruction switched to a language they don't speak at home — grades collapse, they leave.",
        "language",
      ),
    ],
  },
  {
    id: "infrastructure",
    label: "Distance & infrastructure",
    color: paletteColor(5),
    summary: "No nearby secondary school; transport and facility gaps.",
    posts: [
      post(
        "p-in1",
        "youtube",
        "Nearest higher-secondary is 20km — without a bus, that's the end of school.",
        "infrastructure",
      ),
    ],
  },
];

export const POLICY_DEFLECTIONS: DeflectionSpec[] = [
  {
    id: "pdef-struct-curric",
    clusterA: "structural",
    clusterB: "curriculum",
    level: "inter-region",
    unitA: "North",
    unitB: "South",
    point:
      "Whether the binding constraint is income needed now, or the perceived low payoff of staying enrolled.",
    confidence: "high",
  },
  {
    id: "pdef-safety-migration",
    clusterA: "safety",
    clusterB: "migration",
    level: "inter-region",
    unitA: "East",
    unitB: "West",
    point:
      "Whether intervention should target safe access for girls, or portability for migrating families.",
    confidence: "high",
  },
  {
    id: "pdef-lang-curric",
    clusterA: "language",
    clusterB: "curriculum",
    level: "inter-state",
    unitA: "Punjab",
    unitB: "South",
    point:
      "Whether the lever is bridging the language of instruction, or making the curriculum vocational.",
    confidence: "medium",
  },
  {
    id: "pdef-struct-infra",
    clusterA: "structural",
    clusterB: "infrastructure",
    level: "intra-state",
    unitA: "plains blocks",
    unitB: "sparse blocks",
    point:
      "Whether to relieve income pressure, or first close the physical distance to a secondary school.",
    confidence: "medium",
  },
];

export const POLICY_ANSWER: AnswerSegment[] = [
  { kind: "heading", text: "Where should intervention focus?" },
  {
    kind: "body",
    text: "The drivers of dropout are not uniform. The binding constraint differs by region, so a single national lever underperforms a regionally-differentiated package. The recommendation below routes each region to its dominant driver.",
  },
  { kind: "heading", text: "Recommended focus by region" },
  {
    kind: "recommendation",
    region: "North (Hindi belt)",
    clusterId: "structural",
    text: "conditional cash transfers tied to attendance; earn-and-learn evening tracks.",
  },
  {
    kind: "recommendation",
    region: "South",
    clusterId: "curriculum",
    text: "expand vocational and apprenticeship pathways from grade 9.",
  },
  {
    kind: "recommendation",
    region: "East · Bengal",
    clusterId: "safety",
    text: "safe-transport and hostel provision; targeted stipends for girls.",
  },
  {
    kind: "recommendation",
    region: "West · Gujarat",
    clusterId: "migration",
    text: "portable enrolment and seasonal hostels for migrant families.",
  },
  {
    kind: "recommendation",
    region: "Punjab",
    clusterId: "language",
    text: "bridge-language materials and bilingual instruction.",
  },
  {
    kind: "recommendation",
    region: "Sparse blocks",
    clusterId: "infrastructure",
    text: "secondary-school siting and transport subsidies where distance is the barrier.",
  },
  {
    kind: "body",
    text: "\n\nLow-confidence blocks render dimmed; treat their assignment as provisional and verify on the ground before committing budget.",
  },
];

/** Maps the shared Diwali geography onto policy clusters for the policy run. */
export const POLICY_CLUSTER_REMAP: Record<ClusterId, ClusterId> = {
  rama: "structural",
  krishna: "curriculum",
  kali: "safety",
  lakshmi: "migration",
  bandi: "language",
  mahavira: "infrastructure",
};
