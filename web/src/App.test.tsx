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

  it.each(["#/nope", "#/library", "#/canvas", "#/chat/a/b/c", "#"])("rewrites the unknown hash %s to Home", (hash) => {
    start(hash);
    expect(screen.getByRole("heading", { level: 1, name: "Home" })).toBeInTheDocument();
    expect(window.location.hash).toBe("#/home");
  });

  it.each([
    ["#/chat", "Chat"],
    ["#/chat/papers", "Chat"],
    ["#/knowledge-base/papers", "Knowledge Base"],
    ["#/studio/papers-search/search", "Studio"],
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
    start("", documentsServer({ "GET /v1/collections": () => [{ name: "a", document_count: 1, chunk_count: 1, profile: null, display_name: null, store: { name: "lancedb", label: "LanceDB" } }] }));
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
    await user.click(within(screen.getByText("Local workspace").closest("header")!).getByRole("button", { name: "Switch to dark theme" }));
    expect(document.documentElement.dataset.theme).toBe("dark");
    expect(JSON.parse(window.localStorage.getItem(PREFERENCES_KEY) ?? "{}").theme).toBe("dark");
    await user.click(within(screen.getByText("Local workspace").closest("header")!).getByRole("button", { name: "Switch to light theme" }));
    expect(document.documentElement.dataset.theme).toBe("light");
    expect(JSON.parse(window.localStorage.getItem(PREFERENCES_KEY) ?? "{}").theme).toBe("light");
  });

  it("restores the stored theme and keeps the current area", async () => {
    window.localStorage.setItem(PREFERENCES_KEY, JSON.stringify({ theme: "dark", lastCollection: null }));
    start("#/settings");
    expect(document.documentElement.dataset.theme).toBe("dark");
    expect(within(screen.getByText("Local workspace").closest("header")!).getByRole("button", { name: "Switch to light theme" })).toBeInTheDocument();
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
    await user.click(within(screen.getByText("Local workspace").closest("header")!).getByRole("button", { name: "Switch to dark theme" }));
    expect(document.documentElement.dataset.theme).toBe("dark");
  });
});

describe("brand", () => {
  it("shows the decorative logo and name in the navigation header", () => {
    start();
    const logo = nav().querySelector("img");
    expect(logo).not.toBeNull();
    expect(logo).toHaveAttribute("alt", "");
    expect(logo?.getAttribute("src")).toMatch(/omrs-logo\.svg$/);
    expect(within(nav()).getByText("OMRS")).toBeInTheDocument();
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
    expect(within(nav()).getByText("OMRS")).toHaveClass("sr-only");
  });
});

describe("navigation collapse", () => {
  it("collapses to icons, keeps link names and remembers the choice", async () => {
    const user = userEvent.setup();
    start();
    const nav = screen.getByRole("navigation", { name: "Workspace" });
    await user.click(within(nav).getByRole("button", { name: "Collapse navigation" }));
    expect(within(nav).getByRole("button", { name: "Expand navigation" })).toHaveAttribute("aria-expanded", "false");
    expect(within(nav).getByRole("link", { name: "Settings" })).not.toHaveAttribute("title");
    expect(window.localStorage.getItem(NAV_COLLAPSED_KEY)).toBe("true");
  });

  it("starts collapsed when the stored choice says so", () => {
    window.localStorage.setItem(NAV_COLLAPSED_KEY, "true");
    start();
    expect(screen.getByRole("button", { name: "Expand navigation" })).toBeInTheDocument();
  });
});

