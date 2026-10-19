import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { documentsServer, json, PROFILES } from "../test/fakeDocumentsServer";
import { startApp } from "../test/startApp";

const LANCE = { name: "lancedb", label: "LanceDB" };

function userProfile(profile_id: string, title: string, ready = true, not_ready_reasons: string[] = []) {
  return { profile_id, kind: "user", title, description: "", base_profile: "documents", slots: { ingest: "pl_1", search: "pl_2", answer: null }, ready, not_ready_reasons, used_by: [] };
}

const PAPERS = userProfile("papers-search", "Papers search");
const DRAFT = userProfile("draft-notes", "Draft notes", false, ["The Search pipeline is empty.", "The Ingest pipeline is empty."]);

function listing(...extra: ReturnType<typeof userProfile>[]) {
  return { "GET /v1/profiles": () => ({ status: "ok", profiles: [...PROFILES, ...extra] }) };
}

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
        { name: "documents", document_count: 3, chunk_count: 12, profile: "codebase", display_name: null, store: { name: "lancedb", label: "LanceDB" } },
        { name: "notes", document_count: 1, chunk_count: 2, profile: null, display_name: null, store: { name: "lancedb", label: "LanceDB" } },
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
    await waitFor(() => expect(within(panel).getByRole("combobox", { name: "New profile" })).toHaveTextContent("Codebase"));
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
    await user.click(await screen.findByRole("option", { name: /^Documents/ }));
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
      "GET /v1/collections": () => [{ name: "documents", document_count: 3, chunk_count: 12, profile: stored, display_name: null, store: { name: "lancedb", label: "LanceDB" } }],
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
    await user.click(await screen.findByRole("option", { name: /^Codebase/ }));
    await user.click(within(panel).getByRole("button", { name: "Preview profile change" }));
    await user.click(await screen.findByRole("button", { name: "Confirm profile change" }));
    await waitFor(() => expect(within(profilePanel()).getAllByText("codebase", { selector: "[data-slot=badge]" }).length).toBeGreaterThan(0));
    // The picker and Home read the same cache, so the badge in the project header updates too.
    await waitFor(() => expect(within(profilePanel()).queryByText("documents", { selector: "[data-slot=badge]" })).not.toBeInTheDocument());
  });
});

describe("profile list from the server", () => {
  async function open(handlers: Parameters<typeof documentsServer>[0], stored: string | null = null) {
    const server = documentsServer({
      "GET /v1/collections": () => [{ name: "documents", document_count: 3, chunk_count: 12, profile: stored, display_name: null, store: LANCE }],
      ...handlers,
    });
    const user = userEvent.setup();
    startApp("#/knowledge-base/documents", server);
    const panel = await openProfile(user);
    return { server, user, panel };
  }

  it("offers ready profiles in two groups with the title and the ID on each option", async () => {
    const { user, panel } = await open(listing(PAPERS));
    await user.click(within(panel).getByRole("combobox", { name: "New profile" }));
    const builtIn = await screen.findByRole("group", { name: "Built-in profiles" });
    expect(within(builtIn).getAllByRole("option").map((option) => option.textContent)).toEqual(["Documents documents", "Codebase codebase"]);
    const yours = screen.getByRole("group", { name: "Your profiles" });
    expect(within(yours).getAllByRole("option").map((option) => option.textContent)).toEqual(["Papers search papers-search"]);
    expect(within(yours).getByText("papers-search")).toHaveClass("font-mono");
  });

  it("leaves out the Your profiles group when no user profile is ready", async () => {
    const { user, panel } = await open(listing());
    await user.click(within(panel).getByRole("combobox", { name: "New profile" }));
    await screen.findByRole("group", { name: "Built-in profiles" });
    expect(screen.queryByRole("group", { name: "Your profiles" })).not.toBeInTheDocument();
  });

  it("hides a profile that is not ready and explains it with its first reason", async () => {
    const { user, panel } = await open(listing(PAPERS, DRAFT));
    await user.click(within(panel).getByRole("combobox", { name: "New profile" }));
    await screen.findByRole("group", { name: "Your profiles" });
    expect(screen.queryByRole("option", { name: /Draft notes/ })).not.toBeInTheDocument();
    await user.keyboard("{Escape}");
    expect(within(panel).getByText("Draft notes is not ready: The Search pipeline is empty.")).toBeInTheDocument();
    expect(within(panel).queryByText(/Ingest pipeline is empty/)).not.toBeInTheDocument();
  });

  it("pre-selects a stored user profile", async () => {
    const { panel } = await open(listing(PAPERS), "papers-search");
    await waitFor(() => expect(within(panel).getByRole("combobox", { name: "New profile" })).toHaveTextContent("Papers search"));
    expect(within(panel).getByText("papers-search", { selector: "[data-slot=badge]" })).toBeInTheDocument();
    expect(within(panel).getByRole("button", { name: "Preview profile change" })).toBeEnabled();
  });

  it("starts empty when the stored profile is not ready, and still shows its badge", async () => {
    const { panel } = await open(listing(DRAFT), "draft-notes");
    await within(panel).findByText("Draft notes is not ready: The Search pipeline is empty.");
    expect(within(panel).getByText("draft-notes", { selector: "[data-slot=badge]" })).toBeInTheDocument();
    expect(within(panel).getByRole("combobox", { name: "New profile" })).toHaveTextContent("Choose a profile");
    expect(within(panel).getByRole("button", { name: "Preview profile change" })).toBeDisabled();
  });

  it("sends the ID of a picked user profile in the preview body", async () => {
    const { server, user, panel } = await open({
      ...listing(PAPERS),
      "PATCH /v1/collections/documents/profile": () => ({
        status: "preview",
        confirm_required: true,
        contract: { collection: "documents", old_profile: null, new_profile: "papers-search", chunk_count: 12, lever_impacts: [], reingest_pointer: "" },
        confirmation: { token: "ptok", expires_at: "2026-10-13T12:05:00Z", expires_in: 300, validity: "durable", warning: null },
      }),
    });
    await user.click(within(panel).getByRole("combobox", { name: "New profile" }));
    await user.click(await screen.findByRole("option", { name: /Papers search/ }));
    await user.click(within(panel).getByRole("button", { name: "Preview profile change" }));
    expect(await screen.findByRole("region", { name: "Profile change preview" })).toBeInTheDocument();
    expect(server.find("PATCH", "/v1/collections/documents/profile").map((call) => call.body)).toEqual([{ profile: "papers-search", confirm: false }]);
  });

  it("shows one friendly failure line with Retry when the listing fails, and keeps the stored badge", async () => {
    vi.spyOn(console, "error").mockImplementation(() => undefined);
    let fail = true;
    const { user, panel } = await open(
      { "GET /v1/profiles": () => (fail ? json({ status: "error", message: "RAW profiles broke" }, 500) : { status: "ok", profiles: PROFILES }) },
      "papers-search",
    );
    const alert = await within(panel).findByRole("alert");
    expect(alert).toHaveTextContent(/could not complete/i);
    expect(alert).not.toHaveTextContent("RAW");
    expect(within(panel).getByText("papers-search", { selector: "[data-slot=badge]" })).toBeInTheDocument();
    expect(within(panel).getByRole("button", { name: "Preview profile change" })).toBeDisabled();

    fail = false;
    await user.click(within(alert).getByRole("button", { name: "Retry" }));
    await waitFor(() => expect(within(panel).queryByRole("alert")).not.toBeInTheDocument());
    await user.click(within(panel).getByRole("combobox", { name: "New profile" }));
    expect(await screen.findByRole("option", { name: /^Codebase/ })).toBeInTheDocument();
  });
});
