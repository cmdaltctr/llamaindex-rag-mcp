import { ApiError } from "../api/client";

/** What the person can do next. The view renders it as one button or link. */
export type ErrorActionKind = "retry" | "reload" | "back" | "choose-file";

export interface ErrorAction {
  kind: ErrorActionKind;
  label: string;
}

export interface FriendlyError {
  message: string;
  action: ErrorAction;
}

const RETRY: ErrorAction = { kind: "retry", label: "Retry" };

/**
 * Turns any failure into one short message and one action. The raw message
 * (parser text, status lines, stack text) goes to the console only, so it
 * never reaches the page.
 */
export function describeError(error: unknown): FriendlyError {
  console.error(error instanceof Error ? error.message : String(error), error);

  if (!(error instanceof ApiError)) return { message: "Something went wrong.", action: RETRY };

  switch (error.kind) {
    case "network":
      return { message: "The local server is not reachable.", action: RETRY };
    case "not-json":
    case "invalid-json":
      return { message: "The local server sent an unexpected reply.", action: RETRY };
    case "invalid-path":
      return { message: "That address is not valid.", action: { kind: "back", label: "Go back" } };
    case "http":
      break;
  }

  switch (error.status) {
    case 401:
    case 403:
      return {
        message: "The workspace session was not accepted. Open the workspace again from the link that omrg web prints.",
        action: { kind: "reload", label: "Reload the page" },
      };
    case 404:
      return { message: "That item could not be found.", action: { kind: "back", label: "Go back" } };
    case 413:
      return { message: "That file is larger than the server's per-file limit and was not uploaded.", action: { kind: "choose-file", label: "Choose another file" } };
    default:
      return { message: "The local server could not complete that request.", action: RETRY };
  }
}
