import { act, screen, waitFor, within } from "@testing-library/react";
import type { UserEvent } from "@testing-library/user-event";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import type { GraphDocument, RevisionRecord, ValidationIssue } from "../api/pipelines";
import type { Connection } from "../api/settings";
import { CATALOGUE } from "./test/catalogueFixture";
import { CATALOGUE_INGEST } from "./test/catalogueIngest";
import { json } from "./test/fakeServer";
import { EMPTY_PIPELINE, inspector, openAllSections, TEMPLATE_PIPELINE, TEMPLATE_REVISION, UNUSED_PROFILES } from "./test/helpers";
import { mockReactFlow } from "./test/mockReactFlow";
import { openStudio } from "./test/render";

beforeAll(mockReactFlow);

const CHECK_PAUSE = 500;
const WAITING = "Comes from the profile. The value shows when the check finishes.";

type Options = Parameters<typeof openStudio>[1];

/** Opens the Search template pipeline (four steps) and its panel sections. */
async function open(options: Options = {}) {
  const opened = openStudio("#/studio/search-copy/search", { pipelines: [TEMPLATE_PIPELINE], revisions: [TEMPLATE_REVISION], ...options });
  await waitFor(() => expect(opened.view.container.querySelectorAll("[data-slot='op-node']")).toHaveLength(4));
  await openAllSections(opened.user);
  return opened;
}

function card(nodeId: string): HTMLElement {
  const found = document.querySelector<HTMLElement>(`.react-flow__node[data-id="${nodeId}"] [data-slot='op-node']`);
  if (found === null) throw new Error(`No canvas node ${nodeId}`);
  return found;
}

async function selectStep(user: UserEvent, nodeId: string) {
  await user.click(within(screen.getByRole("region", { name: "Steps and connections" })).getByRole("button", { name: new RegExp(`^Node ${nodeId} `) }));
}

describe("values without Validate", () => {
  it("shows the value on the card and in Step settings before the user validates", async () => {
    const { server, user } = await open();
    await waitFor(() => expect(card("prepare")).toHaveTextContent("Number of results: 10 (from profile)"));
    await selectStep(user, "prepare");
    expect(inspector()).toHaveTextContent("Value in use: 10 (from profile)");
    expect(server.calls.some((call) => call.path === "/v1/pipelines/validate" && (call.body as { inputs?: unknown }).inputs !== undefined)).toBe(false);
  });

  it("says where the value comes from while the check has not returned", async () => {
    let release: () => void = () => {};
    let held = false;
    const draftGate = () => {
      if (held) return undefined;
      held = true;
      return new Promise<void>((resolve) => {
        release = resolve;
      });
    };
    const { user } = await open({ draftGate });
    await selectStep(user, "prepare");
    expect(inspector()).toHaveTextContent(WAITING);
    expect(inspector()).not.toHaveTextContent("Value in use");
    expect(card("prepare")).toHaveTextContent("Number of results: From profile");
    await act(async () => release());
    await waitFor(() => expect(inspector()).toHaveTextContent("Value in use: 10 (from profile)"));
    expect(inspector()).not.toHaveTextContent(WAITING);
  });

  it("gives values to the other steps when the draft check refuses an incomplete graph, and leaves the issue list empty", async () => {
    const draftIssues: ValidationIssue[] = [{ code: "unconnected_port", message: "Port query of dense has no source.", node_id: "dense", port: "query" }];
    const { user } = await open({ draftIssues });
    await waitFor(() => expect(card("prepare")).toHaveTextContent("Number of results: 10 (from profile)"));
    expect(screen.queryByText(/has no source/)).not.toBeInTheDocument();
    expect(screen.queryByText("Validation issues")).not.toBeInTheDocument();
    expect(card("dense")).not.toHaveAttribute("data-invalid");
    await selectStep(user, "prepare");
    expect(inspector()).toHaveTextContent("Value in use: 10 (from profile)");
  });
});

