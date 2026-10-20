import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { ReactFlowProvider, type NodeProps } from "@xyflow/react";
import { beforeAll, describe, expect, it, vi } from "vitest";
import type { EdgeSpec, EffectiveControl, NodeSpec, OperationDescriptor, ValidationIssue } from "../api/pipelines";
import { emptyDraft } from "./graph";
import { FlowSurface } from "./FlowSurface";
import { OperationNode, type OperationFlowNode } from "./OperationNode";
import { CATALOGUE } from "./test/catalogueFixture";
import { CATALOGUE_INGEST } from "./test/catalogueIngest";
import { mockReactFlow } from "./test/mockReactFlow";

beforeAll(mockReactFlow);

const FULL_CATALOGUE = [...CATALOGUE, ...CATALOGUE_INGEST];
const FIXED = "(fixed for collections that already hold vectors)";

function mount(isConnectable: boolean, direction?: "horizontal" | "vertical") {
  const operation = CATALOGUE.find((entry) => entry.operation_id === "retrieve.dense");
  const props = {
    id: "dense",
    data: {
      nodeId: "dense",
      operationId: "retrieve.dense",
      operation,
      title: "Dense retrieval",
      showNodeId: false,
      summary: "Embed the query and read the nearest chunks.",
      settings: [],
      moreSettings: 0,
      extraSettings: [],
      connected: [],
      model: undefined,
      enabled: true,
      issues: [],
      direction,
    },
    selected: false,
    isConnectable,
  } as unknown as NodeProps<OperationFlowNode>;
  const { container } = render(
    <ReactFlowProvider>
      <OperationNode {...props} />
    </ReactFlowProvider>,
  );
  return [...container.querySelectorAll(".react-flow__handle")];
}

describe("OperationNode handles", () => {
  it("drop the connectable state when the canvas is read-only", () => {
    const handles = mount(false);
    expect(handles.length).toBeGreaterThan(0);
    for (const handle of handles) expect(handle).not.toHaveClass("connectable");
  });

  it("stay connectable on an editable canvas", () => {
    const handles = mount(true);
    expect(handles.length).toBeGreaterThan(0);
    for (const handle of handles) expect(handle).toHaveClass("connectable");
  });
});

describe("OperationNode handle sides", () => {
  const sides = (handles: Element[], type: "target" | "source") =>
    new Set(handles.filter((h) => h.classList.contains(type === "target" ? "target" : "source")).map((h) => [...h.classList].find((c) => /^react-flow__handle-(left|right|top|bottom)$/.test(c))));

  it("sit left and right on a horizontal graph", () => {
    const handles = mount(true, "horizontal");
    expect(sides(handles, "target")).toEqual(new Set(["react-flow__handle-left"]));
    expect(sides(handles, "source")).toEqual(new Set(["react-flow__handle-right"]));
  });

  it("sit left and right when the graph has no direction", () => {
    const handles = mount(true);
    expect(sides(handles, "target")).toEqual(new Set(["react-flow__handle-left"]));
  });

  it("sit top and bottom on a vertical graph", () => {
    const handles = mount(true, "vertical");
    expect(sides(handles, "target")).toEqual(new Set(["react-flow__handle-top"]));
    expect(sides(handles, "source")).toEqual(new Set(["react-flow__handle-bottom"]));
  });
});

interface SurfaceOptions {
  controls?: Record<string, EffectiveControl[]>;
  embeddingModel?: string | null;
  issues?: ValidationIssue[];
  catalogue?: OperationDescriptor[];
  edges?: EdgeSpec[];
  onChange?: () => void;
}

