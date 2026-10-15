import { describe, expect, it } from "vitest";
import type { Job } from "../api/documents";
import { jobOutcome } from "./jobOutcome";

const BASE: Job = { job_id: "j", status: "completed", result: null, error: null, created_at: "", updated_at: "" };
const job = (patch: Partial<Job>): Job => ({ ...BASE, ...patch });

describe("jobOutcome", () => {
  it.each([
    ["queued", "Queued", "neutral"],
    ["running", "Running", "info"],
  ] as const)("shows a %s job as %s", (status, text, variant) => {
    expect(jobOutcome(job({ status }))).toEqual({ text, variant, detail: null });
  });

  it("shows a failed job as failed with a fixed hint, never the recorded error text", () => {
    const detail = "The ingest stopped before it finished. See the server log in Settings for the reason.";
    expect(jobOutcome(job({ status: "failed", error: "ValueError: bad file" }))).toEqual({ text: "Failed", variant: "error", detail });
    expect(jobOutcome(job({ status: "failed" })).detail).toBe(detail);
    expect(JSON.stringify(jobOutcome(job({ status: "failed", error: "FileNotFoundError: /Users/a/b.md" })))).not.toContain("/Users");
  });

  it("shows a completed job as completed when no file failed", () => {
    expect(jobOutcome(job({ result: { status: "ok", files_indexed: 2, chunks_created: 9, file_details: [{ status: "indexed" }, { status: "indexed" }] } }))).toEqual({ text: "Completed", variant: "success", detail: null });
    expect(jobOutcome(job({ result: null })).variant).toBe("success");
  });

  it("does not call a job completed when every file failed", () => {
    const outcome = jobOutcome(
      job({ result: { status: "error", error_type: "embedding", files_indexed: 0, file_details: [{ file: "/srv/a.md", status: "failed", failure_stage: "embedding", error: "model 'x' not found" }] } }),
    );
    expect(outcome.text).toBe("Nothing indexed");
    expect(outcome.variant).toBe("error");
    expect(outcome.detail).toBe("1 of 1 file could not be indexed. The embedding step failed. Check the embedding model, then try again.");
  });

  it("warns when only some files failed", () => {
    const outcome = jobOutcome(
      job({ result: { status: "partial", files_indexed: 2, file_details: [{ status: "indexed" }, { status: "failed", failure_stage: "parse" }, { status: "indexed" }] } }),
    );
    expect(outcome).toEqual({ text: "Completed with errors", variant: "warning", detail: "1 of 3 files could not be indexed. See the server log in Settings for the reason." });
  });

  it("treats a result status of error without file details as failed", () => {
    expect(jobOutcome(job({ result: { status: "error", message: "boom at /srv/x" } }))).toEqual({ text: "Nothing indexed", variant: "error", detail: "The ingest did not finish. See the server log in Settings for the reason." });
  });

  it("never returns a path, message or exception text from the result", () => {
    const outcome = jobOutcome(
      job({ result: { status: "error", message: "boom /private/tmp/x.md", file_details: [{ file: "/private/tmp/x.md", status: "failed", error: "model 'nomic-embed-text' not found (status code: 404)" }] } }),
    );
    const text = JSON.stringify(outcome);
    expect(text).not.toContain("/private/tmp");
    expect(text).not.toContain("nomic-embed-text");
    expect(text).not.toContain("404");
  });

  it("ignores a malformed result", () => {
    expect(jobOutcome(job({ result: { status: 5, file_details: "x" } })).variant).toBe("success");
  });
});
