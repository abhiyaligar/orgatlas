import { Badge } from "@/components/ui/badge";

import type { Citation } from "@/types";

interface SourceCitationProps {
  citation: Citation;
  index: number;
  onSelect?: (citation: Citation) => void;
}

export function SourceCitation({ citation, index, onSelect }: SourceCitationProps) {
  const body = (
    <>
      <span className="flex h-5 min-w-5 shrink-0 items-center justify-center rounded border border-border text-[11px] font-semibold">
        {index}
      </span>
      <span className="min-w-0 space-y-1">
        <span className="block text-sm font-medium">{citation.title}</span>
        {citation.excerpt ? (
          <span className="block text-xs text-muted-foreground line-clamp-2">{citation.excerpt}</span>
        ) : null}
        <span className="flex items-center gap-2 text-[11px] text-muted-foreground">
          <Badge variant="outline">{citation.type}</Badge>
          <span className="font-mono opacity-70">{citation.source_id}</span>
        </span>
      </span>
    </>
  );

  if (!onSelect) {
    return <div className="flex items-start gap-3">{body}</div>;
  }

  return (
    <button
      type="button"
      onClick={() => onSelect(citation)}
      className="flex w-full items-start gap-3 rounded-md p-2 text-left transition-colors hover:bg-accent focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
    >
      {body}
    </button>
  );
}