/** Renders the nodes through `FlowSurface`, because a card's handles need the React Flow node context. */
async function renderCards(nodes: NodeSpec[], options: SurfaceOptions = {}) {
  const base = emptyDraft();
  const draft = {
    ...base,
    graph: { ...base.graph, nodes, edges: options.edges ?? [] },
    layout: { ...base.layout, positions: Object.fromEntries(nodes.map((node, index) => [node.id, { x: index * 300, y: 0 }])) },
  };
  const view = render(
    <div style={{ width: 1200, height: 600 }}>
      <FlowSurface
        draft={draft}
        catalogue={options.catalogue ?? FULL_CATALOGUE}
        issues={options.issues ?? []}
        controls={options.controls ?? {}}
        embeddingModel={options.embeddingModel ?? null}
        onChange={options.onChange ?? vi.fn()}
        onConnect={vi.fn()}
        onRefused={vi.fn()}
      />
    </div>,
  );
  await waitFor(() => expect(view.container.querySelectorAll("[data-slot='op-node']")).toHaveLength(nodes.length));
  return view;
}

function card(nodeId: string): HTMLElement {
  const found = document.querySelector<HTMLElement>(`.react-flow__node[data-id="${nodeId}"] [data-slot='op-node']`);
  if (found === null) throw new Error(`No canvas node ${nodeId}`);
  return found;
}

const node = (id: string, operation: string, params?: NodeSpec["params"], enabled?: boolean): NodeSpec => ({
  id,
  operation,
  version: 1,
  ...(params ? { params } : {}),
  ...(enabled === undefined ? {} : { enabled }),
});

describe("Step cards show what each step does", () => {
  it("shows the step name, a one-line summary and a setting that is set on the step", async () => {
    await renderCards([node("cross1", "select.rerank", { enabled: false })]);
    expect(card("cross1")).toHaveTextContent("Cross-encoder rerank");
    expect(card("cross1")).toHaveTextContent("Re-score evidence; a failure keeps the pre-rerank scores.");
    expect(card("cross1")).toHaveTextContent("Reranker: Off (set here)");
  });

  it("shows three main settings, says that the profile supplies them while no check has returned, and counts the rest", async () => {
    await renderCards([node("pq1", "retrieve.prepare_query")]);
    expect(card("pq1")).toHaveTextContent("Number of results: From profile");
    expect(card("pq1")).toHaveTextContent("Minimum similarity: From profile");
    expect(card("pq1")).toHaveTextContent("Reranker: From profile");
    expect(card("pq1")).toHaveTextContent("+3 more settings");
    expect(card("pq1")).not.toHaveTextContent("Candidates to fetch");
  });

  it("shows the value and its source once a check has returned them", async () => {
    const controls = {
      pq1: [
        { lever: "retrieval.top_k", value: 10, source: "profile", detail: "profile 'documents'" },
        { lever: "retrieval.rerank_enabled", value: false, source: "environment", detail: "RERANK_ENABLED" },
      ],
    };
    await renderCards([node("pq1", "retrieve.prepare_query")], { controls });
    expect(card("pq1")).toHaveTextContent("Number of results: 10 (from profile)");
    expect(card("pq1")).toHaveTextContent("Reranker: Off (from server settings)");
    expect(card("pq1")).toHaveTextContent("Minimum similarity: From profile");
  });

  it("shows the chunk size of a Split into chunks step with its source", async () => {
    const controls = { split1: [{ lever: "chunking.chunk_size", value: 1024, source: "profile", detail: "profile" }] };
    await renderCards([node("split1", "prepare.chunk")], { controls });
    expect(card("split1")).toHaveTextContent("Chunk size: 1024 (from profile)");
    expect(card("split1")).toHaveTextContent("Split documents");
  });

  it("shows No settings on a step without parameters", async () => {
    await renderCards([node("thr1", "select.threshold"), node("disc1", "source.discover")]);
    expect(card("thr1")).toHaveTextContent("No settings");
    expect(card("disc1")).toHaveTextContent("No settings");
  });

  it("shows port names without type kinds, and no operation id or node id", async () => {
    await renderCards([node("thr1", "select.threshold"), node("disc1", "source.discover")]);
    expect(card("thr1")).toHaveTextContent("evidence");
    expect(card("disc1")).toHaveTextContent("sources");
    for (const id of ["thr1", "disc1"]) {
      const text = card(id).textContent ?? "";
      for (const code of ["ranked_evidence", "select.threshold", "source.discover", "thr1", "disc1"]) expect(text).not.toContain(code);
    }
    const handles = [...card("thr1").querySelectorAll(".react-flow__handle")];
    expect(handles.map((handle) => handle.getAttribute("title"))).toEqual(["evidence", "evidence"]);
  });

  it("shows a settings button named after the step, with an icon that assistive technology skips", async () => {
    await renderCards([node("thr1", "select.threshold")]);
    const button = within(card("thr1")).getByRole("button", { name: "Settings for Threshold and top-k" });
    expect(button).toHaveAttribute("aria-expanded", "false");
    expect(button).toHaveClass("nodrag");
    expect(button.querySelector("svg")).toHaveAttribute("aria-hidden", "true");
  });
});

