import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import App from "./App";

function themeSelect() {
  return screen.getByRole("combobox", { name: "Theme" });
}

describe("theme preference", () => {
  it("follows the system theme by default", () => {
    render(<App />);
    expect(themeSelect()).toHaveValue("system");
    expect(document.documentElement.dataset.theme).toBeUndefined();
  });

  it("applies an explicit theme and keeps it after a reload", async () => {
    const user = userEvent.setup();
    const first = render(<App />);
    await user.selectOptions(themeSelect(), "dark");
    expect(document.documentElement.dataset.theme).toBe("dark");
    first.unmount();
    delete document.documentElement.dataset.theme;

    render(<App />);
    expect(themeSelect()).toHaveValue("dark");
    expect(document.documentElement.dataset.theme).toBe("dark");
  });

  it("returns to the system theme", async () => {
    const user = userEvent.setup();
    render(<App />);
    await user.selectOptions(themeSelect(), "light");
    expect(document.documentElement.dataset.theme).toBe("light");
    await user.selectOptions(themeSelect(), "system");
    expect(document.documentElement.dataset.theme).toBeUndefined();
  });

  it("keeps the current draft view when the theme changes", async () => {
    const user = userEvent.setup();
    render(<App />);
    await user.click(screen.getByRole("link", { name: "Runs" }));
    await user.selectOptions(themeSelect(), "dark");
    expect(screen.getByRole("heading", { level: 1, name: "Runs" })).toBeInTheDocument();
  });

  it("ignores corrupt stored state", () => {
    window.localStorage.setItem("omrg-workspace-ui", "{not json");
    render(<App />);
    expect(themeSelect()).toHaveValue("system");
    expect(screen.getByRole("heading", { level: 1, name: "Canvas" })).toBeInTheDocument();
  });

  it("ignores stored values outside the allowed set", () => {
    window.localStorage.setItem(
      "omrg-workspace-ui",
      JSON.stringify({ version: 1, view: "admin", theme: "neon", inspectorOpen: "yes" }),
    );
    render(<App />);
    expect(themeSelect()).toHaveValue("system");
    expect(screen.getByRole("heading", { level: 1, name: "Canvas" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Inspector" })).toHaveAttribute("aria-expanded", "false");
  });

  it("still works when storage methods throw", async () => {
    const denied = () => {
      throw new DOMException("Storage is disabled", "SecurityError");
    };
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(denied);
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(denied);

    const user = userEvent.setup();
    render(<App />);
    await user.selectOptions(themeSelect(), "dark");
    expect(document.documentElement.dataset.theme).toBe("dark");
  });

  it("still works when the storage object itself is unavailable", async () => {
    vi.spyOn(window, "localStorage", "get").mockImplementation(() => {
      throw new DOMException("Storage is disabled", "SecurityError");
    });

    const user = userEvent.setup();
    render(<App />);
    await user.selectOptions(themeSelect(), "light");
    expect(document.documentElement.dataset.theme).toBe("light");
  });
});
