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
  it("shows the open section of a project inside a card", async () => {
    startApp("#/knowledge-base/documents", documentsServer());
    const table = await sourcesTable();
    expect(table.closest("[data-slot='card']")).not.toBeNull();
  });

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
      documentsServer({ "GET /v1/collections": () => (fail ? json({ status: "error", message: "Unexpected token <" }, 500) : [{ name: "documents", document_count: 3, chunk_count: 12, profile: null, display_name: null, store: { name: "lancedb", label: "LanceDB" } }]) }),
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

  it("shows the vector database in the header with its logo and in each project chip", async () => {
    startApp("#/knowledge-base/documents");
    await sourcesTable();
    const header = screen.getByRole("group", { name: "Project summary" });
    expect(within(header).getByText("LanceDB")).toBeInTheDocument();
    expect(header.querySelector("img[src$='integrations/vector-stores/lancedb.png']")).not.toBeNull();
    const chips = within(screen.getByRole("list", { name: "Projects" })).getAllByRole("button");
    for (const chip of chips) expect(chip).toHaveTextContent("LanceDB");
    expect(screen.getByRole("list", { name: "Projects" }).querySelector("img")).toBeNull();
  });

  it("keeps the Source and Stable ID cells at a readable minimum width, then lets them wrap", async () => {
    startApp("#/knowledge-base/documents");
    const rows = within(await sourcesTable()).getAllByRole("row").slice(1);
    for (const row of rows) {
      const [source, stableId] = within(row).getAllByRole("cell");
      expect(source).toHaveClass("min-w-48", "break-all");
      expect(stableId).toHaveClass("min-w-48", "break-all");
    }
  });

  it("names the vector database in a Database column of the sources table", async () => {
    startApp("#/knowledge-base/documents");
    const table = await sourcesTable();
    expect(within(table).getByRole("columnheader", { name: "Database" })).toBeInTheDocument();
    for (const row of within(table).getAllByRole("row").slice(1)) expect(row).toHaveTextContent("LanceDB");
    expect(table.querySelector("img")).toBeNull();
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

const STORE = { name: "lancedb", label: "LanceDB" };

function namedCollections(displayName: string | null) {
  return [
    { name: "documents", document_count: 3, chunk_count: 12, profile: null, display_name: displayName, store: STORE },
    { name: "notes", document_count: 1, chunk_count: 2, profile: null, display_name: null, store: STORE },
  ];
}

describe("display name", () => {
  it("shows the display name as the title and in the chip, with the collection name kept where it is an identifier", async () => {
    startApp("#/knowledge-base/documents", documentsServer({ "GET /v1/collections": () => namedCollections("Project docs") }));
    expect(await screen.findByRole("heading", { level: 2, name: "Project docs" })).toBeInTheDocument();
    expect(screen.getByText("Collection name: documents")).toBeInTheDocument();
    const chips = within(screen.getByRole("list", { name: "Projects" })).getAllByRole("button");
    expect(chips[0]).toHaveTextContent("Project docs");
    expect(chips[1]).toHaveTextContent("notes");
    // The identifier places keep the collection name.
    expect(await sourcesTable()).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 2, name: "Sources in documents" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Delete collection documents" })).toBeInTheDocument();
    expect(window.location.hash).toBe("#/knowledge-base/documents");
  });

  it("falls back to the collection name when no display name is set", async () => {
    startApp("#/knowledge-base/documents", documentsServer({ "GET /v1/collections": () => namedCollections(null) }));
    expect(await screen.findByRole("heading", { level: 2, name: "documents" })).toBeInTheDocument();
    expect(screen.getByText("Collection name: documents")).toBeInTheDocument();
  });

  it("updates the title everywhere after an edit, without leaving the route", async () => {
    let stored: string | null = null;
    const server = documentsServer({
      "GET /v1/collections": () => namedCollections(stored),
      "PATCH /v1/collections/documents/display-name": (body) => {
        stored = (body.display_name as string) || null;
        return { collection: "documents", display_name: stored };
      },
    });
    const user = userEvent.setup();
    startApp("#/knowledge-base/documents", server);
    await user.click(await screen.findByRole("button", { name: "Edit display name of documents" }));
    await user.type(screen.getByRole("textbox", { name: "Display name" }), "Research notes{Enter}");
    expect(await screen.findByRole("heading", { level: 2, name: "Research notes" })).toBeInTheDocument();
    const chips = within(screen.getByRole("list", { name: "Projects" })).getAllByRole("button");
    await waitFor(() => expect(chips[0]).toHaveTextContent("Research notes"));
    expect(screen.getByText("Collection name: documents")).toBeInTheDocument();
    expect(window.location.hash).toBe("#/knowledge-base/documents");
  });
});
