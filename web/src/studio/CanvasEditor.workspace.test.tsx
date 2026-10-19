/**
 * Canvas state across the workspace: draft persistence, and navigation and
 * theme changes must keep the draft, the node selection and the identity of
 * the latest run (which the server holds).
 */
import { screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { FakeEventSource } from "../runs/test/fakes";
import { readDraft } from "./storage";
import { addWithKeyboard, EMPTY_PIPELINE, findPalette, inspector, latestRun, openAllSections, outline, runPanel, TEMPLATE_PIPELINE, TEMPLATE_REVISION, UNUSED_PROFILES } from "./test/helpers";
import { mockReactFlow } from "./test/mockReactFlow";
import { openStudio } from "./test/render";

beforeAll(mockReactFlow);

beforeEach(() => {
  FakeEventSource.instances = [];
  vi.stubGlobal("EventSource", FakeEventSource);
});

afterEach(() => vi.unstubAllGlobals());

const nav = () => screen.getByRole("navigation", { name: "Workspace" });
const outlineNode = (id: string) => within(outline()).getByRole("button", { name: new RegExp(`^Node ${id} `) });

type User = ReturnType<typeof openStudio>["user"];

/** Waits for the catalogue, then opens every panel section: the panel starts with Operations only. */
async function ready(user: User) {
  await within(await findPalette()).findByRole("button", { name: /retrieve\.dense/ });
  await openAllSections(user);
}

describe("draft persistence", () => {
  it("restores the unsaved draft after the page is opened again", async () => {
    const first = openStudio("#/studio/search-copy/ingest", { pipelines: [EMPTY_PIPELINE] });
    await ready(first.user);
    await addWithKeyboard(first.user, "Dense retrieval", "retrieve.dense");
    expect(readDraft("pnew")?.graph.nodes).toHaveLength(1);
    first.view.unmount();

    const second = openStudio("#/studio/search-copy/ingest", { pipelines: [EMPTY_PIPELINE] });
    await openAllSections(second.user);
    expect(await within(outline()).findByRole("button", { name: /^Node dense/ })).toBeInTheDocument();
  });

  it("keeps a separate draft for each pipeline", async () => {
    const { user } = openStudio("#/studio/search-copy/ingest", { pipelines: [EMPTY_PIPELINE, TEMPLATE_PIPELINE], revisions: [TEMPLATE_REVISION] });
    await ready(user);
    await addWithKeyboard(user, "Dense retrieval", "retrieve.dense");
    window.location.hash = "#/studio/search-copy/search";
    await openAllSections(user);
    await waitFor(() => expect(within(outline()).getByRole("button", { name: /^Node rerank/ })).toBeInTheDocument());
    expect(within(outline()).getAllByRole("button", { name: /^Node / })).toHaveLength(4);
    expect(readDraft("p1")).toBeNull();
    expect(readDraft("pnew")?.graph.nodes.map((node) => node.id)).toEqual(["dense"]);
  });

  it("does not store the server's own graph before the first change", async () => {
    const { user } = openStudio("#/studio/search-copy/search", { pipelines: [TEMPLATE_PIPELINE], revisions: [TEMPLATE_REVISION] });
    await openAllSections(user);
    await within(outline()).findByRole("button", { name: /^Node rerank/ });
    expect(readDraft("p1")).toBeNull();
  });

  it("clears the stored draft when a revision is saved", async () => {
    const { user, server } = openStudio("#/studio/search-copy/ingest", { pipelines: [EMPTY_PIPELINE], profiles: UNUSED_PROFILES });
    await ready(user);
    await addWithKeyboard(user, "Dense retrieval", "retrieve.dense");
    expect(readDraft("pnew")).not.toBeNull();
    await user.click(within(runPanel()).getByRole("button", { name: "Save revision" }));
    await waitFor(() => expect(server.last("POST", "/v1/pipelines/pnew/revisions")).toBeDefined());
    await waitFor(() => expect(readDraft("pnew")).toBeNull());
    expect(runPanel()).toHaveTextContent("The draft matches revision 1.");
  });

  it("keeps working when browser storage throws", async () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    const { user } = openStudio("#/studio/search-copy/ingest", { pipelines: [EMPTY_PIPELINE] });
    await ready(user);
    await addWithKeyboard(user, "Dense retrieval", "retrieve.dense");
    expect(within(outline()).getByRole("button", { name: /^Node dense/ })).toBeInTheDocument();
  });
});

