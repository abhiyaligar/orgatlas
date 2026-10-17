import { useCallback } from "react";

import { useAsyncResource, type AsyncResource } from "@/hooks/useAsyncResource";
import {
  fetchDemoPrompts,
  fetchFileDescription,
  fetchFileTimeline,
  fetchOnboarding,
  fetchRepoBrief,
  fetchRepoChurn,
  fetchRepoCommits,
  fetchRepositories,
} from "@/services/apiClient";
import type {
  ChurnResponse,
  CommitSummary,
  DemoPrompt,
  FileDescriptionResponse,
  FileTimelineResponse,
  InvestigationBriefResponse,
  OnboardingMapResponse,
  RepositorySummary,
} from "@/types";

export function useDemoPrompts(): AsyncResource<DemoPrompt[]> {
  const loader = useCallback(() => fetchDemoPrompts(), []);
  return useAsyncResource<DemoPrompt[]>(loader, []);
}

export function useOnboarding(teamId: string): AsyncResource<OnboardingMapResponse> {
  const loader = useCallback(() => fetchOnboarding(teamId), [teamId]);
  return useAsyncResource<OnboardingMapResponse>(loader, [teamId]);
}
/* --- Repository ingestion and change forensics ---------------------------- */

export function useRepositories(): AsyncResource<RepositorySummary[]> {
  const loader = useCallback(() => fetchRepositories(), []);
  return useAsyncResource<RepositorySummary[]>(loader, []);
}

export function useRepoBrief(repositoryId: string): AsyncResource<InvestigationBriefResponse> {
  const loader = useCallback(() => fetchRepoBrief(repositoryId), [repositoryId]);
  return useAsyncResource<InvestigationBriefResponse>(loader, [repositoryId]);
}

export function useFileTimeline(fileId: string): AsyncResource<FileTimelineResponse> {
  const loader = useCallback(() => fetchFileTimeline(fileId), [fileId]);
  return useAsyncResource<FileTimelineResponse>(loader, [fileId]);
}

export function useFileDescription(fileId: string): AsyncResource<FileDescriptionResponse> {
  const loader = useCallback(() => fetchFileDescription(fileId), [fileId]);
  return useAsyncResource<FileDescriptionResponse>(loader, [fileId]);
}

export function useRepoChurn(
  repositoryId: string,
  pathPrefix = "",
): AsyncResource<ChurnResponse> {
  const loader = useCallback(
    () => fetchRepoChurn(repositoryId, pathPrefix, 25),
    [repositoryId, pathPrefix],
  );
  return useAsyncResource<ChurnResponse>(loader, [repositoryId, pathPrefix]);
}

export function useRepoCommits(repositoryId: string): AsyncResource<CommitSummary[]> {
  const loader = useCallback(() => fetchRepoCommits(repositoryId, 25), [repositoryId]);
  return useAsyncResource<CommitSummary[]>(loader, [repositoryId]);
}
