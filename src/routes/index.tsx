import { createFileRoute } from "@tanstack/react-router";
import { useState } from "react";

import { ConsolidatedPanel } from "@/components/dashboard/ConsolidatedPanel";
import { DeflectionPanel } from "@/components/dashboard/DeflectionPanel";
import { LegendPanel } from "@/components/dashboard/LegendPanel";
import { MapPlaceholder } from "@/components/dashboard/MapPlaceholder";
import { ProgressBar } from "@/components/dashboard/ProgressBar";
import { QueryBar } from "@/components/dashboard/QueryBar";
import { TopBar, type DashboardTab } from "@/components/dashboard/TopBar";

const TITLE = "Pluralistic India — Worldview Explorer";
const DESCRIPTION =
  "A dark cartographic dashboard exploring how regions of India hold different viewpoints on shared topics.";

export const Route = createFileRoute("/")({
  head: () => ({
    meta: [
      { title: TITLE },
      { name: "description", content: DESCRIPTION },
      { property: "og:title", content: TITLE },
      { property: "og:description", content: DESCRIPTION },
      { property: "og:type", content: "website" },
      { name: "twitter:card", content: "summary_large_image" },
    ],
  }),
  component: Index,
});

function Index() {
  const [activeTab, setActiveTab] = useState<DashboardTab>("Map");

  return (
    <main className="relative h-screen w-screen overflow-hidden bg-background">
      <MapPlaceholder />

      <TopBar activeTab={activeTab} onTabChange={setActiveTab} />

      {/* Floating panel layer */}
      <div className="pointer-events-none absolute inset-0 top-14 z-30">
        <div className="absolute top-4 left-1/2 -translate-x-1/2">
          <QueryBar />
        </div>

        {(activeTab === "Map" || activeTab === "Answer") && (
          <div className="absolute top-28 left-5">
            <ConsolidatedPanel />
          </div>
        )}

        {activeTab === "Map" && (
          <div className="absolute top-28 right-5">
            <LegendPanel />
          </div>
        )}

        {activeTab === "About" && (
          <div className="absolute top-28 left-1/2 w-[520px] max-w-[calc(100vw-3rem)] -translate-x-1/2">
            <section className="panel-surface pointer-events-auto rounded-xl p-5">
              <p className="label-micro">About</p>
              <p className="mt-3 text-[13px] leading-relaxed text-muted-foreground">
                Worldview Explorer samples public conversation on a topic, resolves posts to
                districts, and clusters the underlying viewpoints so that regional differences
                become legible on the map. This is an interface preview — all figures shown are
                placeholders.
              </p>
            </section>
          </div>
        )}

        <div className="absolute bottom-6 left-1/2 flex -translate-x-1/2 flex-col items-center gap-3">
          {activeTab === "Deflections" && <DeflectionPanel />}
          <ProgressBar />
        </div>
      </div>
    </main>
  );
}
