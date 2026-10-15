import type { ConnectionProvider, ConnectionRole } from "../api/settings";

export const PROVIDER_NAMES: Record<ConnectionProvider, string> = { ollama: "Ollama", llamacpp: "llama.cpp", openrouter: "OpenRouter" };

export const ROLE_NAMES: Record<ConnectionRole, string> = {
  embeddings: "Embeddings",
  answers: "Answers",
  metadata: "Metadata",
  verification: "Verification",
};

const HTTP_REASON = /^http-(\d{3})$/;

/** The fixed reasons the server may return. Anything else is not shown as raw text. */
export function isKnownReason(reason: string): boolean {
  return ["refused", "timeout", "unauthorised", "not-configured"].includes(reason) || HTTP_REASON.test(reason);
}

/** A plain-words sentence for one connection-test reason. */
export function reasonSentence(reason: string): string {
  switch (reason) {
    case "refused":
      return "The connection was refused. Nothing is listening at that address.";
    case "timeout":
      return "The provider did not answer within 5 seconds.";
    case "unauthorised":
      return "The key was not accepted by the provider.";
    case "not-configured":
      return "No address or key is configured, so nothing was sent.";
  }
  const status = HTTP_REASON.exec(reason)?.[1];
  return status === undefined ? "The test failed." : `The provider answered with HTTP status ${status}.`;
}
