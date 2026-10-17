import { useCallback, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { fetchSymbols } from "@/services/apiClient";
import type { SymbolDescriptionResponse } from "@/types";

/**
 * Symbol lookup against the ingested code.
 *
 * The backend applies the same grounding rules here as everywhere else: every
 * result names the file and line it came from, and undocumented symbols are
 * labelled as such rather than given invented meaning.
 */
export function SymbolLookup({ fileId }: { fileId?: string } = {}) {
  const [name, setName] = useState("");
  const [result, setResult] = useState<SymbolDescriptionResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [searching, setSearching] = useState(false);

  const search = useCallback(() => {
    const trimmed = name.trim();
    if (!trimmed) return;
    setSearching(true);
    fetchSymbols(trimmed, fileId ?? "", 10)
      .then((data) => {
        setResult(data);
        setError(null);
      })
      .catch((cause: unknown) => {
        setError(cause instanceof Error ? cause.message : "Symbol lookup failed");
        setResult(null);
      })
      .finally(() => setSearching(false));
  }, [fileId, name]);

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Symbol lookup</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <form
          className="flex items-end gap-2"
          onSubmit={(event) => {
            event.preventDefault();
            search();
          }}
        >
          <div className="flex-1 space-y-1">
            <label htmlFor="symbol-name" className="text-sm text-muted-foreground">
              Symbol name
            </label>
            <Input
              id="symbol-name"
              value={name}
              onChange={(event) => setName(event.target.value)}
              placeholder="open_connection"
            />
          </div>
          <button
            type="submit"
            disabled={searching}
            className="h-9 rounded-md bg-primary px-4 text-sm text-primary-foreground disabled:opacity-50"
          >
            {searching ? "Searching" : "Search"}
          </button>
        </form>

        {error ? <p className="text-sm text-destructive">{error}</p> : null}

        {result ? (
          <>
            <p className="text-xs text-muted-foreground">
              {result.match_count} match{result.match_count === 1 ? "" : "es"}
            </p>
            {result.guidance.map((line) => (
              <p key={line} className="text-xs text-muted-foreground">
                {line}
              </p>
            ))}
            <ul className="space-y-2">
              {result.matches.map((match) => (
                <li key={match.symbol_id} className="rounded-md border border-border p-2">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="font-mono text-sm">{match.name}</span>
                    <Badge variant={match.documented ? "success" : "warning"}>
                      {match.documented ? "documented" : "undocumented"}
                    </Badge>
                    <Badge variant="outline">{match.visibility}</Badge>
                  </div>
                  <p className="font-mono text-xs text-muted-foreground">{match.signature}</p>
                  <p className="text-xs text-muted-foreground">
                    {match.path}:{match.line}
                  </p>
                  {match.doc_comment ? (
                    <p className="mt-1 text-xs">{match.doc_comment}</p>
                  ) : null}
                </li>
              ))}
            </ul>
          </>
        ) : null}
      </CardContent>
    </Card>
  );
}