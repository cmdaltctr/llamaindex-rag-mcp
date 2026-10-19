import { describe, expect, it, vi } from "vitest";
import { exchangeBootstrap, takeBootstrapSecret } from "./bootstrap";

const SECRET = "omrg_bs_abc123";

function okFetch(status = 200) {
  return vi.fn(async () => new Response('{"status":"ok"}', { status, headers: { "content-type": "application/json" } }));
}

describe("bootstrap exchange", () => {
  it("removes the secret from the address before it posts it", async () => {
    window.history.replaceState({ view: "library" }, "", `/library?tab=1#bootstrap=${SECRET}`);
    let hashAtPost: string | null = null;
    const fetchImpl = vi.fn(async () => {
      hashAtPost = window.location.hash;
      return new Response("{}", { status: 200, headers: { "content-type": "application/json" } });
    });

    await expect(exchangeBootstrap({ fetchImpl })).resolves.toBe("ok");

    expect(hashAtPost).toBe("");
    expect(window.location.pathname + window.location.search).toBe("/library?tab=1");
    expect(window.location.href).not.toContain(SECRET);
    expect(window.history.state).toEqual({ view: "library" });
    expect(fetchImpl).toHaveBeenCalledTimes(1);
    expect(fetchImpl).toHaveBeenCalledWith(
      "/v1/session",
      expect.objectContaining({
        method: "POST",
        credentials: "same-origin",
        body: JSON.stringify({ bootstrap: SECRET }),
        headers: expect.objectContaining({ "Content-Type": "application/json" }),
      }),
    );
  });

  it("keeps other fragment values", () => {
    window.history.replaceState(null, "", `/#view=canvas&bootstrap=${SECRET}`);
    expect(takeBootstrapSecret(window.location, window.history)).toBe(SECRET);
    expect(window.location.hash).toBe("#view=canvas");
  });

  it("does nothing without a bootstrap fragment", async () => {
    window.history.replaceState(null, "", "/#view=canvas");
    const fetchImpl = okFetch();
    await expect(exchangeBootstrap({ fetchImpl })).resolves.toBe("none");
    expect(fetchImpl).not.toHaveBeenCalled();
    expect(window.location.hash).toBe("#view=canvas");
  });

  it("reports a refused or unreachable exchange and still clears the secret", async () => {
    window.history.replaceState(null, "", `/#bootstrap=${SECRET}`);
    await expect(exchangeBootstrap({ fetchImpl: okFetch(403) })).resolves.toBe("failed");
    expect(window.location.href).not.toContain(SECRET);

    window.history.replaceState(null, "", `/#bootstrap=${SECRET}`);
    const offline = vi.fn(async () => {
      throw new TypeError("Failed to fetch");
    });
    await expect(exchangeBootstrap({ fetchImpl: offline })).resolves.toBe("failed");
    expect(window.location.href).not.toContain(SECRET);
  });

  it("treats an empty secret as absent", async () => {
    window.history.replaceState(null, "", "/#bootstrap=");
    const fetchImpl = okFetch();
    await expect(exchangeBootstrap({ fetchImpl })).resolves.toBe("none");
    expect(fetchImpl).not.toHaveBeenCalled();
    expect(window.location.hash).toBe("");
  });
});