describe("canvas state across the workspace", () => {
  it("keeps the draft, the selected node and the latest run after Studio, Experiments, Studio", async () => {
    const run = { run_id: "run1", pipeline_id: "p1", revision_id: "p1-r1", status: "queued" };
    const { user } = openStudio("#/studio/search-copy/search", { pipelines: [EMPTY_PIPELINE, TEMPLATE_PIPELINE], revisions: [TEMPLATE_REVISION], runs: [run] });
    await ready(user);
    await addWithKeyboard(user, "Dense retrieval", "retrieve.dense");
    await user.click(outlineNode("prepare"));
    expect(outlineNode("prepare")).toHaveAttribute("aria-pressed", "true");
    expect(latestRun()).toHaveTextContent("Revision 1");

    await user.click(within(nav()).getByRole("link", { name: "Experiments" }));
    expect(screen.getByRole("heading", { level: 1, name: "Experiments" })).toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "Steps and connections" })).toBeNull();
    await user.click(within(nav()).getByRole("link", { name: "Studio" }));
    await user.click(within(await screen.findByRole("group", { name: "Search copy" })).getByRole("link", { name: "Open profile" }));
    await user.click(within(await screen.findByRole("navigation", { name: "Pipelines of this profile" })).getByRole("link", { name: "Search" }));

    await openAllSections(user);
    expect(await within(outline()).findByRole("button", { name: /^Node dense_2 / })).toBeInTheDocument();
    expect(outlineNode("prepare")).toHaveAttribute("aria-pressed", "true");
    expect(outlineNode("dense_2")).toHaveAttribute("aria-pressed", "false");
    expect(await within(runPanel()).findByRole("region", { name: "Latest run" })).toHaveTextContent("Revision 1");
    expect(runPanel()).toHaveTextContent("The draft differs from revision 1.");
  });

  it("keeps canvas edits and the selection when the theme changes", async () => {
    const { user } = openStudio("#/studio/search-copy/ingest", { pipelines: [EMPTY_PIPELINE] });
    await ready(user);
    await addWithKeyboard(user, "Dense retrieval", "retrieve.dense");
    await addWithKeyboard(user, "Cross-encoder rerank", "select.rerank");
    await user.click(outlineNode("dense"));

    await user.click(within(screen.getByText("Local workspace").closest("header")!).getByRole("button", { name: "Switch to dark theme" }));
    expect(document.documentElement.dataset.theme).toBe("dark");
    await user.click(within(screen.getByText("Local workspace").closest("header")!).getByRole("button", { name: "Switch to light theme" }));
    expect(document.documentElement.dataset.theme).toBe("light");

    expect(outlineNode("dense")).toHaveAttribute("aria-pressed", "true");
    expect(outlineNode("rerank")).toHaveAttribute("aria-pressed", "false");
    expect(within(inspector()).getByRole("button", { name: "Remove step" })).toBeInTheDocument();
  });
});

describe("latest run from the server", () => {
  it("asks the server for the newest run of the open pipeline only", async () => {
    const { server, user } = openStudio("#/studio/search-copy/search", { pipelines: [TEMPLATE_PIPELINE], revisions: [TEMPLATE_REVISION], runs: [] });
    await openAllSections(user);
    await within(outline()).findByRole("button", { name: /^Node rerank/ });
    await waitFor(() => expect(server.calls.some((c) => c.path === "/v1/runs?limit=1&pipeline_id=p1")).toBe(true));
    expect(within(runPanel()).queryByRole("region", { name: "Latest run" })).toBeNull();
  });

  it("shows the run of an older revision with that revision's graph", async () => {
    const older = { ...TEMPLATE_REVISION, revision_id: "p1-r0", revision_number: 1, document: { ...TEMPLATE_REVISION.document, nodes: TEMPLATE_REVISION.document.nodes.slice(0, 2), edges: [], inputs: [], outputs: [] } };
    const current = { ...TEMPLATE_REVISION, revision_id: "p1-r1", revision_number: 2 };
    const run = { run_id: "run1", pipeline_id: "p1", revision_id: "p1-r0", status: "succeeded" };
    const { user } = openStudio("#/studio/search-copy/search", { pipelines: [TEMPLATE_PIPELINE], revisions: [older, current], runs: [run] });
    await openAllSections(user);
    await within(outline()).findByRole("button", { name: /^Node rerank/ });
    const latest = await within(runPanel()).findByRole("region", { name: "Latest run" });
    await waitFor(() => expect(latest).toHaveTextContent("Revision 1"));
    expect(latest).toHaveTextContent("p1-r0");
    await waitFor(() => expect(latest).toHaveTextContent('"id": "dense"'));
    expect(latest).not.toHaveTextContent('"id": "select"');
    expect(runPanel()).toHaveTextContent("The draft matches revision 2.");
  });

  it("leaves Revision and run closed when the latest run finished before the visit", async () => {
    const run = { run_id: "run1", pipeline_id: "p1", revision_id: "p1-r1", status: "succeeded" };
    openStudio("#/studio/search-copy/search", { pipelines: [TEMPLATE_PIPELINE], revisions: [TEMPLATE_REVISION], runs: [run] });
    await within(await findPalette()).findByRole("button", { name: /retrieve\.dense/ });
    await waitFor(() => expect(document.querySelectorAll("[data-slot='op-node']")).toHaveLength(4));
    expect(screen.getByRole("button", { name: "Revision and run" })).toHaveAttribute("aria-expanded", "false");
  });
});

describe("panel state at load", () => {
  it("opens Step settings when the restored draft has a selected node", async () => {
    const first = openStudio("#/studio/search-copy/ingest", { pipelines: [EMPTY_PIPELINE] });
    await ready(first.user);
    await addWithKeyboard(first.user, "Dense retrieval", "retrieve.dense");
    first.view.unmount();

    openStudio("#/studio/search-copy/ingest", { pipelines: [EMPTY_PIPELINE] });
    await within(await findPalette()).findByRole("button", { name: /retrieve\.dense/ });
    expect(screen.getByRole("button", { name: "Step settings" })).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByRole("button", { name: "Operations" })).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByRole("button", { name: "Steps and connections" })).toHaveAttribute("aria-expanded", "false");
  });
});

describe("canvas page heading", () => {
  it("has one level-1 heading, the pipeline title, and focus moves to it when the user enters the canvas from another area", async () => {
    // The pipeline is cached on the first visit, so the editor's own heading is on screen when the route changes.
    const { user } = openStudio("#/studio/search-copy/search", { pipelines: [TEMPLATE_PIPELINE], revisions: [TEMPLATE_REVISION] });
    await screen.findByRole("heading", { level: 1, name: "Search copy" });
    await user.click(within(nav()).getByRole("link", { name: "Experiments" }));
    expect(await screen.findByRole("heading", { level: 1, name: "Experiments" })).toBeInTheDocument();

    window.location.hash = "#/studio/search-copy/search";
    const heading = await screen.findByRole("heading", { level: 1, name: "Search copy" });
    expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);
    await waitFor(() => expect(heading).toHaveFocus());
  });
});
