import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { documentsServer, json, type Handler } from "../test/fakeDocumentsServer";
import { LibraryView } from "./LibraryView";

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

function setup(handlers: Record<string, Handler>) {
  const server = documentsServer(handlers);
  render(<LibraryView fetchImpl={server.fetchImpl} pollMs={5} />);
  return { server, user: userEvent.setup() };
}

function deletes(server: ReturnType<typeof documentsServer>) {
  return server.find("DELETE", "/v1/collections/documents/documents").map((c) => c.body);
}

describe("confirmed deletion", () => {
  it("previews first and deletes nothing until the user confirms with the token", async () => {
    const { server, user } = setup({
      "DELETE /v1/collections/documents/documents": (body) =>
        body.dry_run
          ? { status: "ok", dry_run: true, mode: "metadata", collection: "documents", would_delete: 5, confirmation: confirmation("tok1") }
          : { status: "ok", mode: "metadata", collection: "documents", chunks_removed: 5 },
    });
    await user.click(await screen.findByRole("button", { name: "Delete /srv/docs/present.md" }));

    const preview = await screen.findByRole("region", { name: "Deletion preview" });
    expect(await within(preview).findByText(/removes 5 chunks/)).toBeInTheDocument();
    expect(within(preview).getByText(/sid-present/)).toBeInTheDocument();
    expect(within(preview).getByText("Weaker guarantee")).toBeInTheDocument();
    expect(within(preview).getByText(WARNING)).toBeInTheDocument();
    expect(deletes(server)).toEqual([{ metadata_filter: { source_id: "sid-present" }, dry_run: true }]);

    await user.click(within(preview).getByRole("button", { name: "Confirm deletion" }));
    expect(await within(preview).findByText("Removed 5 chunks.")).toBeInTheDocument();
    expect(deletes(server)[1]).toEqual({ metadata_filter: { source_id: "sid-present" }, confirmation_token: "tok1" });
  });

  it("uses the stored path for a legacy source without a stable id", async () => {
    const { server, user } = setup({
      "DELETE /v1/collections/documents/documents": () => ({
        status: "ok", dry_run: true, mode: "path", collection: "documents", would_delete: 3, confirmation: confirmation("t", "durable"),
      }),
    });
    await user.click(await screen.findByRole("button", { name: "Delete relative/unknown.md" }));
    const preview = await screen.findByRole("region", { name: "Deletion preview" });
    await within(preview).findByText(/removes 3 chunks/);
    expect(within(preview).queryByText("Weaker guarantee")).not.toBeInTheDocument();
    expect(deletes(server)).toEqual([{ path: "relative/unknown.md", dry_run: true }]);
  });

  it("offers a fresh preview when the confirmation is stale (409)", async () => {
    let previews = 0;
    const { server, user } = setup({
      "DELETE /v1/collections/documents/documents": (body) => {
        if (body.dry_run) {
          previews += 1;
          return { status: "ok", dry_run: true, mode: "collection", collection: "documents", would_delete: 12, confirmation: confirmation(`tok${previews}`) };
        }
        if (body.confirmation_token === "tok1") {
          return json({ status: "error", message: "The collection changed after the preview. Preview again." }, 409);
        }
        return { status: "ok", mode: "collection", collection: "documents" };
      },
    });
    await user.click(await screen.findByRole("button", { name: "Delete collection documents" }));
    const preview = await screen.findByRole("region", { name: "Deletion preview" });
    expect(await within(preview).findByText(/removes the whole collection documents \(12 chunks\)/)).toBeInTheDocument();
    await user.click(within(preview).getByRole("button", { name: "Confirm deletion" }));

    expect(await within(preview).findByRole("alert")).toHaveTextContent("The collection changed after the preview. Preview again.");
    expect(within(preview).queryByRole("button", { name: "Confirm deletion" })).not.toBeInTheDocument();
    await user.click(within(preview).getByRole("button", { name: "Preview again" }));
    await user.click(await within(preview).findByRole("button", { name: "Confirm deletion" }));
    expect(await within(preview).findByText("Collection documents deleted.")).toBeInTheDocument();
    expect(deletes(server)).toEqual([
      { dry_run: true },
      { confirmation_token: "tok1" },
      { dry_run: true },
      { confirmation_token: "tok2" },
    ]);
  });

  it("explains a missing confirmation (428) and offers a preview", async () => {
    const { user } = setup({
      "DELETE /v1/collections/documents/documents": (body) =>
        body.dry_run
          ? { status: "ok", dry_run: true, mode: "collection", collection: "documents", would_delete: 12, confirmation: confirmation("tok") }
          : json({ status: "error", message: "A confirmation token is required." }, 428),
    });
    await user.click(await screen.findByRole("button", { name: "Delete collection documents" }));
    const preview = await screen.findByRole("region", { name: "Deletion preview" });
    await user.click(await within(preview).findByRole("button", { name: "Confirm deletion" }));
    expect(await within(preview).findByRole("alert")).toHaveTextContent(/needs a fresh preview/);
    expect(within(preview).getByRole("button", { name: "Preview again" })).toBeInTheDocument();
  });

  it("cancels without deleting", async () => {
    const { server, user } = setup({
      "DELETE /v1/collections/documents/documents": () => ({
        status: "ok", dry_run: true, mode: "collection", collection: "documents", would_delete: 12, confirmation: confirmation("tok"),
      }),
    });
    await user.click(await screen.findByRole("button", { name: "Delete collection documents" }));
    const preview = await screen.findByRole("region", { name: "Deletion preview" });
    await user.click(await within(preview).findByRole("button", { name: "Cancel" }));
    expect(screen.queryByRole("region", { name: "Deletion preview" })).not.toBeInTheDocument();
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

  it("shows exactly what will change, then confirms with the token", async () => {
    const { server, user } = setup({
      "PATCH /v1/collections/documents/profile": (body) =>
        body.confirm
          ? { status: "ok", collection: "documents", profile: "codebase", chunk_count_unchanged: 12 }
          : previewBody,
    });
    await screen.findByRole("table", { name: "Sources in documents" });
    await user.selectOptions(screen.getByRole("combobox", { name: "New profile" }), "codebase");
    await user.click(screen.getByRole("button", { name: "Preview profile change" }));

    const preview = await screen.findByRole("region", { name: "Profile change preview" });
    expect(await within(preview).findByText(/documents to codebase/)).toBeInTheDocument();
    expect(within(preview).getByText(/12 stored chunks stay unchanged/)).toBeInTheDocument();
    const impacts = within(preview).getByRole("table", { name: "Setting changes" });
    expect(within(impacts).getAllByRole("row").slice(1).map((r) => r.textContent)).toEqual([
      "reranker_enabledtrue -> falseNext query",
      "chunk_size1024 -> 512Next ingestion only",
    ]);
    expect(within(preview).getByText("Re-ingest to apply ingest-time levers.")).toBeInTheDocument();
    expect(within(preview).getByText(WARNING)).toBeInTheDocument();
    expect(server.find("PATCH", "/v1/collections/documents/profile").map((c) => c.body)).toEqual([
      { profile: "codebase", confirm: false },
    ]);

    await user.click(within(preview).getByRole("button", { name: "Confirm profile change" }));
    expect(await within(preview).findByText(/Profile changed to codebase\. 12 chunks unchanged\./)).toBeInTheDocument();
    expect(server.find("PATCH", "/v1/collections/documents/profile")[1]?.body).toEqual({
      profile: "codebase",
      confirm: true,
      confirmation_token: "ptok",
    });
  });

  it("offers a fresh preview when the profile confirmation is stale", async () => {
    const { user } = setup({
      "PATCH /v1/collections/documents/profile": (body) =>
        body.confirm ? json({ status: "error", message: "The profile changed. Preview again." }, 409) : previewBody,
    });
    await screen.findByRole("table", { name: "Sources in documents" });
    await user.selectOptions(screen.getByRole("combobox", { name: "New profile" }), "codebase");
    await user.click(screen.getByRole("button", { name: "Preview profile change" }));
    const preview = await screen.findByRole("region", { name: "Profile change preview" });
    await user.click(await within(preview).findByRole("button", { name: "Confirm profile change" }));
    expect(await within(preview).findByRole("alert")).toHaveTextContent("The profile changed. Preview again.");
    expect(within(preview).getByRole("button", { name: "Preview again" })).toBeInTheDocument();
  });
});
