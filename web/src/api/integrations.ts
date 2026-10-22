/**
 * Typed client for `GET /v1/integrations`.
 *
 * Shapes follow `src/omrs/transports/api/integrations_catalogue.py`. The
 * server reports availability for the running launch. Nothing here installs
 * a package.
 */
import type { ApiClient, CallOptions } from "./client";

export type IntegrationAvailability = "available" | "not-installed" | "unknown";

export interface Integration {
  id: string;
  name: string;
  /** One line about what the integration adds. */
  purpose: string;
  /** The pip extra, or null for an always-on integration. */
  extra: string | null;
  /** `uv sync --extra <name>`, or null when there is nothing to install. */
  install_command: string | null;
  /** `pip install "omrs[<name>]"`, or null when there is nothing to install. */
  pip_command: string | null;
  availability: IntegrationAvailability;
}

export async function listIntegrations(api: ApiClient, options: CallOptions = {}): Promise<Integration[]> {
  const reply = await api.request<{ integrations: Integration[] }>("GET", "/v1/integrations", { signal: options.signal });
  return reply.integrations;
}
