import { useMemo } from "react";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ErrorState, LoadingState } from "@/components/shared/RequestStates";
import { useRepoBrief } from "@/hooks/useOrgAtlasData";
import type { DependencyRef, RepositorySummary } from "@/types";

/** Recursively flatten the declared dependency tree of a repository. */
function flattenDependencies(repository: RepositorySummary): DependencyRef[] {
  return repository.dependencies.flatMap((dependency) => [
    { id: dependency.id, name: dependency.name, url: dependency.url },
    ...flattenDependencies(dependency),
  ]);
}

/**
 * The dependency graph for an ingested repository.
 *
 * Dependencies come from declared manifests rather than a resolver, so they are
 * metadata about what the code claims to need, not a verified build order. The
 * label below says so explicitly rather than implying the graph is exact.
 */
export function DependencyView({
  repository,
  onOpenRepository,
}: {
  repository: RepositorySummary;
  onOpenRepository?: (repositoryId: string) => void;
}) {
  const brief = useRepoBrief(repository.id);

  const dependencies = useMemo(() => flattenDependencies(repository), [repository]);

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Declared dependencies</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <p className="text-xs text-muted-foreground">
          Read from manifests, not resolved from a lockfile. A declaration is what the code claims to
          need, so treat this as an orientation aid rather than a build graph.
        </p>

        {dependencies.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            No dependencies were recorded for this repository.
          </p>
        ) : (
          <ul className="space-y-2">
            {dependencies.map((dependency) => (
              <li key={dependency.id} className="space-y-0.5">
                <span className="text-sm">{dependency.name}</span>
                {onOpenRepository && dependency.id !== repository.id ? (
                  <button
                    type="button"
                    className="ml-2 text-xs text-primary underline-offset-4 hover:underline"
                    onClick={() => onOpenRepository(dependency.id)}
                  >
                    open
                  </button>
                ) : null}
                {dependency.url ? (
                  <p className="truncate text-xs text-muted-foreground">{dependency.url}</p>
                ) : null}
              </li>
            ))}
          </ul>
        )}

        {brief.state === "loading" ? <LoadingState label="Loading blast radius" /> : null}
        {brief.state === "error" && brief.failure ? (
          <ErrorState failure={brief.failure} onRetry={brief.reload} />
        ) : null}
        {brief.data && brief.data.dependency_blast_radius.length > 0 ? (
          <div className="space-y-1 border-t border-border pt-3">
            <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              Blast radius
            </p>
            <ul className="flex flex-wrap gap-2">
              {brief.data.dependency_blast_radius.map((dependency) => (
                <li key={dependency.id}>
                  <span className="rounded-md border border-border px-2 py-0.5 text-xs">
                    {dependency.name}
                  </span>
                </li>
              ))}
            </ul>
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
}