import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { statusTicker } from "./mock-data";

export function QueryBar() {
  return (
    <div className="pointer-events-auto w-[min(720px,calc(100vw-3rem))]">
      <div className="panel-surface flex items-center gap-2 rounded-xl p-2">
        <Input
          readOnly
          placeholder="Enter a topic — e.g. Diwali, or 'high-school dropouts: where should government intervene?'"
          className="h-10 border-0 bg-transparent text-sm shadow-none focus-visible:ring-0"
        />
        <Button className="h-10 shrink-0 px-5 text-xs font-semibold tracking-wide uppercase">
          Explore
        </Button>
      </div>

      <div className="mt-2 flex items-center gap-2 px-2">
        <span className="relative flex size-1.5 shrink-0">
          <span className="absolute inline-flex size-full animate-ping rounded-full bg-primary opacity-70" />
          <span className="relative inline-flex size-1.5 rounded-full bg-primary" />
        </span>
        <p className="truncate text-[11px] tracking-wide text-muted-foreground">{statusTicker}</p>
      </div>
    </div>
  );
}
