import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import App from "./App";

const VIEWS = ["Canvas", "Library", "Search", "Ask", "Runs", "Experiments", "Settings"];

function nav() {
  return screen.getByRole("navigation", { name: "Workspace" });
}

describe("application navigation", () => {
  it("lists every workspace view in order", () => {
    render(<App />);
    const links = within(nav()).getAllByRole("link");
    expect(links.map((link) => link.textContent)).toEqual(VIEWS);
  });

  it("opens Canvas by default", () => {
    render(<App />);
    expect(screen.getByRole("heading", { level: 1, name: "Canvas" })).toBeInTheDocument();
    expect(within(nav()).getByRole("link", { name: "Canvas" })).toHaveAttribute("aria-current", "page");
  });

  it.each(VIEWS)("renders the %s view with a heading and an empty state", async (name) => {
    const user = userEvent.setup();
    render(<App />);
    await user.click(within(nav()).getByRole("link", { name }));
    expect(screen.getByRole("heading", { level: 1, name })).toBeInTheDocument();
    expect(within(nav()).getByRole("link", { name })).toHaveAttribute("aria-current", "page");
    expect(screen.getByTestId("empty-state")).toBeInTheDocument();
  });

  it("follows the address hash", () => {
    window.history.replaceState(null, "", "/#/runs");
    render(<App />);
    expect(screen.getByRole("heading", { level: 1, name: "Runs" })).toBeInTheDocument();
  });

  it("restores the last selected view after a reload", async () => {
    const user = userEvent.setup();
    const first = render(<App />);
    await user.click(within(nav()).getByRole("link", { name: "Library" }));
    first.unmount();
    window.history.replaceState(null, "", "/");

    render(<App />);
    expect(screen.getByRole("heading", { level: 1, name: "Library" })).toBeInTheDocument();
  });
});

describe("inspector", () => {
  function toggle() {
    return screen.getByRole("button", { name: "Inspector" });
  }

  it("starts closed and opens with the keyboard", async () => {
    const user = userEvent.setup();
    render(<App />);
    expect(toggle()).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByRole("complementary", { name: "Inspector" })).not.toBeInTheDocument();

    toggle().focus();
    await user.keyboard("{Enter}");
    expect(toggle()).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByRole("complementary", { name: "Inspector" })).toBeInTheDocument();

    await user.keyboard(" ");
    expect(toggle()).toHaveAttribute("aria-expanded", "false");
  });

  it("closes with Escape and returns focus to its toggle", async () => {
    const user = userEvent.setup();
    render(<App />);
    await user.click(toggle());
    const close = within(screen.getByRole("complementary", { name: "Inspector" })).getByRole("button", {
      name: "Close inspector",
    });
    close.focus();
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("complementary", { name: "Inspector" })).not.toBeInTheDocument();
    expect(toggle()).toHaveFocus();
  });

  it("keeps its open state across navigation and reloads", async () => {
    const user = userEvent.setup();
    const first = render(<App />);
    await user.click(toggle());
    await user.click(within(nav()).getByRole("link", { name: "Search" }));
    expect(screen.getByRole("complementary", { name: "Inspector" })).toBeInTheDocument();
    first.unmount();

    render(<App />);
    expect(toggle()).toHaveAttribute("aria-expanded", "true");
  });
});
