import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { describe, expect, it } from "vitest";
import type { GraphDocument, OperationDescriptor } from "../api/pipelines";
import type { Purpose } from "../lib/routes";
import { fromDocument, type Draft } from "./graph";
import { enableHybrid } from "./hybrid";
import { PipelineBar } from "./PipelineBar";
import { CATALOGUE } from "./test/catalogueFixture";
import { TEMPLATE_DOC } from "./test/helpers";

/** TEMPLATE_DOC (Prepare query, Dense retrieval, rerank, threshold) is a known off shape. */
const BASE = fromDocument(TEMPLATE_DOC, { positions: {} });

function setup({ draft = BASE, purpose = "search", catalogue = CATALOGUE, readOnly = false }: { draft?: Draft; purpose?: Purpose; catalogue?: OperationDescriptor[]; readOnly?: boolean } = {}) {
  const seen: { draft: Draft } = { draft };
  function Harness() {
    const [current, setCurrent] = useState(draft);
    seen.draft = current;
    return <PipelineBar draft={current} purpose={purpose} catalogue={catalogue} readOnly={readOnly} onChange={(change) => setCurrent((d) => change(d))} />;
  }
  render(<Harness />);
  return { seen, user: userEvent.setup() };
}

const hybridSwitch = () => screen.getByRole("switch", { name: "Hybrid retrieval" });
const withOverrides = (overrides: GraphDocument["overrides"]) => fromDocument({ ...TEMPLATE_DOC, overrides }, { positions: {} });

describe("PipelineBar hybrid switch", () => {
  it.each(["search", "answer"] as const)("shows the switch on the %s pipeline with its line", (purpose) => {
    setup({ purpose });
    expect(hybridSwitch()).toHaveAttribute("aria-checked", "false");
    expect(screen.getByText("Adds keyword (sparse) search and merges it with vector search.")).toBeInTheDocument();
  });

  it("does not show the switch or the rerank factor on the Ingest pipeline", () => {
    setup({ purpose: "ingest" });
    expect(screen.queryByRole("switch")).toBeNull();
    expect(screen.queryByRole("group", { name: "Rerank candidate factor" })).toBeNull();
  });

  it("reads the saved shape", () => {
    setup({ draft: enableHybrid(BASE), purpose: "answer" });
    expect(hybridSwitch()).toHaveAttribute("aria-checked", "true");
  });

  it("turns hybrid on and off in the draft", async () => {
    const { seen, user } = setup();
    await user.click(hybridSwitch());
    expect(seen.draft.graph.nodes.map((node) => node.operation)).toEqual(expect.arrayContaining(["retrieve.sparse", "combine.rrf"]));
    expect(hybridSwitch()).toHaveAttribute("aria-checked", "true");
    await user.click(hybridSwitch());
    expect(seen.draft.graph.nodes.map((node) => node.operation)).not.toContain("retrieve.sparse");
  });

  it("is disabled with a line for a custom shape", () => {
    const draft = fromDocument({ ...TEMPLATE_DOC, nodes: [...TEMPLATE_DOC.nodes, { id: "dense_2", operation: "retrieve.dense", version: 1 }] }, { positions: {} });
    setup({ draft });
    expect(hybridSwitch()).toBeDisabled();
    expect(screen.getByText("This pipeline has a custom retrieval shape. Change it with the steps on the canvas.")).toBeInTheDocument();
  });

  it("is disabled with the catalogue reason when Sparse retrieval cannot run", () => {
    const catalogue = CATALOGUE.map((op) => (op.operation_id === "retrieve.sparse" ? { ...op, available: false, unavailable_reasons: ["The sparse backend is not installed."] } : op));
    setup({ catalogue });
    expect(hybridSwitch()).toBeDisabled();
    expect(screen.getByText("The sparse backend is not installed.")).toBeInTheDocument();
  });

  it("shows the state of a built-in profile and is disabled", () => {
    setup({ draft: enableHybrid(BASE), readOnly: true });
    expect(hybridSwitch()).toHaveAttribute("aria-checked", "true");
    expect(hybridSwitch()).toBeDisabled();
    expect(screen.getByText("Duplicate this profile to turn hybrid retrieval on or off.")).toBeInTheDocument();
  });
});

describe("PipelineBar pipeline-wide settings", () => {
  it("lists an override with its plain label and removes it", async () => {
    const { seen, user } = setup({ draft: withOverrides({ "retrieval.top_k": 25 }) });
    const list = screen.getByRole("list", { name: "Pipeline-wide settings" });
    expect(within(list).getByText("Number of results: 25")).toBeInTheDocument();
    await user.click(within(list).getByRole("button", { name: "Remove Number of results" }));
    expect(seen.draft.graph.overrides).toEqual({});
    expect(screen.getByText("No pipeline-wide settings.")).toBeInTheDocument();
  });

  it("shows the setting path only in a collapsed Details area", () => {
    setup({ draft: withOverrides({ "retrieval.top_k": 25 }) });
    const details = screen.getByText("Details").closest("details");
    expect(details).not.toHaveAttribute("open");
    expect(details).toHaveTextContent("retrieval.top_k");
    expect(screen.getByRole("list", { name: "Pipeline-wide settings" })).not.toHaveTextContent("retrieval.top_k");
  });

  it("writes and removes the rerank candidate factor", async () => {
    const { seen, user } = setup();
    const group = screen.getByRole("group", { name: "Rerank candidate factor" });
    await user.click(within(group).getByRole("radio", { name: "Set value" }));
    await user.type(within(group).getByLabelText("Rerank candidate factor value"), "5");
    expect(seen.draft.graph.overrides).toEqual({ "retrieval.rerank_fetch_multiplier": 5 });
    await user.click(within(group).getByRole("radio", { name: "Inherit" }));
    expect(seen.draft.graph.overrides).toEqual({});
  });

  it("refuses 0 for the rerank candidate factor", async () => {
    const { seen, user } = setup();
    const group = screen.getByRole("group", { name: "Rerank candidate factor" });
    await user.click(within(group).getByRole("radio", { name: "Set value" }));
    await user.type(within(group).getByLabelText("Rerank candidate factor value"), "0");
    expect(group).toHaveTextContent("Enter a value of at least 1.");
    expect(seen.draft.graph.overrides).toEqual({});
  });

  it("disables the list and the factor on a read-only graph", () => {
    setup({ draft: withOverrides({ "retrieval.top_k": 25, "retrieval.rerank_fetch_multiplier": 4 }), readOnly: true });
    expect(screen.getByRole("button", { name: "Remove Number of results" })).toBeDisabled();
    const group = screen.getByRole("group", { name: "Rerank candidate factor" });
    expect(within(group).getByRole("radio", { name: "Set value" })).toBeDisabled();
    expect(within(group).getByLabelText("Rerank candidate factor value")).toHaveValue("4");
  });
});
