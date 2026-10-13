/** Display labels for experiment and plugin states. Copy is British English. */
import type { ExperimentRecord } from "../api/experiments";

const PLUGIN_STATUS_LABELS: Record<string, string> = {
  compatible: "Compatible",
  incompatible: "Incompatible",
  unchecked: "Not checked",
  needs_approval: "Needs approval",
  unavailable: "Unavailable",
};

/** Names the plugin status. An unknown status keeps its raw value, so nothing reads as compatible by mistake. */
export function pluginStatusLabel(status: string): string {
  return PLUGIN_STATUS_LABELS[status] ?? `Unknown status (${status})`;
}

export function contextLabel(record: Pick<ExperimentRecord, "context_id" | "name">): string {
  return record.name ? `${record.name} (${record.context_id})` : record.context_id;
}

export const WITHOUT_PLUGIN = "The workspace works without the plugin.";
