import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import type { CollectionInfo } from "../api/documents";
import { documentsServer, json } from "../test/fakeDocumentsServer";
import { renderWithProviders } from "../test/providers";
import { DisplayNameEditor } from "./DisplayNameEditor";

const STORE = { name: "lancedb", label: "LanceDB" };
const NAMED: CollectionInfo = { name: "documents", document_count: 3, chunk_count: 12, profile: null, display_name: "Project docs", store: STORE };
const UNNAMED: CollectionInfo = { ...NAMED, display_name: null };
const PATH = "/v1/collections/documents/display-name";

function setup(project: CollectionInfo, handlers: Parameters<typeof documentsServer>[0] = {}) {
  const server = documentsServer({ [`PATCH ${PATH}`]: (body) => ({ collection: "documents", display_name: (body.display_name as string) || null }), ...handlers });
  renderWithProviders(<DisplayNameEditor project={project} />, { fetchImpl: server.fetchImpl });
  return { server, user: userEvent.setup() };
}

const pencil = () => screen.getByRole("button", { name: "Edit display name of documents" });
const field = () => screen.getByRole("textbox", { name: "Display name" });

describe("DisplayNameEditor", () => {
  it("shows the display name as the title and the collection name in grey under it", () => {
    setup(NAMED);
    expect(screen.getByRole("heading", { level: 2, name: "Project docs" })).toBeInTheDocument();
    expect(screen.getByText("Collection name: documents")).toBeInTheDocument();
  });

  it("falls back to the collection name when no display name is set, and still shows the grey line", () => {
    setup(UNNAMED);
    expect(screen.getByRole("heading", { level: 2, name: "documents" })).toBeInTheDocument();
    expect(screen.getByText("Collection name: documents")).toBeInTheDocument();
  });

  it("gives the pencil and the field accessible names that name the collection", async () => {
    const { user } = setup(NAMED);
    await user.click(pencil());
    expect(field()).toHaveValue("Project docs");
    expect(field()).toHaveFocus();
  });

  it("saves on Enter, closes the editor and announces the result", async () => {
    const { server, user } = setup(UNNAMED);
    await user.click(pencil());
    await user.type(field(), "Research notes{Enter}");
    await waitFor(() => expect(screen.queryByRole("textbox", { name: "Display name" })).not.toBeInTheDocument());
    const [call] = server.find("PATCH", PATH);
    expect(call?.body).toEqual({ display_name: "Research notes" });
    expect(await screen.findByRole("status")).toHaveTextContent("Display name saved.");
  });

  it("cancels on Escape without sending a request and keeps the title", async () => {
    const { server, user } = setup(NAMED);
    await user.click(pencil());
    await user.clear(field());
    await user.type(field(), "Changed{Escape}");
    expect(screen.queryByRole("textbox", { name: "Display name" })).not.toBeInTheDocument();
    expect(server.find("PATCH", PATH)).toHaveLength(0);
    expect(screen.getByRole("heading", { level: 2, name: "Project docs" })).toBeInTheDocument();
    expect(pencil()).toHaveFocus();
  });

  it("clears the display name when the field is emptied", async () => {
    const { server, user } = setup(NAMED);
    await user.click(pencil());
    await user.clear(field());
    await user.type(field(), "{Enter}");
    await waitFor(() => expect(server.find("PATCH", PATH)).toHaveLength(1));
    expect(server.find("PATCH", PATH)[0]?.body).toEqual({ display_name: "" });
  });

  it("blocks 81 code points before sending, says the limit, and stays open", async () => {
    const { server, user } = setup(UNNAMED);
    await user.click(pencil());
    await user.click(field());
    await user.paste("\u{1F600}".repeat(81));
    await user.keyboard("{Enter}");
    expect(await screen.findByRole("alert")).toHaveTextContent("at most 80");
    expect(server.find("PATCH", PATH)).toHaveLength(0);
    expect(field()).toBeInTheDocument();
  });

  it("sends exactly 80 code points", async () => {
    const { server, user } = setup(UNNAMED);
    await user.click(pencil());
    await user.click(field());
    await user.paste("\u{1F600}".repeat(80));
    await user.keyboard("{Enter}");
    await waitFor(() => expect(server.find("PATCH", PATH)).toHaveLength(1));
  });

  it("stays open with a friendly error, not the raw message, when the server refuses", async () => {
    const { user } = setup(UNNAMED, { [`PATCH ${PATH}`]: () => json({ status: "error", message: "RAW-SERVER-TEXT" }, 400) });
    await user.click(pencil());
    await user.type(field(), "Name{Enter}");
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("The local server could not complete that request.");
    expect(alert).not.toHaveTextContent("RAW-SERVER-TEXT");
    expect(field()).toHaveValue("Name");
  });

  it("offers Save and Cancel buttons for pointer use", async () => {
    const { server, user } = setup(UNNAMED);
    await user.click(pencil());
    await user.click(screen.getByRole("button", { name: "Cancel" }));
    expect(screen.queryByRole("textbox", { name: "Display name" })).not.toBeInTheDocument();
    await user.click(pencil());
    await user.type(field(), "Via button");
    await user.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(server.find("PATCH", PATH)).toHaveLength(1));
  });
});
