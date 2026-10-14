import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeAll, describe, expect, it, vi } from "vitest";
import { Input } from "./input";
import { Label } from "./label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "./select";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "./tooltip";

beforeAll(() => {
  // jsdom lacks the pointer and scroll APIs that Radix Select calls.
  Element.prototype.hasPointerCapture = () => false;
  Element.prototype.setPointerCapture = () => undefined;
  Element.prototype.releasePointerCapture = () => undefined;
  Element.prototype.scrollIntoView = () => undefined;
  globalThis.ResizeObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
  };
});

describe("Label and Input", () => {
  it("binds the visible label to the field", () => {
    render(
      <>
        <Label htmlFor="name">Collection name</Label>
        <Input id="name" />
      </>,
    );
    expect(screen.getByLabelText("Collection name")).toHaveClass("h-9", "rounded-control");
  });

  it("marks an invalid field", () => {
    render(<Input aria-label="Path" aria-invalid="true" />);
    expect(screen.getByLabelText("Path")).toHaveClass("aria-invalid:border-destructive");
    expect(screen.getByLabelText("Path")).toHaveAttribute("aria-invalid", "true");
  });
});

describe("Select", () => {
  function Fixture({ onValueChange = () => undefined }: { onValueChange?: (v: string) => void }) {
    return (
      <>
        <Label htmlFor="profile">Profile</Label>
        <Select defaultValue="documents" onValueChange={onValueChange}>
          <SelectTrigger id="profile">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="documents">Documents</SelectItem>
            <SelectItem value="codebase">Codebase</SelectItem>
          </SelectContent>
        </Select>
      </>
    );
  }

  it("is a labelled combobox showing the current value", () => {
    render(<Fixture />);
    const combobox = screen.getByRole("combobox", { name: "Profile" });
    expect(combobox).toHaveTextContent("Documents");
    expect(combobox).toHaveClass("h-9");
  });

  it("opens with the keyboard, picks an option and returns focus", async () => {
    const onValueChange = vi.fn();
    const user = userEvent.setup();
    render(<Fixture onValueChange={onValueChange} />);
    const combobox = screen.getByRole("combobox", { name: "Profile" });
    combobox.focus();
    await user.keyboard("{Enter}");
    expect(await screen.findByRole("listbox")).toBeInTheDocument();
    await user.keyboard("{ArrowDown}{Enter}");
    expect(onValueChange).toHaveBeenCalledWith("codebase");
    expect(screen.queryByRole("listbox")).not.toBeInTheDocument();
    expect(combobox).toHaveFocus();
  });

  it("closes on Escape without changing the value", async () => {
    const onValueChange = vi.fn();
    const user = userEvent.setup();
    render(<Fixture onValueChange={onValueChange} />);
    const combobox = screen.getByRole("combobox", { name: "Profile" });
    combobox.focus();
    await user.keyboard("{Enter}");
    await screen.findByRole("listbox");
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("listbox")).not.toBeInTheDocument();
    expect(onValueChange).not.toHaveBeenCalled();
  });
});

describe("Tooltip", () => {
  it("shows on keyboard focus and describes the trigger", async () => {
    const user = userEvent.setup();
    render(
      <TooltipProvider delayDuration={0}>
        <Tooltip>
          <TooltipTrigger asChild>
            <button type="button">Info</button>
          </TooltipTrigger>
          <TooltipContent>More detail</TooltipContent>
        </Tooltip>
      </TooltipProvider>,
    );
    await user.tab();
    expect(await screen.findByRole("tooltip")).toHaveTextContent("More detail");
    expect(screen.getByRole("button", { name: "Info" })).toHaveAccessibleDescription(
      "More detail",
    );
  });
});
