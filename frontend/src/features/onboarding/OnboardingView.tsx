import { useCallback, useMemo } from "react";

import { EmptyState, ErrorState, LoadingState } from "@/components/shared/RequestStates";
import { SourceCitation } from "@/components/shared/SourceCitation";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useOnboarding } from "@/hooks/useOrgAtlasData";
import { OwnedServicesList } from "@/features/onboarding/OwnedServicesList";
import { PeopleToMeetList } from "@/features/onboarding/PeopleToMeetList";
import { TopicCard } from "@/features/onboarding/TopicCard";
import type { Citation } from "@/types";

interface OnboardingViewProps {
  teamId: string;
  onFocusEntity?: (entityId: string) => void;
}

export function OnboardingView({ teamId, onFocusEntity }: OnboardingViewProps) {
  const { data, state, failure, reload } = useOnboarding(teamId);

  const citationIndex = useMemo(() => {
    const index = new Map<string, Citation>();
    for (const citation of data?.reading_list ?? []) {
      index.set(citation.source_id, citation);
    }
    return index;
  }, [data]);

  const citationFor = useCallback(
    (sourceId: string) => citationIndex.get(sourceId),
    [citationIndex],
  );

  if (state === "loading") return <LoadingState label="Loading onboarding map" />;
  if (state === "error" && failure) return <ErrorState failure={failure} onRetry={reload} />;
  if (!data) return <EmptyState title="No onboarding data" />;

  return (
    <div className="space-y-6">
      <div className="space-y-1">
        <h2 className="text-xl font-semibold">{data.team_name}</h2>
        {data.mission ? <p className="text-sm text-muted-foreground">{data.mission}</p> : null}
      </div>

      <section aria-labelledby="onboarding-path" className="space-y-3">
        <h3 id="onboarding-path" className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
          First-week learning path
        </h3>
        {data.topics.length > 0 ? (
          <ol className="space-y-3">
            {data.topics.map((topic) => (
              <li key={topic.id}>
                <TopicCard topic={topic} citationFor={citationFor} />
              </li>
            ))}
          </ol>
        ) : (
          <EmptyState title="No onboarding topics recorded for this team" />
        )}
      </section>

      <div className="grid gap-4 lg:grid-cols-2">
        <OwnedServicesList services={data.owned_services} onSelect={onFocusEntity} />
        <PeopleToMeetList people={data.people_to_meet} />
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-sm">Reading list</CardTitle>
        </CardHeader>
        <CardContent>
          {data.reading_list.length > 0 ? (
            <ul className="space-y-3">
              {data.reading_list.map((citation) => (
                <li key={citation.source_id}>
                  <SourceCitation citation={citation} index={0} />
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-sm text-muted-foreground">
              No source documents are linked to this team yet.
            </p>
          )}
        </CardContent>
      </Card>
    </div>
  );
}