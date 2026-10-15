import { ApiError } from "../api/client";
import { describeError } from "../lib/errors";

const REFUSALS: Record<string, string> = {
  // Folder creation.
  traversal: 'A folder name cannot contain "..".',
  not_relative: "Enter a path inside the root, not a full path.",
  too_deep: "A folder can be at most four levels deep.",
  invalid_name: "Use letters, numbers, dots, dashes, underscores and spaces. A name must start and end with a letter or number.",
  symlink_escape: "A link in that path leads out of the root. Choose another path.",
  not_a_directory: "A file already uses that name. Choose another name.",
  root_unknown: "That root is not approved on this server.",
  root_required: "Choose a root first, because this server approves more than one.",
  exists: "That folder already exists.",
  // Experiment registration.
  not_found: "That folder does not exist.",
  outside_root: "That folder is outside every approved experiment root.",
  overlaps_context: "That folder overlaps an experiment that is already active. Revoke it first, or choose another folder.",
  is_root: "Register a folder below the root, not the root itself.",
  action_unknown: "Choose at least one permitted action.",
  store_unknown: "That store backend is not available on this server.",
  store_not_declared: "Declare the store as an experiment factor to use another store backend.",
};

/** The stable refusal code of an experiment or folder request, when the server sent one. */
export function refusalCode(error: unknown): string | null {
  if (!(error instanceof ApiError) || error.kind !== "http") return null;
  const code = (error.body as { code?: unknown } | undefined)?.code;
  return typeof code === "string" ? code : null;
}

/**
 * One friendly line for a refused folder or experiment request, chosen by
 * the server's stable `code`. The server's own text goes to the console only.
 */
export function refusalMessage(error: unknown): string {
  const code = refusalCode(error);
  if (code !== null && REFUSALS[code] !== undefined) {
    console.error(error instanceof Error ? error.message : String(error), error);
    return REFUSALS[code];
  }
  if (error instanceof ApiError && error.status === 409) {
    console.error(error.message, error);
    return "No experiment root is approved on this server.";
  }
  return describeError(error).message;
}
