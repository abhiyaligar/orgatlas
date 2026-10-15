import { useState } from "react";

import { ErrorState, EmptyState } from "@/components/shared/RequestStates";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { AnswerPanel } from "@/features/ask/AnswerPanel";
import { DemoPromptSelector } from "@/features/ask/DemoPromptSelector";
import { EvidenceDrawer } from "@/features/ask/EvidenceDrawer";
import { useAskQuestion } from "@/hooks/useAskQuestion";

import type { Citation } from "@/types";

export function AskWorkspace() {
  const [question, setQuestion] = useState("");
  const [submitted, setSubmitted] = useState<string | null>(null);
  const [selectedCitation, setSelectedCitation] = useState<Citation | null>(null);
  const { response, pending, failure, ask } = useAskQuestion();

  const submit = (value: string) => {
    const trimmed = value.trim();
    if (!trimmed || pending) return;
    setSubmitted(trimmed);
    setSelectedCitation(null);
    void ask({ question: trimmed });
  };

  return (
    <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_20rem]">
      <div className="min-w-0 space-y-4">
        <Card>
          <CardContent className="space-y-3 py-5">
            <label htmlFor="orgatlas-question" className="text-sm font-medium">
              Ask about a system, decision, owner, or dependency
            </label>
            <form
              className="flex gap-2"
              onSubmit={(event) => {
                event.preventDefault();
                submit(question);
              }}
            >
              <Input
                id="orgatlas-question"
                value={question}
                onChange={(event) => setQuestion(event.target.value)}
                placeholder="Why does Checkout use Kafka instead of synchronous calls?"
                autoComplete="off"
              />
              <Button type="submit" disabled={pending || question.trim().length === 0}>
                {pending ? "Asking…" : "Ask"}
              </Button>
            </form>
          </CardContent>
        </Card>

        {pending ? <Skeleton className="h-40 w-full" /> : null}

        {failure ? <ErrorState failure={failure} /> : null}

        {response ? (
          <AnswerPanel
            response={response}
            onCitationSelect={setSelectedCitation}
            onFollowUp={submit}
          />
        ) : !pending && !failure ? (
          <EmptyState
            title="No question asked yet"
            description="Pick an example on the right, or type a question of your own."
          />
        ) : null}
      </div>

      <div className="space-y-4">
        <Card>
          <CardContent className="py-4">
            <h2 className="px-3 pb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              Example questions
            </h2>
            <DemoPromptSelector selectedPrompt={submitted} onSelect={submit} />
          </CardContent>
        </Card>

        {selectedCitation ? (
          <EvidenceDrawer citation={selectedCitation} onClose={() => setSelectedCitation(null)} />
        ) : null}
      </div>
    </div>
  );
}