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
        message: "The workspace session was not accepted. Reload the page. If that fails, run omrs web open in a terminal.",
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

/** The text of a server error body, when the body holds one. */
function bodyMessage(body: unknown): string | null {
  if (typeof body !== "object" || body === null) return null;
  const record = body as Record<string, unknown>;
  const message = record.message ?? record.detail;
  return typeof message === "string" && message.length > 0 ? message : null;
}

/**
 * Like `describeError`, for a refused Settings save. A 400 or 409 with a
 * message in the body shows that message, because the server words it to name
 * the rule or the source and never the refused value. Everything else keeps
 * the generic text of `describeError`.
 */
export function describeSaveError(error: unknown): FriendlyError {
  if (error instanceof ApiError && error.kind === "http" && (error.status === 400 || error.status === 409)) {
    const message = bodyMessage(error.body);
    if (message !== null) {
      return { message, action: error.status === 409 ? { kind: "reload", label: "Reload" } : RETRY };
    }
  }
  return describeError(error);
}
