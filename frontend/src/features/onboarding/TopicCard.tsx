import { Card, CardContent } from "@/components/ui/card";

import type { Citation, OnboardingTopic } from "@/types";

interface TopicCardProps {
  topic: OnboardingTopic;
  citationFor?: (sourceId: string) => Citation | undefined;
}

export function TopicCard({ topic, citationFor }: TopicCardProps) {
  const resources = topic.resources ?? [];

  return (
    <Card>
      <CardContent className="space-y-3 py-5">
        <div className="flex items-start gap-3">
          <span
            aria-hidden="true"
            className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-primary text-xs font-semibold text-primary-foreground"
          >
            {topic.sequence}
          </span>
          <div className="min-w-0">
            <h4 className="text-sm font-semibold">{topic.title}</h4>
            {topic.summary ? (
              <p className="mt-1 text-sm text-muted-foreground">{topic.summary}</p>
            ) : null}
          </div>
        </div>

        {resources.length > 0 ? (
          <ul className="space-y-1 border-l border-border pl-4 text-xs">
            {resources.map((resourceId) => {
              const citation = citationFor?.(resourceId);
              return (
                <li key={resourceId} className="text-muted-foreground">
                  <span className="font-medium text-foreground">
                    {citation?.title ?? resourceId}
                  </span>
                  {citation?.type ? (
                    <span className="ml-2 opacity-70">({citation.type})</span>
                  ) : null}
                </li>
              );
            })}
          </ul>
        ) : null}
      </CardContent>
    </Card>
  );
}