import { useCallback } from "react";

import { useAsyncResource, type AsyncResource } from "@/hooks/useAsyncResource";
import { fetchDemoPrompts, fetchOnboarding } from "@/services/apiClient";
import type { DemoPrompt, OnboardingMapResponse } from "@/types";

export function useDemoPrompts(): AsyncResource<DemoPrompt[]> {
  const loader = useCallback(() => fetchDemoPrompts(), []);
  return useAsyncResource<DemoPrompt[]>(loader, []);
}

export function useOnboarding(teamId: string): AsyncResource<OnboardingMapResponse> {
  const loader = useCallback(() => fetchOnboarding(teamId), [teamId]);
  return useAsyncResource<OnboardingMapResponse>(loader, [teamId]);
}