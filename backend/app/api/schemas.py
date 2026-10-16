from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: str = "ok"
    service: str = "orgatlas-api"
    environment: str
    version: str = "0.1.0"
    graph_connected: bool = True
    graph_name: str = ""
    graph_exists: bool = False
    available_graphs: List[str] = Field(default_factory=list)


class DemoPrompt(BaseModel):
    id: str
    prompt: str
    intent: str
    expected_entities: List[str] = Field(default_factory=list)


class Citation(BaseModel):
    source_id: str
    title: str
    type: str  # document, incident, pull_request, ticket, adr
    url: Optional[str] = None
    excerpt: Optional[str] = None
    author: Optional[str] = None
    created_at: Optional[str] = None


class GraphNode(BaseModel):
    id: str
    label: str  # Organization, Team, Person, Service, Repository, Decision, etc.
    name: str
    properties: Dict[str, Any] = Field(default_factory=dict)


class GraphEdge(BaseModel):
    id: str
    source: str
    target: str
    type: str  # OWNS, DEPENDS_ON, USES, AFFECTS, DECIDED_BY, SUPPORTED_BY, etc.
    properties: Dict[str, Any] = Field(default_factory=dict)


class EvidenceSubgraph(BaseModel):
    nodes: List[GraphNode] = Field(default_factory=list)
    edges: List[GraphEdge] = Field(default_factory=list)
    paths: List[str] = Field(default_factory=list)


class AskQuestionRequest(BaseModel):
    question: str
    context: Optional[str] = None
    session_id: Optional[str] = None


class AskQuestionResponse(BaseModel):
    answer: str
    evidence_summary: str
    citations: List[Citation] = Field(default_factory=list)
    graph: EvidenceSubgraph = Field(default_factory=EvidenceSubgraph)
    confidence: str = "supported"  # supported, partial, insufficient
    suggested_questions: List[str] = Field(default_factory=list)


class OnboardingTopic(BaseModel):
    id: str
    title: str
    sequence: int
    summary: str
    resources: List[str] = Field(default_factory=list)


class OwnedService(BaseModel):
    id: str
    name: str
    description: str
    criticality: str  # critical, high, medium, low
    repository_url: Optional[str] = None
    maintainers: List[str] = Field(default_factory=list)


class PersonSummary(BaseModel):
    id: str
    name: str
    role: str
    expertise: List[str] = Field(default_factory=list)


class OnboardingMapResponse(BaseModel):
    team_id: str
    team_name: str
    mission: str
    topics: List[OnboardingTopic] = Field(default_factory=list)
    owned_services: List[OwnedService] = Field(default_factory=list)
    people_to_meet: List[PersonSummary] = Field(default_factory=list)
    reading_list: List[Citation] = Field(default_factory=list)
    graph: EvidenceSubgraph = Field(default_factory=EvidenceSubgraph)


class EntityDetailResponse(BaseModel):
    id: str
    label: str
    name: str
    properties: Dict[str, Any] = Field(default_factory=dict)
    neighbors: List[Dict[str, Any]] = Field(default_factory=list)
    citations: List[Citation] = Field(default_factory=list)


class DecisionTraceResponse(BaseModel):
    decision_id: str
    title: str
    summary: str
    alternatives: str
    status: str
    decided_at: Optional[str] = None
    citations: List[Citation] = Field(default_factory=list)
    graph: EvidenceSubgraph = Field(default_factory=EvidenceSubgraph)


class IngestRequest(BaseModel):
    repository_url: str


class IngestJobResponse(BaseModel):
    id: int
    repository_url: str
    repository_id: Optional[str] = None
    status: str = "queued"
    stage_detail: Optional[str] = None
    commits_ingested: int = 0
    files_indexed: int = 0
    identities_resolved: int = 0
    error_message: Optional[str] = None
    created_at: Optional[str] = None
    completed_at: Optional[str] = None


class RepositorySummary(BaseModel):
    id: str
    name: str
    url: str
    source: Optional[str] = None
    commit_count: int = 0
    file_count: int = 0
    dependencies: List["RepositorySummary"] = Field(default_factory=list)


RepositorySummary.model_rebuild()


class Contributor(BaseModel):
    author_id: str = ""
    author: str = ""
    commits: int = 0


class CommitSummary(BaseModel):
    sha: str
    message: str = ""
    authored_at: Optional[str] = None
    pr_number: Optional[int] = None
    author: str = ""
    paths: List[str] = Field(default_factory=list)


class FileChurn(BaseModel):
    file_id: str
    path: str
    is_test: bool = False
    changes: int = 0


class DependencyRef(BaseModel):
    id: str
    name: str = ""
    url: Optional[str] = None


class FileTimelineResponse(BaseModel):
    file_id: str
    path: str
    repository_id: str
    change_count: int
    history: List[CommitSummary]
    contributors: List[Contributor]
    citations: List[Citation]
    graph: EvidenceSubgraph = Field(default_factory=EvidenceSubgraph)


class ChurnResponse(BaseModel):
    repository_id: str
    path_prefix: str = ""
    files: List[FileChurn]
    hotspots: List[FileChurn]


class CoupledFile(BaseModel):
    file_id: str
    path: str
    shared_commits: int


class CouplingResponse(BaseModel):
    file_id: str
    path: str
    coupled: List[CoupledFile]
    advice: str


class InvestigationBriefResponse(BaseModel):
    repository_id: str
    path_prefix: str = ""
    hotspots: List[FileChurn]
    contributors: List[Contributor]
    dependency_blast_radius: List[DependencyRef]
    guidance: List[str]


class ProvenanceResponse(BaseModel):
    commit: CommitSummary
    decisions: List[Dict[str, Any]] = Field(default_factory=list)
    citations: List[Citation] = Field(default_factory=list)
    gaps: List[str] = Field(default_factory=list)
    confidence: str = "insufficient"
    graph: EvidenceSubgraph = Field(default_factory=EvidenceSubgraph)
