import { describe, expect, it } from "vitest";
import { documentsServer, json } from "../test/fakeDocumentsServer";
import { ApiError, createApiClient } from "./client";
import { getIntegrationInstall, installIntegration, listIntegrations, type Integration, type IntegrationInstall } from "./integrations";

const ENTRY: Integration = {
  id: "azure",
  name: "Azure Document Intelligence",
  purpose: "Cloud document reading.",
  extra: "azure",
  install_command: "uv sync --extra azure",
  pip_command: 'pip install "omrs[azure]"',
  availability: "not-installed",
  installable: false,
  install_reason: "not-uv-tool",
  packages: ["azure-ai-documentintelligence>=1.0.0"],
  install_caution: null,
};

const RUNNING: IntegrationInstall = {
  state: "running",
  extra: "anthropic",
  started_at: "2026-10-24T10:00:00Z",
  finished_at: null,
  reason: null,
  exit_code: null,
  output: ["Resolved 3 packages"],
};

describe("listIntegrations", () => {
  it("returns the install type and the integrations array from the envelope", async () => {
    const server = documentsServer({ "GET /v1/integrations": () => ({ status: "ok", install_type: "checkout", integrations: [ENTRY] }) });
    const result = await listIntegrations(createApiClient(server.fetchImpl));
    expect(result).toEqual({ install_type: "checkout", integrations: [ENTRY] });
    expect(server.calls[0]).toMatchObject({ method: "GET", path: "/v1/integrations" });
  });

  it("throws an ApiError for an HTTP failure", async () => {
    const server = documentsServer({ "GET /v1/integrations": () => json({ status: "error", message: "boom" }, 500) });
    await expect(listIntegrations(createApiClient(server.fetchImpl))).rejects.toBeInstanceOf(ApiError);
  });
});

describe("getIntegrationInstall", () => {
  it("returns the install state from the envelope", async () => {
    const server = documentsServer({ "GET /v1/integrations/install": () => ({ status: "ok", install: RUNNING }) });
    expect(await getIntegrationInstall(createApiClient(server.fetchImpl))).toEqual(RUNNING);
    expect(server.calls[0]).toMatchObject({ method: "GET", path: "/v1/integrations/install" });
  });
});

describe("installIntegration", () => {
  it("posts to the extra's install route and returns the running state", async () => {
    const server = documentsServer({ "POST /v1/integrations/anthropic/install": () => json({ status: "ok", install: RUNNING }, 202) });
    expect(await installIntegration(createApiClient(server.fetchImpl), "anthropic")).toEqual(RUNNING);
    expect(server.find("POST", "/v1/integrations/anthropic/install")).toHaveLength(1);
  });

  it("throws an ApiError with the reason for a refusal", async () => {
    const server = documentsServer({
      "POST /v1/integrations/anthropic/install": () => json({ status: "error", message: "An install is running.", reason: "install-running" }, 409),
    });
    const error = await installIntegration(createApiClient(server.fetchImpl), "anthropic").catch((caught: unknown) => caught);
    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).status).toBe(409);
  });
});
