import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";

import type { ApiFailure } from "@/types";

export function LoadingState({ label = "Loading" }: { label?: string }) {
  return (
    <div className="space-y-3" role="status" aria-live="polite">
      <span className="sr-only">{label}</span>
      <Skeleton className="h-6 w-1/3" />
      <Skeleton className="h-24 w-full" />
      <Skeleton className="h-24 w-full" />
    </div>
  );
}

export function ErrorState({ failure, onRetry }: { failure: ApiFailure; onRetry?: () => void }) {
  const isOffline = failure.status === 0;

  return (
    <Card role="alert" className="border-destructive/40">
      <CardContent className="space-y-3 py-6">
        <h3 className="text-sm font-semibold text-destructive">
          {isOffline ? "Cannot reach the API" : `Request failed (${failure.status})`}
        </h3>
        <p className="text-sm text-muted-foreground">{failure.message}</p>
        {onRetry ? (
          <Button size="sm" variant="outline" onClick={onRetry}>
            Try again
          </Button>
        ) : null}
      </CardContent>
    </Card>
  );
}

export function EmptyState({ title, description }: { title: string; description?: string }) {
  return (
    <Card>
      <CardContent className="space-y-1 py-8 text-center">
        <h3 className="text-sm font-semibold">{title}</h3>
        {description ? (
          <p className="text-sm text-muted-foreground">{description}</p>
        ) : null}
      </CardContent>
    </Card>
  );
}