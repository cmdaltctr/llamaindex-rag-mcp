import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { StrictMode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { FetchLike } from "../api/client";
import { json } from "../test/fakeDocumentsServer";
import { controlledStream, sseFrame, stageFrame } from "../test/fakeStream";
import { providers, renderWithProviders } from "../test/providers";
import { AnswerProgress } from "./AnswerProgress";
import { AssistantTurn } from "./AssistantTurn";

const STREAM = "/v1/collections/documents/answer/stream";
const BLOCKING = "/v1/collections/documents/answer";

function answer(overrides: Record<string, unknown> = {}) {
  return { status: "ok", query: "q", answer: "Lineage is kept.", citations: [], evidence: [], failure_stage: null, error: null, completion_source: "server", ...overrides };
}

function progressList() {
  return screen.getByRole("list", { name: "Answer progress" });
}

function rows() {
  return within(progressList())
    .getAllByRole("listitem")
    .map((row) => ({ text: row.textContent, done: row.querySelector(".lucide-check") !== null, current: row.querySelector(".lucide-loader-circle, .lucide-loader2") !== null }));
}

afterEach(() => {
  vi.useRealTimers();
});

describe("AnswerProgress", () => {
  it("shows the stages in order, with a tick on each finished one", () => {
    render(<AnswerProgress stages={["searching", "writing", "citing"]} />);
    expect(rows()).toEqual([
      { text: "Searching", done: true, current: false },
      { text: "Writing the answer", done: true, current: false },
      { text: "Checking citations", done: false, current: true },
    ]);
    expect(screen.queryByText("Verifying claims")).not.toBeInTheDocument();
  });

  it("spins the current stage icon only when motion is allowed", () => {
    render(<AnswerProgress stages={["searching"]} />);
    const icon = progressList().querySelector("svg")!;
    expect(icon.getAttribute("class")).toContain("motion-safe:animate-spin");
    expect(icon.getAttribute("class")).not.toMatch(/(^|\s)animate-spin/);
    expect(icon).toHaveAttribute("aria-hidden", "true");
  });

  it("makes only the current stage line a polite status region", () => {
    render(<AnswerProgress stages={["searching", "writing"]} />);
    const regions = screen.getAllByRole("status");
    expect(regions).toHaveLength(1);
    expect(regions[0]).toHaveTextContent("Writing the answer");
    expect(regions[0]).toHaveAttribute("aria-live", "polite");
  });

  it("counts seconds outside the live region", () => {
    vi.useFakeTimers();
    render(<AnswerProgress stages={["searching"]} />);
    const counter = screen.getByText("0 s");
    expect(counter).toHaveAttribute("aria-hidden", "true");
    expect(counter.className).toContain("tabular-nums");
    act(() => vi.advanceTimersByTime(3000));
    expect(counter).toHaveTextContent("3 s");
    expect(screen.getByRole("status")).not.toHaveTextContent("3 s");
  });

  it("shows the waiting line and the counter when no stage arrives within 10 s", () => {
    vi.useFakeTimers();
    render(<AnswerProgress stages={[]} />);
    act(() => vi.advanceTimersByTime(10_000));
    expect(screen.getByRole("status")).toHaveTextContent("Waiting for the answer.");
    expect(screen.getByText("10 s")).toBeInTheDocument();
  });

  it("stops its timer when it unmounts", () => {
    vi.useFakeTimers();
    const { unmount } = render(<AnswerProgress stages={[]} />);
    unmount();
    expect(vi.getTimerCount()).toBe(0);
  });
});

/** Serves each stream request from the next queued response; the blocking route is counted. */
function server(responses: (() => Response)[]) {
  const fetchImpl = vi.fn<FetchLike>(async (path) => {
    if (path === STREAM) return responses.shift()!();
    if (path === BLOCKING) return json(answer());
    return json({ status: "error", message: "no route" }, 404);
  });
  return { fetchImpl, blockingCalls: () => fetchImpl.mock.calls.filter(([path]) => path === BLOCKING).length };
}

function renderTurn(fetchImpl: FetchLike, props: Partial<Parameters<typeof AssistantTurn>[0]> = {}) {
  vi.spyOn(console, "error").mockImplementation(() => undefined);
  return renderWithProviders(
    <ul>
      <AssistantTurn collection="documents" question="What is kept?" onShowChunk={() => undefined} {...props} />
    </ul>,
    { fetchImpl },
  );
}

describe("AssistantTurn with a streamed answer", () => {
  it("shows each stage as it arrives, then the answer in place of the progress", async () => {
    const stream = controlledStream();
    const { fetchImpl, blockingCalls } = server([() => stream.response]);
    renderTurn(fetchImpl);
    expect(await screen.findByRole("status")).toHaveTextContent("Waiting for the answer.");
    act(() => stream.push(stageFrame("searching", 1)));
    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("Searching"));
    act(() => stream.push(stageFrame("writing", 2) + stageFrame("citing", 3)));
    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("Checking citations"));
    expect(rows().map((row) => row.done)).toEqual([true, true, false]);
    act(() => stream.push(sseFrame("result", answer())));
    expect(await screen.findByText("Lineage is kept.")).toBeInTheDocument();
    expect(screen.queryByRole("list", { name: "Answer progress" })).not.toBeInTheDocument();
    expect(screen.queryByText("Verifying claims")).not.toBeInTheDocument();
    expect(blockingCalls()).toBe(0);
  });

  it("never shows Writing the answer for a no-evidence run", async () => {
    const stream = controlledStream();
    const { fetchImpl } = server([() => stream.response]);
    renderTurn(fetchImpl);
    act(() => stream.push(stageFrame("searching", 1)));
    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("Searching"));
    expect(screen.queryByText("Writing the answer")).not.toBeInTheDocument();
    act(() => stream.push(sseFrame("result", answer({ status: "no_evidence", answer: null }))));
    expect(await screen.findByText("No evidence")).toBeInTheDocument();
    expect(screen.queryByText("Writing the answer")).not.toBeInTheDocument();
    expect(screen.queryByRole("list", { name: "Answer progress" })).not.toBeInTheDocument();
  });

  it("clears the old stages when Retry starts a new answer", async () => {
    const first = controlledStream();
    const second = controlledStream();
    const { fetchImpl } = server([() => first.response, () => second.response]);
    renderTurn(fetchImpl);
    act(() => first.push(stageFrame("searching", 1) + stageFrame("writing", 2)));
    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("Writing the answer"));
    act(() => first.push(sseFrame("result", answer({ status: "error", answer: null, failure_stage: "generation", error: "boom" }))));
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Retry" }));
    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("Waiting for the answer."));
    expect(screen.queryByText("Searching")).not.toBeInTheDocument();
    expect(screen.queryByText("Writing the answer")).not.toBeInTheDocument();
    second.close();
  });

  it("shows one friendly line with Retry when the stream drops, and does not ask the blocking route", async () => {
    const stream = controlledStream();
    const { fetchImpl, blockingCalls } = server([() => stream.response]);
    renderTurn(fetchImpl);
    act(() => stream.push(stageFrame("searching", 1) + stageFrame("writing", 2)));
    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("Writing the answer"));
    act(() => stream.close());
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("The local server is not reachable.");
    expect(alert).not.toHaveTextContent(/stream|ended|result/i);
    expect(within(alert).getByRole("button", { name: "Retry" })).toBeInTheDocument();
    expect(blockingCalls()).toBe(0);
  });

  it("never mounts the progress for a saved turn", () => {
    const { fetchImpl } = server([]);
    renderTurn(fetchImpl, { saved: answer() as never });
    expect(screen.getByText("Lineage is kept.")).toBeInTheDocument();
    expect(screen.queryByRole("list", { name: "Answer progress" })).not.toBeInTheDocument();
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
    expect(fetchImpl).not.toHaveBeenCalled();
  });

  it("still answers under strict mode, whose test remount must not abort the request", async () => {
    const stream = controlledStream();
    const { fetchImpl } = server([() => stream.response]);
    vi.spyOn(console, "error").mockImplementation(() => undefined);
    // Strict mode re-runs effects only at the root, as `main.tsx` mounts it.
    const Providers = providers({ fetchImpl });
    render(
      <StrictMode>
        <Providers>
          <ul>
            <AssistantTurn collection="documents" question="What is kept?" onShowChunk={() => undefined} />
          </ul>
        </Providers>
      </StrictMode>,
    );
    await waitFor(() => expect(fetchImpl).toHaveBeenCalledTimes(1));
    act(() => stream.push(stageFrame("searching", 1) + sseFrame("result", answer())));
    expect(await screen.findByText("Lineage is kept.")).toBeInTheDocument();
  });
});
