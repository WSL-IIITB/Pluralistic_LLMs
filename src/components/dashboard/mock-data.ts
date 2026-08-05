/**
 * UI-only mock data. A separate engineer will replace these with real
 * data sources; keep the shapes stable and swap the values.
 */

export type ViewpointCluster = {
  id: string;
  label: string;
  /** Tailwind background class bound to a design-system cluster token. */
  swatchClass: string;
};

export const viewpointClusters: ViewpointCluster[] = [
  { id: "rama", label: "Rama / Ayodhya", swatchClass: "bg-cluster-1" },
  { id: "krishna", label: "Krishna / Narakasura", swatchClass: "bg-cluster-2" },
  { id: "kali", label: "Kali Puja", swatchClass: "bg-cluster-3" },
  { id: "lakshmi", label: "New Year / Lakshmi", swatchClass: "bg-cluster-4" },
  { id: "bandi-chhor", label: "Bandi Chhor Divas", swatchClass: "bg-cluster-5" },
  { id: "mahavira", label: "Mahavira Nirvana", swatchClass: "bg-cluster-6" },
];

export type RegionalViewpoint = {
  region: string;
  detail: string;
  swatchClass: string;
};

export const regionalViewpoints: RegionalViewpoint[] = [
  { region: "North", detail: "Rama's return to Ayodhya", swatchClass: "bg-cluster-1" },
  { region: "South", detail: "Krishna defeating Narakasura", swatchClass: "bg-cluster-2" },
  { region: "East / Bengal", detail: "Kali Puja", swatchClass: "bg-cluster-3" },
  { region: "West / Gujarat", detail: "New year & Lakshmi puja", swatchClass: "bg-cluster-4" },
  { region: "Sikh", detail: "Bandi Chhor Divas", swatchClass: "bg-cluster-5" },
  { region: "Jain", detail: "Mahavira's nirvana", swatchClass: "bg-cluster-6" },
];

export const consolidatedParagraphs: string[] = [
  "Diwali is observed across nearly every state in the union, and the surface grammar of the festival is remarkably consistent: rows of oil lamps, sweets exchanged between households, cleaned and decorated thresholds, and family gatherings that stretch over several nights.",
  "Underneath that shared ritual layer, however, regions commemorate materially different events. The lamps mean different things depending on where the post was written, and the divine figure at the centre of the story changes with geography and community.",
  "The clusters below are drawn from the sampled corpus and attributed by region. Where a district returned too few posts, the reading falls back to its parent state.",
];

export const layerToggles = [
  { id: "columns", label: "Show 3D columns" },
  { id: "links", label: "Show deflection links" },
  { id: "split", label: "Highlight split states" },
];

export const regionOptions = ["North", "South", "East", "West", "Sikh", "Jain"];

export const statusTicker =
  "Collected 1,240 posts · resolved 380 to districts · found 5 viewpoint clusters · analyzing deflections…";
