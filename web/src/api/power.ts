/**
 * The power routes of the login item. `GET` says whether this server is the
 * login item, which is the only case where the page may act on it. `POST`
 * answers 202 and acts after the response: `restart` asks launchd to signal the
 * app so it starts again, `off` unloads the agent. A 409 means work is running
 * or the server is not the login item; a bearer credential gets 403.
 */
import type { ApiClient, CallOptions } from "./client";

export type PowerAction = "restart" | "off";

export interface PowerState {
  /** True when the running app is the login item; false for a foreground `omrs web`. */
  managed: boolean;
}

/** The 202 body. The page does not read it; the status code is the answer. */
export interface PowerAccepted {
  status: string;
  action: PowerAction;
}

export function getPower(api: ApiClient, options: CallOptions = {}): Promise<PowerState> {
  return api.request<PowerState>("GET", "/v1/server/power", { signal: options.signal });
}

export function postPower(api: ApiClient, action: PowerAction): Promise<PowerAccepted> {
  return api.request<PowerAccepted>("POST", "/v1/server/power", { body: { action } });
}
