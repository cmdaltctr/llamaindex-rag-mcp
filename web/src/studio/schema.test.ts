import { describe, expect, it } from "vitest";
import { mappedFieldLabel, optionLabel } from "./labels";
import { checkValue, paramFields } from "./schema";
import { CATALOGUE } from "./test/catalogueFixture";
import { CATALOGUE_INGEST } from "./test/catalogueIngest";

function fields(id: string) {
  const found = CATALOGUE.find((entry) => entry.operation_id === id);
  if (found === undefined) throw new Error(id);
  return Object.fromEntries(paramFields(found).map((field) => [field.name, field]));
}

describe("parameter schema", () => {
  it("reads nullable integers, numbers and booleans with bounds and levers", () => {
    const prepare = fields("retrieve.prepare_query");
    expect(prepare.top_k).toMatchObject({ kind: "integer", nullable: true, minimum: 1, lever: "retrieval.top_k" });
    expect(prepare.similarity_threshold).toMatchObject({ kind: "number", minimum: 0, maximum: 1 });
    expect(prepare.rerank).toMatchObject({ kind: "boolean", nullable: true, lever: "retrieval.rerank_enabled" });
    expect(prepare.collection).toMatchObject({ kind: "string", nullable: true });
    expect(prepare.metadata_filter).toMatchObject({ kind: "json", nullable: true, label: "Metadata filter" });
  });

  it("reads enums", () => {
    expect(fields("prepare.enrich").taxonomy_mode).toMatchObject({
      kind: "enum",
      options: ["category", "file_type"],
      nullable: true,
      lever: "metadata.taxonomy_mode",
    });
  });

  it("reads the PDF reader as a nullable enum with unavailable choices and the inherited value", () => {
    const read = CATALOGUE_INGEST.find((entry) => entry.operation_id === "read.document");
    if (read === undefined) throw new Error("read.document");
    const field = paramFields(read).find((entry) => entry.name === "pdf_reader");
    expect(field).toMatchObject({
      kind: "enum",
      nullable: true,
      options: ["liteparse", "pdf_inspector", "pypdf", "pypdfium2"],
      unavailableOptions: { pypdfium2: "The package 'pypdfium2' is not installed." },
      inheritedValue: "pdf_inspector",
    });
  });

  it("gives other fields no unavailable choices and no inherited value", () => {
    const prepare = fields("retrieve.prepare_query");
    expect(prepare.top_k).toMatchObject({ unavailableOptions: {}, inheritedValue: undefined });
  });

  it("resolves local $ref definitions", () => {
    const [field] = paramFields({
      ...CATALOGUE[0]!,
      lever_params: {},
      parameters: {
        type: "object",
        $defs: { Mode: { enum: ["a", "b"], type: "string" } },
        properties: { mode: { $ref: "#/$defs/Mode", default: "a" } },
      },
    });
    expect(field).toMatchObject({ kind: "enum", options: ["a", "b"], nullable: false, defaultValue: "a" });
  });

  it("checks values against the schema", () => {
    const prepare = fields("retrieve.prepare_query");
    expect(checkValue(prepare.top_k!, "0")).toEqual({ error: "Enter a value of at least 1." });
    expect(checkValue(prepare.top_k!, "2.5")).toEqual({ error: "Enter a whole number." });
    expect(checkValue(prepare.top_k!, "abc")).toEqual({ error: "Enter a number." });
    expect(checkValue(prepare.top_k!, "8")).toEqual({ value: 8 });
    expect(checkValue(prepare.similarity_threshold!, "1.5")).toEqual({ error: "Enter a value of at most 1." });
    expect(checkValue(prepare.similarity_threshold!, "0.25")).toEqual({ value: 0.25 });
    expect(checkValue(prepare.top_k!, "")).toEqual({ value: null });
  });
});

describe("plain labels", () => {
  it("names the main settings in plain words", () => {
    const prepare = fields("retrieve.prepare_query");
    expect(prepare.top_k!.label).toBe("Number of results");
    expect(prepare.similarity_threshold!.label).toBe("Minimum similarity");
    expect(prepare.rerank!.label).toBe("Reranker");
    expect(fields("select.rerank").enabled!.label).toBe("Reranker");
    expect(fields("combine.rrf").rrf_k!.label).toBe("Fusion constant (k)");
  });

  it("gives an array parameter no control", () => {
    const [field] = paramFields({ ...CATALOGUE[0]!, lever_params: {}, parameters: { type: "object", properties: { tags: { type: "array", title: "Tags" } } } });
    expect(field!.kind).toBe("unsupported");
  });

  it("names the PDF reader in plain words", () => {
    const reader = paramFields(CATALOGUE_INGEST.find((op) => op.operation_id === "read.document")!).find((field) => field.name === "pdf_reader");
    expect(reader!.label).toBe("PDF reader");
  });

  it("keeps the schema title on the field", () => {
    expect(fields("retrieve.prepare_query").top_k).toMatchObject({ title: "Top K", label: "Number of results" });
  });

  it("falls back to the schema title in sentence case for a field without a label", () => {
    const [field] = paramFields({
      ...CATALOGUE[0]!,
      lever_params: {},
      parameters: { type: "object", properties: { widget_count: { type: "integer", title: "Widget Count" } } },
    });
    expect(field!.label).toBe("Widget count");
  });

  it("takes the label of every fixture parameter from the map, not from the fallback", () => {
    const unmapped = CATALOGUE.flatMap((operation) =>
      paramFields(operation)
        .filter((field) => mappedFieldLabel(field) === undefined)
        .map((field) => `${operation.operation_id}.${field.name}`),
    );
    expect(unmapped).toEqual([]);
  });

  it("maps option values to readable labels and keeps an unmapped value as it is", () => {
    const taxonomy = fields("prepare.enrich").taxonomy_mode!;
    expect(optionLabel(taxonomy, "category")).toBe("Category");
    expect(optionLabel(taxonomy, "file_type")).toBe("File type");
    expect(optionLabel(taxonomy, "other_value")).toBe("other_value");
    const fallback = { name: "strategy_fallback", title: "Strategy Fallback", lever: "chunking.strategy_fallback" };
    expect(optionLabel(fallback, "markdown")).toBe("Markdown");
    expect(optionLabel(fallback, "code")).toBe("Code");
    expect(optionLabel(fallback, "sentence")).toBe("Sentences");
  });
});
