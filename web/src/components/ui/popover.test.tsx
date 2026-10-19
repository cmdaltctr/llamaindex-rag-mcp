import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
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
});
