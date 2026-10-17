import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ErrorState, LoadingState } from "@/components/shared/RequestStates";
import { useRepoCommits } from "@/hooks/useOrgAtlasData";
import type { CommitSummary } from "@/types";

function CommitRow({ commit }: { commit: CommitSummary }) {
  return (
    <li className="space-y-1 border-b border-border pb-3 last:border-0 last:pb-0">
      <div className="flex flex-wrap items-center gap-2">
        <code className="text-xs">{commit.sha.slice(0, 7)}</code>
        {commit.pr_number ? <Badge variant="secondary">#{commit.pr_number}</Badge> : null}
        <span className="text-sm">{commit.message}</span>
      </div>
      <p className="text-xs text-muted-foreground">
        {commit.author}
        {commit.authored_at ? ` / ${commit.authored_at}` : ""}
      </p>
      {commit.paths.length > 0 ? (
        <p className="truncate text-xs text-muted-foreground">{commit.paths.join(", ")}</p>
      ) : null}
    </li>
  );
}

/** Commits for one repository, newest first. */
export function CommitTimeline({ repositoryId }: { repositoryId: string }) {
  const commits = useRepoCommits(repositoryId);

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Recent commits</CardTitle>
      </CardHeader>
      <CardContent>
        {commits.state === "loading" ? <LoadingState label="Loading commits" /> : null}
        {commits.state === "error" && commits.failure ? (
          <ErrorState failure={commits.failure} onRetry={commits.reload} />
        ) : null}
        {commits.data && commits.data.commits.length === 0 ? (
          <p className="text-sm text-muted-foreground">No commits recorded.</p>
        ) : null}
        {commits.data && commits.data.commits.length > 0 ? (
          <ol className="space-y-3">
            {commits.data.commits.map((commit) => (
              <CommitRow key={commit.sha} commit={commit} />
            ))}
          </ol>
        ) : null}
      </CardContent>
    </Card>
  );
}