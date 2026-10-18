import { screen, waitFor, within } from "@testing-library/react";
import type { UserEvent } from "@testing-library/user-event";
import { beforeAll, describe, expect, it } from "vitest";
import type { GraphDocument, RevisionRecord } from "../api/pipelines";
import type { ProfileDetail } from "../api/profiles";
import { CATALOGUE } from "./test/catalogueFixture";
import { CATALOGUE_INGEST } from "./test/catalogueIngest";
import { DOCUMENTS_PROFILE, EMPTY_PIPELINE, inspector, openAllSections, STANDARD_GRAPHS, UNUSED_PROFILES, USER_PROFILE } from "./test/helpers";
import { mockReactFlow } from "./test/mockReactFlow";
import { openStudio } from "./test/render";

beforeAll(mockReactFlow);

const EMBED_DOC: GraphDocument = {
  schema_version: 1,
  nodes: [{ id: "emb1", operation: "embed.chunks", version: 1, params: {}, enabled: true }],
  edges: [],
  inputs: [],
  outputs: [],
  profile: null,
  collection: null,
  overrides: {},
};

const REVISION: RevisionRecord = {
  revision_id: "pnew-r1",
  pipeline_id: "pnew",
  revision_number: 1,
  content_hash: "hash1",
  schema_version: 1,
  document: EMBED_DOC,
  created_at: "2026-10-17T12:00:00Z",
};

const CHOSEN = { provider: "onnx", model: "bge-small", source: "profile" as const, dimensions: 384 };
const UNLOCKED = { locked: false, collections: [] };

function userProfile(extra: Partial<ProfileDetail> = {}): ProfileDetail[] {
  return UNUSED_PROFILES.map((profile) => (profile.profile_id === USER_PROFILE.profile_id ? { ...profile, ...extra } : profile));
}

async function openIngest(profiles: ProfileDetail[]) {
  const opened = openStudio("#/studio/search-copy/ingest", {
    pipelines: [{ ...EMPTY_PIPELINE, current_revision_id: "pnew-r1" }],
    revisions: [REVISION],
    profiles,
    catalogue: [...CATALOGUE, ...CATALOGUE_INGEST],
  });
  await waitFor(() => expect(opened.view.container.querySelectorAll("[data-slot='op-node']")).toHaveLength(1));
  await openAllSections(opened.user);
  return opened;
}

function card(): HTMLElement {
  return document.querySelector<HTMLElement>(`.react-flow__node[data-id="emb1"] [data-slot='op-node']`)!;
}

async function selectEmbed(user: UserEvent) {
  await user.click(within(screen.getByRole("region", { name: "Steps and connections" })).getByRole("button", { name: /^Node emb1 / }));
}

describe("the Embed chunks step and the profile embedding model", () => {
  it("shows the model controls in Step settings for a user profile", async () => {
    const { user } = await openIngest(userProfile({ embedding: CHOSEN, embedding_lock: UNLOCKED }));
    await selectEmbed(user);
    expect(await within(inspector()).findByRole("button", { name: "Check model" })).toBeInTheDocument();
    expect(within(inspector()).getByRole("textbox", { name: "Model" })).toHaveValue("bge-small");
  });

  it("shows the lock text instead of the controls when the profile is locked", async () => {
    const lock = { locked: true, collections: [{ collection: "papers", provider: "onnx", model: "bge-small", chunk_count: 4 }] };
    const { user } = await openIngest(userProfile({ embedding: CHOSEN, embedding_lock: lock }));
    await selectEmbed(user);
    expect(await within(inspector()).findByText(/^Locked: papers already holds vectors made with bge-small\./)).toBeInTheDocument();
    expect(within(inspector()).queryByRole("button", { name: "Check model" })).not.toBeInTheDocument();
  });

  it("gives the card line the effective model of the profile", async () => {
    await openIngest(userProfile({ embedding: CHOSEN, embedding_lock: UNLOCKED }));
    await waitFor(() => expect(card()).toHaveTextContent("Model: bge-small"));
  });

  it("shows the server default as read-only text for a built-in profile", async () => {
    const builtin: ProfileDetail = {
      ...DOCUMENTS_PROFILE,
      embedding: { provider: "ollama", model: "nomic-embed-text", source: "server_default", dimensions: null },
      embedding_lock: UNLOCKED,
      standard_graphs: { ...STANDARD_GRAPHS, ingest: EMBED_DOC },
    };
    const opened = openStudio("#/studio/documents/ingest", { profiles: [builtin], catalogue: [...CATALOGUE, ...CATALOGUE_INGEST] });
    await waitFor(() => expect(opened.view.container.querySelectorAll("[data-slot='op-node']")).toHaveLength(1));
    await openAllSections(opened.user);
    await selectEmbed(opened.user);
    expect(await within(inspector()).findByText(/server default, read-only/)).toBeInTheDocument();
    expect(within(inspector()).queryByRole("button", { name: "Check model" })).not.toBeInTheDocument();
  });
});
