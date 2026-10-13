/**
 * One-time bootstrap exchange for the local session.
 *
 * `omrg web` prints a launch link `http://127.0.0.1:<port>/#bootstrap=<secret>`.
 * A fragment never reaches the server or its access log. On load the page
 * reads the secret, removes it from the address bar and history with
 * `history.replaceState`, and only then exchanges it with `POST /v1/session`.
 * The server answers with an HttpOnly, SameSite=Strict session cookie.
 */

import type { FetchLike } from "./client";

const FRAGMENT_KEY = "bootstrap";
const SESSION_PATH = "/v1/session";

export type BootstrapOutcome = "none" | "ok" | "failed";

export interface BootstrapOptions {
  location?: Location;
  history?: History;
  fetchImpl?: FetchLike;
}

/** Removes `bootstrap=` from the fragment and returns its value, or `null`. */
export function takeBootstrapSecret(location: Location, history: History): string | null {
  const fragment = location.hash.startsWith("#") ? location.hash.slice(1) : location.hash;
  if (fragment === "") return null;
  const params = new URLSearchParams(fragment);
  const secret = params.get(FRAGMENT_KEY);
  if (secret === null) return null;
  params.delete(FRAGMENT_KEY);
  const rest = params.toString();
  history.replaceState(history.state, "", location.pathname + location.search + (rest ? `#${rest}` : ""));
  return secret === "" ? null : secret;
}

/**
 * Exchanges a bootstrap secret from the fragment for a session cookie.
 *
 * Returns `"none"` when the page has no secret, `"ok"` when the server
 * accepted it, and `"failed"` otherwise. The secret is never logged.
 */
export async function exchangeBootstrap(options: BootstrapOptions = {}): Promise<BootstrapOutcome> {
  const secret = takeBootstrapSecret(options.location ?? window.location, options.history ?? window.history);
  if (secret === null) return "none";
  const fetchImpl = options.fetchImpl ?? ((input, init) => fetch(input, init));
  try {
    const response = await fetchImpl(SESSION_PATH, {
      method: "POST",
      headers: { Accept: "application/json", "Content-Type": "application/json" },
      credentials: "same-origin",
      body: JSON.stringify({ bootstrap: secret }),
    });
    return response.ok ? "ok" : "failed";
  } catch {
    return "failed";
  }
}
