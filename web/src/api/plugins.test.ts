import { describe, expect, it } from "vitest";
import { documentsServer, json } from "../views/test/fakeDocumentsServer";
import {
  editorTabUrl,
  editorToken,
  listPlugins,
  openEditor,
  recheckPlugin,
  registerPlugin,
  stopEditor,
  unregisterPlugin,
  type EditorOpened,
} from "./plugins";

const STATE = {
  name: "marimo",
  status: "compatible",
  message: "marimo 0.25.1 is compatible",
  executable: "/home/u/.local/bin/marimo",
  version: "0.25.1",
  launchable: true,
  display_name: "marimo notebook editor",
  tool: "marimo",
};

const OPENED: EditorOpened = {
  status: "ok",
  launch_id: "launch_1",
  plugin: "marimo",
  notebook: "/srv/exp/chunks/starter.py",
  experiment_context: "exp_1",
  url_without_token: "http://127.0.0.1:2719/",
  token_delivery: { method: "response_body_once", token: "editor-secret" },
  trust_notice: "Trust text.",
};

describe("plugins client", () => {
  it("lists plugin states, running editors, the install hint and the trust notice", async () => {
    const server = documentsServer({
      "GET /v1/plugins": () => ({ status: "ok", plugins: [STATE], editors: [], install_hint: "Install outside OMRG.", trust_notice: "Trust text." }),
    });
    const list = await listPlugins({ fetchImpl: server.fetchImpl });
    expect(list.plugins[0]!.status).toBe("compatible");
    expect(list.install_hint).toBe("Install outside OMRG.");
  });

  it("registers only with explicit approval", async () => {
    const server = documentsServer({ "POST /v1/plugins": () => json({ status: "ok", plugin: STATE, trust_notice: "Trust text." }, 201) });
    await expect(registerPlugin({ manifestPath: "/m.json", executablePath: "/bin/marimo", approved: false }, { fetchImpl: server.fetchImpl })).rejects.toThrow(
      /approval/,
    );
    expect(server.calls).toHaveLength(0);
    await registerPlugin({ manifestPath: "/m.json", executablePath: "/bin/marimo", approved: true }, { fetchImpl: server.fetchImpl });
    expect(server.calls[0]!.body).toEqual({ manifest_path: "/m.json", executable_path: "/bin/marimo", approved: true });
  });

  it("rechecks and unregisters by name", async () => {
    const server = documentsServer({
      "POST /v1/plugins/marimo/recheck": () => ({ status: "ok", plugin: { ...STATE, status: "incompatible" } }),
      "DELETE /v1/plugins/marimo": () => ({ status: "ok", name: "marimo", unregistered: true }),
    });
    expect((await recheckPlugin("marimo", { fetchImpl: server.fetchImpl })).status).toBe("incompatible");
    await unregisterPlugin("marimo", { fetchImpl: server.fetchImpl });
    expect(server.calls.map((c) => `${c.method} ${c.path}`)).toEqual(["POST /v1/plugins/marimo/recheck", "DELETE /v1/plugins/marimo"]);
    await expect(unregisterPlugin("../session", { fetchImpl: server.fetchImpl })).rejects.toThrow(/unsafe/);
  });

  it("opens an editor only with consent and sends the context and notebook", async () => {
    const server = documentsServer({ "POST /v1/plugins/marimo/editors": () => json(OPENED, 201) });
    const request = { notebook: "starter.py", experimentContext: "exp_1" };
    await expect(openEditor("marimo", { ...request, consent: false }, { fetchImpl: server.fetchImpl })).rejects.toThrow(/consent/);
    expect(server.calls).toHaveLength(0);
    const opened = await openEditor("marimo", { ...request, consent: true }, { fetchImpl: server.fetchImpl });
    expect(opened.launch_id).toBe("launch_1");
    expect(server.calls[0]!.body).toEqual({ notebook: "starter.py", experiment_context: "exp_1", consent: true });
  });

  it("stops an editor by launch id", async () => {
    const server = documentsServer({ "DELETE /v1/plugin-editors/launch_1": () => ({ status: "ok", launch_id: "launch_1", stopped: true }) });
    await stopEditor("launch_1", { fetchImpl: server.fetchImpl });
    expect(server.calls[0]!.method).toBe("DELETE");
  });
});

describe("editor delivery", () => {
  it("opens only a loopback http URL without a token", () => {
    expect(editorTabUrl(OPENED)).toBe("http://127.0.0.1:2719/");
    expect(editorTabUrl({ ...OPENED, url_without_token: "http://localhost:2720/" })).toBe("http://localhost:2720/");
  });

  it.each(["https://example.com/", "javascript:alert(1)", "http://10.0.0.5:2719/", "http://127.0.0.1:2719/?access_token=editor-secret"])(
    "refuses %s",
    (url) => {
      expect(() => editorTabUrl({ ...OPENED, url_without_token: url })).toThrow();
    },
  );

  it("returns the token only for the response-body-once method", () => {
    expect(editorToken(OPENED)).toBe("editor-secret");
    const other = { ...OPENED, token_delivery: { method: "query_parameter", token: "x" } } as unknown as EditorOpened;
    expect(() => editorToken(other)).toThrow(/delivery/);
  });
});
