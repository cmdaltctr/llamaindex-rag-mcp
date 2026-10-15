import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { documentsServer, json } from "../test/fakeDocumentsServer";
import { renderWithProviders } from "../test/providers";
import { ChunkViewer } from "./ChunkViewer";

function chunkView(id: string, index: number, text: string) {
  return {
    chunk_id: id, source_id: "sid", source_version: "v1", source_chunk_index: index,
    source_chunk_count: 4, source: "/srv/docs/present.md", page_label: index === 2 ? "4" : null, text, metadata: {},
  };
}

function inspection(id: string, index: number, text: string, previous: unknown[], next: unknown[]) {
  return { status: "ok", collection: "documents", text_format: "plain", chunk: chunkView(id, index, text), previous, next };
}

function setup(onClose = vi.fn()) {
  const server = documentsServer({
    "GET /v1/collections/documents/chunks/c-2": () =>
      inspection("c-2", 2, "<b>Second</b> chunk", [chunkView("c-1", 1, "First chunk")], [chunkView("c-3", 3, "Third chunk")]),
    "GET /v1/collections/documents/chunks/c-3": () => inspection("c-3", 3, "Third chunk", [chunkView("c-2", 2, "x")], []),
    "GET /v1/collections/documents/chunks/bad": () => json({ status: "error", message: "Boom <html>" }, 500),
  });
  renderWithProviders(<ChunkViewer collection="documents" chunkId="c-2" onClose={onClose} />, { fetchImpl: server.fetchImpl });
  return { server, onClose, user: userEvent.setup() };
}

describe("ChunkViewer", () => {
  it("shows the chunk text, source and position in a named dialog", async () => {
    const { server } = setup();
    const dialog = await screen.findByRole("dialog", { name: "Stored chunk" });
    expect(await within(dialog).findByText("<b>Second</b> chunk")).toBeInTheDocument();
    expect(dialog.querySelector("b")).toBeNull();
    expect(within(dialog).getByText("/srv/docs/present.md")).toBeInTheDocument();
    expect(within(dialog).getByText(/Chunk 3 of 4/)).toBeInTheDocument();
    expect(within(dialog).getByText(/Page 4/)).toBeInTheDocument();
    expect(server.find("GET", "/v1/collections/documents/chunks/c-2")[0]?.path).toBe("/v1/collections/documents/chunks/c-2?window=1");
  });

  it("moves to neighbouring chunks and disables the missing ones", async () => {
    const { user } = setup();
    const dialog = await screen.findByRole("dialog", { name: "Stored chunk" });
    await within(dialog).findByText(/Second/);
    await user.click(within(dialog).getByRole("button", { name: "Next chunk" }));
    expect(await within(dialog).findByText("Third chunk")).toBeInTheDocument();
    expect(within(dialog).getByRole("button", { name: "Next chunk" })).toBeDisabled();
    expect(within(dialog).getByRole("button", { name: "Previous chunk" })).toBeEnabled();
  });

  it("closes with Escape", async () => {
    const { user, onClose } = setup();
    await screen.findByRole("dialog", { name: "Stored chunk" });
    await user.keyboard("{Escape}");
    expect(onClose).toHaveBeenCalled();
  });

  it("shows a friendly failure and never the raw text", async () => {
    vi.spyOn(console, "error").mockImplementation(() => undefined);
    const server = documentsServer({ "GET /v1/collections/documents/chunks/bad": () => json({ status: "error", message: "Boom <html>" }, 500) });
    renderWithProviders(<ChunkViewer collection="documents" chunkId="bad" onClose={() => undefined} />, { fetchImpl: server.fetchImpl });
    const alert = await screen.findByRole("alert");
    expect(alert).not.toHaveTextContent("Boom");
  });
});
