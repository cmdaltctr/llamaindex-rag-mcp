import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import App from "../App";
import { NAV_COLLAPSED_KEY } from "../lib/navCollapsed";
import { PREFERENCES_KEY } from "../lib/preferences";
import { documentsServer, json } from "../test/fakeDocumentsServer";
import { createQueryClient } from "../api/queries";
import { renderWithProviders } from "../test/providers";

const REPOSITORY = "https://github.com/cmdaltctr/llamaindex-rag-mcp";
const HEALTH_UP = { "GET /v1/health": () => ({ status: "ok", ready: true, version: "2.3.4" }) };
const HEALTH_DOWN = { "GET /v1/health": () => json({ detail: "down" }, 503) };

function start(handlers: Parameters<typeof documentsServer>[0] = HEALTH_UP, hash = "") {
  window.history.replaceState(null, "", `/${hash}`);
  const server = documentsServer(handlers);
  renderWithProviders(<App />, { fetchImpl: server.fetchImpl });
}

function foot() {
  return screen.getByRole("group", { name: "Quick controls" });
}

/** The foot's controls in document order. */
function controls() {
  return Array.from(foot().querySelectorAll<HTMLElement>("button, a"));
}

function storedTheme() {
  return JSON.parse(window.localStorage.getItem(PREFERENCES_KEY) ?? "{}").theme;
}