describe("the automatic check follows the graph", () => {
  beforeEach(() => vi.useFakeTimers({ shouldAdvanceTime: true }));
  afterEach(() => vi.useRealTimers());

  const advance = (ms: number) => act(async () => void (await vi.advanceTimersByTimeAsync(ms)));
  const turnOn = (user: UserEvent) => user.click(within(inspector()).getByRole("radio", { name: "On" }));

  /** Opens the pipeline and lets the check that runs on open finish. */
  async function openChecked(options: Options = {}) {
    const opened = await open(options);
    await waitFor(() => expect(opened.server.draftChecks()).toBe(1));
    await advance(100);
    return { ...opened, initial: opened.server.draftChecks() };
  }

  it("sends one check, 500 ms after a parameter edit", async () => {
    const { server, user, initial } = await openChecked();
    expect(initial).toBe(1);
    await selectStep(user, "rerank");
    await turnOn(user);
    await advance(CHECK_PAUSE - 200);
    expect(server.draftChecks()).toBe(initial);
    await advance(400);
    await waitFor(() => expect(server.draftChecks()).toBe(initial + 1));
    await advance(CHECK_PAUSE * 2);
    expect(server.draftChecks()).toBe(initial + 1);
  });

  it("sends one check for three edits within the pause", async () => {
    const { server, user, initial } = await openChecked();
    await selectStep(user, "rerank");
    await turnOn(user);
    await user.click(within(inspector()).getByRole("radio", { name: "Off" }));
    await user.click(within(inspector()).getByRole("radio", { name: "On" }));
    await advance(CHECK_PAUSE + 100);
    await waitFor(() => expect(server.draftChecks()).toBe(initial + 1));
    await advance(CHECK_PAUSE * 2);
    expect(server.draftChecks()).toBe(initial + 1);
  });

  it("sends no check when only the selection changes, and keeps the values", async () => {
    const { server, user, initial } = await openChecked();
    await waitFor(() => expect(card("prepare")).toHaveTextContent("Number of results: 10 (from profile)"));
    await selectStep(user, "dense");
    await selectStep(user, "rerank");
    await advance(CHECK_PAUSE * 2);
    expect(server.draftChecks()).toBe(initial);
    expect(card("prepare")).toHaveTextContent("Number of results: 10 (from profile)");
  });

  it("sends no check when a step moves, and keeps the values", async () => {
    const { server, initial } = await openChecked();
    await waitFor(() => expect(card("prepare")).toHaveTextContent("Number of results: 10 (from profile)"));
    const before = card("prepare").closest<HTMLElement>(".react-flow__node")!.style.transform;
    const wrapper = card("prepare").closest<HTMLElement>(".react-flow__node")!;
    wrapper.focus();
    await act(async () => {
      wrapper.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true }));
      wrapper.dispatchEvent(new KeyboardEvent("keydown", { key: "ArrowRight", bubbles: true }));
    });
    await advance(CHECK_PAUSE * 2);
    expect(wrapper.style.transform).not.toBe(before);
    expect(server.draftChecks()).toBe(initial);
    expect(card("prepare")).toHaveTextContent("Number of results: 10 (from profile)");
  });

  it("drops the values after a graph edit until the new check returns", async () => {
    const { user } = await openChecked();
    await waitFor(() => expect(card("prepare")).toHaveTextContent("Number of results: 10 (from profile)"));
    await selectStep(user, "rerank");
    await turnOn(user);
    expect(card("prepare")).toHaveTextContent("Number of results: From profile");
    expect(card("prepare")).not.toHaveTextContent("10 (from profile)");
    await advance(CHECK_PAUSE + 100);
    await waitFor(() => expect(card("prepare")).toHaveTextContent("Number of results: 10 (from profile)"));
    expect(card("rerank")).toHaveTextContent("Reranker: On (set here)");
  });

  it("does not show the answer for an older draft", async () => {
    let release: () => void = () => {};
    let calls = 0;
    const draftGate = () => {
      calls += 1;
      if (calls > 1) return undefined;
      return new Promise<void>((resolve) => {
        release = resolve;
      });
    };
    // The answer depends on the draft: the older draft reports 10 and the edited draft reports 20.
    const validate = (body: { document: { nodes: { params?: Record<string, unknown> }[] }; inputs?: unknown }) => {
      if (body.inputs !== undefined) return undefined as unknown as Response;
      const edited = body.document.nodes.some((node) => node.params !== undefined && Object.keys(node.params).length > 0);
      const control = { lever: "retrieval.top_k", value: edited ? 20 : 10, source: "profile", detail: "documents" };
      return json({ status: "ok", valid: true, admitted: false, order: [], nodes: [{ node_id: "prepare", controls: [control] }] });
    };
    const { user } = await open({ draftGate, validate });
    await selectStep(user, "rerank");
    await turnOn(user);
    await advance(CHECK_PAUSE + 100);
    await waitFor(() => expect(card("prepare")).toHaveTextContent("Number of results: 20 (from profile)"));
    await act(async () => release());
    await advance(CHECK_PAUSE);
    expect(card("prepare")).toHaveTextContent("Number of results: 20 (from profile)");
    expect(card("prepare")).not.toHaveTextContent("10 (from profile)");
  });
});

