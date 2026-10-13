import { screen, within } from "@testing-library/react";
import type { UserEvent } from "@testing-library/user-event";
import { expect } from "vitest";
import type { GraphDocument, PipelineRecord, RevisionRecord } from "../../api/pipelines";

export function palette() {
  return screen.getByRole("region", { name: "Operation catalogue" });
}

export function outline() {
  return screen.getByRole("region", { name: "Graph outline" });
}

export function inspector() {
  return screen.getByRole("region", { name: "Node settings" });
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

/** Chooses the source port, then the target port, from the connection menus, and presses Connect. */
export async function connectWithKeyboard(user: UserEvent, from: string, to: string) {
  const menu = screen.getByRole("region", { name: "Connect ports" });
  await user.selectOptions(within(menu).getByLabelText("From output"), from);
  await user.selectOptions(within(menu).getByLabelText("To input"), to);
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
