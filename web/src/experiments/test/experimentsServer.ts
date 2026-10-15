import { vi } from "vitest";
import type { FetchLike } from "../../api/client";
import type { ExperimentEntry, FolderNode, FolderRoot } from "../../api/experiments";
import type { EditorInfo, PluginState } from "../../api/plugins";
import type { RunDetailRecord, RunEventRecord, RunResultRecord } from "../../api/runs";
import { documentsServer, json, type Handler } from "../../test/fakeDocumentsServer";
import { runRouter } from "./runRouter";

export const TRUST =
  "Notebook Python runs with your user account's filesystem and network permissions. A dependency environment is not an operating-system sandbox. Open only notebooks you trust.";
export const INSTALL_HINT = "Install the notebook editor outside OMRG, for example `uv tool install marimo`. OMRG never installs or updates it.";
export const EDITOR_TOKEN = "editor-secret-7f3a";
export const CREDENTIAL_TOKEN = "bearer-secret-91c2";

/** A context entry. `relative` is the workspace path below `/srv/exp`; it defaults to the name. */
export function entry(id: string, name: string, status: "active" | "revoked" = "active", relative = name, factors: string[] = []): ExperimentEntry {
  return {
    experiment: {
      context_id: id,
      name,
      root: "/srv/exp",
      workspace: `/srv/exp/${relative}`,
      output_dir: `/srv/exp/${relative}/output`,
      store_backend: "lancedb",
      declared_factors: factors,
      actions: ["ingest", "read"],
      approved_at: "2026-10-13T12:00:00+00:00",
      revoked_at: status === "revoked" ? "2026-10-13T13:00:00+00:00" : null,
      status,
    },
    identity: {
      context_id: id,
      store_kind: "lancedb",
      store_path: `/srv/exp/${relative}/output/lancedb`,
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
  /** Directories that exist below the first root, as relative paths such as `hybrid-search`. */
  dirs: string[];
  entries: ExperimentEntry[];
  plugins: PluginState[];
  editors: EditorInfo[];
  runs: RunDetailRecord[];
  results: Record<string, RunResultRecord>;
  events: Record<string, RunEventRecord[]>;
}

/** The directory tree the server lists: every directory, with registered workspaces as leaves. */
function buildTree(root: string, state: ServerState): FolderNode[] {
  const nodes = new Map<string, FolderNode>();
  const top: FolderNode[] = [];
  const ensure = (relative: string): FolderNode => {
    const known = nodes.get(relative);
    if (known) return known;
    const parts = relative.split("/");
    const node: FolderNode = { name: parts.at(-1)!, path: relative, workspace: `${root}/${relative}`, context_id: null, children: [] };
    nodes.set(relative, node);
    if (parts.length === 1) top.push(node);
    else ensure(parts.slice(0, -1).join("/")).children.push(node);
    return node;
  };
  for (const dir of state.dirs) ensure(dir);
  for (const { experiment } of state.entries) {
    if (!experiment.workspace.startsWith(`${root}/`)) continue;
    ensure(experiment.workspace.slice(root.length + 1)).context_id = experiment.context_id;
  }
  return top;
}

function folders(state: ServerState): FolderRoot[] {
  return state.roots.map((root, index) => ({ root, tree: index === 0 ? buildTree(root, state) : [] }));
}

/** In-memory stand-in for the experiment, folder, credential, plugin and run routes. */
export function experimentsServer(initial: Partial<ServerState> = {}, extra: Record<string, Handler> = {}) {
  const state: ServerState = { roots: ["/srv/exp"], dirs: [], entries: [], plugins: [], editors: [], runs: [], results: {}, events: {}, ...initial };
  const handlers: Record<string, Handler> = {
    "GET /v1/experiments": () => ({ status: "ok", roots: state.roots, folders: folders(state), experiments: state.entries, trust_notice: TRUST }),
    "POST /v1/experiment-folders": (body) => {
      const path = String(body.path);
      if (state.roots.length === 0) return json({ status: "error", message: "No experiment root is approved. Restart with `omrg web --experiment-root`." }, 409);
      if (path.split("/").includes("..")) return json({ status: "error", code: "traversal", message: "RAW traversal text" }, 400);
      if (state.dirs.includes(path)) return json({ status: "error", code: "exists", message: "RAW exists text" }, 409);
      state.dirs = [...state.dirs, path];
      const name = path.split("/").at(-1)!;
      return json({ status: "ok", folder: { root: state.roots[0], path, name, workspace: `${state.roots[0]}/${path}` } }, 201);
    },
    "POST /v1/experiments": (body) => {
      const workspace = String(body.workspace);
      const relative = workspace.slice(`${state.roots[0]}/`.length);
      if (!state.dirs.includes(relative)) return json({ status: "error", code: "not_found", message: "RAW not found text" }, 400);
      const created = entry(`exp_${state.entries.length + 1}`, String(body.name || "unnamed"), "active", relative, (body.declared_factors as string[] | undefined) ?? []);
      state.entries = [...state.entries, created];
      return json({ status: "ok", ...created, trust_notice: TRUST }, 201);
    },
    "POST /v1/credentials": (body) =>
      json({ status: "ok", id: "cred_1", token: CREDENTIAL_TOKEN, scopes: body.scopes, label: body.label, experiment_context: body.experiment_context }, 201),
    "GET /v1/plugins": () => ({ status: "ok", plugins: state.plugins, editors: state.editors, install_hint: INSTALL_HINT, trust_notice: TRUST }),
    "POST /v1/plugins": () => {
      const added: PluginState = { ...MARIMO, name: "new", display_name: "New editor", status: "unchecked", launchable: false, message: "Recheck to probe the executable." };
      state.plugins = [...state.plugins, added];
      return json({ status: "ok", plugin: added, trust_notice: TRUST }, 201);
    },
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
    "POST /v1/plugins/marimo/recheck": () => ({ status: "ok", plugin: { ...MARIMO, message: "marimo 0.25.2 is compatible" } }),
    "DELETE /v1/plugins/old": () => {
      state.plugins = state.plugins.filter((p) => p.name !== "old");
      return { status: "ok", name: "old", unregistered: true };
    },
    ...extra,
  };
  for (const item of state.entries) {
    handlers[`DELETE /v1/experiments/${item.experiment.context_id}`] = () => {
      item.experiment = { ...item.experiment, status: "revoked", revoked_at: "2026-10-13T14:00:00+00:00" };
      return { status: "ok", experiment: item.experiment };
    };
  }

  const base = documentsServer(handlers);
  const runs = runRouter({ runs: state.runs, results: state.results, events: state.events });
  const fetchImpl = vi.fn<FetchLike>(async (path, init) => {
    const url = new URL(path, "http://omrg.test");
    const method = init?.method ?? "GET";
    // A handler passed in `extra` overrides the run routes, for example to make the list fail.
    if (!runs.handles(url.pathname) || `${method} ${url.pathname}` in extra) return base.fetchImpl(path, init);
    base.calls.push({ method, path, body: null, headers: new Headers(init?.headers) });
    return runs.route(method, url);
  });
  return { ...base, fetchImpl, state, runs: runs.runs };
}