describe("the Embed chunks card names the embedding model", () => {
  const document: GraphDocument = {
    schema_version: 1,
    nodes: [{ id: "emb1", operation: "embed.chunks", version: 1, params: {}, enabled: true }],
    edges: [],
    inputs: [],
    outputs: [],
    profile: null,
    collection: null,
    overrides: {},
  };
  const revision: RevisionRecord = {
    revision_id: "pnew-r1",
    pipeline_id: "pnew",
    revision_number: 1,
    content_hash: "hash1",
    schema_version: 1,
    document,
    created_at: "2026-10-17T12:00:00Z",
  };
  const FIXED = "(fixed for collections that already hold vectors)";

  const provider = (roles: Connection["roles"]): Connection => ({
    provider: "ollama",
    display_name: "Ollama",
    locality: "local",
    installed: true,
    install_hint: null,
    fields: [],
    read_only: [
      { label: "Embedding model", value: "nomic-embed-text" },
      { label: "Chat model", value: "qwen3" },
    ],
    roles,
  });

  async function openIngest(options: Options) {
    const opened = openStudio("#/studio/search-copy/ingest", {
      pipelines: [{ ...EMPTY_PIPELINE, current_revision_id: "pnew-r1" }],
      revisions: [revision],
      profiles: UNUSED_PROFILES,
      catalogue: [...CATALOGUE, ...CATALOGUE_INGEST],
      ...options,
    });
    await waitFor(() => expect(opened.view.container.querySelectorAll("[data-slot='op-node']")).toHaveLength(1));
    return opened;
  }

  /** Waits until the connection summary has been asked for and answered, so "unknown" is a settled state. */
  async function settled(server: { calls: { path: string }[] }) {
    await waitFor(() => expect(server.calls.some((call) => call.path === "/v1/connections")).toBe(true));
    await new Promise((resolve) => setTimeout(resolve, 50));
  }

  it("shows the model of the provider that holds the embeddings role", async () => {
    await openIngest({ connections: [provider(["embeddings", "answers"])] });
    await waitFor(() => expect(card("emb1")).toHaveTextContent(`Model: nomic-embed-text ${FIXED}`));
    expect(card("emb1")).not.toHaveTextContent("No settings");
  });

  it("says the model is unknown when the connection summary fails to load", async () => {
    const { server } = await openIngest({});
    await settled(server);
    expect(card("emb1")).toHaveTextContent(`Model: unknown ${FIXED}`);
    expect(card("emb1")).not.toHaveTextContent("nomic-embed-text");
  });

  it("says the model is unknown when no provider holds the embeddings role", async () => {
    const { server } = await openIngest({ connections: [provider(["answers"])] });
    await settled(server);
    expect(card("emb1")).toHaveTextContent(`Model: unknown ${FIXED}`);
    expect(card("emb1")).not.toHaveTextContent("nomic-embed-text");
  });
});
