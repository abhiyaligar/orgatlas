import { ArrowRight } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { parsePaths, type PathStep } from "@/features/graph/pathSteps";

interface EvidenceTrailProps {
  paths: readonly string[] | null | undefined;
  /** Highlights a step whose name matches this node, so a click in the graph
   * and the trail agree on what was focused. */
  focusedNodeName?: string | null;
}

/**
 * The ordered evidence path: every node the walk touched, in the order it was
 * touched, with the edge that led into each step.
 *
 * The subgraph below shows the same nodes as a picture, which is good for
 * shape and bad for sequence. This is the answer to "what did it actually go
 * through", in the order the backend walked it.
 */
export function EvidenceTrail({ paths, focusedNodeName }: EvidenceTrailProps) {
  const parsed = parsePaths(paths);
  if (parsed.length === 0) return null;

  return (
    <div className="space-y-4">
      {parsed.map((path, pathIndex) => (
        <div key={pathIndex} className="space-y-2">
          <div className="flex items-center gap-2">
            <span className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
              {parsed.length > 1 ? `Path ${pathIndex + 1}` : "Evidence path"}
            </span>
            <span className="text-xs text-muted-foreground">
              {path.steps.length} node{path.steps.length === 1 ? "" : "s"}
            </span>
          </div>

          {path.steps.length > 1 ? (
            <ol className="flex flex-wrap items-center gap-1.5" aria-label="Evidence path">
              {path.steps.map((step, index) => (
                <li key={`${step.position}-${step.name}`} className="flex items-center gap-1.5">
                  {index > 0 ? <Hop edge={step.edgeIn} /> : null}
                  <StepChip step={step} focused={isFocused(step, focusedNodeName)} />
                </li>
              ))}
            </ol>
          ) : (
            <p className="font-mono text-xs text-muted-foreground">{path.raw}</p>
          )}
        </div>
      ))}
    </div>
  );
}

function isFocused(step: PathStep, focusedNodeName?: string | null): boolean {
  return Boolean(focusedNodeName) && step.name === focusedNodeName;
}

function Hop({ edge }: { edge: string | null }) {
  return (
    <span className="flex items-center gap-1" aria-hidden="true">
      <span className="text-[10px] uppercase tracking-wide text-muted-foreground">
        {edge ?? ""}
      </span>
      <ArrowRight className="h-3 w-3 shrink-0 text-muted-foreground" />
    </span>
  );
}

function StepChip({ step, focused }: { step: PathStep; focused: boolean }) {
  return (
    <span
      data-focused={focused ? "true" : undefined}
      className={[
        "inline-flex items-center gap-1.5 rounded-md border px-2 py-1 text-xs",
        focused
          ? "border-primary bg-primary/10 ring-1 ring-primary/40"
          : "border-border bg-muted/40",
      ].join(" ")}
    >
      <span className="font-mono text-[10px] text-muted-foreground">{step.position}</span>
      <span className="font-medium">{step.name}</span>
      {step.label ? (
        <Badge variant="secondary" className="px-1.5 py-0 text-[10px] font-normal">
          {step.label}
        </Badge>
      ) : null}
    </span>
  );
}