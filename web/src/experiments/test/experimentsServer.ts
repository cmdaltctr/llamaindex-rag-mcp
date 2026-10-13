import type { ExperimentEntry } from "../../api/experiments";
import type { EditorInfo, PluginState } from "../../api/plugins";
import { documentsServer, json, type Handler } from "../../views/test/fakeDocumentsServer";

export const TRUST =
  "Notebook Python runs with your user account's filesystem and network permissions. A dependency environment is not an operating-system sandbox. Open only notebooks you trust.";
export const INSTALL_HINT = "Install the notebook editor outside OMRG, for example `uv tool install marimo`. OMRG never installs or updates it.";
export const EDITOR_TOKEN = "editor-secret-7f3a";
export const CREDENTIAL_TOKEN = "bearer-secret-91c2";

export function entry(id: string, name: string, status: "active" | "revoked" = "active"): ExperimentEntry {
  return {
    experiment: {
      context_id: id,
      name,
      root: "/srv/exp",
      workspace: `/srv/exp/${name}`,
      output_dir: `/srv/exp/${name}/output`,
      store_backend: "lancedb",
      declared_factors: [],
      actions: ["ingest", "read"],
      approved_at: "2026-10-13T12:00:00+00:00",
      revoked_at: status === "revoked" ? "2026-10-13T13:00:00+00:00" : null,
      status,
    },
    identity: {
      context_id: id,
      store_kind: "lancedb",
      store_path: `/srv/exp/${name}/output/lancedb`,
      embedding_provider: "onnx",
      embedding_model: "bge-small-en",
      index_identity: `idx-${id}`,
    },
  };
}

export const MARIMO: PluginState = {
  name: "marimo",
  status: "compatible",
  message: "marimo 0.25.1 is compatible",
  executable: "/home/u/.local/bin/marimo",
  version: "0.25.1",
  launchable: true,
  display_name: "marimo notebook editor",
  tool: "marimo",
};

export interface ServerState {
  roots: string[];
  entries: ExperimentEntry[];
  plugins: PluginState[];
  editors: EditorInfo[];
  runs: Record<string, unknown>[];
}

/** In-memory stand-in for the experiment, credential, plugin and run routes. */
export function experimentsServer(initial: Partial<ServerState> = {}, extra: Record<string, Handler> = {}) {
  const state: ServerState = { roots: ["/srv/exp"], entries: [], plugins: [], editors: [], runs: [], ...initial };
  const handlers: Record<string, Handler> = {
    "GET /v1/experiments": () => ({ status: "ok", roots: state.roots, experiments: state.entries, trust_notice: TRUST }),
    "POST /v1/experiments": (body) => {
      const name = String(body.name || "unnamed");
      const created = entry(`exp_${state.entries.length + 1}`, name);
      created.experiment.workspace = String(body.workspace);
      state.entries = [...state.entries, created];
      return json({ status: "ok", ...created, trust_notice: TRUST }, 201);
    },
    "POST /v1/credentials": (body) =>
      json({ status: "ok", id: "cred_1", token: CREDENTIAL_TOKEN, scopes: body.scopes, label: body.label, experiment_context: body.experiment_context }, 201),
    "GET /v1/plugins": () => ({ status: "ok", plugins: state.plugins, editors: state.editors, install_hint: INSTALL_HINT, trust_notice: TRUST }),
    "POST /v1/plugins/marimo/editors": (body) => {
      const editor: EditorInfo = {
        launch_id: "launch_1",
        plugin: "marimo",
        notebook: `/srv/exp/chunks/${String(body.notebook)}`,
        experiment_context: String(body.experiment_context),
        url_without_token: "http://127.0.0.1:2719/",
      };
      state.editors = [...state.editors, editor];
      return json({ status: "ok", ...editor, token_delivery: { method: "response_body_once", token: EDITOR_TOKEN }, trust_notice: TRUST }, 201);
    },
    "DELETE /v1/plugin-editors/launch_1": () => {
      state.editors = state.editors.filter((e) => e.launch_id !== "launch_1");
      return { status: "ok", launch_id: "launch_1", stopped: true };
    },
    "GET /v1/runs": () => ({ status: "ok", runs: state.runs }),
    ...extra,
  };
  for (const item of state.entries) {
    handlers[`DELETE /v1/experiments/${item.experiment.context_id}`] = () => {
      item.experiment = { ...item.experiment, status: "revoked", revoked_at: "2026-10-13T14:00:00+00:00" };
      return { status: "ok", experiment: item.experiment };
    };
  }
  return { ...documentsServer(handlers), state };
}

export function run(runId: string, contextId: string | null, status = "succeeded"): Record<string, unknown> {
  return {
    run_id: runId,
    pipeline_id: "p1",
    revision_id: "p1-r1",
    graph_hash: "h",
    status,
    origin: "submit",
    source_run_id: null,
    settings: {},
    // Same shape as the server: ExperimentEngine.resources() nests the identity under "backend".
    resources: contextId
      ? { experiment: { context_id: contextId, graph_identity: "h", backend: { context_id: contextId, index_identity: `idx-${contextId}`, store_kind: "lancedb" } } }
      : {},
    inputs: {},
    failure: null,
    result_ref: null,
    last_sequence: 3,
    created_at: "2026-10-13T12:30:00Z",
    started_at: null,
    finished_at: null,
  };
}
