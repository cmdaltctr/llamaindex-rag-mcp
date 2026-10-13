import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { documentsServer, json, type Handler } from "../test/fakeDocumentsServer";
import { LibraryView } from "./LibraryView";

function renderLibrary(handlers: Record<string, Handler> = {}) {
  const server = documentsServer(handlers);
  render(<LibraryView fetchImpl={server.fetchImpl} pollMs={5} />);
  return server;
}

async function sourcesTable() {
  return screen.findByRole("table", { name: "Sources in documents" });
}

describe("Library listing", () => {
  it("lists collections with their counts", async () => {
    renderLibrary();
    const list = await screen.findByRole("list", { name: "Collections" });
    expect(within(list).getByRole("button", { name: /documents/ })).toHaveTextContent("3 sources, 12 chunks");
    expect(within(list).getByRole("button", { name: /notes/ })).toHaveTextContent("1 source, 2 chunks");
  });

  it("shows sources with chunk counts, stable ids and machine-local availability", async () => {
    renderLibrary();
    const rows = within(await sourcesTable()).getAllByRole("row").slice(1);
    expect(rows).toHaveLength(3);
    expect(rows[0]).toHaveTextContent("/srv/docs/present.md");
    expect(rows[0]).toHaveTextContent("sid-present");
    expect(rows[0]).toHaveTextContent("5");
    expect(rows[0]).toHaveTextContent("Present on this machine");
    expect(rows[1]).toHaveTextContent("Missing on this machine");
    expect(rows[2]).toHaveTextContent("Unknown on this machine");
    // Unknown availability must never read as a missing or lost source.
    expect(rows[2]).not.toHaveTextContent(/missing|lost|deleted/i);
    expect(rows[2]).toHaveTextContent("No stable ID (legacy row)");
  });

  it("shows an empty state when there are no collections", async () => {
    renderLibrary({ "GET /v1/collections": () => [] });
    expect(await screen.findByText("No collections yet")).toBeInTheDocument();
    expect(screen.getByTestId("empty-state")).toBeInTheDocument();
  });

  it("reports a listing failure", async () => {
    renderLibrary({ "GET /v1/collections": () => json({ status: "error", message: "Store offline." }, 500) });
    expect(await screen.findByRole("alert")).toHaveTextContent("Store offline.");
  });
});

describe("Library uploads", () => {
  it("states the 50 MiB limit", async () => {
    renderLibrary();
    expect(await screen.findByText(/50 MiB per file/)).toBeInTheDocument();
  });

  it("shows the server's per-file rejection and still uploads the other files", async () => {
    const server = renderLibrary({
      "POST /v1/uploads/preflight": (body) =>
        body.name === "big.pdf"
          ? json({ status: "error", message: "big.pdf is larger than the 50 MiB limit.", error_type: "validation" }, 413)
          : body.name === "pack.zip"
            ? json({ status: "error", message: "Files of type .zip cannot be ingested.", error_type: "validation" }, 415)
            : { status: "ok", name: body.name, max_bytes: 52428800 },
      "POST /v1/uploads": () => json({ status: "ok", upload: { id: "u1", name: "ok.md", size: 2, sha256: "x" } }, 201),
      "POST /v1/ingestions": () =>
        json({ job_id: "j1", status: "queued", result: null, error: null, created_at: "t", updated_at: "t" }, 202),
      "GET /v1/jobs/j1": () => ({ job_id: "j1", status: "running", result: null, error: null, created_at: "t", updated_at: "t" }),
    });
    const user = userEvent.setup();
    await sourcesTable();
    const files = [
      new File(["x".repeat(4)], "big.pdf", { type: "application/pdf" }),
      new File(["zz"], "pack.zip", { type: "application/zip" }),
      new File(["ok"], "ok.md", { type: "text/markdown" }),
    ];
    await user.upload(screen.getByLabelText("Files to upload"), files);
    await user.click(screen.getByRole("button", { name: "Upload and ingest" }));

    const results = await screen.findByRole("list", { name: "Upload results" });
    expect(await within(results).findByText(/ok\.md: uploaded, ingestion queued/)).toBeInTheDocument();
    expect(within(results).getByText(/big\.pdf: rejected\. big\.pdf is larger than the 50 MiB limit\./)).toBeInTheDocument();
    expect(within(results).getByText(/pack\.zip: rejected\. Files of type \.zip cannot be ingested\./)).toBeInTheDocument();
    // Rejected files never send their bytes.
    expect(server.find("POST", "/v1/uploads").filter((c) => c.path === "/v1/uploads")).toHaveLength(1);
    // The upload is ingested by its managed-root path.
    expect(server.find("POST", "/v1/ingestions")[0]?.body).toEqual({
      path: "/home/u/.omrg/workspace/uploads/u1/ok.md",
      collection: "documents",
    });
  });
});