describe("Step cards with the same name", () => {
  const twoDense = [node("dense", "retrieve.dense"), node("dense_2", "retrieve.dense"), node("thr1", "select.threshold")];

  it("shows the node id on both cards and on no other card", async () => {
    await renderCards(twoDense);
    expect(within(card("dense")).getByText("dense")).toBeInTheDocument();
    expect(within(card("dense_2")).getByText("dense_2")).toBeInTheDocument();
    expect(card("thr1").textContent).not.toContain("thr1");
  });

  it("names each card after its step, and adds the node id when the name repeats", async () => {
    await renderCards(twoDense);
    expect(screen.getByRole("group", { name: "Threshold and top-k step" })).toBeInTheDocument();
    expect(screen.getByRole("group", { name: "Dense retrieval step, dense_2" })).toBeInTheDocument();
    expect(screen.getByRole("group", { name: "Dense retrieval step, dense" })).toBeInTheDocument();
  });
});

describe("Step cards keep their status text", () => {
  it("shows Bypassed, Unavailable and the issue messages", async () => {
    const unavailable = FULL_CATALOGUE.map((entry) =>
      entry.operation_id === "select.threshold" ? { ...entry, available: false, unavailable_reasons: ["No sparse backend."] } : entry,
    );
    const issues: ValidationIssue[] = [{ code: "unconnected_port", message: "No source.", node_id: "thr1", port: "evidence" }];
    await renderCards([node("cross1", "select.rerank", undefined, false), node("thr1", "select.threshold")], { catalogue: unavailable, issues });
    expect(card("cross1")).toHaveTextContent("Bypassed");
    expect(card("thr1")).toHaveTextContent("Unavailable");
    expect(card("thr1")).toHaveTextContent("evidence: No source.");
    expect(card("thr1")).toHaveAttribute("data-invalid", "true");
  });
});

describe("The Embed chunks card", () => {
  it("names the embedding model and says it is fixed", async () => {
    await renderCards([node("emb1", "embed.chunks")], { embeddingModel: "nomic-embed-text" });
    expect(card("emb1")).toHaveTextContent(`Model: nomic-embed-text ${FIXED}`);
    expect(card("emb1")).not.toHaveTextContent("No settings");
    expect(within(card("emb1")).getByText("nomic-embed-text").tagName).toBe("CODE");
  });

  it("says the model is unknown when the connection summary gave none", async () => {
    await renderCards([node("emb1", "embed.chunks")], { embeddingModel: null });
    expect(card("emb1")).toHaveTextContent(`Model: unknown ${FIXED}`);
    expect(card("emb1")).not.toHaveTextContent("No settings");
  });

  it("shows no model line on another step", async () => {
    await renderCards([node("thr1", "select.threshold")], { embeddingModel: "nomic-embed-text" });
    expect(card("thr1")).not.toHaveTextContent("Model:");
  });
});

