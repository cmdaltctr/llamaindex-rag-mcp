/**
 * Typed client for the notebook plugin and editor routes.
 *
 * Shapes follow `src/omrg/transports/api/routes_plugins.py`. OMRG installs
 * and updates nothing: these calls register, recheck, unregister, open and
 * stop only. The editor token arrives once in the open response
 * (`token_delivery.method = "response_body_once"`) and never in a URL.
 */
import { ClientRefusal, type ApiClient, type CallOptions } from "./client";
import { safeId } from "./experiments";

export const PLUGIN_STATUSES = ["compatible", "incompatible", "unchecked", "needs_approval", "unavailable"] as const;
export type PluginStatus = (typeof PLUGIN_STATUSES)[number];

export interface PluginState {
  name: string;
  status: PluginStatus;
  /** What the operator can do next. Shown verbatim. */
  message: string;
  executable: string;
  version: string | null;
  launchable: boolean;
  display_name: string | null;
  tool: string | null;
}

export interface EditorInfo {
  launch_id: string;
  plugin: string;
  notebook: string;
  experiment_context: string | null;
  url_without_token: string;
}

export interface PluginList {
  plugins: PluginState[];
  editors: EditorInfo[];
  install_hint: string;
  trust_notice: string;
}

export interface EditorOpened extends EditorInfo {
  status: "ok";
  token_delivery: { method: "response_body_once"; token: string };
  trust_notice: string;
}

export interface RegisterRequest {
  manifestPath: string;
  executablePath: string;
  approved: boolean;
}

export interface OpenRequest {
  notebook: string;
  experimentContext: string;
  consent: boolean;
}

export function listPlugins(api: ApiClient, options: CallOptions = {}): Promise<PluginList> {
  return api.request<PluginList>("GET", "/v1/plugins", { signal: options.signal });
}

/** Registration is an explicit trust decision: nothing is sent without approval. */
export async function registerPlugin(api: ApiClient, request: RegisterRequest, options: CallOptions = {}): Promise<PluginState> {
  if (request.approved !== true) throw new Error("Registering a plugin needs your explicit approval.");
  const body = { manifest_path: request.manifestPath, executable_path: request.executablePath, approved: true };
  return (await api.request<{ plugin: PluginState }>("POST", "/v1/plugins", { body, signal: options.signal })).plugin;
}

export async function recheckPlugin(api: ApiClient, name: string, options: CallOptions = {}): Promise<PluginState> {
  const path = `/v1/plugins/${safeId(name)}/recheck`;
  return (await api.request<{ plugin: PluginState }>("POST", path, { body: {}, signal: options.signal })).plugin;
}

export async function unregisterPlugin(api: ApiClient, name: string, options: CallOptions = {}): Promise<void> {
  await api.request("DELETE", `/v1/plugins/${safeId(name)}`, { signal: options.signal });
}

/** Opening runs notebook Python with the user's permissions: nothing is sent without consent. */
export async function openEditor(api: ApiClient, name: string, request: OpenRequest, options: CallOptions = {}): Promise<EditorOpened> {
  if (request.consent !== true) throw new Error("Opening a notebook editor needs your consent.");
  const body = { notebook: request.notebook, experiment_context: request.experimentContext, consent: true };
  return api.request<EditorOpened>("POST", `/v1/plugins/${safeId(name)}/editors`, { body, signal: options.signal });
}

export async function stopEditor(api: ApiClient, launchId: string, options: CallOptions = {}): Promise<void> {
  await api.request("DELETE", `/v1/plugin-editors/${safeId(launchId)}`, { signal: options.signal });
}

const LOOPBACK_HOSTS = new Set(["127.0.0.1", "localhost", "[::1]"]);

/**
 * The address to open in a new tab. Only a loopback `http` URL with no query
 * or fragment is accepted, so the token can never travel in the address.
 */
export function editorTabUrl(editor: EditorInfo): string {
  let url: URL;
  try {
    url = new URL(editor.url_without_token);
  } catch {
    throw new ClientRefusal("The server gave an editor address that is not a valid URL.");
  }
  if (url.protocol !== "http:" || !LOOPBACK_HOSTS.has(url.hostname)) {
    throw new ClientRefusal("The server gave an editor address that is not on this computer.");
  }
  if (url.search !== "" || url.hash !== "" || url.username !== "" || url.password !== "") {
    throw new ClientRefusal("The server gave an editor address with extra parts. It was not opened.");
  }
  return url.href;
}

/** The editor access token, accepted only from the response-body-once delivery method. */
export function editorToken(opened: EditorOpened): string {
  const delivery = opened.token_delivery as { method?: unknown; token?: unknown } | undefined;
  if (delivery?.method !== "response_body_once" || typeof delivery.token !== "string" || delivery.token === "") {
    throw new ClientRefusal("The server used a token delivery method that this page does not support.");
  }
  return delivery.token;
}
