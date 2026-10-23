import { createServer, type ViteDevServer } from "vite";
import { afterEach, describe, expect, it, vi } from "vitest";

const servers: ViteDevServer[] = [];

afterEach(async () => {
  await Promise.all(servers.splice(0).map((server) => server.close()));
  vi.unstubAllEnvs();
});

/** A second Vite server that stands in for the local web transport. */
async function fakeApi(): Promise<string> {
  const api = await createServer({
    configFile: false,
    logLevel: "silent",
    server: { port: 0, host: "127.0.0.1" },
    plugins: [
      {
        name: "fake-omrs-api",
        configureServer(server) {
          server.middlewares.use((request, response, next) => {
            // Without Node typings the request type has no fields.
            const url = (request as { url?: string }).url ?? "";
            if (!url.startsWith("/v1/")) return next();
            response.setHeader("content-type", "application/json");
            response.end(JSON.stringify({ path: url }));
          });
        },
      },
    ],
  });
  servers.push(api);
  await api.listen();
  return api.resolvedUrls!.local[0]!;
}

describe("dev proxy", () => {
  it("forwards /v1 requests to the local web transport instead of the dev server 404", async () => {
    vi.stubEnv("OMRS_API_URL", (await fakeApi()).replace(/\/$/, ""));
    const dev = await createServer({ configFile: "vite.config.ts", logLevel: "silent", server: { port: 0, host: "127.0.0.1" } });
    servers.push(dev);
    await dev.listen();

    const response = await fetch(`${dev.resolvedUrls!.local[0]}v1/collections?x=1`);
    expect(response.headers.get("content-type")).toContain("application/json");
    expect(await response.json()).toEqual({ path: "/v1/collections?x=1" });
  }, 20_000);

  it("defaults to the omrs web port", async () => {
    vi.stubEnv("OMRS_API_URL", "");
    const config = (await import("../../vite.config")).default;
    const resolved = typeof config === "function" ? await config({ mode: "test", command: "serve" }) : config;
    expect(resolved.server?.proxy).toMatchObject({ "/v1": { target: "http://127.0.0.1:8765" } });
  });
});
