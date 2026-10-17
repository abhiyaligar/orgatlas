import { useMemo, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useRepoBrief, useRepoChurn, useRepositories } from "@/hooks/useOrgAtlasData";
import { EmptyState, ErrorState, LoadingState } from "@/components/shared/RequestStates";
import { RepoIngestPanel } from "@/features/repos/RepoIngestPanel";
import { CommitTimeline } from "@/features/repos/CommitTimeline";
import { DependencyView } from "@/features/repos/DependencyView";
import { FileHistory } from "@/features/repos/FileHistory";
import { SymbolLookup } from "@/features/repos/SymbolLookup";
import type { RepositorySummary } from "@/types";

/**
 * Which of the three repository kinds this is.
 *
 * Ingested repositories carry a `source` naming where the code came from; the
 * fictional seed carries none. A third group is real but metadata-only: a
 * dependency named in a manifest that was deliberately never cloned.
 */
type RepositoryKind = "ingested" | "metadata-only" | "seeded";

function repositoryKind(repository: RepositorySummary): RepositoryKind {
  if (!repository.source) return "seeded";
  if (repository.commit_count === 0 && repository.file_count === 0) return "metadata-only";
  return "ingested";
}

const KIND_LABELS: Record<RepositoryKind, string> = {
  ingested: "ingested",
  "metadata-only": "declared dependency, not cloned",
  seeded: "fictional seed",
};

function RepositoryCard({
  repository,
  selected,
  onSelect,
}: {
  repository: RepositorySummary;
  selected: boolean;
  onSelect: () => void;
}) {
  const kind = repositoryKind(repository);

  return (
    <li>
      <button
        type="button"
        onClick={onSelect}
        aria-pressed={selected}
        className={`w-full rounded-md border p-3 text-left transition-colors hover:bg-accent ${
          selected ? "border-primary bg-accent" : "border-border"
        }`}
      >
        <div className="flex items-center justify-between gap-2">
          <span className="font-medium">{repository.name}</span>
          <Badge variant={kind === "ingested" ? "success" : kind === "seeded" ? "warning" : "outline"}>
            {KIND_LABELS[kind]}
          </Badge>
        </div>
        <p className="truncate text-xs text-muted-foreground">{repository.url}</p>
        <p className="mt-1 text-xs text-muted-foreground">
          {kind === "metadata-only"
            ? "no code ingested"
            : `${repository.commit_count} commits / ${repository.file_count} files`}
          {repository.dependencies.length
            ? ` / ${repository.dependencies.length} declared dependencies`
            : ""}
        </p>
      </button>
    </li>
  );
}

