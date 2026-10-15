import { screen, waitFor, within } from "@testing-library/react";
import { beforeAll, describe, expect, it } from "vitest";
import { json } from "./test/fakeServer";
import {
  addWithKeyboard,
  choose,
  connectWithKeyboard,
  edgeNames,
  EMPTY_PIPELINE,
  inspector,
  outline,
  palette,
  runPanel,
  savedDocument,
  TEMPLATE_PIPELINE,
  TEMPLATE_REVISION,
} from "./test/helpers";
import { mockReactFlow } from "./test/mockReactFlow";
import { openStudio } from "./test/render";

beforeAll(mockReactFlow);

/** Opens the empty pipeline `pnew`, or the saved search copy `p1`. */
function setup(options: Parameters<typeof openStudio>[1] = {}, id = "pnew") {
  const pipelines = id === "pnew" ? [EMPTY_PIPELINE] : [TEMPLATE_PIPELINE];
  return openStudio(`#/studio/${id}`, { pipelines, revisions: id === "pnew" ? [] : [TEMPLATE_REVISION], ...options });
}

describe("canvas catalogue and editing", () => {
  it("lists the catalogue and disables unavailable operations with their reasons", async () => {
    setup();
    const verify = await within(await screen.findByRole("region", { name: "Operation catalogue" })).findByRole("button", {
      name: "Add Verify claims (verify.claims)",
    });
    expect(verify).toBeDisabled();
    expect(within(palette()).getByText(/no judge model is configured/)).toBeInTheDocument();
    expect(within(palette()).getByRole("button", { name: "Add Dense retrieval (retrieve.dense)" })).toBeEnabled();
    expect(screen.getByTestId("empty-state")).toHaveTextContent(/graph is empty/);
  });

  it("puts the flow surface in the main column and the palette in the right column", async () => {
    const { view } = setup({}, "p1");
    await within(await screen.findByRole("region", { name: "Graph outline" })).findByRole("button", { name: /^Node rerank/ });
    const surface = view.container.querySelector(".react-flow");
    const columns = view.container.querySelectorAll("section > div.grid > div");
    expect(columns).toHaveLength(2);
    expect(columns[0]).toContainElement(surface as HTMLElement);
    expect(columns[1]).toContainElement(palette());
    expect(columns[1]).toContainElement(inspector());
    expect(columns[0]).not.toContainElement(palette());
  });

  it("filters the catalogue by search text", async () => {
    const { user } = setup();
    await within(await screen.findByRole("region", { name: "Operation catalogue" })).findByRole("button", { name: /retrieve\.dense/ });
    await user.type(within(palette()).getByLabelText("Search operations"), "cross-encoder");
    expect(within(palette()).getAllByRole("button").map((b) => b.getAttribute("aria-label"))).toEqual([
      "Add Cross-encoder rerank (select.rerank)",
    ]);
  });

  it("shows one friendly line with Retry when the catalogue cannot load", async () => {
    const { server, user } = setup({ failures: { "GET /v1/pipeline-operations": 500 } });
    const alert = await within(await screen.findByRole("region", { name: "Operation catalogue" })).findByRole("alert");
    expect(alert).toHaveTextContent("The local server could not complete that request.");
    expect(alert).not.toHaveTextContent("Boom");
    delete server.failures["GET /v1/pipeline-operations"];
    await user.click(within(alert).getByRole("button", { name: "Retry" }));
    expect(await within(palette()).findByRole("button", { name: "Add Dense retrieval (retrieve.dense)" })).toBeEnabled();
  });

  it("adds and connects nodes with the keyboard and saves the wiring", async () => {
    const { server, user } = setup();
    await screen.findByRole("region", { name: "Operation catalogue" });
    await addWithKeyboard(user, "Prepare query", "retrieve.prepare_query");
    await addWithKeyboard(user, "Dense retrieval", "retrieve.dense");
    await connectWithKeyboard(user, "prepare_query.query", "dense.query");
    expect(edgeNames()).toEqual(["prepare_query.query to dense.query"]);
    expect(screen.getByRole("status")).toHaveTextContent("Connected prepare_query.query to dense.query.");

    within(runPanel()).getByRole("button", { name: "Save revision" }).focus();
    await user.keyboard("{Enter}");
    await waitFor(() => expect(server.last("POST", "/v1/pipelines/pnew/revisions")).toBeDefined());
    expect(savedDocument(server.last("POST", "/v1/pipelines/pnew/revisions")).edges).toEqual([
      { source: { node: "prepare_query", port: "query" }, target: { node: "dense", port: "query" } },
    ]);
  });

  it("explains an incompatible connection and does not add it", async () => {
    const { user } = setup();
    await screen.findByRole("region", { name: "Operation catalogue" });
    await addWithKeyboard(user, "Sparse retrieval", "retrieve.sparse");
    await addWithKeyboard(user, "Threshold and top-k", "select.threshold");
    await connectWithKeyboard(user, "sparse.evidence", "threshold.evidence");
    expect(screen.getByRole("alert")).toHaveTextContent(/Cannot connect.*sparse_rank_v1/);
    expect(edgeNames()).toEqual([]);
  });

  it("deletes a selected node with Delete and a connection with Backspace", async () => {
    const { user } = setup();
    await screen.findByRole("region", { name: "Operation catalogue" });
    await addWithKeyboard(user, "Prepare query", "retrieve.prepare_query");
    await addWithKeyboard(user, "Dense retrieval", "retrieve.dense");
    await addWithKeyboard(user, "Sparse retrieval", "retrieve.sparse");
    await connectWithKeyboard(user, "prepare_query.query", "dense.query");
    await connectWithKeyboard(user, "prepare_query.query", "sparse.query");

    within(outline()).getByRole("button", { name: "Connection prepare_query.query to sparse.query" }).focus();
    await user.keyboard("{Enter}{Backspace}");
    expect(edgeNames()).toEqual(["prepare_query.query to dense.query"]);

    const dense = within(outline()).getByRole("button", { name: /^Node dense/ });
    dense.focus();
    await user.keyboard("{Enter}");
    expect(dense).toHaveAttribute("aria-pressed", "true");
    await user.keyboard("{Delete}");
    expect(within(outline()).queryByRole("button", { name: /^Node dense/ })).not.toBeInTheDocument();
    expect(edgeNames()).toEqual([]);
  });

  it("opens the settings of a node when it is selected, without leaving the page", async () => {
    const { user } = setup();
    await screen.findByRole("region", { name: "Operation catalogue" });
    expect(within(inspector()).getByText(/Select a node to edit its settings/)).toBeInTheDocument();
    await addWithKeyboard(user, "Dense retrieval", "retrieve.dense");
    expect(within(inspector()).getByRole("heading", { name: /Node dense/ })).toBeInTheDocument();
    expect(window.location.hash).toBe("#/studio/pnew");
  });

  it("rewires a saved template and saves the new connections, with layout kept apart", async () => {
    const { server, user } = setup({}, "p1");
    await within(await screen.findByRole("region", { name: "Graph outline" })).findByRole("button", { name: /^Node rerank/ });

    await user.click(within(outline()).getByRole("button", { name: "Remove connection dense.evidence to rerank.evidence" }));
    await user.click(within(outline()).getByRole("button", { name: "Remove connection rerank.evidence to select.evidence" }));
    await user.click(within(outline()).getByRole("button", { name: /^Node rerank/ }));
    await user.click(within(inspector()).getByRole("button", { name: "Remove node" }));
    await connectWithKeyboard(user, "dense.evidence", "select.evidence");
    await user.click(within(runPanel()).getByRole("button", { name: "Save revision" }));

    await waitFor(() => expect(server.last("POST", "/v1/pipelines/p1/revisions")).toBeDefined());
    const doc = savedDocument(server.last("POST", "/v1/pipelines/p1/revisions"));
    expect(doc.nodes.map((n) => n.id)).toEqual(["prepare", "dense", "select"]);
    expect(doc.edges).toEqual([
      { source: { node: "prepare", port: "query" }, target: { node: "dense", port: "query" } },
      { source: { node: "dense", port: "evidence" }, target: { node: "select", port: "evidence" } },
    ]);
    expect(doc).not.toHaveProperty("positions");
    expect(doc).not.toHaveProperty("layout");

    await user.click(within(runPanel()).getByRole("button", { name: "Save layout" }));
    await waitFor(() => expect(server.last("PUT", "/v1/pipelines/p1/layout")).toBeDefined());
    const layout = (server.last("PUT", "/v1/pipelines/p1/layout")!.body as { layout: Record<string, unknown> }).layout;
    expect(Object.keys(layout).sort()).toEqual(["positions", "selection", "title", "viewport"]);
    expect(layout.positions).toHaveProperty("dense", { x: 240, y: 0 });
    expect(server.calls.filter((c) => c.path.endsWith("/revisions") && c.method === "POST")).toHaveLength(1);
  });

  it("shows server validation issues on the matching node and port", async () => {
    const issue = { code: "incompatible_ports", message: "Score kind sparse_rank_v1 is not accepted.", node_id: "threshold", port: "evidence" };
    const { user, view } = setup({
      validate: () => json({ status: "error", message: "Invalid graph.", error_type: "validation", issues: [issue] }, 422),
    });
    await screen.findByRole("region", { name: "Operation catalogue" });
    await addWithKeyboard(user, "Threshold and top-k", "select.threshold");
    await user.click(within(runPanel()).getByRole("button", { name: "Validate" }));

    expect(await within(runPanel()).findByText(/incompatible_ports/)).toBeInTheDocument();
    const node = view.container.querySelector('.react-flow__node[data-id="threshold"]');
    expect(node).not.toBeNull();
    expect(node).toHaveTextContent("evidence: Score kind sparse_rank_v1 is not accepted.");
    expect(within(outline()).getByRole("button", { name: /^Node threshold.*1 issue/ })).toBeInTheDocument();
    expect(within(inspector()).getByText(/Score kind sparse_rank_v1 is not accepted/)).toBeInTheDocument();
    expect(screen.getByRole("alert")).toHaveTextContent("The graph has 1 issue.");
  });

  it("shows one friendly line when a save fails and keeps the draft", async () => {
    const { user } = setup({ failures: { "POST /v1/pipelines/pnew/revisions": 500 } });
    await screen.findByRole("region", { name: "Operation catalogue" });
    await addWithKeyboard(user, "Dense retrieval", "retrieve.dense");
    await user.click(within(runPanel()).getByRole("button", { name: "Save revision" }));
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("The local server could not complete that request.");
    expect(alert).not.toHaveTextContent("Boom");
    expect(within(outline()).getByRole("button", { name: /^Node dense/ })).toBeInTheDocument();
  });

  it("selects the graph profile and keeps collection inheritance by default", async () => {
    const { server, user } = setup();
    await screen.findByRole("region", { name: "Operation catalogue" });
    await addWithKeyboard(user, "Dense retrieval", "retrieve.dense");
    await user.click(within(runPanel()).getByRole("button", { name: "Save revision" }));
    await waitFor(() => expect(server.last("POST", "/v1/pipelines/pnew/revisions")).toBeDefined());
    expect(savedDocument(server.last("POST", "/v1/pipelines/pnew/revisions"))).not.toHaveProperty("profile");
    await choose(user, screen.getByLabelText("Profile"), "codebase");
    await user.click(within(runPanel()).getByRole("button", { name: "Save revision" }));
    await waitFor(() => expect(savedDocument(server.last("POST", "/v1/pipelines/pnew/revisions")).profile).toBe("codebase"));
  });
});
