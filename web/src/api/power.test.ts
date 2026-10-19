import { describe, expect, it } from "vitest";
import { createApiClient } from "./client";
import { getPower, postPower } from "./power";
import { documentsServer, json } from "../test/fakeDocumentsServer";

describe("power client", () => {
  it("reads managed from GET /v1/server/power", async () => {
    const server = documentsServer({ "GET /v1/server/power": () => ({ managed: true }) });
    await expect(getPower(createApiClient(server.fetchImpl))).resolves.toEqual({ managed: true });
  });

  it("posts the action as the JSON body and accepts a 202", async () => {
    const server = documentsServer({ "POST /v1/server/power": () => json({ status: "accepted", action: "off" }, 202) });
    await postPower(createApiClient(server.fetchImpl), "off");
    expect(server.find("POST", "/v1/server/power")[0]?.body).toEqual({ action: "off" });
  });
});
