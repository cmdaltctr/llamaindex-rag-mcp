import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import App from "./App";
import { NAV_COLLAPSED_KEY } from "./lib/navCollapsed";
import { PREFERENCES_KEY } from "./lib/preferences";
import { renderWithProviders } from "./test/providers";
import { documentsServer, json } from "./test/fakeDocumentsServer";

const AREAS = ["Home", "Chat", "Knowledge Base", "Studio", "Experiments", "Integrations", "Settings"];

function nav() {
  return screen.getByRole("navigation", { name: "Workspace" });
}

function start(hash = "", server = documentsServer()) {
  window.history.replaceState(null, "", `/${hash}`);
  return { server, ...renderWithProviders(<App />, { fetchImpl: server.fetchImpl }) };
}

describe("navigation", () => {
  it("lists the seven areas in order, each with a decorative icon", () => {
    start();
    const links = within(nav()).getAllByRole("link");
    expect(links.map((link) => link.querySelector("span.sr-only")?.textContent)).toEqual(AREAS);
    for (const link of links) {
      const icon = link.querySelector("svg");
      expect(icon).not.toBeNull();
      expect(icon).toHaveAttribute("aria-hidden", "true");
    }
  });

  it("opens Home and writes #/home on a fresh visit", () => {
    start();
    expect(screen.getByRole("heading", { level: 1, name: "Home" })).toBeInTheDocument();
    expect(within(nav()).getByRole("link", { name: "Home" })).toHaveAttribute("aria-current", "page");
    expect(window.location.hash).toBe("#/home");
  });

  it.each(["#/nope", "#/library", "#/canvas", "#/chat/a/b", "#"])("rewrites the unknown hash %s to Home", (hash) => {
    start(hash);
    expect(screen.getByRole("heading", { level: 1, name: "Home" })).toBeInTheDocument();
    expect(window.location.hash).toBe("#/home");
  });

  it.each([
    ["#/chat", "Chat"],
    ["#/chat/papers", "Chat"],
    ["#/knowledge-base/papers", "Knowledge Base"],
    ["#/studio/pl_1", "Studio"],
    ["#/experiments/runs/r1", "Experiments"],
    ["#/integrations", "Integrations"],
    ["#/settings", "Settings"],
  ])("opens %s with %s active", (hash, name) => {
    start(hash);
    expect(within(nav()).getByRole("link", { name })).toHaveAttribute("aria-current", "page");
    expect(window.location.hash).toBe(hash);
  });

  it("follows a click, pushes history, and follows back and forward", async () => {
    const user = userEvent.setup();
    start();
    await user.click(within(nav()).getByRole("link", { name: "Chat" }));
    expect(window.location.hash).toBe("#/chat");
    expect(within(nav()).getByRole("link", { name: "Chat" })).toHaveAttribute("aria-current", "page");
    await user.click(within(nav()).getByRole("link", { name: "Settings" }));
    expect(within(nav()).getByRole("link", { name: "Settings" })).toHaveAttribute("aria-current", "page");

    window.history.back();
    await waitFor(() => expect(within(nav()).getByRole("link", { name: "Chat" })).toHaveAttribute("aria-current", "page"));
    window.history.forward();
    await waitFor(() => expect(within(nav()).getByRole("link", { name: "Settings" })).toHaveAttribute("aria-current", "page"));
  });

  it("moves focus to the heading after the user navigates, not on first load", async () => {
    const user = userEvent.setup();
    start();
    expect(screen.getByRole("heading", { level: 1, name: "Home" })).not.toHaveFocus();
    await user.click(within(nav()).getByRole("link", { name: "Studio" }));
    await waitFor(() => expect(screen.getByRole("heading", { level: 1, name: "Studio" })).toHaveFocus());
  });

  it("keeps a skip link to the main region", () => {
    start();
    expect(screen.getByRole("link", { name: "Skip to content" })).toHaveAttribute("href", "#workspace-main");
  });

  it("keeps every short label within eight characters so seven fit one row at 390px", () => {
    start();
    const labels = [...nav().querySelectorAll("span[aria-hidden='true']")].map((span) => span.textContent ?? "");
    expect(labels).toHaveLength(7);
    for (const label of labels) expect(label.length, label).toBeLessThanOrEqual(8);
  });

  it("truncates a short label that is still too wide instead of touching its neighbour", () => {
    start();
    for (const span of nav().querySelectorAll("span[aria-hidden='true']")) expect(span).toHaveClass("w-full", "truncate", "text-center");
  });

  it("gives narrow screens a row of targets at least 44px high", () => {
    start();
    for (const link of within(nav()).getAllByRole("link")) expect(link.className).toContain("min-h-11");
  });

  it("marks the top bar by border and shadow, so it stands out from the canvas in both themes", () => {
    start();
    const bar = screen.getByText("Local workspace").closest("header");
    expect(bar).not.toBeNull();
    expect(bar).toHaveClass("border-b", "border-border", "shadow-floating");
  });

  it("has no global Inspector", () => {
    start();
    expect(screen.queryByRole("button", { name: "Inspector" })).not.toBeInTheDocument();
  });
});

