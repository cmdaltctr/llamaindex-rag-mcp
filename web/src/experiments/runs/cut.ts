import { boundText, MAX_PREVIEW_ROWS } from "../../runs/evidence";
import { safeEntry } from "../../runs/redact";

/** How deep `SafeValue` renders before it says "nested value not shown". */
export const MAX_DEPTH = 4;

/** Whether `SafeValue` shows less than the whole value: a text over 4 KiB, a list over 100 entries, or nesting too deep. */
export function isCut(value: unknown, depth = 0): boolean {
  if (typeof value === "string") return boundText(value).truncated;
  if (typeof value !== "object" || value === null) return false;
  if (depth >= MAX_DEPTH) return true;
  const entries = Array.isArray(value) ? value.map((item, index) => [String(index), item] as const) : Object.entries(value);
  if (entries.length > MAX_PREVIEW_ROWS) return true;
  return entries.some(([key, item]) => isCut(safeEntry(key, item), depth + 1));
}

/** A summary the server cut: it carries `truncated: true` and, when it wrote one, an `artefact_ref`. */
export function serverCut(value: unknown): { ref: unknown } | null {
  if (typeof value !== "object" || value === null || Array.isArray(value)) return null;
  const record = value as Record<string, unknown>;
  return record.truncated === true ? { ref: record.artefact_ref } : null;
}
