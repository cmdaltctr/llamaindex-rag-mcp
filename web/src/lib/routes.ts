/**
 * The typed route model. The address bar hash is the only source of location:
 * nothing else stores the current area, project or pipeline.
 */
export type Route =
  | { area: "home" }
  | { area: "knowledge-base"; collection: string | null }
  | { area: "chat"; collection: string | null }
  | { area: "studio"; pipelineId: string | null }
  | { area: "experiments"; runId: string | null }
  | { area: "integrations" }
  | { area: "settings" };

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
    case "settings":
      return first === undefined ? { area } : HOME;
    case "knowledge-base":
    case "chat": {
      if (second !== undefined) return HOME;
      if (first === undefined) return { area, collection: null };
      const collection = decode(first);
      return collection === null ? HOME : { area, collection };
    }
    case "studio": {
      if (second !== undefined) return HOME;
      if (first === undefined) return { area, pipelineId: null };
      const pipelineId = decode(first);
      return pipelineId === null ? HOME : { area, pipelineId };
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

function withSegment(base: string, value: string | null): string {
  return value === null ? base : `${base}/${encodeURIComponent(value)}`;
}

/** The hash for a route, with every identifier percent-encoded. */
export function formatRoute(route: Route): string {
  switch (route.area) {
    case "home":
    case "integrations":
    case "settings":
      return `#/${route.area}`;
    case "knowledge-base":
    case "chat":
      return withSegment(`#/${route.area}`, route.collection);
    case "studio":
      return withSegment("#/studio", route.pipelineId);
    case "experiments":
      return route.runId === null ? "#/experiments" : `#/experiments/runs/${encodeURIComponent(route.runId)}`;
  }
}
