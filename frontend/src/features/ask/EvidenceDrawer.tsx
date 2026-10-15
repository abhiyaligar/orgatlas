import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

import type { Citation } from "@/types";

interface EvidenceDrawerProps {
  citation: Citation | null;
  onClose: () => void;
}

export function EvidenceDrawer({ citation, onClose }: EvidenceDrawerProps) {
  if (!citation) return null;

  return (
    <Card className="border-sky-500/30">
      <CardHeader className="flex flex-row items-start justify-between space-y-0">
        <CardTitle className="text-sm">Source detail</CardTitle>
        <Button variant="ghost" size="sm" onClick={onClose} aria-label="Close source detail">
          Close
        </Button>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="space-y-1">
          <p className="text-sm font-medium">{citation.title}</p>
          <div className="flex flex-wrap items-center gap-2 text-[11px] text-muted-foreground">
            <Badge variant="outline">{citation.type}</Badge>
            <span className="font-mono">{citation.source_id}</span>
          </div>
        </div>

        {citation.excerpt ? (
          <blockquote className="border-l-2 border-border pl-3 text-sm italic text-muted-foreground">
            {citation.excerpt}
          </blockquote>
        ) : (
          <p className="text-sm text-muted-foreground">No excerpt recorded for this source.</p>
        )}

        <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-xs">
          {citation.author ? (
            <>
              <dt className="text-muted-foreground">Author</dt>
              <dd>{citation.author}</dd>
            </>
          ) : null}
          {citation.created_at ? (
            <>
              <dt className="text-muted-foreground">Created</dt>
              <dd>{citation.created_at}</dd>
            </>
          ) : null}
          {citation.url ? (
            <>
              <dt className="text-muted-foreground">Link</dt>
              <dd className="truncate font-mono">{citation.url}</dd>
            </>
          ) : null}
        </dl>
      </CardContent>
    </Card>
  );
}