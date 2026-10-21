import { Moon, Sun } from "lucide-react";

import { setTheme, useTheme } from "@/lib/theme";
import { assetUrl, STATIC_DATA } from "@/lib/worldview/api";
import { DASHBOARD_TABS, type DashboardTab } from "@/lib/worldview/explorer";

export { DASHBOARD_TABS, type DashboardTab };

type TopBarProps = {
  activeTab: DashboardTab;
  onTabChange: (tab: DashboardTab) => void;
};

export function TopBar({ activeTab, onTabChange }: TopBarProps) {
  const theme = useTheme();
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
        <h1 className="text-sm font-medium tracking-tight text-foreground">
          Pluralistic Karnataka
        </h1>
        <span className="label-micro self-end pb-px">Worldview Explorer</span>
      </div>

      <div className="flex items-center">
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
