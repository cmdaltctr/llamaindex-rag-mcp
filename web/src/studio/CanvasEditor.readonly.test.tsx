import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import type { GraphDocument } from "../api/pipelines";
import { READ_ONLY_NOTICE, READ_ONLY_RUN_LINE } from "./profileCopy";
import {
  CODEBASE_PROFILE,
  DOCUMENTS_PROFILE,
  EMPTY_PIPELINE,
  inspector,
  openAllSections,
  outline,
  palette,
  runPanel,
  STANDARD_GRAPHS,
  TEMPLATE_DOC,
  TEMPLATE_PIPELINE,
  TEMPLATE_REVISION,
} from "./test/helpers";
import { mockReactFlow } from "./test/mockReactFlow";
import { openStudio } from "./test/render";

beforeAll(mockReactFlow);
afterEach(() => vi.restoreAllMocks());

const FIXTURES = { pipelines: [EMPTY_PIPELINE, TEMPLATE_PIPELINE], revisions: [TEMPLATE_REVISION] };

/** Opens the standard Search graph of the built-in `documents` profile and waits until its steps are drawn. */
async function openBuiltIn(purpose = "search") {
  const opened = openStudio(`#/studio/documents/${purpose}`, FIXTURES);
  await screen.findByRole("heading", { level: 1, name: "Documents" });
  await openAllSections(opened.user);
  await within(outline()).findAllByRole("button", { name: /^Node / });
  return opened;
}

const nodeNames = () => within(outline()).getAllByRole("button", { name: /^Node / });
const stepElement = (id: string) => document.querySelector<HTMLElement>(`.react-flow__node[data-id="${id}"]`)!;

