/**
 * The text a step card and Step settings show for a step: its main settings,
 * the value of each setting with where it comes from, and the one-line summary.
 * Pure functions, so a unit test covers them without React Flow.
 */
import type { EffectiveControl, JsonValue, NodeSpec, OperationDescriptor } from "../api/pipelines";
import { optionLabel } from "./labels";
import { paramFields, type ParamField } from "./schema";

/** The settings of the draft's graph that change a value: its collection and its overrides. */
export interface GraphSettings {
  collection: string | null;
  overrides: Record<string, JsonValue>;
}

const MAIN_SETTINGS = 3;

const SOURCE_TEXT: Record<string, string> = {
  node: "set here",
  graph: "from pipeline settings",
  environment: "from server settings",
  profile: "from profile",
};

/**
 * The first three editable settings in catalogue order, with the collection
 * setting last, then the editable settings left over (`rest`) and their number.
 */
export function mainSettings(operation: OperationDescriptor): { shown: ParamField[]; rest: ParamField[]; more: number } {
  const editable = paramFields(operation).filter((field) => field.kind !== "unsupported");
  const ordered = [...editable.filter((field) => !field.isCollection), ...editable.filter((field) => field.isCollection)];
  const rest = ordered.slice(MAIN_SETTINGS);
  return { shown: ordered.slice(0, MAIN_SETTINGS), rest, more: rest.length };
}

/** The control that a check reported for the field's lever, if any. */
export function controlFor(field: ParamField, controls: readonly EffectiveControl[] | undefined): EffectiveControl | undefined {
  return field.lever === undefined ? undefined : controls?.find((control) => control.lever === field.lever);
}

/** A value as the user reads it: On or Off, the option label, or plain text. */
export function formatValue(field: ParamField, value: JsonValue): string {
  if (value === true) return "On";
  if (value === false) return "Off";
  if (field.kind === "enum") return optionLabel(field, value);
  return typeof value === "string" ? value : JSON.stringify(value);
}

export function sourceText(source: string): string {
  return SOURCE_TEXT[source] ?? source;
}

/** The rule (1 to 7, see design D4) that gave the text, and the text. */
function resolveSetting(
  field: ParamField,
  node: NodeSpec,
  control: EffectiveControl | undefined,
  graph: GraphSettings,
): { rule: number; text: string } {
  const own = node.params?.[field.name];
  if (own !== undefined && own !== null) return { rule: 1, text: `${formatValue(field, own)} (set here)` };
  if (field.lever !== undefined) {
    if (control !== undefined) return { rule: 2, text: `${formatValue(field, control.value)} (${sourceText(control.source)})` };
    const override = graph.overrides[field.lever];
    if (override !== undefined) return { rule: 3, text: `${formatValue(field, override)} (from pipeline settings)` };
    return { rule: 4, text: "From profile" };
  }
  if (field.isCollection) return { rule: 5, text: graph.collection ? `${graph.collection} (from pipeline settings)` : "Server default" };
  if (field.defaultValue !== undefined && field.defaultValue !== null) return { rule: 6, text: `${formatValue(field, field.defaultValue)} (default)` };
  return { rule: 7, text: "Default" };
}

/** The value in use, or the reason it is not known yet. The first matching rule wins. */
export function settingValue(
  field: ParamField,
  node: NodeSpec,
  control: EffectiveControl | undefined,
  graph: GraphSettings,
): string {
  return resolveSetting(field, node, control, graph).text;
}

/** The note under a control in Step settings, or `null` when the setting has no value source to name. */
export function valueNote(
  field: ParamField,
  node: NodeSpec,
  control: EffectiveControl | undefined,
  graph: GraphSettings,
): string | null {
  const { rule, text } = resolveSetting(field, node, control, graph);
  if (rule <= 3) return `Value in use: ${text}`;
  if (rule === 4) return "Comes from the profile. The value shows when the check finishes.";
  return null;
}

/** The text up to and including the first full stop that ends a sentence, or all of it. */
export function firstSentence(text: string): string {
  const end = text.indexOf(". ");
  return end === -1 ? text : text.slice(0, end + 1);
}

export interface CardLines {
  summary: string;
  settings: { label: string; value: string }[];
  /** The other editable settings, shown when the user expands the mini card. */
  extraSettings: { label: string; value: string }[];
  /** The number of extra settings. */
  moreSettings: number;
}

/** What a step card shows below the title: the one-line summary and the main settings with their values. */
export function cardLines(
  operation: OperationDescriptor,
  node: NodeSpec,
  controls: readonly EffectiveControl[] | undefined,
  graph: GraphSettings,
): CardLines {
  const { shown, rest, more } = mainSettings(operation);
  const line = (field: ParamField) => ({ label: field.label, value: settingValue(field, node, controlFor(field, controls), graph) });
  return { summary: firstSentence(operation.description), settings: shown.map(line), extraSettings: rest.map(line), moreSettings: more };
}
