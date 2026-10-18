import { cleanup, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { beforeAll, describe, expect, it } from "vitest";
import { json } from "./test/fakeServer";
import {
  addWithKeyboard,
  connectWithKeyboard,
  edgeNames,
  EMPTY_PIPELINE,
  inspector,
  openAllSections,
  openSections,
  outline,
  palette,
  runPanel,
  savedDocument,
  TEMPLATE_PIPELINE,
  TEMPLATE_REVISION,
  UNUSED_PROFILES, findPalette } from "./test/helpers";
import { mockReactFlow } from "./test/mockReactFlow";
import { openStudio } from "./test/render";

beforeAll(mockReactFlow);

/** Opens the empty pipeline `pnew`, or the saved search copy `p1`. */
function setup(options: Parameters<typeof openStudio>[1] = {}, id = "pnew") {
  const pipelines = id === "pnew" ? [EMPTY_PIPELINE] : [TEMPLATE_PIPELINE];
  return openStudio(`#/studio/search-copy/${id === "pnew" ? "ingest" : "search"}`, { pipelines, revisions: id === "pnew" ? [] : [TEMPLATE_REVISION], profiles: UNUSED_PROFILES, ...options });
}

describe("canvas catalogue and editing", () => {
  it("lists the catalogue and disables unavailable operations with their reasons", async () => {
    setup();
    const verify = await within(await findPalette()).findByRole("button", {
      name: "Add Verify claims (verify.claims)",
    });
    expect(verify).toBeDisabled();
    expect(within(palette()).getByText(/no judge model is configured/)).toBeInTheDocument();
    expect(within(palette()).getByRole("button", { name: "Add Dense retrieval (retrieve.dense)" })).toBeEnabled();
    expect(screen.getByTestId("empty-state")).toHaveTextContent(/graph is empty/);
  });

  describe("hideable header", () => {
    const INTRO_START = /^Build your own profile\./;

    async function opened() {
      const result = setup({}, "pnew");
      await screen.findByRole("button", { name: "Operations" });
      return result;
    }

    const intro = () => screen.getByText(INTRO_START);
    const tabs = () => screen.getByRole("navigation", { name: "Pipelines of this profile" });

    it("starts shown, with one toggle that reports it is expanded", async () => {
      await opened();
      expect(screen.getByRole("button", { name: "Hide header" })).toHaveAttribute("aria-expanded", "true");
      expect(intro().closest("[inert]")).toBeNull();
      expect(tabs().closest("[inert]")).toBeNull();
    });

    it("hides only the intro line and the tabs, and the toggle keeps its place and its focus", async () => {
      const { user } = await opened();
      const toggle = screen.getByRole("button", { name: "Hide header" });
      await user.click(toggle);
      const hidden = screen.getByRole("button", { name: "Show header" });
      expect(hidden).toBe(toggle);
      expect(hidden).toHaveAttribute("aria-expanded", "false");
      expect(hidden).toHaveFocus();
      expect(intro().closest("[inert]")).not.toBeNull();
      expect(tabs().closest("[inert]")).not.toBeNull();
      expect(screen.getByRole("heading", { level: 1 }).closest("[inert]")).toBeNull();
      expect(screen.getByRole("link", { name: "All profiles" }).closest("[inert]")).toBeNull();
      expect(document.querySelector("[data-slot='header-strip']")).toBeNull();
    });

    it("shows them again with the same toggle", async () => {
      const { user } = await opened();
      const toggle = screen.getByRole("button", { name: "Hide header" });
      await user.click(toggle);
      await user.click(screen.getByRole("button", { name: "Show header" }));
      expect(screen.getByRole("button", { name: "Hide header" })).toBe(toggle);
      expect(toggle).toHaveFocus();
      expect(intro().closest("[inert]")).toBeNull();
      expect(tabs().closest("[inert]")).toBeNull();
    });

    it("clips the hidden part with no padding on the clipped element, so nothing peeks out", async () => {
      await opened();
      const clipped = intro().closest(".overflow-hidden") as HTMLElement;
      expect(clipped).not.toBeNull();
      expect(clipped.className).toMatch(/min-h-0/);
      expect(clipped.className).not.toMatch(/(^|\s)(p|px|py|pt|pb)-\d/);
    });

    it("keeps a notice visible while the header is hidden", async () => {
      const { user } = await opened();
      await user.click(screen.getByRole("button", { name: "Hide header" }));
      await openAllSections(user);
      await addWithKeyboard(user, "Dense retrieval", "retrieve.dense");
      const notice = await screen.findByText(/Added node dense/);
      expect(notice).toBeVisible();
      expect(notice.closest("[inert]")).toBeNull();
    });

    it("starts shown again on a new visit", async () => {
      const { user, view } = await opened();
      await user.click(screen.getByRole("button", { name: "Hide header" }));
      view.unmount();
      cleanup();
      await opened();
      expect(screen.getByRole("button", { name: "Hide header" })).toBeInTheDocument();
    });
  });

  describe("intro line", () => {
    const INTRO =
      "Build your own profile. Click a step to change it in Step settings. Drag from one port to another to connect steps, or use Connect ports.";

    async function expectIntroAboveTabs(user: Awaited<ReturnType<typeof setup>>["user"]) {
      const heading = await screen.findByRole("heading", { level: 1 });
      await screen.findByRole("button", { name: "Operations" });
      const intro = screen.getByText(INTRO);
      const tabs = screen.getByRole("navigation", { name: "Pipelines of this profile" });
      expect(heading.compareDocumentPosition(intro) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
      expect(intro.compareDocumentPosition(tabs) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
      expect(intro.closest(".react-flow")).toBeNull();
      expect(intro.closest("[data-slot='op-node']")).toBeNull();
      expect(intro.closest("[data-slot='info-popover-content']")).toBeNull();
      expect(intro).toHaveClass("py-1");
      await user.click(screen.getByRole("button", { name: "About the Ingest pipeline" }));
      expect(screen.getAllByText(INTRO)).toHaveLength(1);
    }

    it("shows once above the tabs for an empty pipeline, with the new empty state", async () => {
      const { user } = setup();
      await expectIntroAboveTabs(user);
      expect(await screen.findByTestId("empty-state")).toHaveTextContent("The graph is empty. Add a step from Operations to start.");
    });

    it("shows once above the tabs for a pipeline with steps, outside the flow surface", async () => {
      const { view, user } = setup({}, "p1");
      await waitFor(() => expect(view.container.querySelectorAll("[data-slot='op-node']")).toHaveLength(4));
      await expectIntroAboveTabs(user);
      expect(screen.queryByTestId("empty-state")).not.toBeInTheDocument();
    });
  });

  it("fills the main area with the flow surface and puts every control in one floating panel", async () => {
    const { view, user } = setup({}, "p1");
    await openAllSections(user);
    const surface = view.container.querySelector(".react-flow") as HTMLElement;
    const panel = screen.getByRole("complementary", { name: "Canvas panel" });
    expect(surface).not.toBeNull();
    expect(panel).not.toContainElement(surface);
    const regions = ["Pipeline settings", "Operations", "Steps and connections", "Connect ports", "Revision and run", "Step settings"];
    for (const name of regions) expect(panel).toContainElement(screen.getByRole("region", { name }));
    expect(view.container.querySelectorAll("[data-slot='card']")).toHaveLength(0);
  });

  it("filters the catalogue by search text", async () => {
    const { user } = setup();
    await within(await findPalette()).findByRole("button", { name: /retrieve\.dense/ });
    await user.type(within(palette()).getByLabelText("Search operations"), "cross-encoder");
    expect(within(palette()).getAllByRole("button").map((b) => b.getAttribute("aria-label"))).toEqual([
      "Add Cross-encoder rerank (select.rerank)",
    ]);
  });

  it("shows one friendly line with Retry when the catalogue cannot load", async () => {
    const { server, user } = setup({ failures: { "GET /v1/pipeline-operations": 500 } });
    const alert = await within(await findPalette()).findByRole("alert");
    expect(alert).toHaveTextContent("The local server could not complete that request.");
    expect(alert).not.toHaveTextContent("Boom");
    delete server.failures["GET /v1/pipeline-operations"];
    await user.click(within(alert).getByRole("button", { name: "Retry" }));
    expect(await within(palette()).findByRole("button", { name: "Add Dense retrieval (retrieve.dense)" })).toBeEnabled();
  });

  it("adds and connects nodes with the keyboard and saves the wiring", async () => {
    const { server, user } = setup();
    await findPalette();
    await openAllSections(user);
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
    await findPalette();
    await openAllSections(user);
    await addWithKeyboard(user, "Sparse retrieval", "retrieve.sparse");
    await addWithKeyboard(user, "Threshold and top-k", "select.threshold");
    await connectWithKeyboard(user, "sparse.evidence", "threshold.evidence");
    expect(screen.getByRole("alert")).toHaveTextContent(/Cannot connect.*sparse_rank_v1/);
    expect(edgeNames()).toEqual([]);
  });

  it("deletes a selected node with Delete and a connection with Backspace", async () => {
    const { user } = setup();
    await findPalette();
    await openAllSections(user);
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
    await findPalette();
    await openSections(user, "Step settings");
    expect(within(inspector()).getByText(/Select a step to edit its settings/)).toBeInTheDocument();
    await addWithKeyboard(user, "Dense retrieval", "retrieve.dense");
    expect(within(inspector()).getByRole("heading", { name: "Dense retrieval" })).toBeInTheDocument();
    expect(window.location.hash).toBe("#/studio/search-copy/ingest");
  });

  it("opens Step settings by itself when a node is added", async () => {
    const { user } = setup();
    await findPalette();
    expect(screen.getByRole("button", { name: "Step settings" })).toHaveAttribute("aria-expanded", "false");
    await addWithKeyboard(user, "Dense retrieval", "retrieve.dense");
    expect(screen.getByRole("button", { name: "Step settings" })).toHaveAttribute("aria-expanded", "true");
    expect(within(inspector()).getByRole("heading", { name: "Dense retrieval" })).toBeInTheDocument();
  });

  it("opens Step settings with the step when its card is clicked, or when Enter is pressed on the focused card", async () => {
    const { user, view } = setup({}, "p1");
    await waitFor(() => expect(view.container.querySelectorAll("[data-slot='op-node']")).toHaveLength(4));
    const wrapper = (id: string) => view.container.querySelector<HTMLElement>(`.react-flow__node[data-id="${id}"]`)!;
    const header = screen.getByRole("button", { name: "Step settings" });
    expect(header).toHaveAttribute("aria-expanded", "false");

    // `fireEvent.click` sends the click alone. A `user.click` also sends a mousedown, which d3-drag cannot read in jsdom.
    fireEvent.click(within(wrapper("select")).getByText("Threshold and top-k"));
    expect(header).toHaveAttribute("aria-expanded", "true");
    expect(wrapper("select").querySelector("[data-slot='op-node']")).toHaveAttribute("data-selected", "true");
    expect(within(inspector()).queryByText(/Select a step to edit its settings/)).not.toBeInTheDocument();

    wrapper("dense").focus();
    await user.keyboard("{Enter}");
    expect(wrapper("dense").querySelector("[data-slot='op-node']")).toHaveAttribute("data-selected", "true");
    expect(wrapper("select").querySelector("[data-slot='op-node']")).not.toHaveAttribute("data-selected");
    expect(within(inspector()).queryByText(/Select a step to edit its settings/)).not.toBeInTheDocument();
  });

  it("rewires a saved template and saves the new connections, with layout kept apart", async () => {
    const { server, user } = setup({}, "p1");
    await openAllSections(user);
    await within(outline()).findByRole("button", { name: /^Node rerank/ });

    await user.click(within(outline()).getByRole("button", { name: "Remove connection dense.evidence to rerank.evidence" }));
    await user.click(within(outline()).getByRole("button", { name: "Remove connection rerank.evidence to select.evidence" }));
    await user.click(within(outline()).getByRole("button", { name: /^Node rerank/ }));
    await user.click(within(inspector()).getByRole("button", { name: "Remove step" }));
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
    expect(Object.keys(layout).sort()).toEqual(["direction", "positions", "selection", "viewport"]);
    expect(layout.positions).toHaveProperty("dense", { x: 240, y: 0 });
    expect(server.calls.filter((c) => c.path.endsWith("/revisions") && c.method === "POST")).toHaveLength(1);
  });

  it("shows server validation issues on the matching node and port", async () => {
    const issue = { code: "incompatible_ports", message: "Score kind sparse_rank_v1 is not accepted.", node_id: "threshold", port: "evidence" };
    const { user, view } = setup({
      validate: () => json({ status: "error", message: "Invalid graph.", error_type: "validation", issues: [issue] }, 422),
    });
    await findPalette();
    await openAllSections(user);
    await addWithKeyboard(user, "Threshold and top-k", "select.threshold");
    await user.click(within(runPanel()).getByRole("button", { name: "Validate" }));

    expect(await within(runPanel()).findByText(/incompatible_ports/)).toBeInTheDocument();
    const node = view.container.querySelector('.react-flow__node[data-id="threshold"]');
    expect(node).not.toBeNull();
    expect(node).toHaveTextContent("evidence: Score kind sparse_rank_v1 is not accepted.");
    expect(within(outline()).getByRole("button", { name: /^Node threshold.*1 issue/ })).toBeInTheDocument();
    // The message shows in Step settings outside Details. The code shows only inside Details.
    const details = within(inspector()).getByText("Details").closest("details")!;
    expect(details).toHaveTextContent("incompatible_ports");
    const messages = within(inspector()).getAllByText(/Score kind sparse_rank_v1 is not accepted/);
    expect(messages.some((element) => !details.contains(element))).toBe(true);
    const codeOutside = [...inspector().querySelectorAll("*")].some((el) => !details.contains(el) && el.children.length === 0 && (el.textContent ?? "").includes("incompatible_ports"));
    expect(codeOutside).toBe(false);
    expect(screen.getByRole("alert")).toHaveTextContent("The graph has 1 issue.");
  });

  it("shows one friendly line when a save fails and keeps the draft", async () => {
    const { user } = setup({ failures: { "POST /v1/pipelines/pnew/revisions": 500 } });
    await findPalette();
    await openAllSections(user);
    await addWithKeyboard(user, "Dense retrieval", "retrieve.dense");
    await user.click(within(runPanel()).getByRole("button", { name: "Save revision" }));
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("The local server could not complete that request.");
    expect(alert).not.toHaveTextContent("Boom");
    expect(within(outline()).getByRole("button", { name: /^Node dense/ })).toBeInTheDocument();
  });

  it("shows the graph profile as read-only text, with no Title field and no profile list", async () => {
    const revision = { ...TEMPLATE_REVISION, document: { ...TEMPLATE_REVISION.document, profile: "documents" } };
    const { user } = setup({ revisions: [revision] }, "p1");
    await findPalette();
    await openAllSections(user);
    expect(within(screen.getByRole("region", { name: "Pipeline settings" })).getByText("Base profile: documents")).toBeInTheDocument();
    expect(screen.queryByLabelText("Title")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Profile")).not.toBeInTheDocument();
    expect(screen.getByLabelText("Collection")).toBeInTheDocument();
  });

  it("shows the inherited base profile as text when the graph names none", async () => {
    const { user } = setup();
    await findPalette();
    await openAllSections(user);
    expect(screen.getByText("Base profile: inherited from each collection")).toBeInTheDocument();
    expect(screen.queryByLabelText("Title")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Profile")).not.toBeInTheDocument();
    expect(screen.queryByRole("combobox", { name: "Profile" })).not.toBeInTheDocument();
  });
});
