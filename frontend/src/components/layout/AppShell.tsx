import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

interface AppShellProps {
  header: ReactNode;
  aside?: ReactNode;
  children: ReactNode;
  className?: string;
}

export function AppShell({ header, aside, children, className }: AppShellProps) {
  return (
    <div className={cn("flex min-h-screen flex-col bg-background text-foreground", className)}>
      {header}
      <div className="flex flex-1 flex-col lg:flex-row">
        {aside ? (
          <aside className="w-full shrink-0 border-b border-border lg:w-72 lg:border-b-0 lg:border-r">
            {aside}
          </aside>
        ) : null}
        <main className="min-w-0 flex-1">{children}</main>
      </div>
    </div>
  );
}