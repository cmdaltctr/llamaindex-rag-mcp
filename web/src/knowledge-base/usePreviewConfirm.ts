import { useState } from "react";
import { isConfirmationRequired, isStaleConfirmation, type Confirmation } from "../api/documents";

export type Phase = "idle" | "previewing" | "ready" | "confirming" | "done" | "failed";

/** `stale` and `required` are the two confirmation refusals; both need a new preview. */
export interface Failure {
  kind: "stale" | "required" | "other";
  error: unknown;
}

export interface FlowState<P, R> {
  phase: Phase;
  preview?: P;
  result?: R;
  failure?: Failure;
}

/**
 * Preview-bound destructive action (design D8). A preview mutates nothing and
 * returns a single-use token. Confirm sends that token. Any rejected
 * confirmation spends the token, so the only way forward is a new preview:
 * 409 means the preview is stale, used or expired, 428 means none was sent.
 */
export function usePreviewConfirm<P extends { confirmation?: Confirmation }, R>(
  preview: () => Promise<P>,
  confirm: (token: string) => Promise<R>,
  initial: Phase = "idle",
) {
  const [state, setState] = useState<FlowState<P, R>>({ phase: initial });

  async function runPreview() {
    setState({ phase: "previewing" });
    await loadPreview();
  }

  /** The preview request alone; safe to call from an effect because it sets state only after awaiting. */
  async function loadPreview() {
    try {
      setState({ phase: "ready", preview: await preview() });
    } catch (error) {
      setState({ phase: "failed", failure: { kind: "other", error } });
    }
  }

  async function runConfirm() {
    const token = state.preview?.confirmation?.token;
    if (token === undefined) {
      setState({ phase: "failed", failure: { kind: "required", error: null } });
      return;
    }
    setState({ ...state, phase: "confirming" });
    try {
      setState({ phase: "done", preview: state.preview, result: await confirm(token) });
    } catch (error) {
      // Keep no preview either way: the token is spent whatever the reason.
      const kind = isStaleConfirmation(error) ? "stale" : isConfirmationRequired(error) ? "required" : "other";
      setState({ phase: "failed", failure: { kind, error } });
    }
  }

  return { state, runPreview, loadPreview, runConfirm };
}
