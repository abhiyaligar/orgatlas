"""Formatting helpers that turn raw FalkorDB records into client-ready graph payloads."""

import logging
from typing import Any, Dict, List, Optional, Sequence

from app.api.schemas import GraphEdge, GraphNode

logger = logging.getLogger(__name__)

UNKNOWN_LABEL = "Unknown"
ARROW_TEMPLATE = "──{edge_type}──>"


def safe_str(value: Any) -> str:
    """Coerce a value to string without ever returning None."""
    if value is None:
        return ""
    return str(value)


def extract_properties(node: Any) -> Dict[str, Any]:
    """Read the property mapping from a FalkorDB node, a plain dict, or None."""
    if node is None:
        return {}
    if isinstance(node, dict):
        return node
    properties = getattr(node, "properties", None)
    if isinstance(properties, dict):
        return properties
    return {}


def extract_labels(node: Any) -> List[str]:
    """Read labels from a FalkorDB node or a plain dict."""
    if node is None:
        return []
    if isinstance(node, dict):
        label = node.get("label")
        return [safe_str(label)] if label else []
    labels = getattr(node, "labels", None)
    if isinstance(labels, (list, tuple, set)):
        return [safe_str(label) for label in labels if label]
    return [safe_str(labels)] if labels else []


def display_name(node: Any) -> str:
    """Prefer a human-readable name, falling back to title then stable id."""
    properties = extract_properties(node)
    for key in ("name", "title", "id"):
        value = properties.get(key)
        if value:
            return safe_str(value)
    return ""


def build_graph_node(node: Any, label: Optional[str] = None) -> Optional[GraphNode]:
    """Convert a raw graph node into a GraphNode, or None when it carries no stable id."""
    properties = extract_properties(node)
    node_id = safe_str(properties.get("id"))
    if not node_id:
        return None

    labels = extract_labels(node)
    return GraphNode(
        id=node_id,
        label=label or (labels[0] if labels else UNKNOWN_LABEL),
        name=display_name(node),
        properties=properties,
    )


def build_graph_nodes(nodes: Sequence[Any], label: Optional[str] = None) -> List[GraphNode]:
    """Convert a collection of raw nodes, dropping any that cannot be identified."""
    built: List[GraphNode] = []
    for node in nodes or []:
        graph_node = build_graph_node(node, label=label)
        if graph_node is not None:
            built.append(graph_node)
    return built


def build_graph_edge(
    edge_id: str,
    source: str,
    target: str,
    edge_type: str,
    properties: Optional[Dict[str, Any]] = None,
) -> GraphEdge:
    """Build a GraphEdge from already-resolved node ids."""
    return GraphEdge(
        id=safe_str(edge_id),
        source=safe_str(source),
        target=safe_str(target),
        type=safe_str(edge_type),
        properties=properties or {},
    )


def render_path(
    start_name: str,
    start_label: str,
    hops: Sequence[tuple],
) -> str:
    """Render an ordered traversal as a readable path.

    Each hop is a ``(edge_type, target_name, target_label)`` tuple, producing
    output such as ``Checkout [Service] ──USES──> Kafka [Technology]``.
    """
    rendered = f"{safe_str(start_name)} [{safe_str(start_label)}]"
    for hop in hops:
        edge_type, target_name, target_label = hop
        arrow = ARROW_TEMPLATE.format(edge_type=safe_str(edge_type))
        rendered += f" {arrow} {safe_str(target_name)} [{safe_str(target_label)}]"
    return rendered


def index_nodes_by_id(nodes: Sequence[GraphNode]) -> Dict[str, GraphNode]:
    """Index graph nodes by their stable id for edge-to-path resolution."""
    return {node.id: node for node in nodes or []}


def render_edge_path(nodes: Sequence[GraphNode], edges: Sequence[GraphEdge], node_ids: Sequence[str]) -> str:
    """Render the path that visits node_ids in order, using edges to describe each hop."""
    index = index_nodes_by_id(nodes)
    chain = [node_id for node_id in node_ids if node_id in index]
    if len(chain) < 2:
        return ""

    edge_index: Dict[tuple, str] = {}
    for edge in edges or []:
        edge_index[(edge.source, edge.target)] = edge.type
        edge_index[(edge.target, edge.source)] = edge.type

    head = index[chain[0]]
    hops: List[tuple] = []
    for source_id, target_id in zip(chain, chain[1:]):
        edge_type = edge_index.get((source_id, target_id))
        if not edge_type:
            return ""
        target = index[target_id]
        hops.append((edge_type, target.name, target.label))

    return render_path(head.name, head.label, hops)