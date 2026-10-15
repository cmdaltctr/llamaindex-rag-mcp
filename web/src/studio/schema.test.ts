import { describe, expect, it } from "vitest";
import { checkValue, paramFields } from "./schema";
import { CATALOGUE } from "./test/catalogueFixture";

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
    expect(prepare.metadata_filter?.kind).toBe("unsupported");
  });

  it("reads enums", () => {
    expect(fields("prepare.enrich").taxonomy_mode).toMatchObject({
      kind: "enum",
      options: ["category", "file_type"],
      nullable: true,
      lever: "metadata.taxonomy_mode",
    });
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
