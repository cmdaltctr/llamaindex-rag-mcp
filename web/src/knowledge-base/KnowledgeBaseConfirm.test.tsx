import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { documentsServer, json, PROFILES, type Handler } from "../test/fakeDocumentsServer";
import { startApp } from "../test/startApp";

const WARNING = "The vector store reports only a process-local validity token.";

function confirmation(token: string, validity: "durable" | "process_local" = "process_local") {
  return {
    token,
    expires_at: "2026-10-13T12:05:00Z",
    expires_in: 300,
    validity,
    warning: validity === "process_local" ? WARNING : null,
  };
}

async function setup(handlers: Record<string, Handler>, section: string | null = null) {
  vi.spyOn(console, "error").mockImplementation(() => undefined);
  const { server } = startApp("#/knowledge-base/documents", documentsServer({ "GET /v1/profiles": () => ({ status: "ok", profiles: PROFILES }), ...handlers }));
  const user = userEvent.setup();
  await screen.findByRole("table", { name: "Sources in documents" });
  if (section !== null) await user.click(screen.getByRole("button", { name: section }));
  return { server, user };
}

function deletes(server: ReturnType<typeof documentsServer>) {
  return server.find("DELETE", "/v1/collections/documents/documents").map((call) => call.body);
}

describe("confirmed deletion", () => {
  it("previews first and deletes nothing until the user confirms with the token", async () => {
    const { server, user } = await setup({
      "DELETE /v1/collections/documents/documents": (body) =>
        body.dry_run
          ? { status: "ok", dry_run: true, mode: "metadata", collection: "documents", would_delete: 5, confirmation: confirmation("tok1") }
          : { status: "ok", mode: "metadata", collection: "documents", chunks_removed: 5 },
    });
    await user.click(screen.getByRole("button", { name: "Delete /srv/docs/present.md" }));

    const dialog = await screen.findByRole("dialog", { name: "Delete source" });
    expect(await within(dialog).findByText(/removes 5 chunks/)).toBeInTheDocument();
    expect(within(dialog).getByText(/sid-present/)).toBeInTheDocument();
    expect(within(dialog).getByText("Weaker guarantee")).toBeInTheDocument();
    expect(within(dialog).getByText(WARNING)).toBeInTheDocument();
    expect(deletes(server)).toEqual([{ metadata_filter: { source_id: "sid-present" }, dry_run: true }]);

    await user.click(within(dialog).getByRole("button", { name: "Confirm deletion" }));
    expect(await within(dialog).findByText("Removed 5 chunks.")).toBeInTheDocument();
    expect(deletes(server)[1]).toEqual({ metadata_filter: { source_id: "sid-present" }, confirmation_token: "tok1" });
  });

  it("refreshes the collection list and the sources after a confirmed deletion, not after the preview", async () => {
    let removed = false;
    const { server, user } = await setup({
      "GET /v1/collections": () => [{ name: "documents", document_count: removed ? 2 : 3, chunk_count: removed ? 7 : 12, profile: "documents", display_name: null, store: { name: "lancedb", label: "LanceDB" } }],
      "DELETE /v1/collections/documents/documents": (body) =>
        body.dry_run
          ? { status: "ok", dry_run: true, mode: "metadata", collection: "documents", would_delete: 5, confirmation: confirmation("tok9") }
          : (removed = true, { status: "ok", mode: "metadata", collection: "documents", chunks_removed: 5 }),
    });
    const lists = () => server.find("GET", "/v1/collections").filter((call) => call.path === "/v1/collections").length;
    const sources = () => server.find("GET", "/v1/collections/documents/documents").length;
    const [listsBefore, sourcesBefore] = [lists(), sources()];

    await user.click(screen.getByRole("button", { name: "Delete /srv/docs/present.md" }));
    const dialog = await screen.findByRole("dialog", { name: "Delete source" });
    await within(dialog).findByText(/removes 5 chunks/);
    expect(lists()).toBe(listsBefore);

    await user.click(within(dialog).getByRole("button", { name: "Confirm deletion" }));
    await within(dialog).findByText("Removed 5 chunks.");
    await waitFor(() => expect(lists()).toBe(listsBefore + 1));
    await waitFor(() => expect(sources()).toBe(sourcesBefore + 1));
    expect((await screen.findAllByText("2 documents, 7 chunks")).length).toBeGreaterThan(0);
  });

  it("uses the stored path for a legacy source without a stable id", async () => {
    const { server, user } = await setup({
      "DELETE /v1/collections/documents/documents": () => ({
        status: "ok", dry_run: true, mode: "path", collection: "documents", would_delete: 3, confirmation: confirmation("t", "durable"),
      }),
    });
    await user.click(screen.getByRole("button", { name: "Delete relative/unknown.md" }));
    const dialog = await screen.findByRole("dialog", { name: "Delete source" });
    await within(dialog).findByText(/removes 3 chunks/);
    expect(within(dialog).queryByText("Weaker guarantee")).not.toBeInTheDocument();
    expect(deletes(server)).toEqual([{ path: "relative/unknown.md", dry_run: true }]);
  });

  it("offers a fresh preview when the confirmation is stale (409)", async () => {
    let previews = 0;
    const { server, user } = await setup({
      "DELETE /v1/collections/documents/documents": (body) => {
        if (body.dry_run) {
          previews += 1;
          return { status: "ok", dry_run: true, mode: "collection", collection: "documents", would_delete: 12, confirmation: confirmation(`tok${previews}`) };
        }
        if (body.confirmation_token === "tok1") return json({ status: "error", message: "RAW The collection changed after the preview." }, 409);
        return { status: "ok", mode: "collection", collection: "documents" };
      },
    });
    await user.click(screen.getByRole("button", { name: "Delete collection documents" }));
    const dialog = await screen.findByRole("dialog", { name: "Delete collection" });
    expect(await within(dialog).findByText(/removes the whole collection documents \(12 chunks\)/)).toBeInTheDocument();
    await user.click(within(dialog).getByRole("button", { name: "Confirm deletion" }));

    const alert = await within(dialog).findByRole("alert");
    expect(alert).toHaveTextContent(/out of date/i);
    expect(alert).not.toHaveTextContent("RAW");
    expect(within(dialog).queryByRole("button", { name: "Confirm deletion" })).not.toBeInTheDocument();
    await user.click(within(dialog).getByRole("button", { name: "Preview again" }));
    await user.click(await within(dialog).findByRole("button", { name: "Confirm deletion" }));

    expect(await screen.findByText("Collection documents deleted.")).toBeInTheDocument();
    expect(deletes(server)).toEqual([{ dry_run: true }, { confirmation_token: "tok1" }, { dry_run: true }, { confirmation_token: "tok2" }]);
    // The project is gone, so the Knowledge Base returns to the picker and forgets it.
    await waitFor(() => expect(window.location.hash).toBe("#/knowledge-base"));
    expect(JSON.parse(window.localStorage.getItem("omrs-preferences") ?? "{}").lastCollection).toBeNull();
  });

  it("explains a missing confirmation (428) and offers a preview", async () => {
    const { user } = await setup({
      "DELETE /v1/collections/documents/documents": (body) =>
        body.dry_run
          ? { status: "ok", dry_run: true, mode: "collection", collection: "documents", would_delete: 12, confirmation: confirmation("tok") }
          : json({ status: "error", message: "RAW A confirmation token is required." }, 428),
    });
    await user.click(screen.getByRole("button", { name: "Delete collection documents" }));
    const dialog = await screen.findByRole("dialog", { name: "Delete collection" });
    await user.click(await within(dialog).findByRole("button", { name: "Confirm deletion" }));
    const alert = await within(dialog).findByRole("alert");
    expect(alert).toHaveTextContent(/needs a fresh preview/);
    expect(alert).not.toHaveTextContent("RAW");
    expect(within(dialog).getByRole("button", { name: "Preview again" })).toBeInTheDocument();
  });

  it("shows a friendly failure with Retry when the preview request fails", async () => {
    const { user } = await setup({ "DELETE /v1/collections/documents/documents": () => json({ message: "RAW boom" }, 500) });
    await user.click(screen.getByRole("button", { name: "Delete collection documents" }));
    const dialog = await screen.findByRole("dialog", { name: "Delete collection" });
    const alert = await within(dialog).findByRole("alert");
    expect(alert).not.toHaveTextContent("RAW");
    expect(within(alert).getByRole("button", { name: "Retry" })).toBeInTheDocument();
  });

  it("cancels without deleting", async () => {
    const { server, user } = await setup({
      "DELETE /v1/collections/documents/documents": () => ({
        status: "ok", dry_run: true, mode: "collection", collection: "documents", would_delete: 12, confirmation: confirmation("tok"),
      }),
    });
    await user.click(screen.getByRole("button", { name: "Delete collection documents" }));
    const dialog = await screen.findByRole("dialog", { name: "Delete collection" });
    await user.click(await within(dialog).findByRole("button", { name: "Cancel" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(deletes(server)).toEqual([{ dry_run: true }]);
  });
});

describe("confirmed profile change", () => {
  const previewBody = {
    status: "preview",
    confirm_required: true,
    contract: {
      collection: "documents",
      old_profile: "documents",
      new_profile: "codebase",
      chunk_count: 12,
      lever_impacts: [
        { lever: "reranker_enabled", change: "true -> false", timing: "query-time" },
        { lever: "chunk_size", change: "1024 -> 512", timing: "ingest-time" },
      ],
      reingest_pointer: "Re-ingest to apply ingest-time levers.",
    },
    confirmation: confirmation("ptok"),
  };

  async function choose(user: ReturnType<typeof userEvent.setup>) {
    await user.click(screen.getByRole("combobox", { name: "New profile" }));
    await user.click(await screen.findByRole("option", { name: /^Codebase/ }));
    await user.click(screen.getByRole("button", { name: "Preview profile change" }));
    return screen.findByRole("region", { name: "Profile change preview" });
  }

  it("shows exactly what will change, then confirms with the token", async () => {
    const { server, user } = await setup(
      { "PATCH /v1/collections/documents/profile": (body) => (body.confirm ? { status: "ok", collection: "documents", profile: "codebase", chunk_count_unchanged: 12 } : previewBody) },
      "Profile",
    );
    const preview = await choose(user);
    expect(await within(preview).findByText(/documents to codebase/)).toBeInTheDocument();
    expect(within(preview).getByText(/12 stored chunks stay unchanged/)).toBeInTheDocument();
    const impacts = within(preview).getByRole("table", { name: "Setting changes" });
    expect(within(impacts).getAllByRole("row").slice(1).map((row) => row.textContent)).toEqual([
      "reranker_enabledtrue -> falseNext query",
      "chunk_size1024 -> 512Next ingestion only",
    ]);
    expect(within(preview).getByText("Re-ingest to apply ingest-time levers.")).toBeInTheDocument();
    expect(within(preview).getByText(WARNING)).toBeInTheDocument();
    expect(server.find("PATCH", "/v1/collections/documents/profile").map((call) => call.body)).toEqual([{ profile: "codebase", confirm: false }]);

    await user.click(within(preview).getByRole("button", { name: "Confirm profile change" }));
    expect(await within(preview).findByText(/Profile changed to codebase\. 12 chunks unchanged\./)).toBeInTheDocument();
    expect(server.find("PATCH", "/v1/collections/documents/profile")[1]?.body).toEqual({ profile: "codebase", confirm: true, confirmation_token: "ptok" });
  });

  it("offers a fresh preview when the profile confirmation is stale", async () => {
    const { user } = await setup(
      { "PATCH /v1/collections/documents/profile": (body) => (body.confirm ? json({ status: "error", message: "RAW The profile changed." }, 409) : previewBody) },
      "Profile",
    );
    const preview = await choose(user);
    await user.click(await within(preview).findByRole("button", { name: "Confirm profile change" }));
    const alert = await within(preview).findByRole("alert");
    expect(alert).toHaveTextContent(/out of date/i);
    expect(alert).not.toHaveTextContent("RAW");
    expect(within(preview).getByRole("button", { name: "Preview again" })).toBeInTheDocument();
  });
});
