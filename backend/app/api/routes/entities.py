from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter

from app.api.schemas import EntityDetailResponse
from app.core.errors import EntityNotFoundError
from app.evidence.formatter import build_graph_node, safe_str
from app.evidence.service import EvidenceService
from app.graph.gateway import graph_gateway

router = APIRouter(prefix="/entity", tags=["Entities"])

_evidence = EvidenceService()

NEIGHBOUR_KEYS = {"outgoing": "target", "incoming": "source"}
SOURCE_LABELS = {"document", "incident", "ticket", "pullrequest"}


def _collect_neighbours(
    relations: Optional[List[Dict[str, Any]]], direction: str
) -> Tuple[List[Dict[str, Any]], List[Any]]:
    """Split raw relationship maps into neighbour entries and their source candidates."""
    neighbours: List[Dict[str, Any]] = []
    sources: List[Any] = []

    for relation in relations or []:
        if not isinstance(relation, dict):
            continue
        related = relation.get(NEIGHBOUR_KEYS[direction])
        graph_node = build_graph_node(related)
        if graph_node is None:
            continue

        neighbours.append(
            {
                "relationship": safe_str(relation.get("rel")),
                "direction": direction,
                "node": graph_node.model_dump(),
            }
        )
        if graph_node.label.lower() in SOURCE_LABELS:
            sources.append(related)

    return neighbours, sources


@router.get("/{entity_id}", response_model=EntityDetailResponse)
async def get_entity_detail(entity_id: str):
    """Return a graph entity with its outgoing and incoming neighbours."""
    data = graph_gateway.get_entity_detail(entity_id)
    entity_node = build_graph_node(data.get("entity")) if data else None
    if entity_node is None:
        raise EntityNotFoundError(entity_id)

    outgoing, outgoing_sources = _collect_neighbours(data.get("outgoing"), "outgoing")
    incoming, incoming_sources = _collect_neighbours(data.get("incoming"), "incoming")

    citations = _evidence.normalize_citations(outgoing_sources + incoming_sources, source_type="document")

    return EntityDetailResponse(
        id=entity_node.id,
        label=entity_node.label,
        name=entity_node.name,
        properties=entity_node.properties,
        neighbors=outgoing + incoming,
        citations=citations,
    )