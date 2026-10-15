import { useEffect, useRef } from "react";
import cytoscape, { type Core } from "cytoscape";

import { EmptyState } from "@/components/shared/RequestStates";
import { colorForLabel, GRAPH_STYLES, LAYOUT_OPTIONS, toCytoscapeElements } from "@/features/graph/graphConfig";

import type { EvidenceSubgraph, GraphNode } from "@/types";

interface EvidenceGraphProps {
  graph: EvidenceSubgraph;
  highlightedNodeId?: string | null;
  onNodeSelect?: (node: GraphNode) => void;
}

export function EvidenceGraph({ graph, highlightedNodeId, onNodeSelect }: EvidenceGraphProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const cyRef = useRef<Core | null>(null);
  const onNodeSelectRef = useRef(onNodeSelect);

  onNodeSelectRef.current = onNodeSelect;

  useEffect(() => {
    const container = containerRef.current;
    if (!container || graph.nodes.length === 0) return;

    const cy = cytoscape({
      container,
      elements: toCytoscapeElements(graph),
      style: GRAPH_STYLES,
      layout: LAYOUT_OPTIONS,
    });
    cyRef.current = cy;

    cy.nodes().forEach((node) => {
      const label = String(node.data("nodeLabel") ?? "");
      const color = colorForLabel(label);
      node.style({
        "background-color": color.background,
        "border-color": color.border,
        color: color.text,
      });
    });

    cy.on("tap", "node", (event) => {
      const id = event.target.id();
      const matched = graph.nodes.find((node) => node.id === id);
      if (matched) onNodeSelectRef.current?.(matched);
    });

    return () => {
      cy.destroy();
      cyRef.current = null;
    };
  }, [graph]);

  useEffect(() => {
    const cy = cyRef.current;
    if (!cy || cy.destroyed()) return;

    cy.batch(() => {
      cy.elements().removeClass("dimmed");
      cy.nodes().removeClass("highlighted");

      if (!highlightedNodeId) return;

      const target = cy.getElementById(highlightedNodeId);
      if (target.empty()) return;

      target.addClass("highlighted");
      const neighbourhood = target.closedNeighborhood();
      cy.elements().difference(neighbourhood).addClass("dimmed");
      target.connectedEdges().removeClass("dimmed");
    });
  }, [highlightedNodeId, graph]);

  if (graph.nodes.length === 0) {
    return (
      <EmptyState
        title="No graph to display"
        description="Ask a question to see the evidence path returned by the knowledge graph."
      />
    );
  }

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-muted-foreground">
        <span>
          {graph.nodes.length} nodes · {graph.edges.length} edges
        </span>
        {highlightedNodeId ? (
          <span className="font-mono">focused: {highlightedNodeId}</span>
        ) : null}
      </div>
      <div
        ref={containerRef}
        data-testid="evidence-graph-canvas"
        className="h-96 w-full rounded-md border border-border bg-slate-950"
      />
    </div>
  );
}