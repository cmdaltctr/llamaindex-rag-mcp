import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { PREFERENCES_KEY } from "../lib/preferences";
import { documentsServer, json } from "../test/fakeDocumentsServer";
import { startApp } from "../test/startApp";

function stored() {
  return JSON.parse(window.localStorage.getItem(PREFERENCES_KEY) ?? "{}") as { lastCollection?: string | null };
}

async function sourcesTable() {
  return screen.findByRole("table", { name: "Sources in documents" });
}

describe("project routes", () => {
  it("shows the project named in the URL, so a reload keeps it", async () => {
    startApp("#/knowledge-base/notes");
    expect(await screen.findByRole("heading", { level: 2, name: "notes" })).toBeInTheDocument();
    expect(window.location.hash).toBe("#/knowledge-base/notes");
    expect(await screen.findByTestId("empty-state")).toHaveTextContent(/no sources/i);
  });

  it("writes the last-used collection when a project opens", async () => {
    startApp("#/knowledge-base/documents");
    await sourcesTable();
    await waitFor(() => expect(stored().lastCollection).toBe("documents"));
  });

  it("opens the last-used collection when the server still lists it", async () => {
    window.localStorage.setItem(PREFERENCES_KEY, JSON.stringify({ theme: "system", lastCollection: "notes" }));
    startApp("#/knowledge-base");
    expect(await screen.findByRole("heading", { level: 2, name: "notes" })).toBeInTheDocument();
    expect(window.location.hash).toBe("#/knowledge-base/notes");
  });

  it("shows the project picker and drops a last-used collection that no longer exists", async () => {
    window.localStorage.setItem(PREFERENCES_KEY, JSON.stringify({ theme: "system", lastCollection: "gone" }));
    startApp("#/knowledge-base");
    const picker = await screen.findByRole("list", { name: "Projects" });
    expect(within(picker).getAllByRole("button").map((button) => button.textContent)).toEqual([
      expect.stringContaining("documents"),
      expect.stringContaining("notes"),
    ]);
    await waitFor(() => expect(stored().lastCollection).toBeNull());
    expect(window.location.hash).toBe("#/knowledge-base");
  });

  it("opens a project chosen in the picker", async () => {
    const user = userEvent.setup();
    startApp("#/knowledge-base");
    const picker = await screen.findByRole("list", { name: "Projects" });
    await user.click(within(picker).getByRole("button", { name: /notes/ }));
    expect(window.location.hash).toBe("#/knowledge-base/notes");
    expect(await screen.findByRole("heading", { level: 2, name: "notes" })).toBeInTheDocument();
    expect(stored().lastCollection).toBe("notes");
  });

  it("switches project with the same picker", async () => {
    const user = userEvent.setup();
    startApp("#/knowledge-base/documents");
    await sourcesTable();
    const picker = screen.getByRole("list", { name: "Projects" });
    expect(within(picker).getByRole("button", { name: /documents/ })).toHaveAttribute("aria-pressed", "true");
    await user.click(within(picker).getByRole("button", { name: /notes/ }));
    expect(window.location.hash).toBe("#/knowledge-base/notes");
    expect(within(picker).getByRole("button", { name: /notes/ })).toHaveAttribute("aria-pressed", "true");
  });

  it("shows not-found with a link to the picker for an unknown collection", async () => {
    startApp("#/knowledge-base/missing");
    expect(await screen.findByText(/collection .missing. could not be found/i)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Choose a project" })).toHaveAttribute("href", "#/knowledge-base");
  });

  it("offers a way to start a new project when no collection exists", async () => {
    startApp("#/knowledge-base", documentsServer({ "GET /v1/collections": () => [] }));
    expect(await screen.findByRole("textbox", { name: "Target collection" })).toBeInTheDocument();
    expect(screen.queryByRole("list", { name: "Projects" })).not.toBeInTheDocument();
  });

  it("shows a friendly failure with Retry when the listing fails", async () => {
    vi.spyOn(console, "error").mockImplementation(() => undefined);
    let fail = true;
    startApp(
      "#/knowledge-base/documents",
      documentsServer({ "GET /v1/collections": () => (fail ? json({ status: "error", message: "Unexpected token <" }, 500) : [{ name: "documents", document_count: 3, chunk_count: 12, profile: null }]) }),
    );
    const alert = await screen.findByRole("alert");
    expect(alert).not.toHaveTextContent("Unexpected token");
    fail = false;
    await userEvent.setup().click(within(alert).getByRole("button", { name: "Retry" }));
    expect(await sourcesTable()).toBeInTheDocument();
  });
});

describe("sources", () => {
  it("lists sources with chunk counts, stable ids and machine-local status badges", async () => {
    startApp("#/knowledge-base/documents");
    const rows = within(await sourcesTable()).getAllByRole("row").slice(1);
    expect(rows).toHaveLength(3);
    expect(rows[0]).toHaveTextContent("/srv/docs/present.md");
    expect(rows[0]).toHaveTextContent("sid-present");
    expect(rows[0]).toHaveTextContent("5");
    expect(within(rows[0]!).getByText("Present on this machine")).toHaveAttribute("data-slot", "badge");
    expect(rows[1]).toHaveTextContent("Missing on this machine");
    expect(rows[2]).toHaveTextContent("Unknown on this machine");
    // Unknown availability must never read as a missing or lost source.
    expect(rows[2]).not.toHaveTextContent(/missing|lost|deleted/i);
    expect(rows[2]).toHaveTextContent("No stable ID (legacy row)");
  });

  it("shows the collection's profile label", async () => {
    startApp("#/knowledge-base/documents");
    await sourcesTable();
    expect(screen.getByText("documents", { selector: "[data-slot=badge]" })).toBeInTheDocument();
  });

  it("shows one section at a time, switched by chips", async () => {
    const user = userEvent.setup();
    startApp("#/knowledge-base/documents");
    await sourcesTable();
    const group = screen.getByRole("group", { name: "Sections" });
    expect(within(group).getAllByRole("button").map((button) => button.textContent)).toEqual(["Sources", "Search", "Add", "Profile"]);
    expect(within(group).getByRole("button", { name: "Sources" })).toHaveAttribute("aria-pressed", "true");

    await user.click(within(group).getByRole("button", { name: "Search" }));
    expect(screen.queryByRole("table", { name: "Sources in documents" })).not.toBeInTheDocument();
    expect(screen.getByRole("search", { name: "Search documents" })).toBeInTheDocument();
    expect(within(group).getByRole("button", { name: "Search" })).toHaveAttribute("aria-pressed", "true");
    expect(within(group).getByRole("button", { name: "Sources" })).toHaveAttribute("aria-pressed", "false");

    await user.click(within(group).getByRole("button", { name: "Add" }));
    expect(screen.queryByRole("search", { name: "Search documents" })).not.toBeInTheDocument();
    expect(screen.getByLabelText("Files to upload")).toBeInTheDocument();

    await user.click(within(group).getByRole("button", { name: "Profile" }));
    expect(screen.getByRole("region", { name: "Collection profile" })).toBeInTheDocument();
    // Section is view state: the route does not change.
    expect(window.location.hash).toBe("#/knowledge-base/documents");
  });
});
