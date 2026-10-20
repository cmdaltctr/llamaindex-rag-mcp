/**
 * Reads an operation's parameter JSON schema (Pydantic output) into simple
 * form fields. A nullable parameter inherits its value when it is `null`.
 */
import type { JsonSchema, JsonValue, OperationDescriptor } from "../api/pipelines";
import { fieldLabel } from "./labels";

/** `json` is a JSON object, edited as text. */
export type FieldKind = "string" | "number" | "integer" | "boolean" | "enum" | "json" | "unsupported";

export interface ParamField {
  name: string;
  /** The schema title, for example "Top K". Shown in the Details area. */
  title: string;
  /** The plain label shown on cards and in Step settings, for example "Number of results". */
  label: string;
  description: string;
  kind: FieldKind;
  nullable: boolean;
  options: JsonValue[];
  minimum?: number;
  maximum?: number;
  exclusiveMinimum?: number;
  exclusiveMaximum?: number;
  defaultValue: JsonValue | undefined;
  /** Settings lever this parameter overrides, for example `retrieval.rerank_enabled`. */
  lever?: string;
  /** Choices the host cannot run, each with a reason. Empty for most fields. */
  unavailableOptions: Record<string, string>;
  /** Value the step inherits from the host when this field is empty, if the host reports one. */
  inheritedValue: JsonValue | undefined;
  /** True for the parameter that names the collection the step reads. */
  isCollection: boolean;
}

function resolve(schema: JsonSchema, root: JsonSchema): JsonSchema {
  const ref = schema.$ref;
  if (!ref?.startsWith("#/$defs/")) return schema;
  const target = root.$defs?.[ref.slice("#/$defs/".length)];
  return target ? { ...target, ...schema, $ref: undefined } : schema;
}

function kindOf(schema: JsonSchema): FieldKind {
  if (Array.isArray(schema.enum)) return "enum";
  switch (schema.type) {
    case "string":
    case "number":
    case "integer":
    case "boolean":
      return schema.type;
    case "object":
      return "json";
    default:
      return "unsupported";
  }
}

export function paramFields(operation: OperationDescriptor): ParamField[] {
  const root = operation.parameters;
  return Object.entries(root.properties ?? {}).map(([name, raw]) => {
    const property = resolve(raw, root);
    const variants = (property.anyOf ?? [property]).map((variant) => resolve(variant, root));
    const nullable = variants.some((variant) => variant.type === "null");
    const value = variants.find((variant) => variant.type !== "null") ?? property;
    const title = property.title ?? name;
    const lever = operation.lever_params[name];
    return {
      name,
      title,
      label: fieldLabel({ name, title, lever }),
      description: property.description ?? "",
      kind: kindOf(value),
      nullable,
      options: value.enum ?? [],
      minimum: value.minimum,
      maximum: value.maximum,
      exclusiveMinimum: value.exclusiveMinimum,
      exclusiveMaximum: value.exclusiveMaximum,
      defaultValue: property.default,
      lever,
      unavailableOptions: operation.unavailable_options[name] ?? {},
      inheritedValue: operation.inherited_values[name] as JsonValue | undefined,
      isCollection: operation.collection_param === name,
    };
  });
}

export type CheckResult = { value: JsonValue } | { error: string };

/** Checks text typed into a number field. Empty text means "inherit" (`null`). */
export function checkValue(field: ParamField, text: string): CheckResult {
  const trimmed = text.trim();
  if (trimmed === "") return { value: null };
  if (field.kind === "string" || field.kind === "enum") return { value: trimmed };
  const value = Number(trimmed);
  if (!Number.isFinite(value)) return { error: "Enter a number." };
  if (field.kind === "integer" && !Number.isInteger(value)) return { error: "Enter a whole number." };
  if (field.minimum !== undefined && value < field.minimum) return { error: `Enter a value of at least ${field.minimum}.` };
  if (field.maximum !== undefined && value > field.maximum) return { error: `Enter a value of at most ${field.maximum}.` };
  if (field.exclusiveMinimum !== undefined && value <= field.exclusiveMinimum) {
    return { error: `Enter a value greater than ${field.exclusiveMinimum}.` };
  }
  if (field.exclusiveMaximum !== undefined && value >= field.exclusiveMaximum) {
    return { error: `Enter a value less than ${field.exclusiveMaximum}.` };
  }
  return { value };
}