describe("engine status pill", () => {
  it("shows the collection count", async () => {
    start();
    expect(await screen.findByText("2 collections")).toBeInTheDocument();
  });

  it("uses the singular for one collection", async () => {
    start("", documentsServer({ "GET /v1/collections": () => [{ name: "a", document_count: 1, chunk_count: 1, profile: null }] }));
    expect(await screen.findByText("1 collection")).toBeInTheDocument();
  });

  it("shows offline when the server is unreachable", async () => {
    start("", documentsServer({ "GET /v1/collections": () => json({ message: "x" }, 503) }));
    expect(await screen.findByText("Offline")).toBeInTheDocument();
  });
});

describe("theme controls", () => {
  it("follows the system theme by default", () => {
    start();
    expect(document.documentElement.dataset.theme).toBeUndefined();
  });

  it("keeps the theme select out of the top bar", () => {
    start();
    expect(screen.queryByRole("combobox", { name: "Theme" })).not.toBeInTheDocument();
  });

  it("switches between light and dark with one click and names the target", async () => {
    const user = userEvent.setup();
    start();
    await user.click(screen.getByRole("button", { name: "Switch to dark theme" }));
    expect(document.documentElement.dataset.theme).toBe("dark");
    expect(JSON.parse(window.localStorage.getItem(PREFERENCES_KEY) ?? "{}").theme).toBe("dark");
    await user.click(screen.getByRole("button", { name: "Switch to light theme" }));
    expect(document.documentElement.dataset.theme).toBe("light");
    expect(JSON.parse(window.localStorage.getItem(PREFERENCES_KEY) ?? "{}").theme).toBe("light");
  });

  it("restores the stored theme and keeps the current area", async () => {
    window.localStorage.setItem(PREFERENCES_KEY, JSON.stringify({ theme: "dark", lastCollection: null }));
    start("#/settings");
    expect(document.documentElement.dataset.theme).toBe("dark");
    expect(screen.getByRole("button", { name: "Switch to light theme" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 1, name: "Settings" })).toBeInTheDocument();
  });

  it("falls back to defaults and removes a stored value that fails validation", () => {
    window.localStorage.setItem(PREFERENCES_KEY, JSON.stringify({ theme: "neon" }));
    start();
    expect(document.documentElement.dataset.theme).toBeUndefined();
    expect(window.localStorage.getItem(PREFERENCES_KEY)).toBeNull();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("still works when storage throws", async () => {
    const denied = () => {
      throw new DOMException("Storage is disabled", "SecurityError");
    };
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(denied);
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(denied);
    const user = userEvent.setup();
    start();
    await user.click(screen.getByRole("button", { name: "Switch to dark theme" }));
    expect(document.documentElement.dataset.theme).toBe("dark");
  });
});

describe("brand", () => {
  it("shows the decorative logo and name in the navigation header", () => {
    start();
    const logo = nav().querySelector("img");
    expect(logo).not.toBeNull();
    expect(logo).toHaveAttribute("alt", "");
    expect(logo?.getAttribute("src")).toMatch(/omrg-logo\.svg$/);
    expect(within(nav()).getByText("OMRG")).toBeInTheDocument();
  });

  it("shows the server version beside the name and hides it when collapsed", async () => {
    const user = userEvent.setup();
    start("", documentsServer({ "GET /v1/health": () => ({ status: "ok", ready: true, version: "2.3.4" }) }));
    expect(await within(nav()).findByText("v2.3.4")).toBeInTheDocument();
    await user.click(within(nav()).getByRole("button", { name: "Collapse navigation" }));
    expect(within(nav()).queryByText("v2.3.4")).not.toBeInTheDocument();
  });

  it("keeps the name for screen readers when collapsed", async () => {
    const user = userEvent.setup();
    start();
    await user.click(within(nav()).getByRole("button", { name: "Collapse navigation" }));
    expect(within(nav()).getByText("OMRG")).toHaveClass("sr-only");
  });
});

describe("navigation collapse", () => {
  it("collapses to icons, keeps link names and remembers the choice", async () => {
    const user = userEvent.setup();
    start();
    const nav = screen.getByRole("navigation", { name: "Workspace" });
    await user.click(within(nav).getByRole("button", { name: "Collapse navigation" }));
    expect(within(nav).getByRole("button", { name: "Expand navigation" })).toHaveAttribute("aria-expanded", "false");
    expect(within(nav).getByRole("link", { name: "Settings" })).toHaveAttribute("title", "Settings");
    expect(window.localStorage.getItem(NAV_COLLAPSED_KEY)).toBe("true");
  });

  it("starts collapsed when the stored choice says so", () => {
    window.localStorage.setItem(NAV_COLLAPSED_KEY, "true");
    start();
    expect(screen.getByRole("button", { name: "Expand navigation" })).toBeInTheDocument();
  });
});
