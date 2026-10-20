import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { describe, expect, it } from "vitest";
import type { EffectiveControl, NodeSpec } from "../api/pipelines";
import { emptyDraft, type Draft } from "./graph";
import { StepSettingsFields } from "./StepSettingsFields";
import { CATALOGUE } from "./test/catalogueFixture";

function draftWith(node: NodeSpec): Draft {
  const base = emptyDraft();
  return { ...base, graph: { ...base.graph, nodes: [node] } };
}

function setup(node: NodeSpec, { readOnly = false, controls = {} }: { readOnly?: boolean; controls?: Record<string, EffectiveControl[]> } = {}) {
  const operation = CATALOGUE.find((entry) => entry.operation_id === node.operation)!;
  const seen = { draft: draftWith(node) };
  function Harness() {
    const [draft, setDraft] = useState(seen.draft);
    seen.draft = draft;
    return <StepSettingsFields draft={draft} nodeId={node.id} operation={operation} controls={controls} readOnly={readOnly} onChange={(change) => setDraft((d) => change(d))} />;
  }
  render(<Harness />);
  return { seen, user: userEvent.setup() };
}

const legends = () => screen.getAllByRole("group").map((group) => group.querySelector("legend")?.textContent);

describe("StepSettingsFields", () => {
  it("shows the Prepare query settings with their plain labels", () => {
    setup({ id: "pq", operation: "retrieve.prepare_query", version: 1 });
    expect(legends()).toEqual(expect.arrayContaining(["Number of results", "Minimum similarity", "Reranker", "Candidates to fetch", "Collection"]));
    expect(screen.queryByRole("checkbox", { name: "Bypass this step" })).toBeNull();
  });

  it("shows the value note from the latest check", () => {
    const controls = { pq: [{ lever: "retrieval.top_k", value: 10, source: "profile", detail: "profile 'documents'" }] };
    setup({ id: "pq", operation: "retrieve.prepare_query", version: 1 }, { controls });
    expect(within(screen.getByRole("group", { name: "Number of results" })).getByText("Value in use: 10 (from profile)")).toBeInTheDocument();
  });

  it("writes a metadata filter to the draft and clears it", async () => {
    const { seen, user } = setup({ id: "pq", operation: "retrieve.prepare_query", version: 1 });
    const field = screen.getByRole("textbox", { name: "Metadata filter value" });
    await user.click(field);
    await user.paste('{"file_type": "pdf"}');
    expect(seen.draft.graph.nodes[0]?.params).toEqual({ metadata_filter: { file_type: "pdf" } });
    await user.clear(field);
    expect(seen.draft.graph.nodes[0]).not.toHaveProperty("params.metadata_filter");
  });

  it("offers the bypass switch for Cross-encoder rerank and writes it to the draft", async () => {
    const { seen, user } = setup({ id: "rr", operation: "select.rerank", version: 1 });
    await user.click(screen.getByRole("checkbox", { name: "Bypass this step" }));
    expect(seen.draft.graph.nodes[0]?.enabled).toBe(false);
    expect(screen.getByRole("group", { name: "Reranker" })).toBeInTheDocument();
  });

  it("disables every control on a read-only graph", () => {
    setup({ id: "rr", operation: "select.rerank", version: 1, params: { enabled: false } }, { readOnly: true });
    expect(screen.getByRole("checkbox", { name: "Bypass this step" })).toBeDisabled();
    for (const radio of within(screen.getByRole("group", { name: "Reranker" })).getAllByRole("radio")) expect(radio).toBeDisabled();
    expect(within(screen.getByRole("group", { name: "Reranker" })).getByRole("radio", { name: "Off" })).toBeChecked();
  });
});
