import { describe, expect, it } from "vitest";
import { documentsServer, json } from "../test/fakeDocumentsServer";
import { ApiError, createApiClient } from "./client";
import { createExperiment, createExperimentFolder, issueBoundCredential, listExperiments, revokeExperiment, workspacePath } from "./experiments";

const CONTEXT_ID = "exp_0123456789abcdef";

const ENTRY = {
  experiment: {
    context_id: CONTEXT_ID,
    name: "chunk sizes",
    root: "/srv/exp",
    workspace: "/srv/exp/chunks",
    output_dir: "/srv/exp/chunks/output",
    store_backend: "lancedb",
    declared_factors: [],
    actions: ["ingest", "read"],
    approved_at: "2026-10-13T12:00:00+00:00",
    revoked_at: null,
    status: "active",
  },
  identity: {
    context_id: "exp_0123456789abcdef",
    store_kind: "lancedb",
    store_path: "/srv/exp/chunks/output/lancedb",
    embedding_provider: "onnx",
    embedding_model: "bge-small",
    index_identity: "a1b2c3d4e5f60718",
  },
};

describe("experiments client", () => {
  it("lists roots, contexts and the trust notice", async () => {
    const server = documentsServer({
      "GET /v1/experiments": () => ({ status: "ok", roots: ["/srv/exp"], experiments: [ENTRY], trust_notice: "Trust text." }),
    });
    const api = createApiClient(server.fetchImpl);
    const list = await listExperiments(api);
    expect(list.roots).toEqual(["/srv/exp"]);
    expect(list.experiments[0]!.identity.index_identity).toBe("a1b2c3d4e5f60718");
    expect(list.trust_notice).toBe("Trust text.");
  });

  it("registers a workspace with an absolute path and the chosen actions", async () => {
    const server = documentsServer({
      "POST /v1/experiments": () => json({ status: "ok", ...ENTRY, trust_notice: "Trust text." }, 201),
    });
    const api = createApiClient(server.fetchImpl);
    const created = await createExperiment(api, { workspace: "/srv/exp/chunks", name: "chunk sizes", actions: ["read"] });
    expect(created.experiment.context_id).toBe("exp_0123456789abcdef");
    expect(server.calls[0]!.body).toEqual({ workspace: "/srv/exp/chunks", name: "chunk sizes", actions: ["read"] });
  });

  it("raises the server's refusal message and keeps its code", async () => {
    const server = documentsServer({
      "POST /v1/experiments": () =>
        json({ status: "error", code: "outside_root", message: "The workspace is outside every approved experiment root.", context_id: null }, 400),
    });
    const api = createApiClient(server.fetchImpl);
    const error = await createExperiment(api, { workspace: "/tmp/x", name: "", actions: ["read"] }).catch((e: unknown) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).message).toBe("The workspace is outside every approved experiment root.");
    expect((error as ApiError).status).toBe(400);
  });

  it("creates a folder from a relative path and returns the workspace to register", async () => {
    const folder = { root: "/srv/exp", path: "hybrid-search/run-1", name: "run-1", workspace: "/srv/exp/hybrid-search/run-1" };
    const server = documentsServer({ "POST /v1/experiment-folders": () => json({ status: "ok", folder }, 201) });
    const created = await createExperimentFolder(createApiClient(server.fetchImpl), { path: "hybrid-search/run-1" });
    expect(created).toEqual(folder);
    expect(server.calls[0]!.body).toEqual({ path: "hybrid-search/run-1", root: null });
  });

  it("keeps the stable refusal code of a folder the server refuses", async () => {
    const server = documentsServer({
      "POST /v1/experiment-folders": () => json({ status: "error", code: "traversal", message: "no" }, 400),
    });
    const error = await createExperimentFolder(createApiClient(server.fetchImpl), { path: "../x" }).catch((e: unknown) => e);
    expect((error as ApiError).status).toBe(400);
    expect((error as ApiError).body).toMatchObject({ code: "traversal" });
  });

  it("revokes a context by id and refuses unsafe identifiers", async () => {
    const server = documentsServer({
      "DELETE /v1/experiments/exp_0123456789abcdef": () => ({ status: "ok", experiment: { ...ENTRY.experiment, status: "revoked" } }),
    });
    const api = createApiClient(server.fetchImpl);
    const revoked = await revokeExperiment(api, CONTEXT_ID);
    expect(revoked.status).toBe("revoked");
    await expect(revokeExperiment(api, "../credentials")).rejects.toThrow(/unsafe/);
    expect(server.calls).toHaveLength(1);
  });

  it("issues a credential bound to one context", async () => {
    const server = documentsServer({
      "POST /v1/credentials": (body) =>
        json({ status: "ok", id: "cred1", token: "secret-token", scopes: body.scopes, label: body.label, experiment_context: body.experiment_context }, 201),
    });
    const api = createApiClient(server.fetchImpl);
    const issued = await issueBoundCredential(api, CONTEXT_ID, ["graph", "read", "run"], "notebook");
    expect(issued.token).toBe("secret-token");
    expect(server.calls[0]!.body).toEqual({ scopes: ["graph", "read", "run"], label: "notebook", experiment_context: "exp_0123456789abcdef" });
  });

  it("refuses a credential without a context, so it can never reach the live library", async () => {
    const server = documentsServer();
    const api = createApiClient(server.fetchImpl);
    await expect(issueBoundCredential(api, "", ["read"], "")).rejects.toThrow(/unsafe/);
    expect(server.calls).toHaveLength(0);
  });
});

describe("workspacePath", () => {
  it("joins a relative folder to the chosen approved root", () => {
    expect(workspacePath("/srv/exp", "chunks/run-1")).toBe("/srv/exp/chunks/run-1");
  });

  it.each(["/etc", "../outside", "a/../../b", "", "~/x"])("refuses %j before any request", (relative) => {
    expect(() => workspacePath("/srv/exp", relative)).toThrow();
  });
});
