import { describe, expect, it } from "vitest";
import type { NodeOutcomeRecord } from "../api/runs";
import { outcomeRows } from "./NodeOutcomes";
import { bypassReason, displayStatus, EMPTY_RUN_VIEW } from "./runState";

const stored: NodeOutcomeRecord = {
  node_id: "rerank",
  status: "succeeded",
  error: null,
  fallback: null,
  effects: [],
  duration_s: 0.01,
  unit_id: null,
  summary: { reranked: false, reason: "disabled by node parameter" },
};

describe("outcomeRows for a finished run opened without replay", () => {
  it("shows a pass-through node as bypassed from its stored summary", () => {
    const row = outcomeRows([stored], EMPTY_RUN_VIEW)[0]!;
    expect(displayStatus(row.state)).toBe("bypassed");
    expect(bypassReason(row.state)).toContain("disabled by node parameter");
  });

  it("keeps a node without a stored summary as completed", () => {
    const row = outcomeRows([{ ...stored, summary: undefined }], EMPTY_RUN_VIEW)[0]!;
    expect(displayStatus(row.state)).toBe("succeeded");
  });
});
