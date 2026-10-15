import { useDemoPrompts } from "@/hooks/useOrgAtlasData";

import type { DemoPrompt } from "@/types";

interface DemoPromptSelectorProps {
  selectedPrompt: string | null;
  onSelect: (prompt: string) => void;
}

export function DemoPromptSelector({ selectedPrompt, onSelect }: DemoPromptSelectorProps) {
  const { data, state } = useDemoPrompts();

  if (state === "loading") {
    return (
      <p className="px-3 py-2 text-xs text-muted-foreground" role="status">
        Loading example questions…
      </p>
    );
  }

  if (!data || data.length === 0) {
    return (
      <p className="px-3 py-2 text-xs text-muted-foreground">
        No example questions are available.
      </p>
    );
  }

  return (
    <ul className="space-y-1 p-2">
      {data.map((prompt: DemoPrompt) => {
        const isSelected = prompt.prompt === selectedPrompt;
        return (
          <li key={prompt.id}>
            <button
              type="button"
              onClick={() => onSelect(prompt.prompt)}
              className={
                isSelected
                  ? "w-full rounded-md bg-accent px-3 py-2 text-left text-xs font-medium text-accent-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
                  : "w-full rounded-md px-3 py-2 text-left text-xs text-muted-foreground transition-colors hover:bg-accent/60 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
              }
            >
              {prompt.prompt}
            </button>
          </li>
        );
      })}
    </ul>
  );
}