import { useState } from "react";
import { isConfirmationRequired, type Confirmation } from "../../api/documents";
import { messageOf } from "../shared/labels";

export type Phase = "idle" | "previewing" | "ready" | "confirming" | "done" | "failed";

export interface FlowState<P, R> {
  phase: Phase;
  preview?: P;
  result?: R;
  error?: string;
}

const MISSING_TOKEN =
  "The server needs a fresh preview before it changes anything. Nothing was changed. Preview again to continue.";

/**
 * Preview-bound destructive action (design D8). A preview mutates nothing and
 * returns a single-use token. Confirm sends that token. Any rejected
 * confirmation spends the token, so the only way forward is a new preview:
 * 409 (stale, used or expired) shows the server's reason, 428 explains that
 * a preview is required.
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
      const result = await preview();
      setState({ phase: "ready", preview: result });
    } catch (error) {
      setState({ phase: "failed", error: messageOf(error) });
    }
  }

  async function runConfirm() {
    const token = state.preview?.confirmation?.token;
    if (token === undefined) {
      setState({ phase: "failed", error: MISSING_TOKEN });
      return;
    }
    setState({ ...state, phase: "confirming" });
    try {
      const result = await confirm(token);
      setState({ phase: "done", preview: state.preview, result });
    } catch (error) {
      // A 409 carries the server's reason (stale, used or expired). Keep no
      // preview either way: its token is spent whatever the reason.
      setState({ phase: "failed", error: isConfirmationRequired(error) ? MISSING_TOKEN : messageOf(error) });
    }
  }

  return { state, runPreview, loadPreview, runConfirm };
}
