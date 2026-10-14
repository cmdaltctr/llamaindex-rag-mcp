import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { Button } from "./button";

describe("Button", () => {
  it("uses the tinted primary treatment by default", () => {
    render(<Button>Save</Button>);
    const button = screen.getByRole("button", { name: "Save" });
    expect(button).toHaveClass(
      "bg-primary-tint",
      "border-primary-tint-border",
      "text-primary-label",
      "hover:bg-primary-tint-hover",
      "active:bg-primary-tint-active",
      "h-9",
      "rounded-control",
    );
    // Never a solid accent fill, and never the raw accent as text.
    expect(button).not.toHaveClass("bg-primary", "text-primary");
  });

  it("sizes small and extra-small to 32px and 24px", () => {
    render(
      <>
        <Button size="sm">Small</Button>
        <Button size="xs">Tiny</Button>
      </>,
    );
    expect(screen.getByRole("button", { name: "Small" })).toHaveClass("h-8");
    expect(screen.getByRole("button", { name: "Tiny" })).toHaveClass("h-6");
  });

  it("keeps the chip selection neutral, not accent", () => {
    render(
      <Button variant="chip" aria-pressed="true">
        Documents
      </Button>,
    );
    const chip = screen.getByRole("button", { name: "Documents" });
    expect(chip).toHaveClass("aria-pressed:bg-selection");
    expect(chip.className).not.toMatch(/primary/);
  });

  it("uses the error label for the destructive variant", () => {
    render(<Button variant="destructive">Delete</Button>);
    const button = screen.getByRole("button", { name: "Delete" });
    expect(button).toHaveClass("text-status-error-label", "bg-destructive/10");
  });

  it("defaults to type=button and honours an explicit submit", () => {
    render(
      <form>
        <Button>Plain</Button>
        <Button type="submit">Send</Button>
      </form>,
    );
    expect(screen.getByRole("button", { name: "Plain" })).toHaveAttribute("type", "button");
    expect(screen.getByRole("button", { name: "Send" })).toHaveAttribute("type", "submit");
  });

  it("fires onClick and ignores clicks while disabled", async () => {
    const onClick = vi.fn();
    const user = userEvent.setup();
    const { rerender } = render(<Button onClick={onClick}>Go</Button>);
    await user.click(screen.getByRole("button", { name: "Go" }));
    expect(onClick).toHaveBeenCalledTimes(1);
    rerender(
      <Button onClick={onClick} disabled>
        Go
      </Button>,
    );
    await user.click(screen.getByRole("button", { name: "Go" }));
    expect(onClick).toHaveBeenCalledTimes(1);
  });

  it("renders the child element when asChild is set", () => {
    render(
      <Button asChild>
        <a href="#/chat">Chat</a>
      </Button>,
    );
    const link = screen.getByRole("link", { name: "Chat" });
    expect(link).toHaveAttribute("href", "#/chat");
    expect(link).toHaveClass("bg-primary-tint");
  });
});
