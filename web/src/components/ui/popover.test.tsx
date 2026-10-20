import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { Popover } from "./popover";

function setup() {
  const user = userEvent.setup();
  render(
    <div>
      <Popover
        slot="test-content"
        trigger={(props) => (
          <button type="button" {...props}>
            Open it
          </button>
        )}
      >
        <p>Inside the panel.</p>
      </Popover>
      <button type="button">Elsewhere</button>
      <div data-slot="select-content">
        <button type="button">A select option</button>
      </div>
    </div>,
  );
  return user;
}

const trigger = () => screen.getByRole("button", { name: "Open it" });

describe("Popover primitive", () => {
  it("starts closed, opens on click and links the trigger to the panel", async () => {
    const user = setup();
    expect(trigger()).toHaveAttribute("aria-expanded", "false");
    await user.click(trigger());
    const panel = screen.getByText("Inside the panel.").closest("[data-slot='test-content']")!;
    expect(trigger()).toHaveAttribute("aria-expanded", "true");
    expect(trigger()).toHaveAttribute("aria-controls", panel.id);
  });

  it("closes on Escape and returns focus to the trigger", async () => {
    const user = setup();
    await user.click(trigger());
    await user.click(screen.getByText("Inside the panel."));
    await user.keyboard("{Escape}");
    expect(screen.queryByText("Inside the panel.")).not.toBeInTheDocument();
    expect(trigger()).toHaveFocus();
  });

  it("treats a select list on the page body as part of the panel", async () => {
    const user = setup();
    await user.click(trigger());
    await user.click(screen.getByRole("button", { name: "A select option" }));
    expect(screen.getByText("Inside the panel.")).toBeInTheDocument();
    screen.getByRole("button", { name: "A select option" }).focus();
    await user.keyboard("{Escape}");
    expect(screen.getByText("Inside the panel.")).toBeInTheDocument();
  });

  it("closes on a click outside and on a second click of the trigger", async () => {
    const user = setup();
    await user.click(trigger());
    await user.click(screen.getByRole("button", { name: "Elsewhere" }));
    expect(screen.queryByText("Inside the panel.")).not.toBeInTheDocument();
    await user.click(trigger());
    await user.click(trigger());
    expect(screen.queryByText("Inside the panel.")).not.toBeInTheDocument();
  });

  it("stays open when the panel itself scrolls, and closes when the page scrolls", async () => {
    const user = setup();
    await user.click(trigger());
    fireEvent.scroll(screen.getByText("Inside the panel."));
    expect(screen.getByText("Inside the panel.")).toBeInTheDocument();
    fireEvent.scroll(window);
    expect(screen.queryByText("Inside the panel.")).not.toBeInTheDocument();
  });
  /** jsdom has no layout, so give the trigger a position on a 768 px high screen. */
  function placeTrigger(top: number, height = 36) {
    trigger().getBoundingClientRect = () =>
      ({ top, bottom: top + height, left: 20, right: 56, width: 36, height, x: 20, y: top, toJSON: () => ({}) }) as DOMRect;
  }

  function renderAbove() {
    render(
      <Popover slot="test-content" placement="above" trigger={(props) => <button type="button" {...props}>Open it</button>}>
        <p>Inside the panel.</p>
      </Popover>,
    );
  }

  const panelOf = () => screen.getByText("Inside the panel.").closest<HTMLElement>("[data-slot='test-content']")!;

  it("opens above the trigger when asked, so a trigger at the screen bottom keeps its panel in view", async () => {
    const user = userEvent.setup();
    renderAbove();
    placeTrigger(700);
    await user.click(trigger());
    expect(panelOf().style.bottom).not.toBe("");
    expect(panelOf().style.top).toBe("");
  });

  it("flips below the trigger when there is more room below, so a trigger near the top keeps its panel in view", async () => {
    const user = userEvent.setup();
    renderAbove();
    placeTrigger(92);
    await user.click(trigger());
    expect(panelOf().style.top).not.toBe("");
    expect(panelOf().style.bottom).toBe("");
  });
  describe("when the trigger sits near the top of a short screen", () => {
    function openAt(rect: { top: number; bottom: number }, placement: "above" | "below" = "above") {
      const spy = vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockReturnValue({ ...rect, left: 20, right: 60, width: 40, height: 40, x: 20, y: rect.top, toJSON: () => ({}) });
      Object.defineProperty(window, "innerHeight", { configurable: true, value: 600 });
      const user = userEvent.setup();
      render(
        <Popover slot="test-content" placement={placement} trigger={(props) => <button type="button" {...props}>Open it</button>}>
          <p>Inside the panel.</p>
        </Popover>,
      );
      return { user, spy };
    }

    it("flips below the trigger when there is more room there, so the panel stays on screen", async () => {
      const { user, spy } = openAt({ top: 100, bottom: 140 });
      await user.click(trigger());
      const panel = screen.getByText("Inside the panel.").closest<HTMLElement>("[data-slot='test-content']")!;
      expect(panel.style.top).not.toBe("");
      expect(panel.style.bottom).toBe("");
      spy.mockRestore();
    });

    it("never lets the panel grow past the room on its side, and lets it scroll", async () => {
      const { user, spy } = openAt({ top: 100, bottom: 140 }, "above");
      await user.click(trigger());
      const panel = screen.getByText("Inside the panel.").closest<HTMLElement>("[data-slot='test-content']")!;
      expect(parseInt(panel.style.maxHeight, 10)).toBeLessThanOrEqual(600 - 140 - 4 - 8);
      expect(panel).toHaveClass("overflow-y-auto");
      spy.mockRestore();
    });
    it("caps the height at the real room even when that is under 160px", async () => {
      Object.defineProperty(window, "innerHeight", { configurable: true, value: 600 });
      const { user, spy } = openAt({ top: 100, bottom: 140 });
      Object.defineProperty(window, "innerHeight", { configurable: true, value: 250 });
      await user.click(trigger());
      const panel = screen.getByText("Inside the panel.").closest<HTMLElement>("[data-slot='test-content']")!;
      expect(parseInt(panel.style.maxHeight, 10)).toBeLessThan(160);
      spy.mockRestore();
    });
  });
});
