import { describe, expect, it } from "vitest";
import { createApiClient } from "./client";
import { DOCUMENT_READING_KEYS, getDocumentReadingSettings, saveDocumentReadingSettings } from "./settingsDocumentReading";
import { documentsServer } from "../test/fakeDocumentsServer";

const STATE = { status: "ok", revision: "r1", settings: [], pdf_readers: [], pdf_reader_in_use: "pypdf", ocr: { workers_dir: null, worker_command_set: false, engines: [] } };

function setup(handlers: Parameters<typeof documentsServer>[0]) {
  const server = documentsServer(handlers);
  return { server, api: createApiClient(server.fetchImpl) };
}

describe("document reading API", () => {
  it("lists the nine keys in the contract order", () => {
    expect(DOCUMENT_READING_KEYS).toEqual([
      "pdf_reader",
      "ocr_fallback_enabled",
      "ocr_fallback_min_confidence",
      "ocr_fallback_page_fraction",
      "ocr_routing_unit",
      "ocr_engine_primary",
      "ocr_engine_fallback",
      "ocr_maths_routing_enabled",
      "ocr_maths_page_fraction",
    ]);
  });

  it("reads the state with GET /v1/settings/document-reading", async () => {
    const { api, server } = setup({ "GET /v1/settings/document-reading": () => STATE });
    await expect(getDocumentReadingSettings(api)).resolves.toEqual(STATE);
    expect(server.calls.map((call) => [call.method, call.path, call.body])).toEqual([["GET", "/v1/settings/document-reading", null]]);
  });

  it("saves values and the revision with PUT /v1/settings/document-reading, keeping null to reset a key", async () => {
    const { api, server } = setup({ "PUT /v1/settings/document-reading": () => ({ ...STATE, revision: "r2" }) });
    const values = { pdf_reader: "liteparse", ocr_fallback_page_fraction: 0.2, ocr_engine_fallback: null };
    await expect(saveDocumentReadingSettings(api, values, { revision: "r1" })).resolves.toMatchObject({ revision: "r2" });
    expect(server.calls.map((call) => [call.method, call.path, call.body])).toEqual([["PUT", "/v1/settings/document-reading", { values, revision: "r1" }]]);
  });
});
