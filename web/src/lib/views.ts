import { Database, FlaskConical, House, MessageCircle, Plug, Settings, Workflow, type LucideIcon } from "lucide-react";
import { STUDIO_SUMMARY } from "../studio/profileCopy";
import { HOME, type Route, type RouteArea } from "./routes";

/** One of the seven workspace areas. Copy is British English. */
export interface AreaDefinition {
  id: RouteArea;
  label: string;
  /** Shown under the md breakpoint, where seven items share one row. */
  shortLabel: string;
  icon: LucideIcon;
  summary: string;
  /** Where the navigation link goes. */
  route: Route;
}

export const AREAS: readonly AreaDefinition[] = [
  { id: "home", label: "Home", shortLabel: "Home", icon: House, summary: "Your projects and their knowledge bases.", route: HOME },
  { id: "chat", label: "Chat", shortLabel: "Chat", icon: MessageCircle, summary: "Ask a knowledge base a question and check the cited evidence.", route: { area: "chat", collection: null, chatId: null } },
  { id: "knowledge-base", label: "Knowledge Base", shortLabel: "Data", icon: Database, summary: "Sources, search, uploads and the profile of a project.", route: { area: "knowledge-base", collection: null } },
  { id: "studio", label: "Studio", shortLabel: "Studio", icon: Workflow, summary: STUDIO_SUMMARY, route: { area: "studio", profileId: null, purpose: null } },
  { id: "experiments", label: "Experiments", shortLabel: "Labs", icon: FlaskConical, summary: "Experiment folders, notebooks and pipeline runs.", route: { area: "experiments", runId: null } },
  { id: "integrations", label: "Integrations", shortLabel: "Add-ons", icon: Plug, summary: "Optional integrations and how to install them.", route: { area: "integrations" } },
  { id: "settings", label: "Settings", shortLabel: "Settings", icon: Settings, summary: "Appearance, connections, MCP access, server log and runtime.", route: { area: "settings", section: null } },
];

export function areaById(id: RouteArea): AreaDefinition {
  const area = AREAS.find((candidate) => candidate.id === id);
  if (area === undefined) throw new Error(`Unknown area: ${id}`);
  return area;
}
