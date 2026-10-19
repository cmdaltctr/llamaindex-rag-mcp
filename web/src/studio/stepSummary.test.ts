import { describe, expect, it } from "vitest";
import type { EffectiveControl, NodeSpec, OperationDescriptor } from "../api/pipelines";
import { paramFields } from "./schema";
import { cardLines, firstSentence, mainSettings, settingValue } from "./stepSummary";
import { CATALOGUE } from "./test/catalogueFixture";

function operation(id: string): OperationDescriptor {
  const found = CATALOGUE.find((entry) => entry.operation_id === id);
  if (found === undefined) throw new Error(id);
  return found;
}

function field(id: string, name: string) {
  const found = paramFields(operation(id)).find((candidate) => candidate.name === name);
  if (found === undefined) throw new Error(`${id}.${name}`);
  return found;
}

const NODE: NodeSpec = { id: "prepare", operation: "retrieve.prepare_query" };
const NO_OVERRIDES = { collection: null, overrides: {} };

function control(lever: string, value: EffectiveControl["value"], source: string): EffectiveControl {
  return { lever, value, source, detail: "detail text" };
}

describe("mainSettings", () => {
  it("takes three settings in catalogue order, puts the collection last and counts the rest", () => {
    const { shown, more } = mainSettings(operation("retrieve.prepare_query"));
    expect(shown.map((entry) => entry.name)).toEqual(["top_k", "similarity_threshold", "rerank"]);
    expect(more).toBe(2);
  });

  it("also returns the left-over settings, in order, as rest", () => {
    const { rest } = mainSettings(operation("retrieve.prepare_query"));
    expect(rest.map((entry) => entry.name)).toEqual(["fetch_k", "collection"]);
    expect(mainSettings(operation("retrieve.dense")).rest).toEqual([]);
  });

  it("shows the collection when it is the only setting", () => {
    const { shown, more } = mainSettings(operation("retrieve.dense"));
    expect(shown.map((entry) => entry.name)).toEqual(["collection"]);
    expect(more).toBe(0);
  });

  it("gives nothing for a step without parameters", () => {
    expect(mainSettings(operation("select.threshold"))).toEqual({ shown: [], rest: [], more: 0 });
  });

  it("does not count a setting that the canvas cannot edit", () => {
    // Prepare query has six parameters; Metadata filter is unsupported, so five are editable: three shown, two more.
    expect(paramFields(operation("retrieve.prepare_query"))).toHaveLength(6);
    expect(mainSettings(operation("retrieve.prepare_query")).more).toBe(2);
  });
});

describe("settingValue", () => {
  const topK = field("retrieve.prepare_query", "top_k");
  const rerank = field("retrieve.prepare_query", "rerank");

  it("1. shows a value set on the step", () => {
    const node = { ...NODE, params: { rerank: false } };
    expect(settingValue(rerank, node, control("retrieval.rerank_enabled", true, "profile"), NO_OVERRIDES)).toBe("Off (set here)");
  });

  it("2. shows the value of a current check with its source", () => {
    expect(settingValue(topK, NODE, control("retrieval.top_k", 10, "profile"), NO_OVERRIDES)).toBe("10 (from profile)");
    expect(settingValue(topK, NODE, control("retrieval.top_k", 4, "environment"), NO_OVERRIDES)).toBe("4 (from server settings)");
    expect(settingValue(topK, NODE, control("retrieval.top_k", 7, "graph"), NO_OVERRIDES)).toBe("7 (from pipeline settings)");
    expect(settingValue(topK, NODE, control("retrieval.top_k", 3, "node"), NO_OVERRIDES)).toBe("3 (set here)");
  });

  it("3. shows a graph override when no check value exists", () => {
    const graph = { collection: null, overrides: { "retrieval.top_k": 5 } };
    expect(settingValue(topK, NODE, undefined, graph)).toBe("5 (from pipeline settings)");
  });

  it("4. says the value comes from the profile while it is not known", () => {
    expect(settingValue(topK, NODE, undefined, NO_OVERRIDES)).toBe("From profile");
  });

  it("5. names the pipeline collection, or the server default", () => {
    const collection = field("retrieve.dense", "collection");
    const dense: NodeSpec = { id: "dense", operation: "retrieve.dense" };
    expect(settingValue(collection, dense, undefined, { collection: "docs", overrides: {} })).toBe("docs (from pipeline settings)");
    expect(settingValue(collection, dense, undefined, NO_OVERRIDES)).toBe("Server default");
  });

  it("6. shows a schema default", () => {
    const expand = field("context.assemble", "expand_window");
    expect(settingValue(expand, { id: "assemble", operation: "context.assemble" }, undefined, NO_OVERRIDES)).toBe("0 (default)");
  });

  it("7. says Default when nothing else is known", () => {
    const fetchK = field("retrieve.prepare_query", "fetch_k");
    expect(settingValue(fetchK, NODE, undefined, NO_OVERRIDES)).toBe("Default");
  });

  it("shows an option by its readable label", () => {
    const taxonomy = field("prepare.enrich", "taxonomy_mode");
    const node: NodeSpec = { id: "enrich", operation: "prepare.enrich", params: { taxonomy_mode: "file_type" } };
    expect(settingValue(taxonomy, node, undefined, NO_OVERRIDES)).toBe("File type (set here)");
  });
});

describe("firstSentence", () => {
  it("cuts the text after the first full stop that ends a sentence", () => {
    expect(firstSentence("Opt-in claim check with the judge model. A missing judge reports a reason.")).toBe(
      "Opt-in claim check with the judge model.",
    );
  });

  it("returns the whole text when it has one sentence", () => {
    expect(firstSentence("Fuse one dense and one sparse ranking.")).toBe("Fuse one dense and one sparse ranking.");
    expect(firstSentence("No full stop here")).toBe("No full stop here");
  });
});

describe("cardLines", () => {
  it("gives the extra settings with their values, and counts them", () => {
    const lines = cardLines(operation("retrieve.prepare_query"), NODE, undefined, { collection: "docs", overrides: {} });
    expect(lines.moreSettings).toBe(2);
    expect(lines.extraSettings).toEqual([
      { label: "Candidates to fetch", value: "Default" },
      { label: "Collection", value: "docs (from pipeline settings)" },
    ]);
  });

  it("gives no extra settings for a step that shows them all", () => {
    expect(cardLines(operation("retrieve.dense"), { id: "d", operation: "retrieve.dense" }, undefined, { collection: null, overrides: {} }).extraSettings).toEqual([]);
  });
});