describe("a built-in profile on the read-only canvas", () => {
  it("draws the standard graph of the open purpose from the profile detail", async () => {
    await openBuiltIn("search");
    expect(nodeNames()).toHaveLength(TEMPLATE_DOC.nodes.length);
    expect(within(outline()).getByRole("button", { name: /^Node rerank / })).toBeInTheDocument();
  });

  it("loads the standard graph of another purpose when its link is selected", async () => {
    const { user } = await openBuiltIn("search");
    await user.click(within(screen.getByRole("navigation", { name: "Pipelines of this profile" })).getByRole("link", { name: "Ingest" }));
    await openAllSections(user);
    expect(await within(outline()).findByRole("button", { name: /^Node enrich / })).toBeInTheDocument();
    expect(nodeNames()).toHaveLength(STANDARD_GRAPHS.ingest.nodes.length);
  });

  it("disables every operation in the catalogue with the reason Read-only profile", async () => {
    await openBuiltIn();
    const adds = within(palette()).getAllByRole("button", { name: /^Add / });
    expect(adds.length).toBeGreaterThan(1);
    for (const button of adds) {
      expect(button).toBeDisabled();
      const described = (button.getAttribute("aria-describedby") ?? "").split(" ").map((id) => document.getElementById(id)?.textContent);
      expect(described).toContain("Read-only profile");
    }
  });

  it("disables every setting field and shows no Remove button for a selected step", async () => {
    const { user } = await openBuiltIn();
    await user.click(within(outline()).getByRole("button", { name: /^Node rerank / }));
    const panel = inspector();
    const controls = within(panel).queryAllByRole("textbox").concat(within(panel).queryAllByRole("combobox"), within(panel).queryAllByRole("checkbox"), within(panel).queryAllByRole("radio"));
    expect(controls.length).toBeGreaterThan(0);
    for (const control of controls) expect(control).toBeDisabled();
    expect(screen.queryByRole("button", { name: /^Remove (step|node)$/ })).not.toBeInTheDocument();
  });

  it("disables a number field that holds a value", async () => {
    const withValues: GraphDocument = {
      ...TEMPLATE_DOC,
      nodes: TEMPLATE_DOC.nodes.map((node) => (node.id === "prepare" ? { ...node, params: { top_k: 5, similarity_threshold: 0.3 } } : node)),
    };
    const profile = { ...DOCUMENTS_PROFILE, standard_graphs: { ...STANDARD_GRAPHS, search: withValues } };
    const opened = openStudio("#/studio/documents/search", { ...FIXTURES, profiles: [profile] });
    await screen.findByRole("heading", { level: 1, name: "Documents" });
    await openAllSections(opened.user);
    await opened.user.click(await within(outline()).findByRole("button", { name: /^Node prepare / }));
    const box = within(inspector()).getByRole("textbox", { name: "Number of results value" });
    expect(box).toHaveValue("5");
    expect(box).toBeDisabled();
    expect(within(inspector()).getByRole("textbox", { name: /similarity.* value/i })).toBeDisabled();
  });

  it("disables the pipeline settings fields", async () => {
    await openBuiltIn();
    const region = screen.getByRole("region", { name: "Pipeline settings" });
    const controls = within(region).queryAllByRole("textbox").concat(within(region).queryAllByRole("combobox"));
    expect(controls.length).toBeGreaterThan(0);
    for (const control of controls) expect(control).toBeDisabled();
  });

  it("offers Validate and no save or run, and says why", async () => {
    await openBuiltIn();
    expect(within(runPanel()).getByRole("button", { name: "Validate" })).toBeEnabled();
    for (const name of ["Save layout", "Save revision", "Run"]) expect(within(runPanel()).queryByRole("button", { name })).not.toBeInTheDocument();
    expect(runPanel()).toHaveTextContent(READ_ONLY_RUN_LINE);
    expect(runPanel()).not.toHaveTextContent("No saved revision");
  });

  it("sends the standard graph when Validate is selected, and reads no run", async () => {
    const { user, server } = await openBuiltIn();
    await user.click(within(runPanel()).getByRole("button", { name: "Validate" }));
    await waitFor(() => expect(server.last("POST", "/v1/pipelines/validate")).toBeDefined());
    const sent = (server.last("POST", "/v1/pipelines/validate")!.body as { document: { nodes: { id: string }[] } }).document;
    expect(sent.nodes.map((node) => node.id)).toEqual(TEMPLATE_DOC.nodes.map((node) => node.id));
    expect(server.calls.filter((call) => call.path === "/v1/runs")).toEqual([]);
    expect(server.calls.filter((call) => call.method !== "GET" && !call.path.endsWith("/validate"))).toEqual([]);
  });

  it("shows Duplicate to edit in the page header and the notice in the info popover", async () => {
    const { user } = await openBuiltIn();
    expect(screen.queryByText(READ_ONLY_NOTICE)).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "About the Search pipeline" }));
    expect(screen.getByText(READ_ONLY_NOTICE)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Duplicate to edit" })).toBeEnabled();
  });

  it("replaces the connection controls with a read-only line", async () => {
    await openBuiltIn();
    const region = screen.getByRole("region", { name: "Connect ports" });
    expect(within(region).getByText("This pipeline is read-only.")).toBeInTheDocument();
    expect(within(region).queryByLabelText("From output")).not.toBeInTheDocument();
    expect(within(region).queryByRole("button", { name: "Connect" })).not.toBeInTheDocument();
  });

  it("lists connections in the outline without Remove buttons", async () => {
    await openBuiltIn();
    expect(within(outline()).getAllByRole("button", { name: /^Connection / }).length).toBeGreaterThan(0);
    expect(within(outline()).queryByRole("button", { name: /^Remove connection / })).not.toBeInTheDocument();
  });

  it("does not let a step be dragged", async () => {
    await openBuiltIn();
    expect(stepElement("rerank")).not.toHaveClass("draggable");
    expect(stepElement("rerank")).toHaveClass("selectable");
  });

  it("keeps the graph when the Delete or Backspace key is pressed on a selected step", async () => {
    const { user } = await openBuiltIn();
    await user.click(within(outline()).getByRole("button", { name: /^Node rerank / }));
    const step = screen.getByLabelText("Cross-encoder rerank step");
    step.focus();
    fireEvent.keyDown(step, { key: "Delete" });
    fireEvent.keyDown(step, { key: "Backspace" });
    expect(nodeNames()).toHaveLength(TEMPLATE_DOC.nodes.length);
    expect(within(outline()).getByRole("button", { name: /^Node rerank / })).toBeInTheDocument();
    // The outline keys do not remove either.
    const item = within(outline()).getByRole("button", { name: /^Node rerank / });
    item.focus();
    await user.keyboard("{Delete}");
    expect(nodeNames()).toHaveLength(TEMPLATE_DOC.nodes.length);
  });

  it("opens the settings of a step when the user selects it", async () => {
    const { user } = await openBuiltIn();
    expect(screen.getByRole("button", { name: /^Step settings/ })).toHaveAttribute("aria-expanded", "true");
    await user.click(within(outline()).getByRole("button", { name: /^Node dense / }));
    expect(within(inspector()).getByRole("heading", { name: "Dense retrieval" })).toBeInTheDocument();
    await user.click(within(outline()).getByRole("button", { name: /^Node rerank / }));
    expect(within(inspector()).getByRole("heading", { name: /rerank/ })).toBeInTheDocument();
  });

  it("stores no draft, even after selecting steps", async () => {
    const setItem = vi.spyOn(Storage.prototype, "setItem");
    const { user } = await openBuiltIn();
    await user.click(within(outline()).getByRole("button", { name: /^Node dense / }));
    await user.click(within(outline()).getByRole("button", { name: /^Node rerank / }));
    expect(setItem.mock.calls.filter(([key]) => String(key).includes("canvas-draft"))).toEqual([]);
    expect(Object.keys(window.localStorage).filter((key) => key.includes("canvas-draft"))).toEqual([]);
  });

  it("gives a second visit the standard graph again, not the earlier selection state as a draft", async () => {
    const { user, view } = await openBuiltIn();
    await user.click(within(outline()).getByRole("button", { name: /^Node dense / }));
    view.unmount();
    openStudio("#/studio/documents/search", FIXTURES);
    await screen.findByRole("heading", { level: 1, name: "Documents" });
    expect(Object.keys(window.localStorage).filter((key) => key.includes("canvas-draft"))).toEqual([]);
  });

  it("opens the second built-in profile read-only as well", async () => {
    const { user } = openStudio("#/studio/codebase/search", { ...FIXTURES, profiles: [CODEBASE_PROFILE] });
    expect(await screen.findByRole("heading", { level: 1, name: "Codebase" })).toBeInTheDocument();
    await screen.findByRole("button", { name: "Operations" });
    await user.click(screen.getByRole("button", { name: "About the Search pipeline" }));
    expect(screen.getByText(READ_ONLY_NOTICE)).toBeInTheDocument();
  });
});