describe("Port handles show whether they are connected", () => {
  const nodes = [node("dense", "retrieve.dense"), node("rerank", "select.rerank"), node("thr1", "select.threshold")];
  const edges: EdgeSpec[] = [{ source: { node: "dense", port: "evidence" }, target: { node: "rerank", port: "evidence" } }];

  /** The handle of one port: `side` is the React Flow type, `target` for an input and `source` for an output. */
  function handle(nodeId: string, side: "target" | "source", port: string): HTMLElement {
    const found = card(nodeId).querySelector<HTMLElement>(`.react-flow__handle.${side}[data-handleid="${port}"]`);
    if (found === null) throw new Error(`No ${side} handle ${port} on ${nodeId}`);
    return found;
  }

  it("marks both ends of a connection, and no other handle", async () => {
    await renderCards(nodes, { edges });
    expect(handle("dense", "source", "evidence")).toHaveAttribute("data-connected", "true");
    expect(handle("rerank", "target", "evidence")).toHaveAttribute("data-connected", "true");
    expect(handle("dense", "target", "query")).not.toHaveAttribute("data-connected");
    expect(handle("rerank", "source", "evidence")).not.toHaveAttribute("data-connected");
    expect(handle("thr1", "target", "evidence")).not.toHaveAttribute("data-connected");
    expect(handle("thr1", "source", "evidence")).not.toHaveAttribute("data-connected");
  });

  it("paints a connected handle green and leaves the others neutral", async () => {
    await renderCards(nodes, { edges });
    expect(handle("dense", "source", "evidence").className).toMatch(/bg-status-success/);
    expect(handle("dense", "source", "evidence").className).toMatch(/border-status-success/);
    expect(handle("dense", "target", "query").className).not.toMatch(/status-success/);
    expect(handle("dense", "target", "query").className).toMatch(/bg-card/);
  });

  it("keeps the input and the output of one port name apart", async () => {
    // Rerank has an input and an output both called evidence. Only the input has an edge.
    await renderCards(nodes, { edges });
    expect(handle("rerank", "target", "evidence").className).toMatch(/bg-status-success/);
    expect(handle("rerank", "source", "evidence").className).not.toMatch(/status-success/);
  });
});

describe("The step summary expands in place", () => {
  const SUMMARY = "Re-score evidence; a failure keeps the pre-rerank scores.";
  const summary = (id: string) => within(card(id)).getByRole("button", { name: SUMMARY });

  it("is a button that starts on one line", async () => {
    await renderCards([node("cross1", "select.rerank")]);
    expect(summary("cross1")).toHaveAttribute("aria-expanded", "false");
    expect(summary("cross1")).toHaveClass("line-clamp-1");
    expect(summary("cross1").querySelector("svg")).toBeNull();
  });

  it("uses a smaller type size than the settings lines, so it reads as background information", async () => {
    await renderCards([node("pq1", "retrieve.prepare_query")]);
    const summaryButton = within(card("pq1")).getByRole("button", { name: /Resolve top-k, threshold/ });
    expect(summaryButton).toHaveClass("text-code");
    const setting = within(card("pq1")).getByText("Number of results:", { exact: false }).closest("li")!;
    expect(setting).not.toHaveClass("text-code");
  });

  it("shows the whole sentence on a click and folds it on a second click", async () => {
    await renderCards([node("cross1", "select.rerank")]);
    fireEvent.click(summary("cross1"));
    expect(summary("cross1")).toHaveAttribute("aria-expanded", "true");
    expect(summary("cross1")).not.toHaveClass("line-clamp-1");
    fireEvent.click(summary("cross1"));
    expect(summary("cross1")).toHaveAttribute("aria-expanded", "false");
    expect(summary("cross1")).toHaveClass("line-clamp-1");
  });

  it("keeps each card's state apart", async () => {
    await renderCards([node("cross1", "select.rerank"), node("thr1", "select.threshold")]);
    fireEvent.click(summary("cross1"));
    const other = within(card("thr1")).getByRole("button", { name: /Apply the score-kind-aware threshold/ });
    expect(other).toHaveAttribute("aria-expanded", "false");
  });

  it("does not select the card, and leaves the drag and pan classes on the button", async () => {
    const onChange = vi.fn();
    await renderCards([node("cross1", "select.rerank")], { onChange });
    expect(summary("cross1")).toHaveClass("nodrag", "nopan");
    fireEvent.click(summary("cross1"));
    fireEvent.keyDown(summary("cross1"), { key: "Enter" });
    expect(onChange).not.toHaveBeenCalled();
    fireEvent.click(within(card("cross1")).getByText("Cross-encoder rerank"));
    expect(onChange).toHaveBeenCalled();
  });
});

