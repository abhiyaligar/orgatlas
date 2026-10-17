import { useCallback, useEffect, useRef, useState } from "react";

import { ApiError, fetchIngestJob, startIngest } from "@/services/apiClient";
import type { ApiFailure, IngestJobResponse, RequestState } from "@/types";

/** How often a running job is polled. */
const POLL_INTERVAL_MS = 2500;

const TERMINAL = new Set(["done", "failed"]);

export interface RepoIngestState {
  state: RequestState;
  job: IngestJobResponse | null;
  failure: ApiFailure | null;
  start: (repositoryUrl: string) => void;
  reset: () => void;
}

export interface RepoIngestOptions {
  /** How often a running job is polled. Overridable so tests need no timers. */
  intervalMs?: number;
}

/**
 * Drive one ingestion job and follow it to completion.
 *
 * The job is tracked server-side, so this only has to start it and poll. The
 * interval is cleared on completion, on unmount, and whenever the component
 * re-renders with a new URL, so an unmounted panel cannot keep polling.
 */
export function useRepoIngest(options: RepoIngestOptions = {}): RepoIngestState {
  const intervalMs = options.intervalMs ?? POLL_INTERVAL_MS;
  const [state, setState] = useState<RequestState>("idle");
  const [job, setJob] = useState<IngestJobResponse | null>(null);
  const [failure, setFailure] = useState<ApiFailure | null>(null);
  const timer = useRef<ReturnType<typeof setInterval> | null>(null);
  const active = useRef(true);

  const clear = useCallback(() => {
    if (timer.current) {
      clearInterval(timer.current);
      timer.current = null;
    }
  }, []);

  useEffect(() => {
    active.current = true;
    return () => {
      active.current = false;
      clear();
    };
  }, [clear]);

  const watch = useCallback(
    (jobId: number) => {
      clear();
      timer.current = setInterval(async () => {
        try {
          const next = await fetchIngestJob(jobId);
          if (!active.current) return;
          setJob(next);

          if (TERMINAL.has(next.status)) {
            clear();
            setState("success");
          }
        } catch (error) {
          if (!active.current) return;
          clear();
          const status = error instanceof ApiError ? error.status : 0;
          setFailure({
            message: error instanceof Error ? error.message : "Polling failed",
            status,
          });
          setState("error");
        }
      }, intervalMs);
    },
    [clear, intervalMs],
  );

  const start = useCallback(
    (repositoryUrl: string) => {
      const trimmed = repositoryUrl.trim();
      if (!trimmed) {
        setFailure({ message: "Enter a repository URL", status: 0 });
        setState("error");
        return;
      }

      setState("loading");
      setFailure(null);

      startIngest({ repository_url: trimmed })
        .then((created) => {
          if (!active.current) return;
          setJob(created);
          if (TERMINAL.has(created.status)) {
            setState("success");
            return;
          }
          watch(created.id);
        })
        .catch((error: unknown) => {
          if (!active.current) return;
          setFailure({
            message: error instanceof Error ? error.message : "Ingestion could not start",
            status: error instanceof ApiError ? error.status : 0,
          });
          setState("error");
        });
    },
    [watch],
  );

  const reset = useCallback(() => {
    clear();
    setJob(null);
    setFailure(null);
    setState("idle");
  }, [clear]);

  return { state, job, failure, start, reset };
}