/**
 * An evidence path arrives from the API as one rendered string per traversal,
 * for example: `Checkout [Service] ──USES──> Kafka [Technology]`.
 *
 * The order in that string is the order the graph was walked, which is the one
 * thing the client cannot work out for itself: a subgraph has no traversal
 * order, so re-deriving it here would invent an order the backend never chose.
 * The steps are therefore parsed out of the string the backend formatted, and
 * the unparsed text is always kept so a format change degrades to the old
 * display instead of hiding evidence.
 */

export interface PathStep {
  /** 1-based position in the traversal. */
  position: number;
  name: string;
  /** Graph label such as Service or Decision. Null when the path omitted it. */
  label: string | null;
  /** Edge type leading into this step, or null for the first one. */
  edgeIn: string | null;
}

export interface ParsedPath {
  steps: PathStep[];
  /** The original text, kept verbatim as a fallback. */
  raw: string;
}

/**
 * `──EDGE──>` is how the backend renders a hop; see evidence/formatter.py.
 * The trailing rule is deliberately loose so a hop that carries no edge type is
 * still recognised as a hop rather than swallowed into the previous node name.
 */
const HOP_PATTERN = /\u2500{2,}\s*([^\u2500>]*?)\s*\u2500*>/g;
const NODE_PATTERN = /^(.*?)\s*\[([^\]]*)\]$/;

function readNode(raw: string): { name: string; label: string | null } | null {
  const text = raw.trim();
  if (!text) return null;
  const match = NODE_PATTERN.exec(text);
  if (match) {
    const name = match[1].trim();
    if (!name) return null;
    return { name, label: match[2].trim() };
  }
  return { name: text, label: null };
}

export function parsePath(path: string): ParsedPath {
  const raw = (path ?? "").trim();
  const steps: PathStep[] = [];
  if (!raw) return { steps, raw };

  const push = (segment: string, edgeIn: string | null) => {
    const node = readNode(segment);
    if (!node) return;
    steps.push({ position: steps.length + 1, edgeIn, ...node });
  };

  let cursor = 0;
  let edgeIn: string | null = null;
  HOP_PATTERN.lastIndex = 0;
  let match = HOP_PATTERN.exec(raw);
  while (match !== null) {
    push(raw.slice(cursor, match.index), edgeIn);
    const edge = match[1].trim();
    edgeIn = edge.length > 0 ? edge : null;
    cursor = match.index + match[0].length;
    match = HOP_PATTERN.exec(raw);
  }
  push(raw.slice(cursor), edgeIn);

  return { steps, raw };
}

export function parsePaths(paths: readonly string[] | null | undefined): ParsedPath[] {
  return (paths ?? []).map(parsePath).filter((path) => path.steps.length > 0);
}