import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { documentsServer, json, UPLOAD_LIMIT, type Handler } from "../test/fakeDocumentsServer";
import { startApp } from "../test/startApp";

const JOB = { result: null, error: null, created_at: "t", updated_at: "t" };
const queued = (id: string) => json({ ...JOB, job_id: id, status: "queued" }, 202);

async function openAdd(handlers: Record<string, Handler> = {}, hash = "#/knowledge-base/documents") {
  const { server } = startApp(hash, documentsServer(handlers));
  const user = userEvent.setup();
  await screen.findByRole("table", { name: "Sources in documents" });
  await user.click(screen.getByRole("button", { name: "Add" }));
  return { server, user };
}

function sized(name: string, bytes: number) {
  const file = new File(["x"], name, { type: "application/pdf" });
  Object.defineProperty(file, "size", { value: bytes });
  return file;
}

describe("uploads", () => {
  it("states the per-file limit", async () => {
    await openAdd();
    expect(screen.getByText(/50 MiB per file/)).toBeInTheDocument();
  });

  it("refuses an oversized file locally, names the limit and never sends it", async () => {
    const { server, user } = await openAdd();
    await user.upload(screen.getByLabelText("Files to upload"), sized("big.pdf", 60 * 1024 * 1024));
    await user.click(screen.getByRole("button", { name: "Upload and ingest" }));
    const results = await screen.findByRole("list", { name: "Upload results" });
    expect(results).toHaveTextContent("big.pdf: not sent. The file is 60 MiB. The limit is 50 MiB per file.");
    expect(server.find("POST", "/v1/uploads")).toHaveLength(0);
  });

  it("accepts a file exactly at the limit", async () => {
    const { server, user } = await openAdd({
      "POST /v1/uploads/preflight": () => ({ status: "ok" }),
      "POST /v1/uploads": () => json({ status: "ok", upload: { id: "u1", name: "edge.pdf", size: 1, sha256: "x" } }, 201),
      "POST /v1/ingestions": () => queued("j0"),
      "GET /v1/jobs/j0": () => ({ ...JOB, job_id: "j0", status: "running" }),
    });
    await user.upload(screen.getByLabelText("Files to upload"), sized("edge.pdf", 50 * 1024 * 1024));
    await user.click(screen.getByRole("button", { name: "Upload and ingest" }));
    expect(await screen.findByText(/edge\.pdf: uploaded, ingestion queued/)).toBeInTheDocument();
    expect(server.find("POST", "/v1/uploads/preflight")).toHaveLength(1);
  });

  it("explains the server's per-file rejections in plain words and still uploads the other files", async () => {
    vi.spyOn(console, "error").mockImplementation(() => undefined);
    const { server, user } = await openAdd({
      "POST /v1/uploads/preflight": (body) =>
        body.name === "big.pdf"
          ? json({ status: "error", message: "RAW big.pdf is larger than the limit." }, 413)
          : body.name === "pack.zip"
            ? json({ status: "error", message: "RAW Files of type .zip cannot be ingested." }, 415)
            : { status: "ok", name: body.name, max_bytes: 52428800 },
      "POST /v1/uploads": () => json({ status: "ok", upload: { id: "u1", name: "ok.md", size: 2, sha256: "x" } }, 201),
      "POST /v1/ingestions": () => queued("j1"),
      "GET /v1/jobs/j1": () => ({ ...JOB, job_id: "j1", status: "running" }),
    });
    await user.upload(screen.getByLabelText("Files to upload"), [
      new File(["x"], "big.pdf", { type: "application/pdf" }),
      new File(["zz"], "pack.zip", { type: "application/zip" }),
      new File(["ok"], "ok.md", { type: "text/markdown" }),
    ]);
    await user.click(screen.getByRole("button", { name: "Upload and ingest" }));

    const results = await screen.findByRole("list", { name: "Upload results" });
    expect(await within(results).findByText(/ok\.md: uploaded, ingestion queued into documents/)).toBeInTheDocument();
    expect(within(results).getByText("big.pdf: rejected. The file is larger than the 50 MiB limit.")).toBeInTheDocument();
    expect(within(results).getByText("pack.zip: rejected. That file type cannot be ingested.")).toBeInTheDocument();
    expect(results).not.toHaveTextContent("RAW");
    // Rejected files never send their bytes; the upload is ingested by its managed-root path.
    expect(server.find("POST", "/v1/uploads").filter((call) => call.path === "/v1/uploads")).toHaveLength(1);
    expect(server.find("POST", "/v1/ingestions")[0]?.body).toEqual({ path: "/home/u/.omrg/workspace/uploads/u1/ok.md", collection: "documents" });
  });

  it("shows the ingest job status after an upload and refreshes the counts when it finishes", async () => {
    let polls = 0;
    const { server, user } = await openAdd({
      "POST /v1/uploads/preflight": () => ({ status: "ok" }),
      "POST /v1/uploads": () => json({ status: "ok", upload: { id: "u1", name: "a.md", size: 1, sha256: "x" } }, 201),
      "POST /v1/ingestions": () => queued("j9"),
      "GET /v1/jobs/j9": () => ({ ...JOB, job_id: "j9", status: ++polls < 2 ? "running" : "completed" }),
    });
    await user.upload(screen.getByLabelText("Files to upload"), new File(["a"], "a.md"));
    await user.click(screen.getByRole("button", { name: "Upload and ingest" }));
    const jobs = await screen.findByRole("list", { name: "Jobs" });
    expect(await within(jobs).findByText("Running")).toBeInTheDocument();
    expect(await within(jobs).findByText("Completed", {}, { timeout: 4000 })).toBeInTheDocument();
    await waitFor(() => expect(server.find("GET", "/v1/collections").filter((call) => call.path === "/v1/collections").length).toBeGreaterThan(1));
  });
});

