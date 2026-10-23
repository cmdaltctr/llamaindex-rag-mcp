import { act, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { PreferencesProvider } from "../lib/PreferencesProvider";
import { renderWithProviders } from "../test/providers";
import { documentsServer } from "../test/fakeDocumentsServer";
import { AppNav } from "./AppNav";

function start(collapsed: boolean) {
  const server = documentsServer();
  renderWithProviders(
    <PreferencesProvider>
      <AppNav current="chat" collapsed={collapsed} onToggle={() => {}} />
    </PreferencesProvider>,
    { fetchImpl: server.fetchImpl },
  );
  return within(screen.getByRole("navigation", { name: "Workspace" }));
}

describe("navigation tooltips", () => {
  beforeEach(() => {
    vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout"], shouldAdvanceTime: true });
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  function setup() {
    return userEvent.setup({ advanceTimers: (ms) => vi.advanceTimersByTime(ms) });
  }

  it.each([true, false])("names each area on hover with no delay (collapsed: %s)", async (collapsed) => {
    const user = setup();
    const nav = start(collapsed);
    await user.hover(nav.getByRole("link", { name: "Knowledge Base" }));
    act(() => vi.advanceTimersByTime(50));
    expect(screen.getByRole("tooltip")).toHaveTextContent("Knowledge Base");
  });

  it("hides the tooltip after three seconds while the pointer stays", async () => {
    const user = setup();
    const nav = start(true);
    await user.hover(nav.getByRole("link", { name: "Studio" }));
    act(() => vi.advanceTimersByTime(2900));
    expect(screen.getByRole("tooltip")).toHaveTextContent("Studio");
    act(() => vi.advanceTimersByTime(200));
    expect(screen.queryByRole("tooltip")).not.toBeInTheDocument();
  });

  it("names the collapse button on hover", async () => {
    const user = setup();
    const nav = start(true);
    await user.hover(nav.getByRole("button", { name: "Expand navigation" }));
    act(() => vi.advanceTimersByTime(50));
    expect(screen.getByRole("tooltip")).toHaveTextContent("Expand navigation");
  });

  it.each([
    ["button", /^Switch to (light|dark) theme$/],
    ["link", /^Settings$/],
    ["button", /^Server status:/],
    ["link", /^OMRS on GitHub$/],
  ] as const)("names the foot %s %s on hover", async (role, name) => {
    const user = setup();
    start(true);
    const foot = within(screen.getByRole("group", { name: "Quick controls" }));
    await user.hover(foot.getByRole(role, { name }));
    act(() => vi.advanceTimersByTime(50));
    expect(screen.getByRole("tooltip")).toHaveTextContent(name);
  });
});

describe("navigation column", () => {
  it("stays in view at full window height when the page scrolls", () => {
    start(false);
    const column = screen.getByRole("navigation", { name: "Workspace" }).parentElement as HTMLElement;
    expect(column).toHaveClass("md:sticky", "md:top-0", "md:h-dvh", "md:self-start");
  });
});
