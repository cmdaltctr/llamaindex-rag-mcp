import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { documentsServer } from "../test/fakeDocumentsServer";
import { LibraryView } from "./LibraryView";

function profilePanel() {
  return screen.getByRole("region", { name: "Collection profile" });
}

describe("stored collection profile", () => {
  it("shows the stored profile of the selected collection from the collection list", async () => {
    const server = documentsServer({
      "GET /v1/collections": () => [
        { name: "documents", document_count: 3, chunk_count: 12, profile: "codebase" },
        { name: "notes", document_count: 1, chunk_count: 2, profile: null },
      ],
    });
    const user = userEvent.setup();
    render(<LibraryView fetchImpl={server.fetchImpl} pollMs={5} />);

    expect(await within(await screen.findByRole("region", { name: "Collection profile" })).findByText("Stored profile: codebase")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /notes/ }));
    expect(await within(profilePanel()).findByText("No profile is stored for this collection.")).toBeInTheDocument();
  });

  it("reloads the stored profile after a confirmed change", async () => {
    let stored = "documents";
    const server = documentsServer({
      "GET /v1/collections": () => [{ name: "documents", document_count: 3, chunk_count: 12, profile: stored }],
      "PATCH /v1/collections/documents/profile": (body) => {
        if (!body.confirm) {
          return {
            status: "preview",
            confirm_required: true,
            contract: { collection: "documents", old_profile: stored, new_profile: "codebase", chunk_count: 12, lever_impacts: [], reingest_pointer: "" },
            confirmation: { token: "ptok", expires_at: "2026-10-13T12:05:00Z", expires_in: 300, validity: "durable", warning: null },
          };
        }
        stored = "codebase";
        return { status: "ok", collection: "documents", profile: "codebase", chunk_count_unchanged: 12 };
      },
    });
    const user = userEvent.setup();
    render(<LibraryView fetchImpl={server.fetchImpl} pollMs={5} />);

    expect(await screen.findByText("Stored profile: documents")).toBeInTheDocument();
    await user.selectOptions(within(profilePanel()).getByRole("combobox", { name: "New profile" }), "codebase");
    await user.click(within(profilePanel()).getByRole("button", { name: "Preview profile change" }));
    await user.click(await screen.findByRole("button", { name: "Confirm profile change" }));
    await waitFor(() => expect(within(profilePanel()).getByText("Stored profile: codebase")).toBeInTheDocument());
  });
});
