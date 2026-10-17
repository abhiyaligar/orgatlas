import { useState } from "react";

import { AppHeader } from "@/components/layout/AppHeader";
import { AppShell } from "@/components/layout/AppShell";
import { DemoModeBanner } from "@/components/layout/DemoModeBanner";
import { AskWorkspace } from "@/features/ask/AskWorkspace";
import { GraphExplorer } from "@/features/graph/GraphExplorer";
import { LandingPage } from "@/features/landing/LandingPage";
import { OnboardingView } from "@/features/onboarding/OnboardingView";
import { RepositoriesView } from "@/features/repos/RepositoriesView";
import { useHashRoute } from "@/lib/useHashRoute";
import type { AppView, EvidenceSubgraph } from "@/types";

const TEAMS = [
  { id: "team_payments", label: "Payments Core" },
  { id: "team_platform", label: "Cloud Infrastructure" },
];

function TeamPicker({ teamId, onChange }: { teamId: string; onChange: (id: string) => void }) {
  return (
    <div className="flex items-center gap-2">
      <label htmlFor="team-picker" className="text-sm text-muted-foreground">
        Team
      </label>
      <select
        id="team-picker"
        value={teamId}
        onChange={(event) => onChange(event.target.value)}
        className="rounded-md border border-input bg-background px-2 py-1.5 text-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
      >
        {TEAMS.map((team) => (
          <option key={team.id} value={team.id}>
            {team.label}
          </option>
        ))}
      </select>
    </div>
  );
}

export function App() {
  const [activeView, setActiveView] = useState<AppView>("ask");
  const [teamId, setTeamId] = useState(TEAMS[0].id);
  const [sharedGraph, setSharedGraph] = useState<EvidenceSubgraph | null>(null);
  const [route, openDashboard, goToLanding] = useHashRoute();

  const teamLabel = TEAMS.find((team) => team.id === teamId)?.label ?? teamId;

  if (route === "landing") {
    return <LandingPage onOpenDashboard={openDashboard} />;
  }

  return (
    <AppShell
      header={
        <>
          <AppHeader
            activeView={activeView}
            onViewChange={setActiveView}
            teamName={activeView === "onboarding" ? teamLabel : undefined}
            onGoHome={goToLanding}
          />
          <DemoModeBanner />
        </>
      }
    >
      <div className="p-6">
        {activeView === "ask" ? (
          <AskWorkspace onAnswer={setSharedGraph} />
        ) : null}

        {activeView === "onboarding" ? (
          <div className="space-y-4">
            <TeamPicker teamId={teamId} onChange={setTeamId} />
            <OnboardingView teamId={teamId} />
          </div>
        ) : null}

        {activeView === "repositories" ? (
            <RepositoriesView onShowGraph={() => setActiveView("graph")} />
          ) : null}

          {activeView === "graph" ? <GraphExplorer graph={sharedGraph} /> : null}
      </div>
    </AppShell>
  );
}