/**
 * The typed route model. The address bar hash is the only source of location:
 * nothing else stores the current area, project, profile, purpose or Settings section.
 */

/** The three pipelines of a profile, in the order the tabs show them. */
export const PURPOSES = ["ingest", "search", "answer"] as const;

export type Purpose = (typeof PURPOSES)[number];

/** The Settings sections, in the order the chips show them. */
export const SETTINGS_SECTIONS = ["appearance", "providers", "chat", "mcp", "log", "runtime", "workspace"] as const;

export type SettingsSection = (typeof SETTINGS_SECTIONS)[number];

export type Route =
  | { area: "home" }
  | { area: "knowledge-base"; collection: string | null }
  | { area: "chat"; collection: string | null; chatId: string | null }
  | { area: "studio"; profileId: string | null; purpose: Purpose | null }
  | { area: "experiments"; runId: string | null }
  | { area: "integrations" }
  | { area: "settings"; section: SettingsSection | null };

export type RouteArea = Route["area"];

export const HOME: Route = { area: "home" };

function decode(segment: string): string | null {
  if (segment === "") return null;
  try {
    return decodeURIComponent(segment);
  } catch {
    return null;
  }
}

/** Parses a hash such as `#/chat/papers`. Anything that does not parse resolves to Home. */
export function parseRoute(hash: string): Route {
  if (!hash.startsWith("#/")) return HOME;
  const parts = hash.slice(2).split("/");
  const [area, first, second, ...rest] = parts;
  if (rest.length > 0) return HOME;

  switch (area) {
    case "home":
    case "integrations":
      return first === undefined ? { area } : HOME;
    case "settings": {
      if (second !== undefined) return HOME;
      if (first === undefined) return { area, section: null };
      return isSettingsSection(first) ? { area, section: first } : HOME;
    }
    case "chat": {
      if (first === undefined) return { area, collection: null, chatId: null };
      const collection = decode(first);
      if (collection === null) return HOME;
      if (second === undefined) return { area, collection, chatId: null };
      const chatId = decode(second);
      return chatId === null ? HOME : { area, collection, chatId };
    }
    case "knowledge-base": {
      if (second !== undefined) return HOME;
      if (first === undefined) return { area, collection: null };
      const collection = decode(first);
      return collection === null ? HOME : { area, collection };
    }
    case "studio": {
      if (first === undefined) return second === undefined ? { area, profileId: null, purpose: null } : HOME;
      const profileId = decode(first);
      if (profileId === null) return HOME;
      if (second === undefined) return { area, profileId, purpose: null };
      return isPurpose(second) ? { area, profileId, purpose: second } : HOME;
    }
    case "experiments": {
      if (first === undefined) return { area, runId: null };
      if (first !== "runs" || second === undefined) return HOME;
      const runId = decode(second);
      return runId === null ? HOME : { area, runId };
    }
    default:
      return HOME;
  }
}

function isPurpose(value: string): value is Purpose {
  return (PURPOSES as readonly string[]).includes(value);
}

function isSettingsSection(value: string): value is SettingsSection {
  return (SETTINGS_SECTIONS as readonly string[]).includes(value);
}

function withSegment(base: string, value: string | null): string {
  return value === null ? base : `${base}/${encodeURIComponent(value)}`;
}

/** The hash for a route, with every identifier percent-encoded. */
export function formatRoute(route: Route): string {
  switch (route.area) {
    case "home":
    case "integrations":
      return `#/${route.area}`;
    case "settings":
      return route.section === null ? "#/settings" : `#/settings/${route.section}`;
    case "knowledge-base":
      return withSegment(`#/${route.area}`, route.collection);
    case "chat":
      if (route.collection === null) return "#/chat";
      return withSegment(withSegment("#/chat", route.collection), route.chatId);
    case "studio":
      if (route.profileId === null) return "#/studio";
      return withSegment(withSegment("#/studio", route.profileId), route.purpose);
    case "experiments":
      return route.runId === null ? "#/experiments" : `#/experiments/runs/${encodeURIComponent(route.runId)}`;
  }
}
