import { RotateCw, Trash2 } from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import {
  deleteSavedRun,
  fetchSavedRun,
  listSavedRuns,
  useWorldviewStore,
  type SavedRunSummary,
} from "@/lib/worldview";

const MODE_LABEL: Record<string, string> = {
  basic: "Basic",
  medium: "Medium",
  high: "High",
  extrahigh: "Extra High",
};

const PROVIDER_LABEL: Record<string, string> = {
  azure_anthropic: "Claude",
  openai: "OpenAI",
  gemma_local: "Gemma (local)",
  mistral_local: "Mistral",
  gemma_remote: "Gemma",
};

interface HistoryPanelProps {
  /** Called after a saved run is loaded into the store, so the caller can
   *  switch back to a tab that actually shows it (e.g. "Map"). */
  onOpenRun: () => void;
}

export function HistoryPanel({ onOpenRun }: HistoryPanelProps) {
  const [runs, setRuns] = useState<SavedRunSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [openingId, setOpeningId] = useState<string | null>(null);
  const loadSavedRun = useWorldviewStore((s) => s.loadSavedRun);

  const refresh = useCallback(async () => {
    setLoading(true);
    setRuns(await listSavedRuns());
    setLoading(false);
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const handleOpen = async (id: string) => {
    setOpeningId(id);
    const data = await fetchSavedRun(id);
    setOpeningId(null);
    if (data) {
      loadSavedRun(data);
      onOpenRun();
    }
  };

  const handleDelete = async (id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    await deleteSavedRun(id);
    void refresh();
  };

  return (
    <div className="absolute top-28 left-1/2 w-[560px] max-w-[calc(100vw-3rem)] -translate-x-1/2">
      <section className="panel-surface pointer-events-auto rounded-xl p-5">
        <div className="flex items-center justify-between">
          <p className="label-micro">Saved Runs</p>
          <Button
            variant="ghost"
            size="sm"
            className="h-7 gap-1.5 text-[11px]"
            onClick={() => void refresh()}
          >
            <RotateCw className="size-3" />
            Refresh
          </Button>
        </div>

        {loading ? (
          <p className="mt-3 text-[12px] text-muted-foreground/70">Loading…</p>
        ) : runs.length === 0 ? (
          <p className="mt-3 text-[12px] leading-snug text-muted-foreground/70">
            No saved runs yet — every completed query is saved here automatically.
          </p>
        ) : (
          <ul className="mt-3 max-h-[55vh] space-y-1 overflow-y-auto">
            {runs.map((run) => (
              <li
                key={run.id}
                onClick={() => void handleOpen(run.id)}
                className="flex cursor-pointer items-center gap-3 rounded-md px-2 py-2 -mx-2 transition-colors hover:bg-white/5"
              >
                <div className="min-w-0 flex-1">
                  <p className="truncate text-[13px] text-foreground">{run.query}</p>
                  <p className="mt-0.5 truncate text-[11px] text-muted-foreground/60">
                    {new Date(run.createdAt).toLocaleString()} · {MODE_LABEL[run.mode] ?? run.mode}{" "}
                    · {PROVIDER_LABEL[run.provider] ?? run.provider} ·{" "}
                    {run.scope === "india-districts"
                      ? `India-wide (legacy) · ${run.areasCount} districts`
                      : `${run.areasCount} regions`}{" "}
                    · {run.clustersCount} clusters
                    {run.deflectionsCount > 0 ? ` · ${run.deflectionsCount} deflections` : ""}
                  </p>
                </div>
                {openingId === run.id ? (
                  <span className="shrink-0 text-[11px] text-muted-foreground/60">Opening…</span>
                ) : (
                  <button
                    type="button"
                    onClick={(e) => void handleDelete(run.id, e)}
                    aria-label="Delete saved run"
                    className="shrink-0 rounded-md p-1.5 text-muted-foreground/50 transition-colors hover:bg-white/10 hover:text-destructive"
                  >
                    <Trash2 className="size-3.5" />
                  </button>
                )}
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
