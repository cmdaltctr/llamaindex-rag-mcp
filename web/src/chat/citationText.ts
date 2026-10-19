import type { Citation } from "../api/documents";
import { formatScore, scoreKindLabel } from "../lib/labels";

export function scoreText(item: Citation): string | null {
  if (item.score === null || item.score === undefined || !item.score_kind) return null;
  return `Score ${formatScore(item.score)}, ${scoreKindLabel(item.score_kind)}`;
}

/** The last path segment, so a chip stays short. The full source shows in the chunk viewer. */
export function sourceName(source: string | null): string {
  if (source === null) return "Unknown source";
  return source.split(/[/\\]/).filter(Boolean).at(-1) ?? source;
}
