import { Info } from "lucide-react";

export const DASHBOARD_TABS = ["Map", "Deflections", "Answer", "About"] as const;
export type DashboardTab = (typeof DASHBOARD_TABS)[number];

type TopBarProps = {
  activeTab: DashboardTab;
  onTabChange: (tab: DashboardTab) => void;
};

export function TopBar({ activeTab, onTabChange }: TopBarProps) {
  return (
    <header className="fixed inset-x-0 top-0 z-40 flex h-14 items-center justify-between border-b border-panel-border bg-background/80 px-5 backdrop-blur-xl">
      <div className="flex items-baseline gap-3">
        <h1 className="text-sm font-medium tracking-tight text-foreground">Pluralistic India</h1>
        <span className="label-micro">Worldview Explorer</span>
      </div>

      <nav aria-label="Dashboard sections" className="flex items-center gap-1">
        {DASHBOARD_TABS.map((tab) => {
          const isActive = tab === activeTab;
          return (
            <button
              key={tab}
              type="button"
              aria-current={isActive ? "page" : undefined}
              onClick={() => onTabChange(tab)}
              className={
                "rounded-full px-3.5 py-1.5 text-xs font-medium transition-colors " +
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
        aria-label="About this explorer"
        className="flex size-8 items-center justify-center rounded-full border border-panel-border text-muted-foreground transition-colors hover:text-foreground"
      >
        <Info className="size-4" />
      </button>
    </header>
  );
}
