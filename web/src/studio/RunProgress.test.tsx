import { screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { useRunMonitor } from "../runs/useRunMonitor";
import { EMPTY_RUN_VIEW } from "../runs/runState";
import { renderWithProviders } from "../test/providers";
import { RunProgress } from "./RunProgress";

const RAW = "Traceback (most recent call last): /Users/someone/omrs/runner.py";

function failingFetch(): typeof fetch {
  return vi.fn(async () => new Response(JSON.stringify({ status: "error", message: RAW }), { status: 500, headers: { "content-type": "application/json" } }));
}

function Probe() {
  const monitor = useRunMonitor("r1", { eventSource: null });
  return <RunProgress runId="r1" status="running" view={EMPTY_RUN_VIEW} mode={monitor.mode} live={monitor.live} error={monitor.error} />;
}

describe("RunProgress", () => {
  it("shows a monitoring failure as one friendly line and keeps the raw text off the page", async () => {
    vi.spyOn(console, "error").mockImplementation(() => {});
    const { container } = renderWithProviders(<Probe />, { fetchImpl: failingFetch() });
    await waitFor(() => expect(screen.getByText(/Event monitoring/)).toBeInTheDocument());
    expect(screen.getByText("Event monitoring: The local server could not complete that request.")).toBeInTheDocument();
    expect(container.textContent).not.toContain("Traceback");
    expect(container.textContent).not.toContain("/Users/");
  });
});
