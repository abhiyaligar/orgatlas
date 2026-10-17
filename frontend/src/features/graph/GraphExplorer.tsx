import { useState } from "react";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { EvidenceGraph } from "@/features/graph/EvidenceGraph";
import { EvidenceTrail } from "@/features/graph/EvidenceTrail";
import { NodeDetailModal } from "@/features/graph/NodeDetailModal";

import type { EvidenceSubgraph, GraphNode } from "@/types";

interface GraphExplorerProps {
  graph: EvidenceSubgraph | null;
}

export function GraphExplorer({ graph }: GraphExplorerProps) {
  const [selectedNode, setSelectedNode] = useState<GraphNode | null>(null);
  const [focusedNodeId, setFocusedNodeId] = useState<string | null>(null);

  const focusedName =
    graph?.nodes.find((node) => node.id === focusedNodeId)?.name ?? null;

  return (
    <div className="space-y-4">
      {graph && graph.paths.length > 0 ? (
        <Card>
          <CardHeader>
            <CardTitle className="text-sm">Nodes touched, in order</CardTitle>
          </CardHeader>
          <CardContent>
            <EvidenceTrail paths={graph.paths} focusedNodeName={focusedName} />
          </CardContent>
        </Card>
      ) : null}

      <Card>
        <CardHeader>
          <CardTitle className="text-sm">Evidence graph</CardTitle>
        </CardHeader>
        <CardContent>
          <EvidenceGraph
            graph={graph ?? { nodes: [], edges: [], paths: [] }}
            highlightedNodeId={focusedNodeId}
            onNodeSelect={(node) => {
              setSelectedNode(node);
              setFocusedNodeId(node.id);
            }}
          />
        </CardContent>
      </Card>

      <NodeDetailModal
        node={selectedNode}
        edges={graph?.edges ?? []}
        onClose={() => setSelectedNode(null)}
      />
    </div>
  );
}