import type { AnswerResult } from "../api/documents";

export interface StatusText {
  label: string;
  meaning: string;
  /** The `Badge` variant that carries the status colour. */
  variant: "success" | "info" | "warning" | "neutral";
}

/**
 * Status labels that keep the server's guarantee. `ok` only means at least
 * one valid citation; it claims verification only when the server reports
 * `verified: true`. The `error` status has no entry: a failed turn shows a
 * failure line with Retry instead.
 */
export function answerStatus(result: AnswerResult): StatusText {
  switch (result.status) {
    case "ok":
      return result.verified === true
        ? {
            label: "Cited and verified",
            meaning: "The answer has at least one valid citation. Claim verification passed for every cited claim.",
            variant: "success",
          }
        : {
            label: "Cited",
            meaning: "The answer has at least one valid citation from the supplied evidence. No verifier checked the claims.",
            variant: "info",
          };
    case "no_evidence":
      return { label: "No evidence", meaning: "Retrieval found nothing. No model was called.", variant: "neutral" };
    case "generation_unverified":
      return {
        label: "Unverified answer",
        meaning: "The answer has no valid citation. Treat it as unsupported. The retrieved evidence is listed below.",
        variant: "warning",
      };
    case "unverified_claims":
      return {
        label: "Unverified claims",
        meaning: "Claim verification found cited claims that the evidence does not support. The answer, citations and evidence are kept.",
        variant: "warning",
      };
    default:
      return { label: `Unknown status: ${String(result.status)}`, meaning: "This client does not know this status.", variant: "neutral" };
  }
}

/** One friendly line for an answer the engine reported as failed. The raw message goes to the console only. */
export function failureLine(result: AnswerResult): string {
  console.error(result.error ?? "The answer failed.", result);
  if (result.failure_stage === "retrieval") return "The knowledge base could not search for evidence.";
  if (result.failure_stage === "generation") return "The model could not write an answer from the evidence.";
  return "The answer could not be completed.";
}
