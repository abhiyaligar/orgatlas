import { useState } from "react";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { EvidenceGraph } from "@/features/graph/EvidenceGraph";
import { NodeDetailModal } from "@/features/graph/NodeDetailModal";

import type { EvidenceSubgraph, GraphNode } from "@/types";

interface GraphExplorerProps {
  graph: EvidenceSubgraph | null;
}

export function GraphExplorer({ graph }: GraphExplorerProps) {
  const [selectedNode, setSelectedNode] = useState<GraphNode | null>(null);
  const [focusedNodeId, setFocusedNodeId] = useState<string | null>(null);

  return (
    <div className="space-y-4">
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

      {graph && graph.paths.length > 0 ? (
        <Card>
          <CardHeader>
            <CardTitle className="text-sm">Readable paths</CardTitle>
          </CardHeader>
          <CardContent>
            <ol className="space-y-2">
              {graph.paths.map((path, index) => (
                <li
                  key={index}
                  className="rounded border border-border bg-muted/40 px-3 py-2 font-mono text-xs"
                >
                  {path}
                </li>
              ))}
            </ol>
          </CardContent>
        </Card>
      ) : null}

      <NodeDetailModal
        node={selectedNode}
        edges={graph?.edges ?? []}
        onClose={() => setSelectedNode(null)}
      />
    </div>
  );
}