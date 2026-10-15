import { describe, expect, it } from "vitest";
import { formatRoute, parseRoute, type Route } from "./routes";

const ROUTES: { route: Route; hash: string }[] = [
  { route: { area: "home" }, hash: "#/home" },
  { route: { area: "knowledge-base", collection: null }, hash: "#/knowledge-base" },
  { route: { area: "knowledge-base", collection: "papers" }, hash: "#/knowledge-base/papers" },
  { route: { area: "chat", collection: null }, hash: "#/chat" },
  { route: { area: "chat", collection: "papers" }, hash: "#/chat/papers" },
  { route: { area: "studio", pipelineId: null }, hash: "#/studio" },
  { route: { area: "studio", pipelineId: "pl_123" }, hash: "#/studio/pl_123" },
  { route: { area: "experiments", runId: null }, hash: "#/experiments" },
  { route: { area: "experiments", runId: "run_9" }, hash: "#/experiments/runs/run_9" },
  { route: { area: "integrations" }, hash: "#/integrations" },
  { route: { area: "settings" }, hash: "#/settings" },
];

describe("routes", () => {
  it.each(ROUTES)("formats $hash", ({ route, hash }) => {
    expect(formatRoute(route)).toBe(hash);
  });

  it.each(ROUTES)("parses $hash", ({ route, hash }) => {
    expect(parseRoute(hash)).toEqual(route);
  });

  it.each(ROUTES)("round-trips $hash", ({ route }) => {
    expect(parseRoute(formatRoute(route))).toEqual(route);
  });

  it.each(["my notes", "a/b", "100% sure", "é ü", "a#b", "a?b", ".."])("encodes the collection name %j", (name) => {
    const route: Route = { area: "chat", collection: name };
    const hash = formatRoute(route);
    expect(hash.slice("#/chat/".length)).toBe(encodeURIComponent(name));
    expect(hash.slice("#/chat/".length)).not.toContain("/");
    expect(parseRoute(hash)).toEqual(route);
  });

  it("encodes a pipeline and a run identifier the same way", () => {
    expect(parseRoute(formatRoute({ area: "studio", pipelineId: "a b" }))).toEqual({ area: "studio", pipelineId: "a b" });
    expect(parseRoute(formatRoute({ area: "experiments", runId: "a/b" }))).toEqual({ area: "experiments", runId: "a/b" });
  });

  it.each([
    "",
    "#",
    "#/",
    "#/nope",
    "#/library",
    "#/canvas",
    "#/search",
    "#/chat//x",
    "#/chat/a/b",
    "#/home/extra",
    "#/experiments/runs",
    "#/experiments/other/x",
    "#/knowledge-base/%E0%A4%A",
    "chat",
  ])("resolves the unknown hash %j to Home", (hash) => {
    expect(parseRoute(hash)).toEqual({ area: "home" });
  });
});