describe("Step settings sit in a mini card that expands in place", () => {
  const miniCard = (id: string) => card(id).querySelector<HTMLElement>("[data-slot='node-settings']")!;
  const more = (id: string) => within(miniCard(id)).getByRole("button", { name: /more settings|Show fewer settings/ });

  it("wraps the settings in a bordered mini card inside the card", async () => {
    await renderCards([node("pq1", "retrieve.prepare_query")]);
    expect(miniCard("pq1")).not.toBeNull();
    expect(miniCard("pq1").className).toMatch(/border/);
    expect(miniCard("pq1").className).toMatch(/rounded/);
    expect(miniCard("pq1")).toHaveTextContent("Number of results: From profile");
    expect(card("pq1")).toContainElement(miniCard("pq1"));
  });

  it("puts No settings and the model line in the same mini card", async () => {
    await renderCards([node("thr1", "select.threshold"), node("emb1", "embed.chunks")], { embeddingModel: "nomic-embed-text" });
    expect(miniCard("thr1")).toHaveTextContent("No settings");
    expect(miniCard("emb1")).toHaveTextContent("Model: nomic-embed-text");
  });

  it("shows a +N more settings button that starts folded", async () => {
    await renderCards([node("pq1", "retrieve.prepare_query")]);
    expect(more("pq1")).toHaveTextContent("+3 more settings");
    expect(more("pq1")).toHaveAttribute("aria-expanded", "false");
    expect(miniCard("pq1")).not.toHaveTextContent("Candidates to fetch");
  });

  it("shows the other settings with their values on a click, and folds them on a second click", async () => {
    await renderCards([node("pq1", "retrieve.prepare_query")]);
    fireEvent.click(more("pq1"));
    expect(more("pq1")).toHaveTextContent("Show fewer settings");
    expect(more("pq1")).toHaveAttribute("aria-expanded", "true");
    expect(miniCard("pq1")).toHaveTextContent("Candidates to fetch: Default");
    expect(miniCard("pq1")).toHaveTextContent("Collection: Server default");
    expect(miniCard("pq1")).toHaveTextContent("Metadata filter: Default");
    expect(miniCard("pq1").querySelectorAll("li")).toHaveLength(6);
    fireEvent.click(more("pq1"));
    expect(more("pq1")).toHaveTextContent("+3 more settings");
    expect(miniCard("pq1").querySelectorAll("li")).toHaveLength(3);
  });

  it("does not select the card", async () => {
    const onChange = vi.fn();
    await renderCards([node("pq1", "retrieve.prepare_query")], { onChange });
    expect(more("pq1")).toHaveClass("nodrag", "nopan");
    fireEvent.click(more("pq1"));
    fireEvent.keyDown(more("pq1"), { key: "Enter" });
    expect(onChange).not.toHaveBeenCalled();
  });

  it("shows no button when the card already shows every setting", async () => {
    await renderCards([node("dense", "retrieve.dense"), node("thr1", "select.threshold")]);
    expect(within(miniCard("dense")).queryByRole("button")).toBeNull();
    expect(within(miniCard("thr1")).queryByRole("button")).toBeNull();
  });

  it("keeps each card's state apart", async () => {
    await renderCards([node("pq1", "retrieve.prepare_query"), node("pq2", "retrieve.prepare_query")]);
    fireEvent.click(more("pq1"));
    expect(more("pq2")).toHaveAttribute("aria-expanded", "false");
  });
});
