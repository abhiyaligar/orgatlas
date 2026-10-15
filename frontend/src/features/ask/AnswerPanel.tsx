import { SourceCitation } from "@/components/shared/SourceCitation";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { RichText } from "@/features/ask/RichText";
import { ConfidenceBadge } from "@/features/ask/ConfidenceBadge";

import type { AskQuestionResponse, Citation } from "@/types";

interface AnswerPanelProps {
  response: AskQuestionResponse;
  onCitationSelect?: (citation: Citation) => void;
  onFollowUp?: (question: string) => void;
  highlightedNodeId?: string | null;
}

export function AnswerPanel({
  response,
  onCitationSelect,
  onFollowUp,
}: AnswerPanelProps) {
  return (
    <div className="space-y-4">
      <Card>
        <CardHeader className="flex flex-row items-center justify-between space-y-0">
          <CardTitle className="text-sm">Answer</CardTitle>
          <ConfidenceBadge confidence={response.confidence} />
        </CardHeader>
        <CardContent className="space-y-4">
          <RichText text={response.answer} />
          <p className="border-t border-border pt-3 text-xs text-muted-foreground">
            {response.evidence_summary}
          </p>
        </CardContent>
      </Card>

      {response.graph.paths.length > 0 ? (
        <Card>
          <CardHeader>
            <CardTitle className="text-sm">Evidence path</CardTitle>
          </CardHeader>
          <CardContent>
            <ol className="space-y-2">
              {response.graph.paths.map((path, index) => (
                <li
                  key={index}
                  className="rounded border border-border bg-muted/40 px-3 py-2 font-mono text-xs leading-relaxed"
                >
                  {path}
                </li>
              ))}
            </ol>
          </CardContent>
        </Card>
      ) : null}

      <Card>
        <CardHeader>
          <CardTitle className="text-sm">
            Sources {response.citations.length > 0 ? `(${response.citations.length})` : ""}
          </CardTitle>
        </CardHeader>
        <CardContent>
          {response.citations.length > 0 ? (
            <ul className="space-y-1">
              {response.citations.map((citation, index) => (
                <li key={citation.source_id}>
                  <SourceCitation
                    citation={citation}
                    index={index + 1}
                    onSelect={onCitationSelect}
                  />
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-sm text-muted-foreground">
              This answer is backed by graph relationships only. No source documents were linked to
              the entities involved.
            </p>
          )}
        </CardContent>
      </Card>

      {response.suggested_questions.length > 0 ? (
        <div className="space-y-2">
          <h3 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
            Follow up
          </h3>
          <ul className="flex flex-wrap gap-2">
            {response.suggested_questions.map((question) => (
              <li key={question}>
                <button
                  type="button"
                  onClick={() => onFollowUp?.(question)}
                  className="rounded-full border border-border px-3 py-1 text-xs text-muted-foreground transition-colors hover:bg-accent hover:text-accent-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
                >
                  {question}
                </button>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </div>
  );
}