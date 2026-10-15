/** Display labels for experiment and plugin states. Copy is British English. */
import type { ExperimentRecord } from "../api/experiments";

const PLUGIN_STATUS_LABELS: Record<string, string> = {
  compatible: "Compatible",
  incompatible: "Incompatible",
  unchecked: "Not checked",
  needs_approval: "Needs approval",
  unavailable: "Unavailable",
};

export type PluginBadgeVariant = "success" | "error" | "warning" | "neutral";

const PLUGIN_STATUS_VARIANTS: Record<string, PluginBadgeVariant> = {
  compatible: "success",
  incompatible: "error",
  unchecked: "neutral",
  needs_approval: "warning",
  unavailable: "error",
};

/** Names the plugin status. An unknown status keeps its raw value, so nothing reads as compatible by mistake. */
export function pluginStatusLabel(status: string): string {
  return PLUGIN_STATUS_LABELS[status] ?? `Unknown status (${status})`;
}

/** Only a known `compatible` status reads as success; an unknown one is neutral. */
export function pluginStatusVariant(status: string): PluginBadgeVariant {
  return PLUGIN_STATUS_VARIANTS[status] ?? "neutral";
}

export function contextLabel(record: Pick<ExperimentRecord, "context_id" | "name">): string {
  return record.name ? `${record.name} (${record.context_id})` : record.context_id;
}

export const WITHOUT_PLUGIN = "The workspace works without the plugin.";
