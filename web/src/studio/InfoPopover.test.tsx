import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { InfoPopover } from "./InfoPopover";

function setup() {
  const user = userEvent.setup();
  render(
    <div>
      <InfoPopover label="About the Ingest pipeline">
        <p>Reads files.</p>
      </InfoPopover>
      <InfoPopover label="About the Search pipeline">
        <p>Finds chunks.</p>
      </InfoPopover>
      <button type="button">Elsewhere</button>
    </div>,
  );
  return user;
}

const trigger = (name: string) => screen.getByRole("button", { name });

describe("InfoPopover", () => {
  it("starts closed and shows no chevron", () => {
    setup();
    expect(trigger("About the Ingest pipeline")).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByText("Reads files.")).not.toBeInTheDocument();
    expect(trigger("About the Ingest pipeline").querySelector("svg.lucide-chevron-down, svg.lucide-chevron-up")).toBeNull();
  });

  it("opens on click, links the button to the panel and closes on a second click", async () => {
    const user = setup();
    await user.click(trigger("About the Ingest pipeline"));
    const panel = screen.getByText("Reads files.").closest("[data-slot='info-popover-content']")!;
    expect(trigger("About the Ingest pipeline")).toHaveAttribute("aria-expanded", "true");
    expect(trigger("About the Ingest pipeline")).toHaveAttribute("aria-controls", panel.id);
    await user.click(trigger("About the Ingest pipeline"));
    expect(screen.queryByText("Reads files.")).not.toBeInTheDocument();
  });

  it("closes on Escape and returns focus to the button", async () => {
    const user = setup();
    await user.click(trigger("About the Ingest pipeline"));
    await user.keyboard("{Escape}");
    expect(screen.queryByText("Reads files.")).not.toBeInTheDocument();
    expect(trigger("About the Ingest pipeline")).toHaveFocus();
  });

  it("closes when the user clicks elsewhere", async () => {
    const user = setup();
    await user.click(trigger("About the Ingest pipeline"));
    await user.click(trigger("Elsewhere"));
    expect(screen.queryByText("Reads files.")).not.toBeInTheDocument();
  });

  it("keeps one popover open at a time", async () => {
    const user = setup();
    await user.click(trigger("About the Ingest pipeline"));
    await user.click(trigger("About the Search pipeline"));
    expect(screen.queryByText("Reads files.")).not.toBeInTheDocument();
    expect(screen.getByText("Finds chunks.")).toBeInTheDocument();
  });

  it("stays open when the user clicks inside the panel", async () => {
    const user = setup();
    await user.click(trigger("About the Ingest pipeline"));
    await user.click(screen.getByText("Reads files."));
    expect(screen.getByText("Reads files.")).toBeInTheDocument();
  });

  it("draws the panel outside any clipping ancestor, so a hidden-overflow region cannot cut it off", async () => {
    const user = userEvent.setup();
    render(
      <div className="overflow-hidden" data-testid="clip">
        <InfoPopover label="About the Ingest pipeline">
          <p>Reads files.</p>
        </InfoPopover>
      </div>,
    );
    await user.click(screen.getByRole("button", { name: "About the Ingest pipeline" }));
    const panel = screen.getByText("Reads files.").closest("[data-slot='info-popover-content']") as HTMLElement;
    expect(screen.getByTestId("clip")).not.toContainElement(panel);
    expect(panel.className).toMatch(/fixed/);
    expect(panel.parentElement).toBe(document.body);
  });

  it("keeps the panel inside the screen width", async () => {
    const user = userEvent.setup();
    render(
      <div style={{ marginLeft: 900 }}>
        <InfoPopover label="About the Ingest pipeline">
          <p>Reads files.</p>
        </InfoPopover>
      </div>,
    );
    await user.click(screen.getByRole("button", { name: "About the Ingest pipeline" }));
    const panel = screen.getByText("Reads files.").closest("[data-slot='info-popover-content']") as HTMLElement;
    const left = Number.parseFloat(panel.style.left);
    expect(left).toBeGreaterThanOrEqual(8);
    expect(left + 288).toBeLessThanOrEqual(window.innerWidth);
  });
});

