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

