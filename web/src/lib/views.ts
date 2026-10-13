/** Workspace views, in navigation order. Copy is British English. */
export const VIEW_IDS = ["canvas", "library", "search", "ask", "runs", "experiments", "settings"] as const;

export type ViewId = (typeof VIEW_IDS)[number];

export interface ViewDefinition {
  id: ViewId;
  label: string;
  summary: string;
  emptyTitle: string;
  emptyBody: string;
}

export const VIEWS: readonly ViewDefinition[] = [
  {
    id: "canvas",
    label: "Canvas",
    summary: "Connect pipeline stages, check the graph and run it.",
    emptyTitle: "No pipeline is open",
    emptyBody: "The node catalogue appears here when the local server is connected.",
  },
  {
    id: "library",
    label: "Library",
    summary: "Sources and collections in this workspace.",
    emptyTitle: "No sources to show",
    emptyBody: "Ingested sources appear here when the local server is connected.",
  },
  {
    id: "search",
    label: "Search",
    summary: "Find passages in a collection.",
    emptyTitle: "Search is not available yet",
    emptyBody: "Results appear here when the local server is connected.",
  },
  {
    id: "ask",
    label: "Ask",
    summary: "Ask a question and check the cited evidence.",
    emptyTitle: "Ask is not available yet",
    emptyBody: "Answers and their citations appear here when the local server is connected.",
  },
  {
    id: "runs",
    label: "Runs",
    summary: "Pipeline runs, their stages and their results.",
    emptyTitle: "No runs yet",
    emptyBody: "Each pipeline run is recorded here with its saved revision and events.",
  },
  {
    id: "experiments",
    label: "Experiments",
    summary: "Experiment workspaces, scoped notebook credentials and the optional notebook editor.",
    emptyTitle: "No notebook tool is registered",
    emptyBody: "Registered external tools appear here after you approve them.",
  },
  {
    id: "settings",
    label: "Settings",
    summary: "Workspace, runtime capabilities, file access and appearance.",
    emptyTitle: "No workspace settings to show",
    emptyBody: "Runtime details appear here when the local server is connected.",
  },
];

export function isViewId(value: unknown): value is ViewId {
  return typeof value === "string" && (VIEW_IDS as readonly string[]).includes(value);
}

export function viewById(id: ViewId): ViewDefinition {
  const view = VIEWS.find((candidate) => candidate.id === id);
  if (view === undefined) throw new Error(`Unknown view: ${id}`);
  return view;
}

/** Reads the view from a hash such as `#/library`. Returns null for anything else. */
export function viewFromHash(hash: string): ViewId | null {
  const candidate = hash.replace(/^#\/?/, "");
  return isViewId(candidate) ? candidate : null;
}
