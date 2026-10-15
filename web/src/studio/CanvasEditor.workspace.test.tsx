/**
 * Canvas state across the workspace: draft persistence, and navigation and
 * theme changes must keep the draft, the node selection and the identity of
 * the latest run (which the server holds).
 */
import { screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { FakeEventSource } from "../runs/test/fakes";
import { readDraft } from "./storage";
import { addWithKeyboard, choose, EMPTY_PIPELINE, inspector, latestRun, outline, runPanel, TEMPLATE_PIPELINE, TEMPLATE_REVISION } from "./test/helpers";
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

async function ready() {
  await within(await screen.findByRole("region", { name: "Operation catalogue" })).findByRole("button", { name: /retrieve\.dense/ });
}

describe("draft persistence", () => {
  it("restores the unsaved draft after the page is opened again", async () => {
    const first = openStudio("#/studio/pnew", { pipelines: [EMPTY_PIPELINE] });
    await ready();
    await addWithKeyboard(first.user, "Dense retrieval", "retrieve.dense");
    expect(readDraft("pnew")?.graph.nodes).toHaveLength(1);
    first.view.unmount();

    openStudio("#/studio/pnew", { pipelines: [EMPTY_PIPELINE] });
    expect(await within(await screen.findByRole("region", { name: "Graph outline" })).findByRole("button", { name: /^Node dense/ })).toBeInTheDocument();
  });

  it("keeps a separate draft for each pipeline", async () => {
    const { user } = openStudio("#/studio/pnew", { pipelines: [EMPTY_PIPELINE, TEMPLATE_PIPELINE], revisions: [TEMPLATE_REVISION] });
    await ready();
    await addWithKeyboard(user, "Dense retrieval", "retrieve.dense");
    window.location.hash = "#/studio/p1";
    await waitFor(() => expect(within(outline()).getByRole("button", { name: /^Node rerank/ })).toBeInTheDocument());
    expect(within(outline()).getAllByRole("button", { name: /^Node / })).toHaveLength(4);
    expect(readDraft("p1")).toBeNull();
    expect(readDraft("pnew")?.graph.nodes.map((node) => node.id)).toEqual(["dense"]);
  });

  it("does not store the server's own graph before the first change", async () => {
    openStudio("#/studio/p1", { pipelines: [TEMPLATE_PIPELINE], revisions: [TEMPLATE_REVISION] });
    await within(await screen.findByRole("region", { name: "Graph outline" })).findByRole("button", { name: /^Node rerank/ });
    expect(readDraft("p1")).toBeNull();
  });

  it("clears the stored draft when a revision is saved", async () => {
    const { user, server } = openStudio("#/studio/pnew", { pipelines: [EMPTY_PIPELINE] });
    await ready();
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
    const { user } = openStudio("#/studio/pnew", { pipelines: [EMPTY_PIPELINE] });
    await ready();
    await addWithKeyboard(user, "Dense retrieval", "retrieve.dense");
    expect(within(outline()).getByRole("button", { name: /^Node dense/ })).toBeInTheDocument();
  });
});

describe("canvas state across the workspace", () => {
  it("keeps the draft, the selected node and the latest run after Studio, Experiments, Studio", async () => {
    const run = { run_id: "run1", pipeline_id: "p1", revision_id: "p1-r1", status: "queued" };
    const { user } = openStudio("#/studio/p1", { pipelines: [TEMPLATE_PIPELINE], revisions: [TEMPLATE_REVISION], runs: [run] });
    await ready();
    await addWithKeyboard(user, "Dense retrieval", "retrieve.dense");
    await user.click(outlineNode("prepare"));
    expect(outlineNode("prepare")).toHaveAttribute("aria-pressed", "true");
    expect(latestRun()).toHaveTextContent("Revision 1");

    await user.click(within(nav()).getByRole("link", { name: "Experiments" }));
    expect(screen.getByRole("heading", { level: 1, name: "Experiments" })).toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "Graph outline" })).toBeNull();
    await user.click(within(nav()).getByRole("link", { name: "Studio" }));
    await user.click((await screen.findAllByRole("link", { name: "Open pipeline" }))[0]!);

    expect(await within(await screen.findByRole("region", { name: "Graph outline" })).findByRole("button", { name: /^Node dense_2 / })).toBeInTheDocument();
    expect(outlineNode("prepare")).toHaveAttribute("aria-pressed", "true");
    expect(outlineNode("dense_2")).toHaveAttribute("aria-pressed", "false");
    expect(await within(runPanel()).findByRole("region", { name: "Latest run" })).toHaveTextContent("Revision 1");
    expect(runPanel()).toHaveTextContent("The draft differs from revision 1.");
  });

  it("keeps canvas edits and the selection when the theme changes", async () => {
    const { user } = openStudio("#/studio/pnew", { pipelines: [EMPTY_PIPELINE] });
    await ready();
    await addWithKeyboard(user, "Dense retrieval", "retrieve.dense");
    await addWithKeyboard(user, "Cross-encoder rerank", "select.rerank");
    await user.click(outlineNode("dense"));

    await choose(user, screen.getByRole("combobox", { name: "Theme" }), "Dark");
    expect(document.documentElement.dataset.theme).toBe("dark");
    await choose(user, screen.getByRole("combobox", { name: "Theme" }), "Light");
    expect(document.documentElement.dataset.theme).toBe("light");

    expect(outlineNode("dense")).toHaveAttribute("aria-pressed", "true");
    expect(outlineNode("rerank")).toHaveAttribute("aria-pressed", "false");
    expect(within(inspector()).getByRole("button", { name: "Remove node" })).toBeInTheDocument();
  });
});

describe("latest run from the server", () => {
  it("asks the server for the newest run of the open pipeline only", async () => {
    const { server } = openStudio("#/studio/p1", { pipelines: [TEMPLATE_PIPELINE], revisions: [TEMPLATE_REVISION], runs: [] });
    await within(await screen.findByRole("region", { name: "Graph outline" })).findByRole("button", { name: /^Node rerank/ });
    await waitFor(() => expect(server.calls.some((c) => c.path === "/v1/runs?limit=1&pipeline_id=p1")).toBe(true));
    expect(within(runPanel()).queryByRole("region", { name: "Latest run" })).toBeNull();
  });

  it("shows the run of an older revision with that revision's graph", async () => {
    const older = { ...TEMPLATE_REVISION, revision_id: "p1-r0", revision_number: 1, document: { ...TEMPLATE_REVISION.document, nodes: TEMPLATE_REVISION.document.nodes.slice(0, 2), edges: [], inputs: [], outputs: [] } };
    const current = { ...TEMPLATE_REVISION, revision_id: "p1-r1", revision_number: 2 };
    const run = { run_id: "run1", pipeline_id: "p1", revision_id: "p1-r0", status: "succeeded" };
    openStudio("#/studio/p1", { pipelines: [TEMPLATE_PIPELINE], revisions: [older, current], runs: [run] });
    await within(await screen.findByRole("region", { name: "Graph outline" })).findByRole("button", { name: /^Node rerank/ });
    const latest = await within(runPanel()).findByRole("region", { name: "Latest run" });
    await waitFor(() => expect(latest).toHaveTextContent("Revision 1"));
    expect(latest).toHaveTextContent("p1-r0");
    await waitFor(() => expect(latest).toHaveTextContent('"id": "dense"'));
    expect(latest).not.toHaveTextContent('"id": "select"');
    expect(runPanel()).toHaveTextContent("The draft matches revision 2.");
  });
});
