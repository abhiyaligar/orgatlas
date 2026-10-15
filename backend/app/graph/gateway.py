import logging
from typing import Any, Dict, List, Optional

from app.graph.connection import graph_manager
from app.graph import queries

logger = logging.getLogger(__name__)


class GraphGateway:
    """Gateway for executing parameterized and bounded OpenCypher queries on FalkorDB."""

    def __init__(self, manager=graph_manager):
        self.manager = manager

    def _execute(self, query: str, params: Optional[Dict[str, Any]] = None) -> List[Any]:
        try:
            graph = self.manager.get_graph()
            result = graph.query(query, params or {})
            return result.result_set
        except Exception as e:
            logger.warning("FalkorDB query failed (%s). Returning empty result: %s", query[:60], str(e))
            return []

    def get_onboarding_context(self, team_id: str) -> Optional[Dict[str, Any]]:
        rows = self._execute(queries.GET_ONBOARDING_TOPICS_BY_TEAM, {"team_id": team_id})
        if not rows or not rows[0]:
            return None
        row = rows[0]
        return {
            "team_id": row[0],
            "team_name": row[1],
            "team_mission": row[2],
            "topics": row[3] or [],
            "services": row[4] or [],
            "people": row[5] or [],
        }

    def get_decision_trace(self, decision_id: str) -> Optional[Dict[str, Any]]:
        rows = self._execute(queries.GET_DECISION_TRACE, {"decision_id": decision_id})
        if not rows or not rows[0] or rows[0][0] is None:
            return None
        row = rows[0]
        return {
            "decision": row[0],
            "people": row[1] or [],
            "teams": row[2] or [],
            "services": row[3] or [],
            "documents": row[4] or [],
            "incidents": row[5] or [],
            "pull_requests": row[6] or [],
            "tickets": row[7] or [],
        }

    def get_change_impact(self, service_id: str) -> Optional[Dict[str, Any]]:
        rows = self._execute(queries.GET_CHANGE_IMPACT, {"service_id": service_id})
        if not rows or not rows[0] or rows[0][0] is None:
            return None
        row = rows[0]
        return {
            "target_service": row[0],
            "owner_team": row[1],
            "downstream_services": row[2] or [],
            "upstream_services": row[3] or [],
            "incidents": row[4] or [],
            "decisions": row[5] or [],
        }

    def get_service_ownership(self, service_id: str) -> Optional[Dict[str, Any]]:
        rows = self._execute(queries.GET_SERVICE_OWNERSHIP, {"service_id": service_id})
        if not rows or not rows[0] or rows[0][0] is None:
            return None
        row = rows[0]
        return {
            "service": row[0],
            "team": row[1],
            "team_members": row[2] or [],
            "contributors": row[3] or [],
            "repository": row[4],
        }

    def get_entity_detail(self, entity_id: str) -> Optional[Dict[str, Any]]:
        rows = self._execute(queries.GET_ENTITY_DETAIL, {"entity_id": entity_id})
        if not rows or not rows[0] or rows[0][0] is None:
            return None
        row = rows[0]
        return {
            "entity": row[0],
            "outgoing": row[1] or [],
            "incoming": row[2] or [],
        }

    def search_entities(self, query_str: str) -> List[Dict[str, Any]]:
        rows = self._execute(queries.SEARCH_ENTITIES, {"query": query_str})
        results = []
        for row in rows:
            results.append({
                "id": row[0],
                "label": row[1],
                "name": row[2],
                "properties": row[3] or {},
            })
        return results


graph_gateway = GraphGateway()
