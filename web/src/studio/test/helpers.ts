import { fireEvent, screen, within } from "@testing-library/react";
import type { UserEvent } from "@testing-library/user-event";
import { expect } from "vitest";
import type { GraphDocument, PipelineRecord, RevisionRecord } from "../../api/pipelines";
import type { ProfileDetail, StandardGraphs } from "../../api/profiles";

export function palette() {
  return screen.getByRole("region", { name: "Operations" });
}

/** Waits for the panel, opens Operations (the panel opens Pipeline settings at first) and returns its region. */
export async function findPalette() {
  const header = await screen.findByRole("button", { name: "Operations" });
  if (header.getAttribute("aria-expanded") !== "true") fireEvent.click(header);
  return screen.findByRole("region", { name: "Operations" });
}

export function outline() {
  return screen.getByRole("region", { name: "Steps and connections" });
}

/** Every panel section. The panel opens only Pipeline settings at first. */
export const ALL_SECTIONS = ["Pipeline settings", "Operations", "Steps and connections", "Connect ports", "Revision and run", "Step settings"];

/** Opens the named panel sections that are still closed, once the canvas has loaded. */
export async function openSections(user: UserEvent, ...titles: string[]) {
  for (const title of titles) {
    const header = await screen.findByRole("button", { name: title });
    if (header.getAttribute("aria-expanded") !== "true") await user.click(header);
  }
}

export const openAllSections = (user: UserEvent) => openSections(user, ...ALL_SECTIONS);

export function inspector() {
  return screen.getByRole("region", { name: "Step settings" });
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

/** A pipeline the server created for an empty graph: no revision yet. */
export const EMPTY_PIPELINE: PipelineRecord = {
  pipeline_id: "pnew",
  title: "Empty pipeline",
  current_revision_id: null,
  layout: { title: "Empty pipeline" },
  created_at: "2026-10-13T12:00:00Z",
  updated_at: "2026-10-13T12:00:00Z",
};

/** A one-step ingest graph. The catalogue fixture has no `ingest.*` operations, so `prepare.enrich` stands in. */
const INGEST_DOC: GraphDocument = {
  schema_version: 1,
  nodes: [{ id: "enrich", operation: "prepare.enrich", version: 1, params: {}, enabled: true }],
  edges: [],
  inputs: [],
  outputs: [],
  profile: null,
  collection: null,
  overrides: {},
};

const ANSWER_DOC: GraphDocument = {
  schema_version: 1,
  nodes: [{ id: "dense", operation: "retrieve.dense", version: 1, params: {}, enabled: true }],
  edges: [],
  inputs: [],
  outputs: [],
  profile: null,
  collection: null,
  overrides: {},
};

/** What `GET /v1/profiles/{built-in}` returns as `standard_graphs`. */
export const STANDARD_GRAPHS: StandardGraphs = { ingest: INGEST_DOC, search: TEMPLATE_DOC, answer: ANSWER_DOC };

const NO_SLOTS = { ingest: null, search: null, answer: null };

/** A built-in profile that one collection uses. */
export const DOCUMENTS_PROFILE: ProfileDetail = {
  profile_id: "documents",
  kind: "builtin",
  title: "Documents",
  description: "Standard settings for prose, reports and notes.",
  base_profile: "documents",
  slots: NO_SLOTS,
  ready: true,
  not_ready_reasons: [],
  used_by: ["notes"],
  standard_graphs: STANDARD_GRAPHS,
};

/** A built-in profile that no collection uses. */
export const CODEBASE_PROFILE: ProfileDetail = {
  profile_id: "codebase",
  kind: "builtin",
  title: "Codebase",
  description: "Standard settings for source code.",
  base_profile: "codebase",
  slots: NO_SLOTS,
  ready: true,
  not_ready_reasons: [],
  used_by: [],
  standard_graphs: STANDARD_GRAPHS,
};

/** The Answer pipeline of `USER_PROFILE`. Ingest is `pnew` (no revision yet) and Search is `p1`. */
export const ANSWER_PIPELINE: PipelineRecord = {
  pipeline_id: "p2",
  title: "Search copy answer",
  current_revision_id: "p2-r1",
  layout: { positions: { dense: { x: 0, y: 0 } } },
  created_at: "2026-10-13T12:00:00Z",
  updated_at: "2026-10-13T12:00:00Z",
};

export const ANSWER_REVISION: RevisionRecord = {
  revision_id: "p2-r1",
  pipeline_id: "p2",
  revision_number: 1,
  content_hash: "hash2",
  schema_version: 1,
  document: ANSWER_DOC,
  created_at: "2026-10-13T12:00:00Z",
};

/** A ready user profile whose slots are the existing fixture pipelines. One collection uses it. */
export const USER_PROFILE: ProfileDetail = {
  profile_id: "search-copy",
  kind: "user",
  title: "Search copy",
  description: "",
  base_profile: "documents",
  slots: { ingest: "pnew", search: "p1", answer: "p2" },
  ready: true,
  not_ready_reasons: [],
  used_by: ["papers"],
  standard_graphs: null,
};

/** A user profile that is not ready and that no collection uses. Its slot pipelines do not exist in the fake server. */
export const NOT_READY_PROFILE: ProfileDetail = {
  profile_id: "half-built",
  kind: "user",
  title: "Half built",
  description: "",
  base_profile: "documents",
  slots: { ingest: "hb-ingest", search: "hb-search", answer: "hb-answer" },
  ready: false,
  not_ready_reasons: ["The Search pipeline has no saved revision. Open it and save a revision."],
  used_by: [],
  standard_graphs: null,
};

/** The profiles the fake server returns when a test passes none: two built-in, two user. */
export const PROFILES: ProfileDetail[] = [DOCUMENTS_PROFILE, CODEBASE_PROFILE, USER_PROFILE, NOT_READY_PROFILE];

/** The same profiles with no collection using `search-copy`, so a save runs with no warning dialog. */
export const UNUSED_PROFILES: ProfileDetail[] = PROFILES.map((profile) => (profile.profile_id === USER_PROFILE.profile_id ? { ...profile, used_by: [] } : profile));
