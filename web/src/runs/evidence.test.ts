import { describe, expect, it } from "vitest";
import { boundText, findEvidence, MAX_PREVIEW_ROWS, scoreText } from "./evidence";
import { maskText, REDACTED, safeEntry } from "./redact";

describe("score kinds", () => {
  it("labels each known score kind with its own name", () => {
    expect(scoreText(0.91234, "reranker_sigmoid_v1")).toEqual({ label: "Reranker score", value: "0.9123" });
    expect(scoreText(0.016393, "rrf_v1")).toEqual({ label: "RRF score", value: "0.01639" });
    expect(scoreText(0.8, "dense_similarity_v1")).toEqual({ label: "Dense similarity", value: "0.8000" });
    expect(scoreText(12.5, "native_fts_v1")).toEqual({ label: "Full-text score", value: "12.50" });
  });

  it("shows no number for a rank-only kind, even when a value is present", () => {
    expect(scoreText(3, "sparse_rank_v1")).toEqual({ label: "Rank only", value: null });
  });

  it("keeps an unknown kind visible and never calls a score a probability", () => {
    expect(scoreText(0.5, "custom_v2")).toEqual({ label: "Score (custom_v2)", value: "0.5000" });
    expect(scoreText(0.5, null)).toEqual({ label: "Score, kind not reported", value: "0.5000" });
    expect(JSON.stringify(scoreText(0.5, "reranker_sigmoid_v1"))).not.toMatch(/probab|confidence|%/i);
  });
});

describe("bounded previews", () => {
  it("cuts text at the 4 KiB server bound and says so", () => {
    const long = "é".repeat(3000);
    const preview = boundText(long);
    expect(preview.truncated).toBe(true);
    expect(new TextEncoder().encode(preview.text).length).toBeLessThanOrEqual(4096);
    expect(preview.text.endsWith("�")).toBe(false);
    expect(boundText("short")).toEqual({ text: "short", truncated: false });
  });

  it("finds ranked rows, citations and an answer in run outputs and caps rows at 100", () => {
    const rows = Array.from({ length: 130 }, (_, i) => ({ chunk_id: `c${i}`, text: "t", score: 1 - i / 200, score_kind: "rrf_v1" }));
    const found = findEvidence({
      results: rows,
      answer: { answer: "RRF fuses ranks.", citations: [{ ordinal: 1, chunk_id: "c1", source: "a.md" }], evidence: rows.slice(0, 2) },
      count: 3,
    });
    expect(found.map((f) => [f.name, f.kind])).toEqual([
      ["results", "rows"],
      ["answer", "answer"],
      ["answer.citations", "citations"],
      ["answer.evidence", "rows"],
    ]);
    const first = found[0]!;
    expect(first.kind === "rows" && first.rows.length).toBe(MAX_PREVIEW_ROWS);
    expect(first.kind === "rows" && first.total).toBe(130);
  });
});

describe("secret exclusion", () => {
  it("masks credential keys whatever their value", () => {
    expect(safeEntry("api_key", "sk-live-1234567890")).toBe(REDACTED);
    expect(safeEntry("Authorization", "Bearer abcdefghijklmnop")).toBe(REDACTED);
    expect(safeEntry("top_k", 10)).toBe(10);
  });

  it("masks bearer tokens and credential query values inside text", () => {
    expect(maskText("sent Bearer abcdefghijklmnop to host")).toBe(`sent Bearer ${REDACTED} to host`);
    expect(maskText("https://x.test/?api_key=s3cr3tvalue&q=1")).toBe(`https://x.test/?api_key=${REDACTED}&q=1`);
    expect(maskText(`already ${REDACTED}`)).toBe(`already ${REDACTED}`);
  });
});
