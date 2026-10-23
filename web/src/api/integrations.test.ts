import { describe, expect, it } from "vitest";
import { documentsServer, json } from "../test/fakeDocumentsServer";
import { ApiError, createApiClient } from "./client";
import { listIntegrations, type Integration } from "./integrations";

const ENTRY: Integration = {
  id: "azure",
  name: "Azure Document Intelligence",
  purpose: "Cloud document reading.",
  extra: "azure",
  install_command: "uv sync --extra azure",
  pip_command: 'pip install "omrs[azure]"',
  availability: "not-installed",
};

describe("listIntegrations", () => {
  it("returns the integrations array from the envelope", async () => {
    const server = documentsServer({ "GET /v1/integrations": () => ({ status: "ok", integrations: [ENTRY] }) });
    const result = await listIntegrations(createApiClient(server.fetchImpl));
    expect(result).toEqual([ENTRY]);
    expect(server.calls[0]).toMatchObject({ method: "GET", path: "/v1/integrations" });
  });

  it("throws an ApiError for an HTTP failure", async () => {
    const server = documentsServer({ "GET /v1/integrations": () => json({ status: "error", message: "boom" }, 500) });
    await expect(listIntegrations(createApiClient(server.fetchImpl))).rejects.toBeInstanceOf(ApiError);
  });
});
