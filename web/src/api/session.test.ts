import { afterEach, describe, expect, it, vi } from "vitest";
import { createSessionRenewer, startSession, takePageSecret } from "./bootstrap";
import { ApiError, createApiClient, type FetchLike } from "./client";

const PAGE_SECRET = "omrg_bs_page123";
const LINK_SECRET = "omrg_bs_link456";

function json(status: number, body: unknown = { status: status < 400 ? "ok" : "error" }) {
  return new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });
}

function addMeta(content: string) {
  const meta = document.createElement("meta");
  meta.name = "omrg-page-secret";
  meta.content = content;
  document.head.append(meta);
}

/** A fake server: `/v1/session` POST signs in; other paths answer 401 until then. */
function fakeServer(options: { acceptSecret?: string | null } = {}) {
  const accept = options.acceptSecret === undefined ? PAGE_SECRET : options.acceptSecret;
  let signedIn = false;
  const fetchImpl = vi.fn<FetchLike>(async (input, init) => {
    if (input === "/v1/session" && init?.method === "POST") {
      const body = JSON.parse(String(init.body)) as { bootstrap: string };
      signedIn = accept !== null && body.bootstrap === accept;
      return json(signedIn ? 200 : 401);
    }
    return signedIn ? json(200, { name: "ok" }) : json(401);
  });
  return {
    fetchImpl,
    restart: () => {
      signedIn = false;
    },
    posts: () => fetchImpl.mock.calls.filter(([input, init]) => input === "/v1/session" && init?.method === "POST"),
  };
}

afterEach(() => {
  document.head.querySelectorAll('meta[name="omrg-page-secret"]').forEach((meta) => meta.remove());
  window.history.replaceState(null, "", "/");
});

describe("page secret", () => {
  it("reads the secret from the page and removes the tag", () => {
    addMeta(PAGE_SECRET);
    expect(takePageSecret(document)).toBe(PAGE_SECRET);
    expect(document.querySelector('meta[name="omrg-page-secret"]')).toBeNull();
    expect(takePageSecret(document)).toBeNull();
  });

  it("treats a missing or empty tag as no secret", () => {
    expect(takePageSecret(document)).toBeNull();
    addMeta("");
    expect(takePageSecret(document)).toBeNull();
  });
});

describe("session renewal", () => {
  it("posts the page secret to the session route", async () => {
    const server = fakeServer();
    await expect(createSessionRenewer(PAGE_SECRET, server.fetchImpl).renew()).resolves.toBe(true);
    expect(server.fetchImpl).toHaveBeenCalledWith(
      "/v1/session",
      expect.objectContaining({ method: "POST", credentials: "same-origin", body: JSON.stringify({ bootstrap: PAGE_SECRET }) }),
    );
  });

  it("shares one request between calls made at the same time", async () => {
    const server = fakeServer();
    const renewer = createSessionRenewer(PAGE_SECRET, server.fetchImpl);
    await expect(Promise.all([renewer.renew(), renewer.renew(), renewer.renew()])).resolves.toEqual([true, true, true]);
    expect(server.posts()).toHaveLength(1);
    expect(renewer.signIns).toBe(1);
    await renewer.renew();
    expect(server.posts()).toHaveLength(2);
    expect(renewer.signIns).toBe(2);
  });

  it("reports a refused or unreachable sign-in as false", async () => {
    const refused = createSessionRenewer(PAGE_SECRET, fakeServer({ acceptSecret: null }).fetchImpl);
    await expect(refused.renew()).resolves.toBe(false);
    expect(refused.signIns).toBe(0);
    const offline = vi.fn<FetchLike>(async () => {
      throw new TypeError("Failed to fetch");
    });
    await expect(createSessionRenewer(PAGE_SECRET, offline).renew()).resolves.toBe(false);
  });
});

