import { act, fireEvent, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { LogRecord } from "../api/settings";
import { json } from "../test/fakeDocumentsServer";
import { FakeEventSource } from "../test/fakeEventSource";
import { startApp } from "../test/startApp";
import { logRecord, settingsServer } from "./test/fixtures";

afterEach(() => {
  vi.unstubAllGlobals();
  FakeEventSource.reset();
});

const BUFFERED = [logRecord(1, "info", "Server started"), logRecord(2, "warning", "Slow disk", "omrg.store"), logRecord(3, "error", "Query failed", "omrg.search")];

async function openLog(records: LogRecord[] = BUFFERED, handlers = {}) {
  FakeEventSource.reset();
  vi.stubGlobal("EventSource", FakeEventSource);
  const server = settingsServer({
    "GET /v1/logs": () => ({ status: "ok", records, last_seq: records.at(-1)?.seq ?? 0 }),
    ...handlers,
  });
  startApp("#/settings", server);
  const user = userEvent.setup();
  await user.click(await screen.findByRole("button", { name: "Server log" }));
  const log = await screen.findByRole("log", { name: "Log records" });
  await waitFor(() => expect(FakeEventSource.instances).toHaveLength(1));
  return { server, user, log };
}

function messages(log: HTMLElement) {
  return within(log)
    .queryAllByRole("listitem")
    .map((item) => item.textContent ?? "");
}

describe("Server log panel", () => {
  it("shows buffered records one per line with time, level, logger and message", async () => {
    const { log } = await openLog();
    const lines = within(log).getAllByRole("listitem");
    expect(lines).toHaveLength(3);
    expect(lines[1]).toHaveTextContent("09:30:02");
    expect(within(lines[1]!).getByText("warning")).toHaveAttribute("data-slot", "badge");
    expect(lines[1]).toHaveTextContent("omrg.store");
    expect(lines[1]).toHaveTextContent("Slow disk");
  });

  it("is a monospace terminal-style log region", async () => {
    const { log } = await openLog();
    expect(log).toHaveClass("font-mono");
    expect(log).toHaveClass("bg-muted");
    expect(log).toHaveAttribute("tabindex", "0");
  });

  it("shows a live line without a reload", async () => {
    const { log } = await openLog();
    act(() => FakeEventSource.latest().frame("log", logRecord(4, "warning", "Disk nearly full"), 4));
    expect(await within(log).findByText("Disk nearly full")).toBeInTheDocument();
    expect(FakeEventSource.latest().url).toBe("/v1/logs/stream?after=3");
  });

  it("renders a message as plain text, never as markup", async () => {
    const { log } = await openLog();
    act(() => FakeEventSource.latest().frame("log", logRecord(4, "info", "<img src=x onerror=alert(1)> <b>bold</b>"), 4));
    expect(await within(log).findByText("<img src=x onerror=alert(1)> <b>bold</b>")).toBeInTheDocument();
    expect(log.querySelector("img")).toBeNull();
    expect(log.querySelector("b")).toBeNull();
  });

  it("filters by minimum level with chips", async () => {
    const { log, user } = await openLog();
    const group = screen.getByRole("group", { name: "Minimum level" });
    expect(within(group).getAllByRole("button").map((b) => b.textContent)).toEqual(["All", "Info", "Warning", "Error"]);
    expect(within(group).getByRole("button", { name: "All" })).toHaveAttribute("aria-pressed", "true");
    await user.click(within(group).getByRole("button", { name: "Warning" }));
    expect(within(group).getByRole("button", { name: "Warning" })).toHaveAttribute("aria-pressed", "true");
    expect(messages(log).join("|")).toContain("Slow disk");
    expect(messages(log).join("|")).toContain("Query failed");
    expect(messages(log).join("|")).not.toContain("Server started");
    await user.click(within(group).getByRole("button", { name: "Error" }));
    expect(messages(log)).toHaveLength(1);
  });

  it("pauses the view: new lines wait until Resume", async () => {
    const { log, user } = await openLog();
    await user.click(screen.getByRole("button", { name: "Pause" }));
    expect(screen.getByRole("button", { name: "Resume" })).toHaveAttribute("aria-pressed", "true");
    act(() => FakeEventSource.latest().frame("log", logRecord(4, "info", "Arrived while paused"), 4));
    expect(within(log).queryByText("Arrived while paused")).toBeNull();
    expect(screen.getByText(/1 new line while paused/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Resume" }));
    expect(await within(log).findByText("Arrived while paused")).toBeInTheDocument();
    expect(screen.queryByText(/new line while paused/)).toBeNull();
  });

  it("copies the visible lines as plain text", async () => {
    const { user } = await openLog();
    await user.click(within(screen.getByRole("group", { name: "Minimum level" })).getByRole("button", { name: "Warning" }));
    await user.click(screen.getByRole("button", { name: "Copy visible log lines" }));
    const copied = await navigator.clipboard.readText();
    expect(copied.split("\n")).toEqual([
      "2026-10-14T09:30:02Z WARNING omrg.store Slow disk",
      "2026-10-14T09:30:03Z ERROR omrg.search Query failed",
    ]);
    expect(await screen.findByText("Copied visible log lines.")).toBeInTheDocument();
  });

  it("says when the server closed the stream", async () => {
    await openLog();
    act(() => FakeEventSource.latest().frame("server.closing", { reason: "shutdown" }));
    expect(await screen.findByText(/server is shutting down/i)).toBeInTheDocument();
  });

  it("states when there are no lines yet", async () => {
    await openLog([]);
    expect(screen.getByText("No log lines yet.")).toBeInTheDocument();
  });

  it("shows a friendly line with Retry when the log cannot load", async () => {
    FakeEventSource.reset();
    vi.stubGlobal("EventSource", FakeEventSource);
    startApp("#/settings", settingsServer({ "GET /v1/logs": () => json({ status: "error", message: "Unexpected token <" }, 500) }));
    await userEvent.setup().click(await screen.findByRole("button", { name: "Server log" }));
    expect(await screen.findByRole("button", { name: "Retry" })).toBeInTheDocument();
    expect(screen.queryByText(/Unexpected token/)).toBeNull();
  });
});

describe("Server log auto-scroll", () => {
  function geometry(log: HTMLElement, size: { scrollHeight: number; clientHeight: number }) {
    let top = 0;
    Object.defineProperty(log, "scrollHeight", { configurable: true, get: () => size.scrollHeight });
    Object.defineProperty(log, "clientHeight", { configurable: true, get: () => size.clientHeight });
    Object.defineProperty(log, "scrollTop", { configurable: true, get: () => top, set: (value: number) => (top = value) });
    return {
      scrollTo(value: number) {
        top = value;
        fireEvent.scroll(log);
      },
      top: () => top,
    };
  }

  it("follows new lines while at the bottom", async () => {
    const { log } = await openLog();
    const scroll = geometry(log, { scrollHeight: 1000, clientHeight: 200 });
    act(() => FakeEventSource.latest().frame("log", logRecord(4, "info", "Line four"), 4));
    await within(log).findByText("Line four");
    expect(scroll.top()).toBe(1000);
  });

  it("stops following when the user scrolls up and resumes at the bottom", async () => {
    const { log } = await openLog();
    const scroll = geometry(log, { scrollHeight: 1000, clientHeight: 200 });
    scroll.scrollTo(100);
    act(() => FakeEventSource.latest().frame("log", logRecord(4, "info", "Line four"), 4));
    await within(log).findByText("Line four");
    expect(scroll.top()).toBe(100);
    expect(screen.getByText(/Not following/)).toBeInTheDocument();

    scroll.scrollTo(800);
    expect(screen.getByText(/Following new lines/)).toBeInTheDocument();
    act(() => FakeEventSource.latest().frame("log", logRecord(5, "info", "Line five"), 5));
    await within(log).findByText("Line five");
    expect(scroll.top()).toBe(1000);
  });
});
