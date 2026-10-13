import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeAll, describe, expect, it } from "vitest";
import { CanvasView } from "./CanvasView";
import { fakeServer, json } from "./test/fakeServer";
import {
  addWithKeyboard,
  connectWithKeyboard,
  edgeNames,
  inspector,
  outline,
  palette,
  runPanel,
  savedDocument,
  TEMPLATE_PIPELINE,
  TEMPLATE_REVISION,
} from "./test/helpers";
import { mockReactFlow } from "./test/mockReactFlow";

beforeAll(mockReactFlow);

function setup(options: Parameters<typeof fakeServer>[0] = {}) {
  const server = fakeServer(options);
  const user = userEvent.setup();
  const view = render(<CanvasView fetchImpl={server.fetchImpl} />);
  return { server, user, view };
}

describe("canvas catalogue and editing", () => {
  it("lists the catalogue and disables unavailable operations with their reasons", async () => {
    setup();
    const verify = await within(palette()).findByRole("button", { name: "Add Verify claims (verify.claims)" });
    expect(verify).toBeDisabled();
    expect(within(palette()).getByText(/no judge model is configured/)).toBeInTheDocument();
    expect(within(palette()).getByRole("button", { name: "Add Dense retrieval (retrieve.dense)" })).toBeEnabled();
    expect(screen.getByTestId("empty-state")).toHaveTextContent(/empty graph/);
    expect(await screen.findByText(/Templates are not available/)).toBeInTheDocument();
  });

  it("filters the catalogue by search text", async () => {
    const { user } = setup();
    await within(palette()).findByRole("button", { name: /retrieve\.dense/ });
    await user.type(within(palette()).getByLabelText("Search operations"), "cross-encoder");
    expect(within(palette()).getAllByRole("button").map((b) => b.getAttribute("aria-label"))).toEqual([
      "Add Cross-encoder rerank (select.rerank)",
    ]);
  });

  it("adds and connects nodes with the keyboard and saves the wiring", async () => {
    const { server, user } = setup();
    await addWithKeyboard(user, "Prepare query", "retrieve.prepare_query");
    await addWithKeyboard(user, "Dense retrieval", "retrieve.dense");
    await connectWithKeyboard(user, "prepare_query::query", "dense::query");
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
    await addWithKeyboard(user, "Sparse retrieval", "retrieve.sparse");
    await addWithKeyboard(user, "Threshold and top-k", "select.threshold");
    await connectWithKeyboard(user, "sparse::evidence", "threshold::evidence");
    expect(screen.getByRole("alert")).toHaveTextContent(/Cannot connect.*sparse_rank_v1/);
    expect(edgeNames()).toEqual([]);
  });

  it("deletes a selected node with Delete and a connection with Backspace", async () => {
    const { user } = setup();
    await addWithKeyboard(user, "Prepare query", "retrieve.prepare_query");
    await addWithKeyboard(user, "Dense retrieval", "retrieve.dense");
    await addWithKeyboard(user, "Sparse retrieval", "retrieve.sparse");
    await connectWithKeyboard(user, "prepare_query::query", "dense::query");
    await connectWithKeyboard(user, "prepare_query::query", "sparse::query");

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

  it("rewires a saved template and saves the new connections, with layout kept apart", async () => {
    const { server, user } = setup({ pipelines: [TEMPLATE_PIPELINE], revisions: [TEMPLATE_REVISION] });
    await user.selectOptions(await screen.findByLabelText("Pipeline"), "p1");
    await within(outline()).findByRole("button", { name: /^Node rerank/ });

    await user.click(within(outline()).getByRole("button", { name: "Remove connection dense.evidence to rerank.evidence" }));
    await user.click(within(outline()).getByRole("button", { name: "Remove connection rerank.evidence to select.evidence" }));
    await user.click(within(outline()).getByRole("button", { name: /^Node rerank/ }));
    await user.click(within(inspector()).getByRole("button", { name: "Remove node" }));
    await connectWithKeyboard(user, "dense::evidence", "select::evidence");
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
    expect(server.calls.filter((c) => c.path.endsWith("/revisions"))).toHaveLength(1);
  });

  it("shows server validation issues on the matching node and port", async () => {
    const issue = { code: "incompatible_ports", message: "Score kind sparse_rank_v1 is not accepted.", node_id: "threshold", port: "evidence" };
    const { user, view } = setup({
      validate: () => json({ status: "error", message: "Invalid graph.", error_type: "validation", issues: [issue] }, 422),
    });
    await addWithKeyboard(user, "Threshold and top-k", "select.threshold");
    await user.click(within(runPanel()).getByRole("button", { name: "Validate" }));

    expect(await within(runPanel()).findByText(/incompatible_ports/)).toBeInTheDocument();
    const node = view.container.querySelector('.react-flow__node[data-id="threshold"]');
    expect(node).not.toBeNull();
    expect(node).toHaveTextContent("evidence: Score kind sparse_rank_v1 is not accepted.");
    expect(within(outline()).getByRole("button", { name: /^Node threshold.*1 issue/ })).toBeInTheDocument();
    expect(within(inspector()).getByText(/Score kind sparse_rank_v1 is not accepted/)).toBeInTheDocument();
  });

  it("restores the unsaved draft after the view is closed and opened again", async () => {
    const first = setup();
    await addWithKeyboard(first.user, "Dense retrieval", "retrieve.dense");
    first.view.unmount();

    setup();
    expect(await within(outline()).findByRole("button", { name: /^Node dense/ })).toBeInTheDocument();
  });
});
