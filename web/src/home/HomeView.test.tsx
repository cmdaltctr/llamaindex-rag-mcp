import { screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import userEvent from "@testing-library/user-event";
import { documentsServer, json } from "../test/fakeDocumentsServer";
import { startApp } from "../test/startApp";

describe("Home", () => {
  it("shows one card per collection with name, profile, document and chunk counts", async () => {
    startApp("#/home");
    const list = await screen.findByRole("list", { name: "Projects" });
    const cards = within(list).getAllByRole("listitem");
    expect(cards).toHaveLength(2);
    expect(cards[0]).toHaveTextContent("documents");
    expect(cards[0]).toHaveTextContent("3 documents");
    expect(cards[0]).toHaveTextContent("12 chunks");
    expect(within(cards[0]!).getByText("documents", { selector: "[data-slot=badge]" })).toBeInTheDocument();
    expect(cards[1]).toHaveTextContent("notes");
    expect(cards[1]).toHaveTextContent("1 document");
    expect(cards[1]).toHaveTextContent("No profile");
  });

  it("shows the vector database of each project with its logo and name", async () => {
    startApp("#/home");
    const list = await screen.findByRole("list", { name: "Projects" });
    for (const card of within(list).getAllByRole("listitem")) {
      expect(card).toHaveTextContent("LanceDB");
      const logo = card.querySelector("img");
      expect(logo?.getAttribute("src")).toMatch(/integrations\/vector-stores\/lancedb\.png$/);
      expect(logo).toHaveAttribute("alt", "");
    }
    // The card body is a column by default. The profile badge and the database name sit in one row,
    // so a wrapping row must reset the direction, or the two items stack and centre.
    for (const body of list.querySelectorAll("[data-slot=card-content]")) {
      expect(body).toHaveClass("flex-row", "flex-wrap");
      expect(body).not.toHaveClass("flex-col");
    }
  });

  it("titles a card with its display name and links by the collection name", async () => {
    startApp("#/home", documentsServer({ "GET /v1/collections": () => [{ name: "documents", document_count: 3, chunk_count: 12, profile: null, display_name: "Project docs", store: { name: "lancedb", label: "LanceDB" } }] }));
    const link = await screen.findByRole("link", { name: /Project docs/ });
    expect(link).toHaveAttribute("href", "#/knowledge-base/documents");
    expect(within(link).getByRole("heading", { name: "Project docs" })).toBeInTheDocument();
  });

  it("shows the real collection name in grey under the counts, with or without a display name", async () => {
    startApp("#/home", documentsServer({ "GET /v1/collections": () => [
      { name: "documents", document_count: 3, chunk_count: 12, profile: null, display_name: "Project docs", store: { name: "lancedb", label: "LanceDB" } },
      { name: "notes", document_count: 1, chunk_count: 2, profile: null, display_name: null, store: { name: "lancedb", label: "LanceDB" } },
    ] }));
    const cards = within(await screen.findByRole("list", { name: "Projects" })).getAllByRole("listitem");
    const first = within(cards[0]!).getByText("Collection name: documents");
    expect(within(cards[1]!).getByText("Collection name: notes")).toBeInTheDocument();
    // It sits after the counts line, so the card reads title, counts, collection name.
    const counts = within(cards[0]!).getByText("3 documents, 12 chunks");
    expect(counts.compareDocumentPosition(first) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it("opens the project in the Knowledge Base from the whole card", async () => {
    const user = userEvent.setup();
    startApp("#/home");
    const link = await screen.findByRole("link", { name: /notes/ });
    expect(link).toHaveAttribute("href", "#/knowledge-base/notes");
    await user.click(link);
    expect(window.location.hash).toBe("#/knowledge-base/notes");
    expect(await screen.findByRole("heading", { level: 1, name: "Knowledge Base" })).toBeInTheDocument();
  });

  it("encodes a collection name in the link", async () => {
    startApp("#/home", documentsServer({ "GET /v1/collections": () => [{ name: "research notes", document_count: 0, chunk_count: 0, profile: null, display_name: null, store: { name: "lancedb", label: "LanceDB" } }] }));
    expect(await screen.findByRole("link", { name: /research notes/ })).toHaveAttribute("href", "#/knowledge-base/research%20notes");
  });

  it("does not request the collection list again when the user moves to Chat", async () => {
    const user = userEvent.setup();
    const { server } = startApp("#/home");
    await screen.findByRole("list", { name: "Projects" });
    await user.click(screen.getByRole("link", { name: "Chat" }));
    expect(await screen.findByRole("list", { name: "Knowledge bases" })).toBeInTheDocument();
    expect(server.calls.filter((call) => call.path === "/v1/collections")).toHaveLength(1);
  });

  it("shows an empty state with one ingest action when there are no collections", async () => {
    startApp("#/home", documentsServer({ "GET /v1/collections": () => [] }));
    const empty = await screen.findByTestId("empty-state");
    expect(empty).toHaveTextContent(/no projects/i);
    expect(within(empty).getAllByRole("link")).toHaveLength(1);
    expect(within(empty).getByRole("link", { name: "Start an ingest" })).toHaveAttribute("href", "#/knowledge-base");
  });

  it("shows a friendly failure with Retry and never the raw text", async () => {
    vi.spyOn(console, "error").mockImplementation(() => undefined);
    let fail = true;
    startApp("#/home", documentsServer({ "GET /v1/collections": () => (fail ? json({ status: "error", message: "Store <html>offline" }, 500) : []) }));
    const alert = await screen.findByRole("alert");
    expect(alert).not.toHaveTextContent("Store");
    fail = false;
    await userEvent.setup().click(within(alert).getByRole("button", { name: "Retry" }));
    expect(await screen.findByTestId("empty-state")).toBeInTheDocument();
  });
});
