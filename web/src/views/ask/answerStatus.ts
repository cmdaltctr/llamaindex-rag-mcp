import type { AnswerResult } from "../../api/documents";

export interface StatusText {
  label: string;
  meaning: string;
}

/**
 * Status labels that keep the server's guarantee. `ok` only means at least
 * one valid citation; it claims verification only when the server reports
 * `verified: true`.
 */
export function answerStatus(result: AnswerResult): StatusText {
  switch (result.status) {
    case "ok":
      return result.verified === true
        ? {
            label: "Cited and verified",
            meaning: "The answer has at least one valid citation. Claim verification passed for every cited claim.",
          }
        : {
            label: "Cited",
            meaning: "The answer has at least one valid citation from the supplied evidence. No verifier checked the claims.",
          };
    case "no_evidence":
      return { label: "No evidence", meaning: "Retrieval found nothing. No model was called." };
    case "generation_unverified":
      return {
        label: "Unverified answer",
        meaning: "The answer has no valid citation. Treat it as unsupported. The retrieved evidence is listed below.",
      };
    case "unverified_claims":
      return {
        label: "Unverified claims",
        meaning: "Claim verification found cited claims that the evidence does not support. The answer, citations and evidence are kept.",
      };
    case "error":
      return {
        label: result.failure_stage ? `Failed during ${result.failure_stage}` : "Failed",
        meaning: [result.failure_stage === "retrieval" ? "The model was not called." : null, result.error]
          .filter((part): part is string => Boolean(part))
          .join(" "),
      };
    default:
      return { label: `Unknown status: ${String(result.status)}`, meaning: "This client does not know this status." };
  }
}
