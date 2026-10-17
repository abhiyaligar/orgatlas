export interface HealthResponse {
  status: string;
  service: string;
  environment: string;
  version: string;
}

export interface DemoPrompt {
  id: string;
  prompt: string;
  intent: string;
  expected_entities: string[];
}

export interface Citation {
  source_id: string;
  title: string;
  type: "document" | "incident" | "pull_request" | "ticket" | "adr" | string;
  url?: string;
  excerpt?: string;
  author?: string;
  created_at?: string;
}

export interface GraphNode {
  id: string;
  label:
    | "Organization"
    | "Team"
    | "Person"
    | "Service"
    | "Repository"
    | "Document"
    | "Decision"
    | "Incident"
    | "PullRequest"
    | "Ticket"
    | "Technology"
    | "OnboardingTopic"
    | string;
  name: string;
  properties: Record<string, unknown>;
}

export interface GraphEdge {
  id: string;
  source: string;
  target: string;
  type: string;
  properties: Record<string, unknown>;
}

export interface EvidenceSubgraph {
  nodes: GraphNode[];
  edges: GraphEdge[];
  paths: string[];
}

export interface AskQuestionRequest {
  question: string;
  context?: string;
  session_id?: string;
}

export interface AskQuestionResponse {
  answer: string;
  evidence_summary: string;
  citations: Citation[];
  graph: EvidenceSubgraph;
  confidence: "supported" | "partial" | "insufficient";
  suggested_questions: string[];
}

export interface OnboardingTopic {
  id: string;
  title: string;
  sequence: number;
  summary: string;
  resources: string[];
}

export interface OwnedService {
  id: string;
  name: string;
  description: string;
  criticality: "critical" | "high" | "medium" | "low" | string;
  repository_url?: string;
  maintainers: string[];
}

export interface PersonSummary {
  id: string;
  name: string;
  role: string;
  expertise: string[];
}

export interface OnboardingMapResponse {
  team_id: string;
  team_name: string;
  mission: string;
  topics: OnboardingTopic[];
  owned_services: OwnedService[];
  people_to_meet: PersonSummary[];
  reading_list: Citation[];
  graph: EvidenceSubgraph;
}

export interface EntityDetailResponse {
  id: string;
  label: string;
  name: string;
  properties: Record<string, unknown>;
  neighbors: Array<{
    relationship: string;
    direction: "incoming" | "outgoing";
    node: GraphNode;
  }>;
  citations: Citation[];
}


/* ---------------------------------------------------------------------------
 * Repository ingestion and change forensics.
 * These mirror the Pydantic response models in backend/app/api/schemas.py.
 * ------------------------------------------------------------------------- */

export interface RepositorySummary {
  id: string;
  name: string;
  url: string;
  source?: string | null;
  commit_count: number;
  file_count: number;
  dependencies: RepositorySummary[];
}

export interface FileChurn {
  file_id: string;
  path: string;
  is_test: boolean;
  changes: number;
}

export interface CommitSummary {
  sha: string;
  message: string;
  authored_at?: string | null;
  pr_number?: number | null;
  author: string;
  paths: string[];
}

export interface Contributor {
  author_id: string;
  author: string;
  commits: number;
}

export interface DependencyRef {
  id: string;
  name: string;
  url?: string | null;
}

export interface CoupledFile {
  file_id: string;
  path: string;
  shared_commits: number;
}

export interface InvestigationBriefResponse {
  repository_id: string;
  path_prefix: string;
  hotspots: FileChurn[];
  contributors: Contributor[];
  dependency_blast_radius: DependencyRef[];
  guidance: string[];
}

export interface ChurnResponse {
  repository_id: string;
  path_prefix: string;
  files: FileChurn[];
  hotspots: FileChurn[];
}

export interface CommitListResponse {
  repository_id: string;
  commits: CommitSummary[];
}

export interface FileTimelineResponse {
  file_id: string;
  path: string;
  repository_id: string;
  change_count: number;
  history: CommitSummary[];
  contributors: Contributor[];
  citations: Citation[];
  graph: EvidenceSubgraph;
}

export interface CouplingResponse {
  file_id: string;
  path: string;
  coupled: CoupledFile[];
  advice: string;
}

export interface DescriptionProvenance {
  origin: string;
  model: string;
  generated_at: string;
  input_sha: string;
  trigger: string;
  prompt_version: string;
  usage: Record<string, number>;
  error: string;
}

export interface FileDescriptionResponse {
  file_id: string;
  path: string;
  name: string;
  language: string;
  is_test: boolean;
  repository_id: string;
  summary: string;
  symbols: string[];
  docs_source: string;
  docs_at_sha: string;
  stale: boolean;
  staleness_reason: string;
  changes_since_docs: number;
  recent_shas: string[];
  provenance: DescriptionProvenance;
  raw_response: string;
}

export interface SymbolMatch {
  symbol_id: string;
  name: string;
  kind: string;
  signature: string;
  doc_comment: string;
  documented: boolean;
  line: number;
  visibility: string;
  container: string;
  language: string;
  file_id: string;
  path: string;
  repository_id: string;
  is_test: boolean;
  changes_since_docs: number;
  recent_history: CommitSummary[];
}

export interface SymbolDescriptionResponse {
  query: string;
  file_id: string;
  match_count: number;
  matches: SymbolMatch[];
  guidance: string[];
  notes: string[];
}

export interface IngestRequest {
  repository_url: string;
}

export type IngestStatus =
  | "queued"
  | "cloning"
  | "parsing"
  | "writing"
  | "describing"
  | "done"
  | "failed";

export interface IngestJobResponse {
  id: number;
  repository_url: string;
  repository_id?: string | null;
  status: IngestStatus | string;
  stage_detail?: string | null;
  commits_ingested: number;
  files_indexed: number;
  identities_resolved: number;
  error_message?: string | null;
  created_at?: string | null;
  completed_at?: string | null;
}