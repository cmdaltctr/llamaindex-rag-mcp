import { describe, expect, it } from "vitest";
import { documentsServer } from "../test/fakeDocumentsServer";
import { SERVER_STOPPED } from "../settings/test/fixtures";
import { createApiClient } from "./client";
import { getLlamacppServer, restartLlamacppServer, saveLlamacppServer, startLlamacppServer, stopLlamacppServer } from "./llamacppServer";

function setup(handlers: Parameters<typeof documentsServer>[0]) {
  const server = documentsServer(handlers);
  return { server, api: createApiClient(server.fetchImpl) };
}

describe("llama.cpp server API", () => {
  it("reads the status", async () => {
    const { api } = setup({ "GET /v1/llamacpp/server": () => SERVER_STOPPED });
    await expect(getLlamacppServer(api)).resolves.toMatchObject({ state: "stopped", reason: null });
  });

  it("saves only the keys it is given", async () => {
    const { api, server } = setup({ "PUT /v1/llamacpp/server": () => SERVER_STOPPED });
    await saveLlamacppServer(api, { context_window: 8192 });
    await saveLlamacppServer(api, { model: null }, { revision: "r1" });
    expect(server.find("PUT", "/v1/llamacpp/server").map((call) => call.body)).toEqual([{ context_window: 8192 }, { model: null, revision: "r1" }]);
  });

  it("starts, stops and restarts with POST and no body", async () => {
    const { api, server } = setup({
      "POST /v1/llamacpp/server/start": () => SERVER_STOPPED,
      "POST /v1/llamacpp/server/stop": () => SERVER_STOPPED,
      "POST /v1/llamacpp/server/restart": () => SERVER_STOPPED,
    });
    await startLlamacppServer(api);
    await stopLlamacppServer(api);
    await restartLlamacppServer(api);
    expect(server.find("POST", "/v1/llamacpp/server/start")).toHaveLength(1);
    expect(server.find("POST", "/v1/llamacpp/server/stop")).toHaveLength(1);
    expect(server.find("POST", "/v1/llamacpp/server/restart")).toHaveLength(1);
  });
});
