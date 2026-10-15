from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: str = "ok"
    service: str = "orgatlas-api"
    environment: str
    version: str = "0.1.0"


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
