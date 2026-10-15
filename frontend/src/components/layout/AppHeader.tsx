import { APP_VIEWS, VIEW_LABELS, type AppView } from "@/types";

import { cn } from "@/lib/utils";

interface AppHeaderProps {
  activeView: AppView;
  onViewChange: (view: AppView) => void;
  teamName?: string;
}

export function AppHeader({ activeView, onViewChange, teamName }: AppHeaderProps) {
  return (
    <header className="flex flex-wrap items-center justify-between gap-4 border-b border-border bg-card px-6 py-3">
      <div className="flex items-baseline gap-3">
        <span className="text-sm font-semibold tracking-[0.2em] text-sky-300">
          ORGATLAS
        </span>
        <span className="text-xs text-muted-foreground">
          engineering team context
        </span>
      </div>

      <nav aria-label="Primary" className="flex items-center gap-1">
        {APP_VIEWS.map((view) => {
          const isActive = view === activeView;
          return (
            <button
              key={view}
              type="button"
              aria-current={isActive ? "page" : undefined}
              onClick={() => onViewChange(view)}
              className={cn(
                "rounded-md px-3 py-1.5 text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring",
                isActive
                  ? "bg-primary text-primary-foreground"
                  : "text-muted-foreground hover:bg-accent hover:text-accent-foreground",
              )}
            >
              {VIEW_LABELS[view]}
            </button>
          );
        })}
      </nav>

      {teamName ? (
        <span className="text-xs text-muted-foreground">Team: {teamName}</span>
      ) : null}
    </header>
  );
}