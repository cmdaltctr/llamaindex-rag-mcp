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
    startApp("#/home", documentsServer({ "GET /v1/collections": () => [{ name: "research notes", document_count: 0, chunk_count: 0, profile: null }] }));
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
