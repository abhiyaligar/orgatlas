import { useState } from "react";

import { AppHeader } from "@/components/layout/AppHeader";
import { AppShell } from "@/components/layout/AppShell";
import { DemoModeBanner } from "@/components/layout/DemoModeBanner";
import type { AppView } from "@/types";

export function App() {
  const [activeView, setActiveView] = useState<AppView>("ask");

  return (
    <AppShell
      header={
        <>
          <AppHeader activeView={activeView} onViewChange={setActiveView} />
          <DemoModeBanner />
        </>
      }
    >
      <div className="p-6">
        <h2 className="text-lg font-semibold">{activeView}</h2>
        <p className="mt-2 text-sm text-muted-foreground">
          Workspace coming online.
        </p>
      </div>
    </AppShell>
  );
}