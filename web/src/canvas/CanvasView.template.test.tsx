import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeAll, beforeEach, describe, expect, it } from "vitest";
import { CanvasView } from "./CanvasView";
import { fakeServer } from "./test/fakeServer";
import { addWithKeyboard, edgeNames, runPanel, savedDocument, TEMPLATE_DOC } from "./test/helpers";
import { mockReactFlow } from "./test/mockReactFlow";

beforeAll(mockReactFlow);
beforeEach(() => window.localStorage.clear());

const TEMPLATES = [
  {
    name: "search",
    title: "Search",
    description: "Reproduces Engine.search: prepare the query, retrieve, rerank and select.",
    standard_operation: "Engine.search",
    document: TEMPLATE_DOC,
    outputs: [{ name: "results", description: "Assembled context (ContextBundle)." }],
  },
  {
    name: "answer",
    title: "Answer",
    description: "Reproduces Engine.answer.",
    standard_operation: "Engine.answer",
    document: { schema_version: 1, nodes: [{ id: "dense", operation: "retrieve.dense" }] },
    outputs: [],
  },
];

/** `null` leaves the templates route missing (404). */
function setup(templates: unknown[] | null = TEMPLATES) {
  const server = fakeServer({ templates: templates ?? undefined });
  const user = userEvent.setup();
  render(<CanvasView fetchImpl={server.fetchImpl} />);
  return { server, user };
}

function picker() {
  return screen.getByRole("region", { name: "Start from template" });
}

describe("start from template", () => {
  it("lists the server templates with their title and description", async () => {
    setup();
    const select = await within(picker()).findByLabelText("Template");
    expect(within(select).getAllByRole("option").map((o) => o.textContent)).toEqual(["Search", "Answer"]);
    expect(within(picker()).getByText(/Reproduces Engine.search/)).toBeInTheDocument();
    expect(within(picker()).getByText(/editable starting point/)).toBeInTheDocument();
  });

  it("loads the template document into a new unsaved draft that the user can edit and save", async () => {
    const { server, user } = setup();
    await within(picker()).findByRole("option", { name: "Search" });
    await user.click(within(picker()).getByRole("button", { name: "Start from template" }));
    await waitFor(() => expect(edgeNames()).toHaveLength(3));
    expect(screen.getByLabelText("Title")).toHaveValue("Search");
    expect(screen.getByLabelText("Pipeline")).toHaveValue("");

    // Editable: add a node, then save. The saved document is the edited draft, not the template.
    await addWithKeyboard(user, "Dense retrieval", "retrieve.dense");
    await user.click(within(runPanel()).getByRole("button", { name: "Save revision" }));
    await waitFor(() => expect(server.last("POST", "/v1/pipelines/pnew/revisions")).toBeDefined());
    const saved = savedDocument(server.last("POST", "/v1/pipelines/pnew/revisions"));
    expect(saved.nodes.map((n) => n.id)).toEqual(["prepare", "dense", "rerank", "select", "dense_2"]);
    expect(saved.edges).toEqual(TEMPLATE_DOC.edges);
  });

  it("asks before it replaces unsaved work", async () => {
    const { user } = setup();
    await addWithKeyboard(user, "Dense retrieval", "retrieve.dense");
    await user.click(within(picker()).getByRole("button", { name: "Start from template" }));
    expect(within(picker()).getByText(/replaces the unsaved draft/)).toBeInTheDocument();
    await user.click(within(picker()).getByRole("button", { name: "Keep my draft" }));
    expect(edgeNames()).toHaveLength(0);

    await user.click(within(picker()).getByRole("button", { name: "Start from template" }));
    await user.click(within(picker()).getByRole("button", { name: "Replace draft" }));
    await waitFor(() => expect(edgeNames()).toHaveLength(3));
  });

  it("keeps the empty-graph start", async () => {
    setup();
    await within(picker()).findByRole("option", { name: "Search" });
    expect(screen.getByTestId("empty-state")).toHaveTextContent(/Start from an empty graph/);
  });

  it("states when the server offers no templates and still allows an empty graph", async () => {
    setup(null);
    expect(await within(picker()).findByText(/Templates are not available/)).toBeInTheDocument();
    expect(within(picker()).queryByRole("button", { name: "Start from template" })).toBeNull();
    expect(screen.getByTestId("empty-state")).toHaveTextContent(/Start from an empty graph/);
  });
});
