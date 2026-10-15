import { Badge } from "@/components/ui/badge";

import type { AskQuestionResponse } from "@/types";

const CONFIDENCE_STYLES: Record<AskQuestionResponse["confidence"], { label: string; className: string }> = {
  supported: { label: "Supported", className: "border-emerald-500/30 bg-emerald-500/15 text-emerald-300" },
  partial: { label: "Partial", className: "border-amber-500/30 bg-amber-500/15 text-amber-200" },
  insufficient: { label: "Insufficient evidence", className: "border-red-500/30 bg-red-500/15 text-red-300" },
};

interface ConfidenceBadgeProps {
  confidence: AskQuestionResponse["confidence"];
}

export function ConfidenceBadge({ confidence }: ConfidenceBadgeProps) {
  const style = CONFIDENCE_STYLES[confidence] ?? CONFIDENCE_STYLES.insufficient;

  return (
    <Badge variant="outline" className={style.className}>
      {style.label}
    </Badge>
  );
}