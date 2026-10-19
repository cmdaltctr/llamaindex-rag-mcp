import { render, screen, waitFor } from "@testing-library/react";
import { useEffect, useState } from "react";
import { describe, expect, it, vi } from "vitest";
import { ApiProvider, useApi } from "./ApiProvider";
import type { FetchLike } from "./client";

function jsonFetch(body: unknown) {
  return vi.fn<FetchLike>(async () => new Response(JSON.stringify(body), { status: 200, headers: { "content-type": "application/json" } }));
}

function Probe() {
  const api = useApi();
  const [text, setText] = useState("loading");
  useEffect(() => {
    void api.request<{ name: string }>("GET", "/v1/health").then((body) => setText(body.name));
  }, [api]);
  return <p>{text}</p>;
}

describe("ApiProvider", () => {
  it("gives descendants a client built from the one fetch implementation", async () => {
    const fetchImpl = jsonFetch({ name: "from-fixture" });
    render(
      <ApiProvider fetchImpl={fetchImpl}>
        <Probe />
      </ApiProvider>,
    );
    await waitFor(() => expect(screen.getByText("from-fixture")).toBeInTheDocument());
    expect(fetchImpl).toHaveBeenCalledTimes(1);
  });

  it("keeps the same client across re-renders", () => {
    const seen: unknown[] = [];
    function Capture() {
      seen.push(useApi());
      return null;
    }
    const fetchImpl = jsonFetch({});
    const view = render(
      <ApiProvider fetchImpl={fetchImpl}>
        <Capture />
      </ApiProvider>,
    );
    view.rerender(
      <ApiProvider fetchImpl={fetchImpl}>
        <Capture />
      </ApiProvider>,
    );
    expect(new Set(seen).size).toBe(1);
  });

  it("falls back to the global fetch when no implementation is given", async () => {
    const original = globalThis.fetch;
    const spy = jsonFetch({ name: "global" });
    globalThis.fetch = spy as unknown as typeof fetch;
    try {
      render(
        <ApiProvider>
          <Probe />
        </ApiProvider>,
      );
      await waitFor(() => expect(screen.getByText("global")).toBeInTheDocument());
    } finally {
      globalThis.fetch = original;
    }
  });

  it("throws a clear error when used outside the provider", () => {
    const consoleError = vi.spyOn(console, "error").mockImplementation(() => undefined);
    expect(() => render(<Probe />)).toThrow(/ApiProvider/);
    consoleError.mockRestore();
  });
});
