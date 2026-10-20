import { render, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { beforeAll, describe, expect, it, vi } from "vitest";
import type { NodeSpec } from "../api/pipelines";
import { FlowSurface } from "./FlowSurface";
import { emptyDraft, type Draft } from "./graph";
import { CATALOGUE } from "./test/catalogueFixture";
import { CATALOGUE_INGEST } from "./test/catalogueIngest";
import { mockReactFlow } from "./test/mockReactFlow";

beforeAll(mockReactFlow);

const node = (id: string, operation: string, params?: NodeSpec["params"]): NodeSpec => ({ id, operation, version: 1, ...(params ? { params } : {}) });

async function setup(nodes: NodeSpec[], { readOnly = false } = {}) {
  const base = emptyDraft();
  const seen: { draft: Draft } = {
    draft: { ...base, graph: { ...base.graph, nodes }, layout: { ...base.layout, positions: Object.fromEntries(nodes.map((n, i) => [n.id, { x: i * 300, y: 0 }])) } },
  };
  const onOpenStepSettings = vi.fn();
  function Harness() {
    const [draft, setDraft] = useState(seen.draft);
    seen.draft = draft;
    return (
      <div style={{ width: 1200, height: 600 }}>
        <FlowSurface
          draft={draft}
          catalogue={[...CATALOGUE, ...CATALOGUE_INGEST]}
          issues={[]}
          embeddingModel="nomic-embed-text"
          readOnly={readOnly}
          onChange={(change) => setDraft((d) => change(d))}
          onConnect={vi.fn()}
          onRefused={vi.fn()}
          onOpenStepSettings={onOpenStepSettings}
        />
      </div>
    );
  }
  const view = render(<Harness />);
  await waitFor(() => expect(view.container.querySelectorAll("[data-slot='op-node']")).toHaveLength(nodes.length));
  return { seen, onOpenStepSettings, user: userEvent.setup() };
}

function card(nodeId: string): HTMLElement {
  const found = document.querySelector<HTMLElement>(`.react-flow__node[data-id="${nodeId}"] [data-slot='op-node']`);
  if (found === null) throw new Error(`No canvas node ${nodeId}`);
  return found;
}

const panel = () => document.querySelector<HTMLElement>("[data-slot='step-card-settings']")!;

describe("the card settings button", () => {
  it("is named after the step and reports whether its panel is open", async () => {
    const { user } = await setup([node("prepare", "retrieve.prepare_query")]);
    const button = within(card("prepare")).getByRole("button", { name: "Settings for Prepare query" });
    expect(button).toHaveAttribute("aria-expanded", "false");
    await user.click(button);
    expect(button).toHaveAttribute("aria-expanded", "true");
    expect(panel()).toBeInTheDocument();
    expect(within(panel()).getByRole("heading", { name: "Prepare query" })).toBeInTheDocument();
  });

  it("does not select the step", async () => {
    const { seen, user } = await setup([node("prepare", "retrieve.prepare_query")]);
    await user.click(within(card("prepare")).getByRole("button", { name: "Settings for Prepare query" }));
    expect(seen.draft.layout.selection).toEqual([]);
  });

  it("closes on Escape and returns focus to the button", async () => {
    const { user } = await setup([node("prepare", "retrieve.prepare_query")]);
    const button = within(card("prepare")).getByRole("button", { name: "Settings for Prepare query" });
    await user.click(button);
    await user.keyboard("{Escape}");
    expect(panel()).toBeNull();
    expect(button).toHaveFocus();
  });
});

describe("the card settings panel", () => {
  it("sets a number from the card", async () => {
    const { seen, user } = await setup([node("prepare", "retrieve.prepare_query")]);
    await user.click(within(card("prepare")).getByRole("button", { name: "Settings for Prepare query" }));
    const group = within(panel()).getByRole("group", { name: "Number of results" });
    await user.click(within(group).getByRole("radio", { name: "Set value" }));
    await user.type(within(group).getByLabelText("Number of results value"), "20");
    expect(seen.draft.graph.nodes[0]?.params).toEqual({ top_k: 20 });
    expect(card("prepare")).toHaveTextContent("Number of results: 20 (set here)");
    expect(seen.draft.layout.selection).toEqual([]);
  });

  it("bypasses a step from the card", async () => {
    const { seen, user } = await setup([node("rerank", "select.rerank")]);
    await user.click(within(card("rerank")).getByRole("button", { name: "Settings for Cross-encoder rerank" }));
    await user.click(within(panel()).getByRole("checkbox", { name: "Bypass this step" }));
    expect(seen.draft.graph.nodes[0]?.enabled).toBe(false);
    expect(card("rerank")).toHaveTextContent("Bypassed");
  });

  it("keeps the step when Backspace is pressed in a panel field", async () => {
    const { seen, user } = await setup([node("prepare", "retrieve.prepare_query", { collection: "papers" })]);
    await user.click(within(card("prepare")).getByRole("button", { name: "Settings for Prepare query" }));
    const field = within(panel()).getByRole("textbox", { name: "Collection value" });
    await user.click(field);
    await user.keyboard("{Backspace}{Backspace}");
    expect(seen.draft.graph.nodes.map((n) => n.id)).toEqual(["prepare"]);
    expect(seen.draft.graph.nodes[0]?.params).toEqual({ collection: "pape" });
  });

  it("leads to Step settings", async () => {
    const { onOpenStepSettings, user } = await setup([node("split", "prepare.chunk")]);
    await user.click(within(card("split")).getByRole("button", { name: "Settings for Split into chunks" }));
    await user.click(within(panel()).getByRole("button", { name: "Open in Step settings" }));
    expect(onOpenStepSettings).toHaveBeenCalledWith("split");
    expect(panel()).toBeNull();
  });

  it("shows values with every control disabled on a read-only graph", async () => {
    const { user } = await setup([node("rerank", "select.rerank", { enabled: false })], { readOnly: true });
    await user.click(within(card("rerank")).getByRole("button", { name: "Settings for Cross-encoder rerank" }));
    expect(within(panel()).getByRole("checkbox", { name: "Bypass this step" })).toBeDisabled();
    const group = within(panel()).getByRole("group", { name: "Reranker" });
    expect(within(group).getByRole("radio", { name: "Off" })).toBeChecked();
    for (const radio of within(group).getAllByRole("radio")) expect(radio).toBeDisabled();
    expect(within(panel()).getByRole("button", { name: "Open in Step settings" })).toBeEnabled();
  });

  it("shows the model line on Embed chunks and offers no model control", async () => {
    const { user } = await setup([node("embed", "embed.chunks")]);
    await user.click(within(card("embed")).getByRole("button", { name: "Settings for Embed chunks" }));
    expect(panel()).toHaveTextContent("Model: nomic-embed-text");
    expect(within(panel()).queryByRole("combobox")).toBeNull();
    expect(within(panel()).getByRole("button", { name: "Open in Step settings" })).toBeInTheDocument();
  });
});
