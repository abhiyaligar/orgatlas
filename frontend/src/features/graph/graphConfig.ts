import type { ElementDefinition, StylesheetJson } from "cytoscape";

import type { EvidenceSubgraph } from "@/types";

export const LABEL_COLORS: Record<string, { background: string; border: string; text: string }> = {
  Service: { background: "#1d4ed8", border: "#60a5fa", text: "#eff6ff" },
  Decision: { background: "#b45309", border: "#fbbf24", text: "#fffbeb" },
  Incident: { background: "#b91c1c", border: "#f87171", text: "#fef2f2" },
  Document: { background: "#15803d", border: "#4ade80", text: "#f0fdf4" },
  Person: { background: "#7e22ce", border: "#c084fc", text: "#faf5ff" },
  Technology: { background: "#475569", border: "#94a3b8", text: "#f8fafc" },
  Team: { background: "#0f766e", border: "#2dd4bf", text: "#f0fdfa" },
  Repository: { background: "#334155", border: "#64748b", text: "#f8fafc" },
  OnboardingTopic: { background: "#0369a1", border: "#38bdf8", text: "#f0f9ff" },
};

export const FALLBACK_COLOR = { background: "#1e293b", border: "#64748b", text: "#e2e8f0" };

export function colorForLabel(label: string) {
  return LABEL_COLORS[label] ?? FALLBACK_COLOR;
}

export const HIGHLIGHT_BORDER = "#f8fafc";
export const DIMMED_OPACITY = 0.2;

export const GRAPH_STYLES: StylesheetJson = [
  {
    selector: "node",
    style: {
      label: "data(label)",
      color: "#e2e8f0",
      "font-size": 10,
      "text-valign": "bottom",
      "text-margin-y": 6,
      "text-wrap": "wrap",
      "text-max-width": "90px",
      width: 26,
      height: 26,
      "background-color": "#1e293b",
      "border-color": "#64748b",
      "border-width": 2,
    },
  },
  {
    selector: "edge",
    style: {
      width: 1.5,
      "line-color": "#475569",
      "target-arrow-color": "#475569",
      "target-arrow-shape": "triangle",
      "curve-style": "bezier",
      label: "data(type)",
      "font-size": 8,
      color: "#94a3b8",
      "text-rotation": "autorotate",
      "text-margin-y": -6,
    },
  },
  {
    selector: "node.highlighted",
    style: {
      "border-color": HIGHLIGHT_BORDER,
      "border-width": 4,
      width: 32,
      height: 32,
    },
  },
  {
    selector: "node.dimmed",
    style: { opacity: DIMMED_OPACITY },
  },
  {
    selector: "edge.dimmed",
    style: { opacity: DIMMED_OPACITY },
  },
];

export function toCytoscapeElements(graph: EvidenceSubgraph): ElementDefinition[] {
  const nodes: ElementDefinition[] = graph.nodes.map((node) => ({
    group: "nodes" as const,
    data: {
      id: node.id,
      label: node.name || node.id,
      nodeLabel: node.label,
      properties: node.properties,
    },
  }));

  const known = new Set(graph.nodes.map((node) => node.id));
  const edges: ElementDefinition[] = graph.edges
    .filter((edge) => known.has(edge.source) && known.has(edge.target))
    .map((edge) => ({
      group: "edges" as const,
      data: { id: edge.id, source: edge.source, target: edge.target, type: edge.type },
    }));

  return [...nodes, ...edges];
}

export const LAYOUT_OPTIONS = {
  name: "breadthfirst",
  directed: true,
  padding: 24,
  spacingFactor: 1.2,
} as const;