describe("navigation on the canvas sub-page", () => {
  const CANVAS = "#/studio/papers-search/search";

  function toggleName() {
    return within(nav()).queryByRole("button", { name: "Expand navigation" }) ? "collapsed" : "expanded";
  }

  async function goTo(hash: string) {
    window.location.hash = hash;
    await waitFor(() => expect(window.location.hash).toBe(hash));
  }

  it("collapses an expanded navigation to the icon column", () => {
    window.localStorage.setItem(NAV_COLLAPSED_KEY, "false");
    start(CANVAS);
    expect(toggleName()).toBe("collapsed");
  });

  it("applies the stored choice again on other routes", async () => {
    window.localStorage.setItem(NAV_COLLAPSED_KEY, "false");
    start(CANVAS);
    await goTo("#/knowledge-base");
    await waitFor(() => expect(toggleName()).toBe("expanded"));
    expect(window.localStorage.getItem(NAV_COLLAPSED_KEY)).toBe("false");
  });

  it("does not store a temporary expansion and collapses again on re-entry", async () => {
    const user = userEvent.setup();
    window.localStorage.setItem(NAV_COLLAPSED_KEY, "false");
    start(CANVAS);
    await user.click(within(nav()).getByRole("button", { name: "Expand navigation" }));
    expect(toggleName()).toBe("expanded");
    expect(window.localStorage.getItem(NAV_COLLAPSED_KEY)).toBe("false");

    await goTo("#/knowledge-base");
    expect(window.localStorage.getItem(NAV_COLLAPSED_KEY)).toBe("false");
    await goTo(CANVAS);
    await waitFor(() => expect(toggleName()).toBe("collapsed"));
    expect(window.localStorage.getItem(NAV_COLLAPSED_KEY)).toBe("false");
  });

  it("collapses again when another profile opens", async () => {
    const user = userEvent.setup();
    start(CANVAS);
    await user.click(within(nav()).getByRole("button", { name: "Expand navigation" }));
    expect(toggleName()).toBe("expanded");
    await goTo("#/studio/other-profile");
    await waitFor(() => expect(toggleName()).toBe("collapsed"));
  });

  it("leaves the gallery on the stored choice", () => {
    window.localStorage.setItem(NAV_COLLAPSED_KEY, "false");
    start("#/studio");
    expect(toggleName()).toBe("expanded");
  });

  it("keeps the toggle working as a stored choice off the canvas", async () => {
    const user = userEvent.setup();
    start("#/studio");
    await user.click(within(nav()).getByRole("button", { name: "Collapse navigation" }));
    expect(window.localStorage.getItem(NAV_COLLAPSED_KEY)).toBe("true");
  });
});

describe("navigation on the chat page", () => {
  function toggleName() {
    return within(nav()).queryByRole("button", { name: "Expand navigation" }) ? "collapsed" : "expanded";
  }

  it("collapses an expanded navigation to the icon column", () => {
    window.localStorage.setItem(NAV_COLLAPSED_KEY, "false");
    start("#/chat");
    expect(toggleName()).toBe("collapsed");
  });

  it("expands for this visit only and applies the stored choice elsewhere", async () => {
    const user = userEvent.setup();
    window.localStorage.setItem(NAV_COLLAPSED_KEY, "false");
    start("#/chat");
    await user.click(within(nav()).getByRole("button", { name: "Expand navigation" }));
    expect(toggleName()).toBe("expanded");
    expect(window.localStorage.getItem(NAV_COLLAPSED_KEY)).toBe("false");

    window.location.hash = "#/home";
    await waitFor(() => expect(window.location.hash).toBe("#/home"));
    window.location.hash = "#/chat";
    await waitFor(() => expect(toggleName()).toBe("collapsed"));
  });
});

describe("shell on the canvas sub-page", () => {
  function main() {
    return document.getElementById("workspace-main") as HTMLElement;
  }

  it("uses the full window height and drops the page padding", () => {
    start("#/studio/papers-search/search");
    const shell = main().parentElement as HTMLElement;
    expect(shell).toHaveClass("h-dvh");
    expect(shell).not.toHaveClass("min-h-dvh");
    expect(main().className).not.toMatch(/(^|\s)(md:)?p-\d/);
    expect(main()).toHaveClass("min-h-0", "overflow-auto", "lg:overflow-hidden");
  });

  it.each(["#/studio", "#/knowledge-base", "#/home"])("keeps the page padding and minimum height on %s", (hash) => {
    start(hash);
    const shell = main().parentElement as HTMLElement;
    expect(shell).toHaveClass("min-h-dvh");
    expect(shell).not.toHaveClass("h-dvh");
    expect(main()).toHaveClass("p-4", "md:p-6");
  });
});
