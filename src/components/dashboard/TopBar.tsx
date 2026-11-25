import { Moon, Sun } from "lucide-react";

import { setTheme, useTheme } from "@/lib/theme";
import { assetUrl, STATIC_DATA } from "@/lib/worldview/api";
import { DASHBOARD_TABS, useExplorerStore, type DashboardTab } from "@/lib/worldview/explorer";
import { STUDY_TOPICS } from "@/lib/worldview/stunting";

export { DASHBOARD_TABS, type DashboardTab };

type TopBarProps = {
  activeTab: DashboardTab;
  onTabChange: (tab: DashboardTab) => void;
};

export function TopBar({ activeTab, onTabChange }: TopBarProps) {
  const theme = useTheme();
  const topic = useExplorerStore((s) => s.topic);
  const setTopic = useExplorerStore((s) => s.setTopic);
  return (
    <header className="fixed inset-x-0 top-0 z-40 flex h-14 items-center justify-between border-b border-panel-border bg-background/80 px-5 backdrop-blur-xl">
      <div className="flex items-center gap-3">
        <img
          src={assetUrl("favicon.svg")}
          alt=""
          width={24}
          height={24}
          className="size-6 rounded-md"
        />
        <h1 className="text-sm font-medium tracking-tight whitespace-nowrap text-foreground">
          Pluralistic Karnataka
        </h1>
        <span className="label-micro hidden self-end pb-px whitespace-nowrap 2xl:inline">
          Worldview Explorer
        </span>
      </div>

      <div className="flex items-center">
        <div
          role="radiogroup"
          aria-label="Study topic"
          className="mr-3 flex items-center gap-0.5 rounded-full border border-panel-border p-0.5"
          title="Which study the data views show; personas are shared"
        >
          {STUDY_TOPICS.map((t) => (
            <button
              key={t.id}
              type="button"
              role="radio"
              aria-checked={topic === t.id}
              onClick={() => setTopic(t.id)}
              className={
                "rounded-full px-3 py-1 text-[11px] font-medium transition-colors " +
                (topic === t.id
                  ? "bg-foreground text-background"
                  : "text-muted-foreground hover:text-foreground")
              }
            >
              {t.label}
            </button>
          ))}
        </div>
        <nav aria-label="Dashboard sections" className="flex items-center gap-1">
          {DASHBOARD_TABS.filter((tab) => !(STATIC_DATA && tab === "History")).map((tab) => {
            const isActive = tab === activeTab;
            return (
              <button
                key={tab}
                type="button"
                aria-current={isActive ? "page" : undefined}
                onClick={() => onTabChange(tab)}
                className={
                  "rounded-full px-3.5 py-1.5 text-xs font-medium whitespace-nowrap transition-colors " +
                  (isActive
                    ? "bg-secondary text-foreground"
                    : "text-muted-foreground hover:text-foreground")
                }
              >
                {tab}
              </button>
            );
          })}
        </nav>

        <button
          type="button"
          onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
          aria-label={theme === "dark" ? "Switch to light theme" : "Switch to dark theme"}
          title={theme === "dark" ? "Light theme" : "Dark theme"}
          className="ml-2 inline-flex size-8 items-center justify-center rounded-full text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground"
        >
          {theme === "dark" ? <Sun className="size-4" /> : <Moon className="size-4" />}
        </button>
      </div>
    </header>
  );
}