describe("Library ingestion from an approved folder", () => {
  it("joins a relative path onto the chosen root and polls the job to completion", async () => {
    let polls = 0;
    const server = renderLibrary({
      "POST /v1/ingestions": () =>
        json({ job_id: "j2", status: "queued", result: null, error: null, created_at: "t", updated_at: "t" }, 202),
      "GET /v1/jobs/j2": () => {
        polls += 1;
        const status = polls < 2 ? "running" : "completed";
        return { job_id: "j2", status, result: { status: "ok" }, error: null, created_at: "t", updated_at: "t" };
      },
    });
    const user = userEvent.setup();
    await sourcesTable();
    const folder = screen.getByRole("combobox", { name: "Approved folder" });
    expect(within(folder).getAllByRole("option").map((o) => o.textContent)).toEqual(["/srv/docs"]);
    await user.type(screen.getByLabelText("Path inside the folder"), "reports/q3.md");
    await user.click(screen.getByRole("button", { name: "Ingest" }));

    const jobs = await screen.findByRole("list", { name: "Jobs" });
    expect(await within(jobs).findByText(/Completed/)).toBeInTheDocument();
    expect(server.find("POST", "/v1/ingestions")[0]?.body).toEqual({ path: "/srv/docs/reports/q3.md", collection: "documents" });
    // A finished job refreshes the listing.
    await waitFor(() => expect(server.find("GET", "/v1/collections/documents/documents").length).toBeGreaterThan(1));
  });

  it("refuses an absolute or escaping path without contacting the server", async () => {
    const server = renderLibrary();
    const user = userEvent.setup();
    await sourcesTable();
    await user.type(screen.getByLabelText("Path inside the folder"), "/etc/passwd");
    await user.click(screen.getByRole("button", { name: "Ingest" }));
    expect(await screen.findByText(/not an absolute path/)).toBeInTheDocument();
    await user.clear(screen.getByLabelText("Path inside the folder"));
    await user.type(screen.getByLabelText("Path inside the folder"), "../../secret");
    await user.click(screen.getByRole("button", { name: "Ingest" }));
    expect(await screen.findByText(/must stay inside the selected folder/)).toBeInTheDocument();
    expect(server.find("POST", "/v1/ingestions")).toHaveLength(0);
  });

  it("shows a failed job with its redacted error", async () => {
    renderLibrary({
      "POST /v1/ingestions": () =>
        json({ job_id: "j3", status: "queued", result: null, error: null, created_at: "t", updated_at: "t" }, 202),
      "GET /v1/jobs/j3": () => ({ job_id: "j3", status: "failed", result: null, error: "ValueError: bad file", created_at: "t", updated_at: "t" }),
    });
    const user = userEvent.setup();
    await sourcesTable();
    await user.type(screen.getByLabelText("Path inside the folder"), "a.md");
    await user.click(screen.getByRole("button", { name: "Ingest" }));
    expect(await screen.findByText(/Failed: ValueError: bad file/)).toBeInTheDocument();
  });
});