const MIB = 1024 * 1024;
const limitOf = (mib: number) => ({ ...UPLOAD_LIMIT, max_bytes: mib * MIB, source: "saved", saved_mib: mib });
const ACCEPT_UPLOAD: Record<string, Handler> = {
  "POST /v1/uploads/preflight": () => ({ status: "ok" }),
  "POST /v1/uploads": () => json({ status: "ok", upload: { id: "u1", name: "mid.pdf", size: 1, sha256: "x" } }, 201),
  "POST /v1/ingestions": () => queued("j0"),
  "GET /v1/jobs/j0": () => ({ ...JOB, job_id: "j0", status: "running" }),
};

describe("the server's upload limit", () => {
  it("states and applies the limit the server reports, not a limit of its own", async () => {
    const { server, user } = await openAdd({ ...ACCEPT_UPLOAD, "GET /v1/settings/upload-limit": () => limitOf(100) });
    expect(await screen.findByText(/Limit: 100 MiB per file\./)).toBeInTheDocument();
    await user.upload(screen.getByLabelText("Files to upload"), sized("mid.pdf", 60 * MIB));
    await user.click(screen.getByRole("button", { name: "Upload and ingest" }));
    expect(await screen.findByText(/mid\.pdf: uploaded, ingestion queued/)).toBeInTheDocument();
    expect(server.find("POST", "/v1/uploads/preflight")).toHaveLength(1);
  });

  it("refuses a file above a lower reported limit without a request, naming that limit", async () => {
    const { server, user } = await openAdd({ "GET /v1/settings/upload-limit": () => limitOf(10) });
    await screen.findByText(/Limit: 10 MiB per file\./);
    await user.upload(screen.getByLabelText("Files to upload"), sized("big.pdf", 12 * MIB));
    await user.click(screen.getByRole("button", { name: "Upload and ingest" }));
    const results = await screen.findByRole("list", { name: "Upload results" });
    expect(results).toHaveTextContent("big.pdf: not sent. The file is 12 MiB. The limit is 10 MiB per file.");
    expect(server.find("POST", "/v1/uploads")).toHaveLength(0);
  });

  it("shows a limit saved in Settings without a page reload", async () => {
    let saved: number | null = null;
    const state = () => (saved === null ? UPLOAD_LIMIT : limitOf(saved));
    const server = documentsServer({
      "GET /v1/settings/upload-limit": state,
      "PUT /v1/settings/upload-limit": (body) => {
        saved = body.max_mib as number;
        return state();
      },
    });
    startApp("#/knowledge-base/documents", server);
    const user = userEvent.setup();
    await screen.findByRole("table", { name: "Sources in documents" });
    await user.click(screen.getByRole("button", { name: "Add" }));
    expect(await screen.findByText(/Limit: 50 MiB per file\./)).toBeInTheDocument();
    const nav = screen.getByRole("navigation", { name: "Workspace" });
    await user.click(within(nav).getByRole("link", { name: "Settings" }));
    await user.click(await screen.findByRole("button", { name: "Workspace" }));
    const panel = await screen.findByRole("region", { name: "Upload limit" });
    await user.type(await within(panel).findByLabelText("Limit per file, in MiB"), "200");
    await user.click(within(panel).getByRole("button", { name: "Save limit" }));
    await within(panel).findByText("The limit in force is 200 MiB per file.");
    await user.click(within(nav).getByRole("link", { name: "Knowledge Base" }));
    await screen.findByRole("table", { name: "Sources in documents" });
    await user.click(screen.getByRole("button", { name: "Add" }));
    expect(await screen.findByText(/Limit: 200 MiB per file\./)).toBeInTheDocument();
  });

  it("leaves the size check to the server when the limit cannot be read, and names no number", async () => {
    vi.spyOn(console, "error").mockImplementation(() => undefined);
    const { server, user } = await openAdd({
      "GET /v1/settings/upload-limit": () => json({ status: "error", message: "RAW boom" }, 500),
      "POST /v1/uploads/preflight": () => json({ status: "error", message: "RAW too large" }, 413),
    });
    await waitFor(() => expect(server.find("GET", "/v1/settings/upload-limit").length).toBeGreaterThan(0));
    await user.upload(screen.getByLabelText("Files to upload"), sized("big.pdf", 60 * MIB));
    await user.click(screen.getByRole("button", { name: "Upload and ingest" }));
    const results = await screen.findByRole("list", { name: "Upload results" });
    expect(results).toHaveTextContent("big.pdf: rejected. The file is larger than the server's per-file limit.");
    expect(server.find("POST", "/v1/uploads/preflight")).toHaveLength(1);
    expect(document.body.textContent).not.toMatch(/\d+ MiB/);
    expect(document.body.textContent).not.toContain("RAW");
  });
});

