export const APP_VIEWS = ["onboarding", "ask", "repositories", "graph"] as const;

export type AppView = (typeof APP_VIEWS)[number];

export const VIEW_LABELS: Record<AppView, string> = {
  onboarding: "Onboarding Map",
  ask: "Ask & Archaeology",
  repositories: "Repositories",
  graph: "Graph Explorer",
};

export type RequestState = "idle" | "loading" | "success" | "error";

export interface ApiFailure {
  message: string;
  status: number;
}