describe("start of the page", () => {
  it("signs in with the page secret when the address has no launch link", async () => {
    const server = fakeServer();
    await expect(startSession(createSessionRenewer(PAGE_SECRET, server.fetchImpl), { fetchImpl: server.fetchImpl })).resolves.toBe("ok");
    expect(server.posts()).toHaveLength(1);
  });

  it("uses a launch link first and does not post the page secret after it worked", async () => {
    window.history.replaceState(null, "", `/#bootstrap=${LINK_SECRET}`);
    const server = fakeServer({ acceptSecret: LINK_SECRET });
    await expect(startSession(createSessionRenewer(PAGE_SECRET, server.fetchImpl), { fetchImpl: server.fetchImpl })).resolves.toBe("ok");
    expect(server.posts()).toHaveLength(1);
    expect(window.location.href).not.toContain(LINK_SECRET);
  });

  it("falls back to the page secret when an old launch link is refused", async () => {
    window.history.replaceState(null, "", `/#bootstrap=${LINK_SECRET}`);
    const server = fakeServer();
    await expect(startSession(createSessionRenewer(PAGE_SECRET, server.fetchImpl), { fetchImpl: server.fetchImpl })).resolves.toBe("ok");
    expect(server.posts()).toHaveLength(2);
  });

  it("keeps the old behaviour when the page has no secret", async () => {
    const server = fakeServer();
    await expect(startSession(null, { fetchImpl: server.fetchImpl })).resolves.toBe("none");
    expect(server.posts()).toHaveLength(0);
  });
});

describe("api client after a server restart", () => {
  it("signs in again once on a 401 and retries the request", async () => {
    const server = fakeServer();
    const api = createApiClient(server.fetchImpl, createSessionRenewer(PAGE_SECRET, server.fetchImpl));

    await expect(api.request("GET", "/v1/collections")).resolves.toEqual({ name: "ok" });
    expect(server.posts()).toHaveLength(1);

    server.restart();
    await expect(api.request("POST", "/v1/collections", { body: { name: "x" } })).resolves.toEqual({ name: "ok" });
    expect(server.posts()).toHaveLength(2);
    const retried = server.fetchImpl.mock.calls.filter(([input]) => input === "/v1/collections");
    // GET refused, GET retried, POST refused, POST retried.
    expect(retried).toHaveLength(4);
    expect(retried[3]?.[1]).toEqual(expect.objectContaining({ method: "POST", body: JSON.stringify({ name: "x" }) }));
  });

  it("shares one sign-in between requests that fail together", async () => {
    const server = fakeServer();
    const api = createApiClient(server.fetchImpl, createSessionRenewer(PAGE_SECRET, server.fetchImpl));
    await Promise.all([api.request("GET", "/v1/a"), api.request("GET", "/v1/b"), api.request("GET", "/v1/c")]);
    expect(server.posts()).toHaveLength(1);
  });

  it("does not sign in twice when a late 401 arrives after a sign-in finished", async () => {
    // Seen in a real browser: requests sent with the old cookie got their 401
    // after the first sign-in had finished, and each started another one.
    const server = fakeServer();
    let releaseLate!: () => void;
    const held = new Promise<void>((resolve) => {
      releaseLate = resolve;
    });
    let lateSent = false;
    const fetchImpl = vi.fn<FetchLike>(async (input, init) => {
      if (input === "/v1/late" && !lateSent) {
        lateSent = true;
        const refused = await server.fetchImpl(input, init);
        await held;
        return refused;
      }
      return server.fetchImpl(input, init);
    });
    const api = createApiClient(fetchImpl, createSessionRenewer(PAGE_SECRET, fetchImpl));

    const late = api.request("GET", "/v1/late");
    await expect(api.request("GET", "/v1/early")).resolves.toEqual({ name: "ok" });
    releaseLate();

    await expect(late).resolves.toEqual({ name: "ok" });
    expect(server.posts()).toHaveLength(1);
  });

  it("retries only once and then reports the 401", async () => {
    const server = fakeServer({ acceptSecret: null });
    const api = createApiClient(server.fetchImpl, createSessionRenewer(PAGE_SECRET, server.fetchImpl));
    const error = await api.request("GET", "/v1/collections").catch((caught: unknown) => caught);
    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).status).toBe(401);
    expect(server.posts()).toHaveLength(1);
    expect(server.fetchImpl.mock.calls.filter(([input]) => input === "/v1/collections")).toHaveLength(1);
  });

  it("does not sign in again for other failures", async () => {
    const fetchImpl = vi.fn<FetchLike>(async () => json(403));
    const renew = vi.fn(async () => true);
    const api = createApiClient(fetchImpl, { signIns: 0, renew });
    await expect(api.request("GET", "/v1/collections")).rejects.toBeInstanceOf(ApiError);
    expect(renew).not.toHaveBeenCalled();
    expect(fetchImpl).toHaveBeenCalledTimes(1);
  });

  it("reports a 401 without a renewer, as before", async () => {
    const fetchImpl = vi.fn<FetchLike>(async () => json(401));
    const api = createApiClient(fetchImpl);
    await expect(api.request("GET", "/v1/collections")).rejects.toMatchObject({ status: 401 });
    expect(fetchImpl).toHaveBeenCalledTimes(1);
  });
});