describe("a user profile canvas stays editable", () => {
  it("offers the catalogue, the save buttons and Run, and no read-only notice", async () => {
    const { user } = openStudio("#/studio/search-copy/search", FIXTURES);
    await screen.findByRole("heading", { level: 1, name: "Search copy" });
    await openAllSections(user);
    expect(await within(palette()).findByRole("button", { name: "Add Dense retrieval (retrieve.dense)" })).toBeEnabled();
    for (const name of ["Save layout", "Save revision", "Validate", "Run"]) expect(within(runPanel()).getByRole("button", { name })).toBeEnabled();
    expect(screen.queryByText(READ_ONLY_NOTICE)).not.toBeInTheDocument();
    expect(screen.queryByText("This pipeline is read-only.")).not.toBeInTheDocument();
    await within(outline()).findByRole("button", { name: /^Node rerank / });
    expect(stepElement("rerank")).toHaveClass("draggable");
  });

  it("removes a selected step with the Delete key", async () => {
    const { user } = openStudio("#/studio/search-copy/search", FIXTURES);
    await screen.findByRole("heading", { level: 1, name: "Search copy" });
    await openAllSections(user);
    await user.click(await within(outline()).findByRole("button", { name: /^Node rerank / }));
    const step = screen.getByLabelText("Cross-encoder rerank step");
    step.focus();
    fireEvent.keyDown(step, { key: "Delete" });
    await waitFor(() => expect(within(outline()).queryByRole("button", { name: /^Node rerank / })).not.toBeInTheDocument());
  });
});
