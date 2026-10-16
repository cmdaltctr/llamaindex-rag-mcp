import { screen, within } from "@testing-library/react";
import type { UserEvent } from "@testing-library/user-event";
import { expect } from "vitest";
import type { GraphDocument, PipelineRecord, RevisionRecord } from "../../api/pipelines";

export function palette() {
  return screen.getByRole("region", { name: "Operations" });
}

export function outline() {
  return screen.getByRole("region", { name: "Nodes and connections" });
}

/** Every panel section. The panel opens only Operations at first. */
export const ALL_SECTIONS = ["Pipeline settings", "Operations", "Nodes and connections", "Connect ports", "Revision and run", "Node settings"];

/** Opens the named panel sections that are still closed, once the canvas has loaded. */
export async function openSections(user: UserEvent, ...titles: string[]) {
  for (const title of titles) {
    const header = await screen.findByRole("button", { name: title });
    if (header.getAttribute("aria-expanded") !== "true") await user.click(header);
  }
}

export const openAllSections = (user: UserEvent) => openSections(user, ...ALL_SECTIONS);

export function inspector() {
  return screen.getByRole("region", { name: "Node settings" });
}

export function latestRun() {
  return within(runPanel()).getByRole("region", { name: "Latest run" });
}

export function runPanel() {
  return screen.getByRole("region", { name: "Revision and run" });
}

/** Adds an operation from the palette with the keyboard only. */
export async function addWithKeyboard(user: UserEvent, title: string, operationId: string) {
  const button = await within(palette()).findByRole("button", { name: `Add ${title} (${operationId})` });
  button.focus();
  await user.keyboard("{Enter}");
}

/** Opens a Radix select by its label and picks the option whose name matches. */
export async function choose(user: UserEvent, trigger: HTMLElement, option: string | RegExp) {
  await user.click(trigger);
  await user.click(await screen.findByRole("option", { name: option }));
}

const portName = (port: string) => new RegExp(`^${port.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")} \\(`);

/** Chooses the source port, then the target port, from the connection menus, and presses Connect with the keyboard. */
export async function connectWithKeyboard(user: UserEvent, from: string, to: string) {
  const menu = screen.getByRole("region", { name: "Connect ports" });
  await choose(user, within(menu).getByLabelText("From output"), portName(from));
  await choose(user, within(menu).getByLabelText("To input"), portName(to));
  within(menu).getByRole("button", { name: "Connect" }).focus();
  await user.keyboard("{Enter}");
}

export function edgeNames(): string[] {
  return within(outline())
    .queryAllByRole("button", { name: /^Connection / })
    .map((button) => button.getAttribute("aria-label")?.replace(/^Connection /, "") ?? "");
}

export function savedDocument(call: { body: unknown } | undefined): GraphDocument {
  expect(call).toBeDefined();
  return (call!.body as { document: GraphDocument }).document;
}

export const TEMPLATE_DOC: GraphDocument = {
  schema_version: 1,
  nodes: [
    { id: "prepare", operation: "retrieve.prepare_query", version: 1, params: {}, enabled: true },
    { id: "dense", operation: "retrieve.dense", version: 1, params: {}, enabled: true },
    { id: "rerank", operation: "select.rerank", version: 1, params: {}, enabled: true },
    { id: "select", operation: "select.threshold", version: 1, params: {}, enabled: true },
  ],
  edges: [
    { source: { node: "prepare", port: "query" }, target: { node: "dense", port: "query" } },
    { source: { node: "dense", port: "evidence" }, target: { node: "rerank", port: "evidence" } },
    { source: { node: "rerank", port: "evidence" }, target: { node: "select", port: "evidence" } },
  ],
  inputs: [{ name: "query", kind: "query", targets: [{ node: "prepare", port: "query" }], required: true }],
  outputs: [{ name: "results", source: { node: "select", port: "evidence" } }],
  profile: null,
  collection: null,
  overrides: {},
};

export const TEMPLATE_PIPELINE: PipelineRecord = {
  pipeline_id: "p1",
  title: "Search copy",
  current_revision_id: "p1-r1",
  layout: { title: "Search copy", positions: { prepare: { x: 0, y: 0 }, dense: { x: 240, y: 0 } } },
  created_at: "2026-10-13T12:00:00Z",
  updated_at: "2026-10-13T12:00:00Z",
};

export const TEMPLATE_REVISION: RevisionRecord = {
  revision_id: "p1-r1",
  pipeline_id: "p1",
  revision_number: 1,
  content_hash: "hash1",
  schema_version: 1,
  document: TEMPLATE_DOC,
  created_at: "2026-10-13T12:00:00Z",
};

export const SEARCH_TEMPLATE = {
  name: "search",
  title: "Search",
  description: "Reproduces Engine.search: prepare the query, retrieve, rerank and select.",
  standard_operation: "Engine.search",
  document: TEMPLATE_DOC,
  outputs: [{ name: "results", description: "Assembled context (ContextBundle)." }],
};

export const TEMPLATES = [
  {
    name: "ingestion",
    title: "Ingest sources",
    description: "Discover, read, prepare, embed and commit each source.",
    standard_operation: "Engine.ingest",
    document: { schema_version: 1, nodes: [{ id: "discover", operation: "ingest.discover" }] },
    outputs: [],
  },
  SEARCH_TEMPLATE,
  {
    name: "answer",
    title: "Answer",
    description: "Reproduces Engine.answer.",
    standard_operation: "Engine.answer",
    document: { schema_version: 1, nodes: [{ id: "dense", operation: "retrieve.dense" }] },
    outputs: [],
  },
];

/** A pipeline the server created for an empty graph: no revision yet. */
export const EMPTY_PIPELINE: PipelineRecord = {
  pipeline_id: "pnew",
  title: "Empty pipeline",
  current_revision_id: null,
  layout: { title: "Empty pipeline" },
  created_at: "2026-10-13T12:00:00Z",
  updated_at: "2026-10-13T12:00:00Z",
};
