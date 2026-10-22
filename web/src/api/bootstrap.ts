/**
 * Sign-in for the local session.
 *
 * Two secrets can open a session, and both go to `POST /v1/session`, which
 * answers with an HttpOnly, SameSite=Strict session cookie:
 *
 * - The one-time launch link `http://127.0.0.1:<port>/#bootstrap=<secret>`.
 *   A fragment never reaches the server or its access log. On load the page
 *   reads the secret, removes it from the address bar and history with
 *   `history.replaceState`, and only then exchanges it.
 * - The workspace sign-in secret, which the server puts into its own page in
 *   a `<meta name="omrs-page-secret">` tag. It lasts across server restarts,
 *   so the page uses it on load and again whenever a request gets 401.
 */

import type { FetchLike, SessionRenewal } from "./client";

const FRAGMENT_KEY = "bootstrap";
const SESSION_PATH = "/v1/session";
const PAGE_SECRET_META = "omrs-page-secret";

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

/** Reads the workspace secret from the page and removes its tag, or returns `null`. */
export function takePageSecret(doc: Document = document): string | null {
  const meta = doc.querySelector<HTMLMetaElement>(`meta[name="${PAGE_SECRET_META}"]`);
  if (meta === null) return null;
  const secret = meta.content;
  meta.remove();
  return secret === "" ? null : secret;
}

/** Posts *secret* to the session route. The secret is never logged. */
async function postSecret(secret: string, fetchImpl: FetchLike = (input, init) => fetch(input, init)): Promise<boolean> {
  try {
    const response = await fetchImpl(SESSION_PATH, {
      method: "POST",
      headers: { Accept: "application/json", "Content-Type": "application/json" },
      credentials: "same-origin",
      body: JSON.stringify({ bootstrap: secret }),
    });
    return response.ok;
  } catch {
    return false;
  }
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
  return (await postSecret(secret, options.fetchImpl)) ? "ok" : "failed";
}

/** Builds the renewer for the workspace secret. Calls made while one is in flight share it. */
export function createSessionRenewer(secret: string, fetchImpl?: FetchLike): SessionRenewal {
  let pending: Promise<boolean> | null = null;
  let signIns = 0;
  return {
    get signIns() {
      return signIns;
    },
    renew() {
      pending ??= postSecret(secret, fetchImpl).then((ok) => {
        pending = null;
        if (ok) signIns += 1;
        return ok;
      });
      return pending;
    },
  };
}

/**
 * Signs in on load: with the launch link when the address has one, else,
 * or when the link is refused, with the workspace secret.
 */
export async function startSession(renew: SessionRenewal | null, options: BootstrapOptions = {}): Promise<BootstrapOutcome> {
  const outcome = await exchangeBootstrap(options);
  if (outcome === "ok" || renew === null) return outcome;
  return (await renew.renew()) ? "ok" : "failed";
}
