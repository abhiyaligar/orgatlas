import { useEffect } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";

import type { GraphEdge, GraphNode } from "@/types";

interface NodeDetailModalProps {
  node: GraphNode | null;
  edges: GraphEdge[];
  onClose: () => void;
}

function formatValue(value: unknown): string {
  if (value === null || value === undefined) return "—";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

export function NodeDetailModal({ node, edges, onClose }: NodeDetailModalProps) {
  useEffect(() => {
    if (!node) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [node, onClose]);

  if (!node) return null;

  const connections = edges
    .filter((edge) => edge.source === node.id || edge.target === node.id)
    .map((edge) => ({
      id: edge.id,
      type: edge.type,
      direction: edge.source === node.id ? "outgoing" : "incoming",
      other: edge.source === node.id ? edge.target : edge.source,
    }));

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label={`Details for ${node.name}`}
      className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/80 p-4"
      onClick={onClose}
    >
      <div
        className="max-h-[80vh] w-full max-w-lg overflow-y-auto rounded-lg border border-border bg-card p-5"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="mb-4 flex items-start justify-between gap-3">
          <div className="space-y-1">
            <h2 className="text-base font-semibold">{node.name || node.id}</h2>
            <Badge variant="outline">{node.label}</Badge>
          </div>
          <Button variant="ghost" size="sm" onClick={onClose} aria-label="Close node details">
            Close
          </Button>
        </div>

        <section className="space-y-2">
          <h3 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            Properties
          </h3>
          <dl className="grid grid-cols-[8rem_1fr] gap-x-3 gap-y-1 text-xs">
            {Object.entries(node.properties).map(([key, value]) => (
              <div key={key} className="contents">
                <dt className="truncate text-muted-foreground">{key}</dt>
                <dd className="break-words">{formatValue(value)}</dd>
              </div>
            ))}
          </dl>
        </section>

        <section className="mt-5 space-y-2">
          <h3 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            Connections ({connections.length})
          </h3>
          {connections.length > 0 ? (
            <ul className="space-y-1 text-xs">
              {connections.map((connection) => (
                <li key={connection.id} className="flex items-center gap-2">
                  <Badge variant="outline" className="shrink-0">
                    {connection.type}
                  </Badge>
                  <span className="text-muted-foreground">{connection.direction}</span>
                  <span className="font-mono">{connection.other}</span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-xs text-muted-foreground">No relationships in this subgraph.</p>
          )}
        </section>
      </div>
    </div>
  );
}