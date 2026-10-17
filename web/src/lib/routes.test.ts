import { describe, expect, it } from "vitest";
import { formatRoute, parseRoute, PURPOSES, SETTINGS_SECTIONS, type Route } from "./routes";

const ROUTES: { route: Route; hash: string }[] = [
  { route: { area: "home" }, hash: "#/home" },
  { route: { area: "knowledge-base", collection: null }, hash: "#/knowledge-base" },
  { route: { area: "knowledge-base", collection: "papers" }, hash: "#/knowledge-base/papers" },
  { route: { area: "chat", collection: null }, hash: "#/chat" },
  { route: { area: "chat", collection: "papers" }, hash: "#/chat/papers" },
  { route: { area: "studio", profileId: null, purpose: null }, hash: "#/studio" },
  { route: { area: "studio", profileId: "papers-search", purpose: null }, hash: "#/studio/papers-search" },
  { route: { area: "studio", profileId: "papers-search", purpose: "ingest" }, hash: "#/studio/papers-search/ingest" },
  { route: { area: "studio", profileId: "papers-search", purpose: "search" }, hash: "#/studio/papers-search/search" },
  { route: { area: "studio", profileId: "papers-search", purpose: "answer" }, hash: "#/studio/papers-search/answer" },
  { route: { area: "experiments", runId: null }, hash: "#/experiments" },
  { route: { area: "experiments", runId: "run_9" }, hash: "#/experiments/runs/run_9" },
  { route: { area: "integrations" }, hash: "#/integrations" },
  { route: { area: "settings", section: null }, hash: "#/settings" },
  ...SETTINGS_SECTIONS.map((section) => ({ route: { area: "settings", section } as Route, hash: `#/settings/${section}` })),
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

  it("encodes a profile and a run identifier the same way", () => {
    const profile: Route = { area: "studio", profileId: "a b/c", purpose: "search" };
    expect(formatRoute(profile)).toBe("#/studio/a%20b%2Fc/search");
    expect(parseRoute(formatRoute(profile))).toEqual(profile);
    expect(parseRoute(formatRoute({ area: "experiments", runId: "a/b" }))).toEqual({ area: "experiments", runId: "a/b" });
  });

  it("knows the three purposes and today's Settings sections", () => {
    expect(PURPOSES).toEqual(["ingest", "search", "answer"]);
    expect(SETTINGS_SECTIONS).toEqual(["appearance", "connections", "mcp", "log", "runtime", "workspace"]);
  });

  it("leaves out the purpose when no profile is named", () => {
    expect(formatRoute({ area: "studio", profileId: null, purpose: "search" })).toBe("#/studio");
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
    "#/studio/papers-search/rerank",
    "#/studio/papers-search/Search",
    "#/studio/papers-search/search/extra",
    "#/studio//search",
    "#/studio/%E0%A4%A",
    "#/settings/keys",
    "#/settings/Appearance",
    "#/settings/appearance/extra",
    "#/settings//",
    "#/knowledge-base/%E0%A4%A",
    "chat",
  ])("resolves the unknown hash %j to Home", (hash) => {
    expect(parseRoute(hash)).toEqual({ area: "home" });
  });
});
