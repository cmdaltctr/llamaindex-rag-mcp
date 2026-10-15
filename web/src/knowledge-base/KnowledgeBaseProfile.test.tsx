import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { documentsServer } from "../test/fakeDocumentsServer";
import { startApp } from "../test/startApp";

const LANCE = { name: "lancedb", label: "LanceDB" };

function profilePanel() {
  return screen.getByRole("region", { name: "Collection profile" });
}

async function openProfile(user: ReturnType<typeof userEvent.setup>) {
  await user.click(await screen.findByRole("button", { name: "Profile" }));
  return profilePanel();
}

describe("stored collection profile", () => {
  it("shows the stored profile of the open project from the collection list", async () => {
    const server = documentsServer({
      "GET /v1/collections": () => [
        { name: "documents", document_count: 3, chunk_count: 12, profile: "codebase", store: { name: "lancedb", label: "LanceDB" } },
        { name: "notes", document_count: 1, chunk_count: 2, profile: null, store: { name: "lancedb", label: "LanceDB" } },
      ],
    });
    const user = userEvent.setup();
    startApp("#/knowledge-base/documents", server);

    const panel = await openProfile(user);
    expect(within(panel).getByText("codebase", { selector: "[data-slot=badge]" })).toBeInTheDocument();
    await user.click(within(screen.getByRole("list", { name: "Projects" })).getByRole("button", { name: /notes/ }));
    expect(await within(profilePanel()).findByText("No profile", { selector: "[data-slot=badge]" })).toBeInTheDocument();
  });

  it("pre-selects the stored profile in the New profile list", async () => {
    const server = documentsServer({
      "GET /v1/collections": () => [{ name: "documents", document_count: 3, chunk_count: 12, profile: "codebase", store: LANCE }],
    });
    const user = userEvent.setup();
    startApp("#/knowledge-base/documents", server);
    const panel = await openProfile(user);
    expect(within(panel).getByRole("combobox", { name: "New profile" })).toHaveTextContent("codebase");
    expect(within(panel).getByRole("button", { name: "Preview profile change" })).toBeEnabled();
  });

  it("starts with no selection and a disabled preview when no profile is stored", async () => {
    const server = documentsServer({
      "GET /v1/collections": () => [{ name: "documents", document_count: 3, chunk_count: 12, profile: null, store: LANCE }],
    });
    const user = userEvent.setup();
    startApp("#/knowledge-base/documents", server);
    const panel = await openProfile(user);
    expect(within(panel).getByText("No profile", { selector: "[data-slot=badge]" })).toBeInTheDocument();
    const list = within(panel).getByRole("combobox", { name: "New profile" });
    expect(list).toHaveTextContent("Choose a profile");
    const preview = within(panel).getByRole("button", { name: "Preview profile change" });
    expect(preview).toBeDisabled();
    await user.click(list);
    await user.click(await screen.findByRole("option", { name: "documents" }));
    expect(preview).toBeEnabled();
  });

  it("shows a stored tag outside the list as a badge and leaves the list empty", async () => {
    const server = documentsServer({
      "GET /v1/collections": () => [{ name: "documents", document_count: 3, chunk_count: 12, profile: "legacy", store: LANCE }],
    });
    const user = userEvent.setup();
    startApp("#/knowledge-base/documents", server);
    const panel = await openProfile(user);
    expect(within(panel).getByText("legacy", { selector: "[data-slot=badge]" })).toBeInTheDocument();
    expect(within(panel).getByRole("combobox", { name: "New profile" })).toHaveTextContent("Choose a profile");
    expect(within(panel).getByRole("button", { name: "Preview profile change" })).toBeDisabled();
  });

  it("reloads the stored profile after a confirmed change", async () => {
    let stored = "documents";
    const server = documentsServer({
      "GET /v1/collections": () => [{ name: "documents", document_count: 3, chunk_count: 12, profile: stored, store: { name: "lancedb", label: "LanceDB" } }],
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
    startApp("#/knowledge-base/documents", server);

    const panel = await openProfile(user);
    expect(within(panel).getByText("documents", { selector: "[data-slot=badge]" })).toBeInTheDocument();
    await user.click(within(panel).getByRole("combobox", { name: "New profile" }));
    await user.click(await screen.findByRole("option", { name: "codebase" }));
    await user.click(within(panel).getByRole("button", { name: "Preview profile change" }));
    await user.click(await screen.findByRole("button", { name: "Confirm profile change" }));
    await waitFor(() => expect(within(profilePanel()).getAllByText("codebase", { selector: "[data-slot=badge]" }).length).toBeGreaterThan(0));
    // The picker and Home read the same cache, so the badge in the project header updates too.
    await waitFor(() => expect(within(profilePanel()).queryByText("documents", { selector: "[data-slot=badge]" })).not.toBeInTheDocument());
  });
});
