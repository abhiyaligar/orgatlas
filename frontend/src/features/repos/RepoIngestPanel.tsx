import { useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { useRepoIngest, type RepoIngestOptions } from "@/hooks/useRepoIngest";
import type { IngestStatus } from "@/types";

/** The stages the backend reports, in the order they occur. */
const STAGES: IngestStatus[] = [
  "queued",
  "cloning",
  "parsing",
  "writing",
  "describing",
  "done",
];

function stageIndex(status: string): number {
  const index = STAGES.indexOf(status as IngestStatus);
  return index === -1 ? 0 : index;
}

function StageTrack({ status }: { status: string }) {
  const current = stageIndex(status);

  return (
    <ol className="flex flex-wrap items-center gap-2" aria-label="Ingestion progress">
      {STAGES.map((stage, index) => {
        const reached = index <= current;
        const active = index === current && status !== "done";
        return (
          <li key={stage} className="flex items-center gap-2">
            <Badge
              variant={active ? "default" : reached ? "secondary" : "outline"}
              aria-current={active ? "step" : undefined}
            >
              {stage}
            </Badge>
            {index < STAGES.length - 1 ? (
              <span aria-hidden="true" className="text-muted-foreground">
                /
              </span>
            ) : null}
          </li>
        );
      })}
    </ol>
  );
}

export function RepoIngestPanel({
  onIngested,
  ...ingestOptions
}: RepoIngestOptions & { onIngested?: () => void }) {
  const [url, setUrl] = useState("https://github.com/FalkorDB/FalkorDB");
  const { state, job, failure, start, reset } = useRepoIngest(ingestOptions);

  return (
    <Card>
      <CardHeader>
        <CardTitle>Ingest a repository</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <form
          className="flex flex-wrap items-end gap-2"
          onSubmit={(event) => {
            event.preventDefault();
            start(url);
          }}
        >
          <div className="flex-1 space-y-1">
            <label htmlFor="repo-url" className="text-sm text-muted-foreground">
              Public repository URL
            </label>
            <Input
              id="repo-url"
              value={url}
              onChange={(event) => setUrl(event.target.value)}
              placeholder="https://github.com/owner/repo"
            />
          </div>
          <Button type="submit" disabled={state === "loading"}>
            {state === "loading" ? "Ingesting" : "Ingest"}
          </Button>
          {job ? (
            <Button type="button" variant="ghost" onClick={reset}>
              Clear
            </Button>
          ) : null}
        </form>

        {job ? (
          <div className="space-y-3 rounded-md border border-border p-3">
            <StageTrack status={job.status} />

            {job.stage_detail ? (
              <p className="text-xs text-muted-foreground">{job.stage_detail}</p>
            ) : null}

            {job.status === "failed" ? (
              <p className="text-sm text-destructive">
                {job.error_message ?? "Ingestion failed without a reason."}
              </p>
            ) : (
              <dl className="grid grid-cols-3 gap-2 text-sm">
                <div>
                  <dt className="text-xs text-muted-foreground">Commits</dt>
                  <dd>{job.commits_ingested}</dd>
                </div>
                <div>
                  <dt className="text-xs text-muted-foreground">Files</dt>
                  <dd>{job.files_indexed}</dd>
                </div>
                <div>
                  <dt className="text-xs text-muted-foreground">Contributors</dt>
                  <dd>{job.identities_resolved}</dd>
                </div>
              </dl>
            )}

            {job.status === "done" ? (
              <Button type="button" variant="secondary" onClick={onIngested}>
                Refresh repository list
              </Button>
            ) : null}
          </div>
        ) : null}

        {failure ? (
          <p className="text-sm text-destructive">{failure.message}</p>
        ) : null}
      </CardContent>
    </Card>
  );
}