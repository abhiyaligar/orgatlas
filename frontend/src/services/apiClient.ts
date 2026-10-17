import type {
  AskQuestionRequest,
  AskQuestionResponse,
  ChurnResponse,
  Citation,
  CommitSummary,
  CouplingResponse,
  DemoPrompt,
  EntityDetailResponse,
  FileDescriptionResponse,
  FileTimelineResponse,
  GraphNode,
  HealthResponse,
  IngestJobResponse,
  IngestRequest,
  InvestigationBriefResponse,
  OnboardingMapResponse,
  RepositorySummary,
  SymbolDescriptionResponse,
} from "@/types";

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000").replace(/\/+$/, "");
const API_PREFIX = "/api";

export class ApiError extends Error {
  readonly status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

interface ErrorBody {
  error?: { message?: string };
  detail?: string;
}

function describeFailure(body: ErrorBody | null, status: number): string {
  return body?.error?.message ?? body?.detail ?? `Request failed with status ${status}`;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;

  try {
    response = await fetch(`${API_BASE_URL}${API_PREFIX}${path}`, {
      headers: { "Content-Type": "application/json" },
      ...init,
    });
  } catch {
    throw new ApiError("Cannot reach the OrgAtlas API. Check that the backend is running.", 0);
  }

  if (!response.ok) {
    let body: ErrorBody | null = null;
    try {
      body = (await response.json()) as ErrorBody;
    } catch {
      body = null;
    }
    throw new ApiError(describeFailure(body, response.status), response.status);
  }

  return (await response.json()) as T;
}

export function fetchHealth(): Promise<HealthResponse> {
  return request<HealthResponse>("/health");
}

export function fetchDemoPrompts(): Promise<DemoPrompt[]> {
  return request<DemoPrompt[]>("/demo-prompts");
}

export function fetchOnboarding(teamId: string): Promise<OnboardingMapResponse> {
  return request<OnboardingMapResponse>(`/onboarding/${encodeURIComponent(teamId)}`);
}

export function fetchEntityDetails(entityId: string): Promise<EntityDetailResponse> {
  return request<EntityDetailResponse>(`/entity/${encodeURIComponent(entityId)}`);
}

export function fetchDecisionTrace(decisionId: string) {
  return request<{
    decision_id: string;
    title: string;
    summary: string;
    alternatives: string;
    status: string;
    decided_at?: string;
    citations: Citation[];
    graph: AskQuestionResponse["graph"];
  }>(`/decisions/${encodeURIComponent(decisionId)}`);
}

export function askQuestion(body: AskQuestionRequest): Promise<AskQuestionResponse> {
  return request<AskQuestionResponse>("/ask", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

/* --- Repository ingestion and change forensics ---------------------------- */

export function fetchRepositories(): Promise<RepositorySummary[]> {
  return request<RepositorySummary[]>("/repos");
}

export function fetchRepoBrief(repositoryId: string): Promise<InvestigationBriefResponse> {
  return request<InvestigationBriefResponse>(
    `/repos/${encodeURIComponent(repositoryId)}/brief`,
  );
}

export function fetchRepoChurn(
  repositoryId: string,
  pathPrefix = "",
  limit = 25,
): Promise<ChurnResponse> {
  const query = new URLSearchParams({ limit: String(limit) });
  if (pathPrefix) query.set("path_prefix", pathPrefix);
  return request<ChurnResponse>(
    `/repos/${encodeURIComponent(repositoryId)}/churn?${query.toString()}`,
  );
}

export function fetchRepoCommits(
  repositoryId: string,
  limit = 25,
  pathPrefix = "",
): Promise<CommitSummary[]> {
  const query = new URLSearchParams({ limit: String(limit) });
  if (pathPrefix) query.set("path_prefix", pathPrefix);
  return request<CommitSummary[]>(
    `/repos/${encodeURIComponent(repositoryId)}/commits?${query.toString()}`,
  );
}

export function fetchFileTimeline(fileId: string, limit = 25): Promise<FileTimelineResponse> {
  return request<FileTimelineResponse>(
    `/repos/file/timeline?file_id=${encodeURIComponent(fileId)}&limit=${limit}`,
  );
}

export function fetchFileCoupling(fileId: string, limit = 15): Promise<CouplingResponse> {
  return request<CouplingResponse>(
    `/repos/file/coupling?file_id=${encodeURIComponent(fileId)}&limit=${limit}`,
  );
}

export function fetchFileDescription(fileId: string): Promise<FileDescriptionResponse> {
  return request<FileDescriptionResponse>(
    `/repos/file/describe?file_id=${encodeURIComponent(fileId)}`,
  );
}

export function fetchSymbols(
  name: string,
  fileId = "",
  limit = 10,
): Promise<SymbolDescriptionResponse> {
  const query = new URLSearchParams({ limit: String(limit) });
  if (fileId) query.set("file_id", fileId);
  return request<SymbolDescriptionResponse>(
    `/repos/file/symbols/${encodeURIComponent(name)}?${query.toString()}`,
  );
}

export function startIngest(body: IngestRequest): Promise<IngestJobResponse> {
  return request<IngestJobResponse>("/repos/ingest", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function fetchIngestJob(jobId: number): Promise<IngestJobResponse> {
  return request<IngestJobResponse>(`/repos/ingest/${jobId}`);
}

export function nodeLabel(node: GraphNode): string {
  return node.label || "Unknown";
}