export function RepositoriesView({ onShowGraph }: { onShowGraph?: () => void }) {
  const { data, state, failure, reload } = useRepositories();
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const ingested = useMemo(
    () => (data ?? []).filter((repository) => repositoryKind(repository) === "ingested"),
    [data],
  );

  const others = useMemo(
    () => (data ?? []).filter((repository) => repositoryKind(repository) !== "ingested"),
    [data],
  );

  const selected = useMemo(
    () => data?.find((repository) => repository.id === selectedId) ?? null,
    [data, selectedId],
  );

  const selectedKind = selected ? repositoryKind(selected) : null;
  const hasCode = selectedKind === "ingested";

  const brief = useRepoBrief(selectedId ?? "");
  const churn = useRepoChurn(selectedId ?? "");
  const [fileId, setFileId] = useState<string | null>(null);

  return (
    <div className="space-y-6">
      <div className="space-y-1">
        <h2 className="text-xl font-semibold">Repositories</h2>
        <p className="text-sm text-muted-foreground">
          Repositories with code were ingested from their git history. Some are recorded as declared
          dependencies without being cloned, and the fictional seed backs the decision and ownership
          material.
        </p>
      </div>

      <RepoIngestPanel onIngested={reload} />

      {state === "loading" ? <LoadingState label="Loading repositories" /> : null}
      {state === "error" && failure ? <ErrorState failure={failure} onRetry={reload} /> : null}

      {state === "success" && ingested.length === 0 ? (
        <EmptyState title="No real repository ingested yet" />
      ) : null}

      {state === "success" && ingested.length > 0 ? (
        <section aria-labelledby="ingested-repos" className="space-y-3">
          <h3 id="ingested-repos" className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
            Ingested
          </h3>
          <ul className="grid gap-3 md:grid-cols-2">
            {ingested.map((repository) => (
              <RepositoryCard
                key={repository.id}
                repository={repository}
                selected={repository.id === selectedId}
                onSelect={() => setSelectedId(repository.id)}
              />
            ))}
          </ul>
        </section>
      ) : null}

      {state === "success" && others.length > 0 ? (
        <section aria-labelledby="other-repos" className="space-y-3">
          <h3 id="other-repos" className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
            Declared and seeded
          </h3>
          <ul className="grid gap-3 md:grid-cols-2">
            {others.map((repository) => (
              <RepositoryCard
                key={repository.id}
                repository={repository}
                selected={repository.id === selectedId}
                onSelect={() => setSelectedId(repository.id)}
              />
            ))}
          </ul>
        </section>
      ) : null}

      {selected ? (
        <section aria-labelledby="repo-brief" className="space-y-3">
          <h3 id="repo-brief" className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
            {selected.name} orientation
          </h3>
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Where the risk is</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              {brief.state === "loading" ? <LoadingState label="Loading brief" /> : null}
              {brief.state === "error" && brief.failure ? (
                <ErrorState failure={brief.failure} onRetry={brief.reload} />
              ) : null}
              {brief.data ? (
                <>
                  <ul className="space-y-1">
                    {brief.data.guidance.map((line) => (
                      <li key={line} className="text-sm text-muted-foreground">
                        {line}
                      </li>
                    ))}
                  </ul>
                  {onShowGraph ? (
                    <button
                      type="button"
                      className="text-sm text-primary underline-offset-4 hover:underline"
                      onClick={onShowGraph}
                    >
                      Open the graph explorer
                    </button>
                  ) : null}
                </>
              ) : null}
            </CardContent>
          </Card>

          {churn.data && churn.data.files.length > 0 ? (
            <Card>
              <CardHeader>
                <CardTitle className="text-base">Hotspots</CardTitle>
              </CardHeader>
              <CardContent>
                <p className="text-xs text-muted-foreground">
                  Files by number of recorded changes. Select one to read its history.
                </p>
                <ul className="mt-2 space-y-1">
                  {churn.data.files.map((file) => (
                    <li key={file.file_id}>
                      <button
                        type="button"
                        aria-pressed={fileId === file.file_id}
                        onClick={() => setFileId(file.file_id)}
                        className={`flex w-full items-center justify-between gap-2 rounded-md border px-2 py-1 text-left text-sm ${
                          fileId === file.file_id
                            ? "border-primary bg-accent"
                            : "border-border hover:bg-accent"
                        }`}
                      >
                        <span className="truncate">{file.path}</span>
                        <span className="flex shrink-0 items-center gap-2">
                          {file.is_test ? <Badge variant="outline">test</Badge> : null}
                          <span className="text-xs text-muted-foreground">
                            {file.changes} changes
                          </span>
                        </span>
                      </button>
                    </li>
                  ))}
                </ul>
              </CardContent>
            </Card>
          ) : null}

          {hasCode && fileId ? <FileHistory fileId={fileId} key={fileId} /> : null}

          {hasCode ? <CommitTimeline repositoryId={selected.id} /> : null}

          {hasCode ? (
            <DependencyView
              repository={selected}
              onOpenRepository={(repositoryId) => setSelectedId(repositoryId)}
            />
          ) : null}

          {hasCode ? <SymbolLookup fileId={fileId ?? undefined} /> : null}
        </section>
      ) : null}
    </div>
  );
}
