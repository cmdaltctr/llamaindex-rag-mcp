/**
 * Typed client for `GET /v1/integrations` and the install routes.
 *
 * Shapes follow `src/omrs/transports/api/integrations_catalogue.py` and
 * `openapi.yaml`. The server reports availability for the running launch. An
 * entry with `installable: true` can be installed with
 * `POST /v1/integrations/{extra}/install`; the new packages work after a
 * restart. Every other entry is installed outside the app with its command.
 */
import type { ApiClient, CallOptions } from "./client";

export type IntegrationAvailability = "available" | "not-installed" | "unknown" | "restart-needed";

/** How the server itself was installed. It decides the copy command. */
export type InstallType = "uv-tool" | "checkout" | "other";

/** Why `installable` is false, or `null` when it is true. */
export type InstallReason = "not-installable-here" | "status-unknown" | "not-uv-tool" | "uv-not-found" | "already-installed" | "no-requirements";

export interface Integration {
  id: string;
  name: string;
  /** One line about what the integration adds. */
  purpose: string;
  /** The pip extra, or null for an always-on integration. */
  extra: string | null;
  /** The copy command for this install type, or null when there is nothing to install. */
  install_command: string | null;
  /** `pip install "omrs[<name>]"`, or null when there is nothing to install. */
  pip_command: string | null;
  availability: IntegrationAvailability;
  /** True when `POST /v1/integrations/{extra}/install` would start an install now. */
  installable: boolean;
  install_reason: InstallReason | null;
  /** The requirements the extra adds, such as `llama-index-llms-anthropic>=0.11.0`. */
  packages: string[];
  /** A warning to read before the install, such as a package version it can change; null for most entries. */
  install_caution: string | null;
  /** True when every install already holds this entry; it has no install command. */
  base: boolean;
}

export interface IntegrationList {
  install_type: InstallType;
  integrations: Integration[];
}

export type InstallState = "idle" | "running" | "succeeded" | "failed";

/** The running or last install of this launch. */
export interface IntegrationInstall {
  state: InstallState;
  /** The extra of the running or last install; null when idle. */
  extra: string | null;
  started_at: string | null;
  finished_at: string | null;
  /** Why the install failed; null unless `state` is `failed`. `check-failed`: installed, but `uv pip check` found a clash. */
  reason: "exit-code" | "check-failed" | "timed-out" | "start-failed" | null;
  exit_code: number | null;
  /** The last output lines (at most 40), redacted by the server. */
  output: string[];
}

export async function listIntegrations(api: ApiClient, options: CallOptions = {}): Promise<IntegrationList> {
  const reply = await api.request<{ install_type: InstallType; integrations: Integration[] }>("GET", "/v1/integrations", { signal: options.signal });
  return { install_type: reply.install_type, integrations: reply.integrations };
}

export async function getIntegrationInstall(api: ApiClient, options: CallOptions = {}): Promise<IntegrationInstall> {
  const reply = await api.request<{ install: IntegrationInstall }>("GET", "/v1/integrations/install", { signal: options.signal });
  return reply.install;
}

/** Starts an install of `extra`. The server answers 202 with the running state, or 409 with a `reason`. */
export async function installIntegration(api: ApiClient, extra: string): Promise<IntegrationInstall> {
  const reply = await api.request<{ install: IntegrationInstall }>("POST", `/v1/integrations/${encodeURIComponent(extra)}/install`);
  return reply.install;
}
