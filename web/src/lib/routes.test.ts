import { describe, expect, it } from "vitest";
import { formatRoute, parseRoute, PURPOSES, SETTINGS_SECTIONS, type Route } from "./routes";

const ROUTES: { route: Route; hash: string }[] = [
  { route: { area: "home" }, hash: "#/home" },
  { route: { area: "knowledge-base", collection: null }, hash: "#/knowledge-base" },
  { route: { area: "knowledge-base", collection: "papers" }, hash: "#/knowledge-base/papers" },
  { route: { area: "chat", collection: null, chatId: null }, hash: "#/chat" },
  { route: { area: "chat", collection: "papers", chatId: null }, hash: "#/chat/papers" },
  { route: { area: "chat", collection: "papers", chatId: "c1" }, hash: "#/chat/papers/c1" },
  { route: { area: "studio", profileId: null, purpose: null }, hash: "#/studio" },
  { route: { area: "studio", profileId: "papers-search", purpose: null }, hash: "#/studio/papers-search" },
  { route: { area: "studio", profileId: "papers-search", purpose: "ingest" }, hash: "#/studio/papers-search/ingest" },
  { route: { area: "studio", profileId: "papers-search", purpose: "search" }, hash: "#/studio/papers-search/search" },
  { route: { area: "studio", profileId: "papers-search", purpose: "answer" }, hash: "#/studio/papers-search/answer" },
  { route: { area: "experiments", runId: null }, hash: "#/experiments" },
  { route: { area: "experiments", runId: "run_9" }, hash: "#/experiments/runs/run_9" },
  { route: { area: "integrations", entry: null }, hash: "#/integrations" },
  { route: { area: "integrations", entry: "anthropic" }, hash: "#/integrations/anthropic" },
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
    const route: Route = { area: "chat", collection: name, chatId: null };
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

  it("knows the three purposes and the nine Settings sections", () => {
    expect(PURPOSES).toEqual(["ingest", "search", "answer"]);
    expect(SETTINGS_SECTIONS).toEqual(["appearance", "providers", "chat", "mcp", "log", "runtime", "workspace", "document-reading", "configuration"]);
  });

  it("parses and formats the Document reading section", () => {
    expect(parseRoute("#/settings/document-reading")).toEqual({ area: "settings", section: "document-reading" });
    expect(formatRoute({ area: "settings", section: "document-reading" })).toBe("#/settings/document-reading");
  });

  it("parses the Providers and Chat sections", () => {
    expect(parseRoute("#/settings/providers")).toEqual({ area: "settings", section: "providers" });
    expect(parseRoute("#/settings/chat")).toEqual({ area: "settings", section: "chat" });
    expect(parseRoute("#/settings/connections")).toEqual({ area: "home" });
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
    "#/chat/a/b/c",
    "#/chat/a//",
    "#/chat/a/%E0%A4%A",
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

describe("integration entry in the route", () => {
  it("encodes the entry and parses it back", () => {
    const hash = formatRoute({ area: "integrations", entry: "pdf inspector" });
    expect(hash).toBe("#/integrations/pdf%20inspector");
    expect(parseRoute(hash)).toEqual({ area: "integrations", entry: "pdf inspector" });
  });

  it.each(["#/integrations/a/b", "#/integrations/%E0%A4%A"])("resolves %j to Home", (hash) => {
    expect(parseRoute(hash)).toEqual({ area: "home" });
  });
});

describe("chat id in the route", () => {
  it("encodes the chat id and keeps it out of the collection segment", () => {
    const hash = formatRoute({ area: "chat", collection: "my docs", chatId: "a/b" });
    expect(hash).toBe("#/chat/my%20docs/a%2Fb");
    expect(parseRoute(hash)).toEqual({ area: "chat", collection: "my docs", chatId: "a/b" });
  });

  it("drops the chat id when no collection is named", () => {
    expect(formatRoute({ area: "chat", collection: null, chatId: "c1" })).toBe("#/chat");
  });
});