describe("navigation foot", () => {
  it("holds four controls in order, theme, Settings, power, GitHub", () => {
    start();
    const items = controls();
    expect(items.map((control) => control.tagName)).toEqual(["BUTTON", "A", "BUTTON", "A"]);
    expect(items[0]).toHaveAccessibleName("Switch to dark theme");
    expect(items[1]).toHaveAccessibleName("Settings");
    expect(items[2]).toHaveAccessibleName(/^Server status/);
    expect(items[3]).toHaveAccessibleName("OMRG on GitHub");
  });

  it("has no language control", () => {
    start();
    expect(within(foot()).queryByRole("combobox")).not.toBeInTheDocument();
    expect(within(foot()).queryByRole("button", { name: /language/i })).not.toBeInTheDocument();
    expect(controls()).toHaveLength(4);
  });

  it("gives every control an icon and keeps the area links apart from the foot", () => {
    start();
    for (const control of controls()) {
      expect(control.querySelector("svg")).not.toBeNull();
    }
    expect(within(screen.getByRole("navigation", { name: "Workspace" })).queryByRole("group", { name: "Quick controls" })).not.toBeInTheDocument();
  });

  it("switches light to dark in one click, stores it and names the next switch", async () => {
    const user = userEvent.setup();
    start();
    await user.click(within(foot()).getByRole("button", { name: "Switch to dark theme" }));
    expect(document.documentElement.dataset.theme).toBe("dark");
    expect(storedTheme()).toBe("dark");
    expect(within(foot()).getByRole("button", { name: "Switch to light theme" })).toBeInTheDocument();
  });

  it("switches dark to light in one click and the Settings select reads the same value", async () => {
    const user = userEvent.setup();
    window.localStorage.setItem(PREFERENCES_KEY, JSON.stringify({ theme: "dark", lastCollection: null }));
    start();
    await user.click(within(foot()).getByRole("button", { name: "Switch to light theme" }));
    expect(document.documentElement.dataset.theme).toBe("light");
    expect(storedTheme()).toBe("light");
    await user.click(within(foot()).getByRole("link", { name: "Settings" }));
    expect(screen.getByRole("combobox", { name: "Theme" })).toHaveTextContent("Light");
  });

  it("links to the Settings route and marks it current there", () => {
    start(HEALTH_UP, "#/settings");
    const link = within(foot()).getByRole("link", { name: "Settings" });
    expect(link).toHaveAttribute("href", "#/settings");
    expect(link).toHaveAttribute("aria-current", "page");
  });

  it("opens Settings from the foot", async () => {
    const user = userEvent.setup();
    start();
    await user.click(within(foot()).getByRole("link", { name: "Settings" }));
    expect(window.location.hash).toBe("#/settings");
  });

  it("shows a green power light, Running and the version while health answers", async () => {
    const user = userEvent.setup();
    start();
    const power = within(foot()).getByRole("button", { name: /^Server status/ });
    await waitFor(() => expect(power).toHaveAccessibleName("Server status: Running"));
    expect(power.querySelector("svg")).toHaveClass("text-status-success");
    await user.click(power);
    const panel = document.querySelector("[data-slot='power-panel']") as HTMLElement;
    expect(within(panel).getByText("Running")).toBeInTheDocument();
    expect(within(panel).getByText(/2\.3\.4/)).toBeInTheDocument();
  });

  it("shows a grey power light and Not answering when health fails", async () => {
    const user = userEvent.setup();
    start(HEALTH_DOWN);
    const power = within(foot()).getByRole("button", { name: /^Server status/ });
    await waitFor(() => expect(power).toHaveAccessibleName("Server status: Not answering"));
    expect(power.querySelector("svg")).toHaveClass("text-muted-foreground");
    expect(power.querySelector("svg")).not.toHaveClass("text-status-success");
    await user.click(power);
    const panel = document.querySelector("[data-slot='power-panel']") as HTMLElement;
    expect(within(panel).getByText("Not answering")).toBeInTheDocument();
    expect(within(panel).queryByText(/2\.3\.4/)).not.toBeInTheDocument();
  });

  it("turns grey and says Not answering when a later health poll fails, without the old version", async () => {
    const user = userEvent.setup();
    let up = true;
    const queryClient = createQueryClient({ retry: false });
    window.history.replaceState(null, "", "/");
    const server = documentsServer({
      "GET /v1/health": () => (up ? { status: "ok", ready: true, version: "2.3.4" } : json({ detail: "down" }, 503)),
    });
    renderWithProviders(<App />, { fetchImpl: server.fetchImpl, queryClient });
    const power = within(foot()).getByRole("button", { name: /^Server status/ });
    await waitFor(() => expect(power).toHaveAccessibleName("Server status: Running"));
    up = false;
    await queryClient.refetchQueries({ queryKey: ["health"] });
    await waitFor(() => expect(power).toHaveAccessibleName("Server status: Not answering"));
    expect(power.querySelector("svg")).toHaveClass("text-muted-foreground");
    await user.click(power);
    const panel = document.querySelector("[data-slot='power-panel']") as HTMLElement;
    expect(within(panel).getByText("Not answering")).toBeInTheDocument();
    expect(within(panel).queryByText(/2\.3\.4/)).not.toBeInTheDocument();
  });

  it("offers Turn off and Restart, both disabled with the two commands named while the server is not the login item", async () => {
    const user = userEvent.setup();
    start({ ...HEALTH_UP, "GET /v1/server/power": () => ({ managed: false }) });
    await user.click(within(foot()).getByRole("button", { name: /^Server status/ }));
    const panel = document.querySelector("[data-slot='power-panel']") as HTMLElement;
    await waitFor(() => expect(within(panel).getByText(/runs in a terminal/i)).toBeInTheDocument());
    expect(within(panel).getByRole("button", { name: "Turn off" })).toBeDisabled();
    expect(within(panel).getByRole("button", { name: "Restart" })).toBeDisabled();
    expect(within(panel).getByText("omrg web restart")).toBeInTheDocument();
    expect(within(panel).getByText("omrg web open")).toBeInTheDocument();
    expect(within(panel).getAllByRole("button", { name: /^Copy/ })).toHaveLength(2);
  });

  it("links to the repository in a new tab without leaking the opener", () => {
    start();
    const link = within(foot()).getByRole("link", { name: "OMRG on GitHub" });
    expect(link).toHaveAttribute("href", REPOSITORY);
    expect(link).toHaveAttribute("target", "_blank");
    expect(link.getAttribute("rel")?.split(" ")).toEqual(expect.arrayContaining(["noopener", "noreferrer"]));
  });

  it("stacks four icon-only controls in one column when the navigation is collapsed", () => {
    window.localStorage.setItem(NAV_COLLAPSED_KEY, "true");
    start();
    expect(foot()).toHaveClass("md:flex-col");
    for (const control of controls()) {
      expect(control.textContent?.trim()).toBe("");
    }
  });

  it("keeps the controls in the page below the md breakpoint", () => {
    start();
    expect(foot()).not.toHaveClass("hidden");
    expect(foot().className).not.toMatch(/(^|\s)(max-md:hidden|hidden)(\s|$)/);
  });
});