describe("ingest progress across the workspace", () => {
  it("updates the Home counts when a job ends after the user has left the Knowledge Base", async () => {
    let finished = false;
    const { user } = await openAdd({
      "GET /v1/collections": () => [{ name: "documents", document_count: finished ? 4 : 3, chunk_count: finished ? 20 : 12, profile: "documents", store: { name: "lancedb", label: "LanceDB" } }],
      "POST /v1/ingestions": () => queued("j8"),
      "GET /v1/jobs/j8": () => ({ ...JOB, job_id: "j8", status: finished ? "completed" : "running" }),
    });
    await user.type(screen.getByLabelText("Path inside the folder"), "a.md");
    await user.click(screen.getByRole("button", { name: "Start ingest" }));
    await screen.findByRole("list", { name: "Jobs" });

    await user.click(within(screen.getByRole("navigation", { name: "Workspace" })).getByRole("link", { name: "Home" }));
    expect(await screen.findByText("3 documents, 12 chunks")).toBeInTheDocument();

    finished = true;
    expect(await screen.findByText("4 documents, 20 chunks", {}, { timeout: 5000 })).toBeInTheDocument();
  });
});

describe("folder ingest", () => {
  it("offers approved roots only, joins a relative path and follows the job to completion", async () => {
    let polls = 0;
    const { server, user } = await openAdd({
      "POST /v1/ingestions": () => queued("j2"),
      "GET /v1/jobs/j2": () => ({ ...JOB, job_id: "j2", status: ++polls < 2 ? "running" : "completed", result: { status: "ok" } }),
    });
    await user.click(screen.getByRole("combobox", { name: "Approved folder" }));
    expect((await screen.findAllByRole("option")).map((option) => option.textContent)).toEqual(["/srv/docs"]);
    await user.keyboard("{Escape}");
    await user.type(screen.getByLabelText("Path inside the folder"), "reports/q3.md");
    await user.click(screen.getByRole("button", { name: "Start ingest" }));

    const jobs = await screen.findByRole("list", { name: "Jobs" });
    expect(await within(jobs).findByText("Completed", {}, { timeout: 4000 })).toBeInTheDocument();
    expect(server.find("POST", "/v1/ingestions")[0]?.body).toEqual({ path: "/srv/docs/reports/q3.md", collection: "documents" });

    // The sources list refreshes the next time it is shown.
    await user.click(screen.getByRole("button", { name: "Sources" }));
    await screen.findByRole("table", { name: "Sources in documents" });
    expect(server.find("GET", "/v1/collections/documents/documents").length).toBeGreaterThan(1);
  });

  it("refuses an absolute or escaping path without contacting the server", async () => {
    const { server, user } = await openAdd();
    await user.type(screen.getByLabelText("Path inside the folder"), "/etc/passwd");
    await user.click(screen.getByRole("button", { name: "Start ingest" }));
    expect(await screen.findByText(/not an absolute path/)).toBeInTheDocument();
    await user.clear(screen.getByLabelText("Path inside the folder"));
    await user.type(screen.getByLabelText("Path inside the folder"), "../../secret");
    await user.click(screen.getByRole("button", { name: "Start ingest" }));
    expect(await screen.findByText(/must stay inside the selected folder/)).toBeInTheDocument();
    expect(server.find("POST", "/v1/ingestions")).toHaveLength(0);
  });

  it("shows a failed job with a fixed hint, never the server error text", async () => {
    const { user } = await openAdd({
      "POST /v1/ingestions": () => queued("j3"),
      "GET /v1/jobs/j3": () => ({ ...JOB, job_id: "j3", status: "failed", error: "ValueError: bad file" }),
    });
    await user.type(screen.getByLabelText("Path inside the folder"), "a.md");
    await user.click(screen.getByRole("button", { name: "Start ingest" }));
    expect(await screen.findByText("Failed")).toBeInTheDocument();
    expect(screen.getByText(/The ingest stopped before it finished/)).toBeInTheDocument();
    expect(screen.queryByText(/ValueError/)).not.toBeInTheDocument();
  });

  it("does not call an ingest job completed when every file failed to index", async () => {
    const result = {
      status: "error",
      error_type: "embedding",
      files_indexed: 0,
      file_details: [{ file: "/srv/docs/notes.md", status: "failed", failure_stage: "embedding", error: "model 'nomic-embed-text' not found (status code: 404)" }],
    };
    const { user } = await openAdd({
      "POST /v1/ingestions": () => queued("j6"),
      "GET /v1/jobs/j6": () => ({ ...JOB, job_id: "j6", status: "completed", result }),
    });
    await user.type(screen.getByLabelText("Path inside the folder"), "notes.md");
    await user.click(screen.getByRole("button", { name: "Start ingest" }));
    const jobs = await screen.findByRole("list", { name: "Jobs" });
    expect(await within(jobs).findByText("Nothing indexed")).toBeInTheDocument();
    expect(within(jobs).queryByText("Completed")).not.toBeInTheDocument();
    expect(within(jobs).getByText(/1 of 1 file could not be indexed\. The embedding step failed/)).toBeInTheDocument();
    expect(jobs.textContent).not.toContain("nomic-embed-text");
    expect(jobs.textContent).not.toContain("/srv/docs");
  });

  it("warns when an ingest job completed with some files failed", async () => {
    const result = { status: "partial", files_indexed: 1, file_details: [{ status: "indexed" }, { status: "failed", failure_stage: "parse" }] };
    const { user } = await openAdd({
      "POST /v1/ingestions": () => queued("j7"),
      "GET /v1/jobs/j7": () => ({ ...JOB, job_id: "j7", status: "completed", result }),
    });
    await user.type(screen.getByLabelText("Path inside the folder"), "a.md");
    await user.click(screen.getByRole("button", { name: "Start ingest" }));
    const jobs = await screen.findByRole("list", { name: "Jobs" });
    expect(await within(jobs).findByText("Completed with errors")).toBeInTheDocument();
    expect(within(jobs).getByText(/1 of 2 files could not be indexed/)).toBeInTheDocument();
  });

  it("states that no folder is approved and names the --root flag in a code element", async () => {
    await openAdd({ "GET /v1/roots": () => ({ status: "ok", roots: [{ id: "m", path: "/uploads", kind: "managed" }] }) });
    const flag = await screen.findByText("omrg web --root FOLDER");
    expect(flag.tagName).toBe("CODE");
    expect(screen.getByText(/No folder is approved/)).toBeInTheDocument();
    expect(screen.queryByLabelText("Path inside the folder")).not.toBeInTheDocument();
  });

  it("sends the job to the target collection when the user names another one", async () => {
    const { server, user } = await openAdd({ "POST /v1/ingestions": () => queued("j4"), "GET /v1/jobs/j4": () => ({ ...JOB, job_id: "j4", status: "running" }) });
    await user.type(screen.getByRole("textbox", { name: "Target collection" }), "fresh");
    await user.type(screen.getByLabelText("Path inside the folder"), "a.md");
    await user.click(screen.getByRole("button", { name: "Start ingest" }));
    await screen.findByRole("list", { name: "Jobs" });
    expect(server.find("POST", "/v1/ingestions")[0]?.body).toEqual({ path: "/srv/docs/a.md", collection: "fresh" });
  });
});

describe("starting a project", () => {
  it("needs a named collection before it ingests when none is open", async () => {
    const { server } = startApp("#/knowledge-base", documentsServer({ "GET /v1/collections": () => [], "POST /v1/ingestions": () => queued("j5"), "GET /v1/jobs/j5": () => ({ ...JOB, job_id: "j5", status: "running" }) }));
    const user = userEvent.setup();
    await screen.findByRole("textbox", { name: "Target collection" });
    expect(await screen.findByRole("button", { name: "Start ingest" })).toBeDisabled();
    await user.type(screen.getByRole("textbox", { name: "Target collection" }), "papers");
    await user.type(screen.getByLabelText("Path inside the folder"), "a.md");
    await user.click(screen.getByRole("button", { name: "Start ingest" }));
    await screen.findByRole("list", { name: "Jobs" });
    expect(server.find("POST", "/v1/ingestions")[0]?.body).toEqual({ path: "/srv/docs/a.md", collection: "papers" });
  });
});
