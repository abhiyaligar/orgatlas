const INLINE_PATTERN = /(\*\*[^*]+\*\*|`[^`]+`)/g;

/**
 * Render a small, fixed subset of markdown: bold spans, inline code and
 * newlines. Deliberately not a full markdown parser.
 */
export function splitInline(text: string): Array<{ type: "text" | "strong" | "code"; value: string }> {
  return text
    .split(INLINE_PATTERN)
    .filter((part) => part.length > 0)
    .map((part) => {
      if (part.startsWith("**") && part.endsWith("**")) {
        return { type: "strong" as const, value: part.slice(2, -2) };
      }
      if (part.startsWith("`") && part.endsWith("`")) {
        return { type: "code" as const, value: part.slice(1, -1) };
      }
      return { type: "text" as const, value: part };
    });
}

export function toBlocks(text: string): string[] {
  return text.split(/\n{2,}/).map((block) => block.trim()).filter(Boolean);
}