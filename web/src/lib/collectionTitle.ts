import type { CollectionInfo } from "../api/documents";

/** Longest display name, in Unicode code points. The server enforces the same limit. */
export const DISPLAY_NAME_MAX = 80;

/** The title shown for a collection: its display name, else its collection name. */
export function collectionTitle(info: Pick<CollectionInfo, "name" | "display_name">): string {
  return info.display_name ?? info.name;
}

/**
 * Why a display name would be refused, or `null` when it is fine (an empty
 * value is fine: it clears the name). It follows the server's rules, so the
 * editor can say so before sending. The server stays the authority.
 */
export function displayNameProblem(raw: string): string | null {
  const value = raw.trim();
  // eslint-disable-next-line no-control-regex -- control characters are exactly what is refused
  if (/[\u0000-\u001F\u007F]/.test(value)) return "The name must not contain control characters.";
  if ([...value].length > DISPLAY_NAME_MAX) return `The name must be at most ${DISPLAY_NAME_MAX} characters.`;
  return null;
}
