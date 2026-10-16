import { Blocks, Cable, ListTree, Play, Settings2, SlidersHorizontal, type LucideIcon } from "lucide-react";

export type SectionId = "pipeline-settings" | "operations" | "nodes" | "connect" | "run" | "node-settings";

export interface PanelSection {
  id: SectionId;
  title: string;
  icon: LucideIcon;
}

/** The sections of the canvas panel, in display order. The rail uses the same order and icons. */
export const SECTIONS: readonly PanelSection[] = [
  { id: "pipeline-settings", title: "Pipeline settings", icon: SlidersHorizontal },
  { id: "operations", title: "Operations", icon: Blocks },
  { id: "nodes", title: "Nodes and connections", icon: ListTree },
  { id: "connect", title: "Connect ports", icon: Cable },
  { id: "run", title: "Revision and run", icon: Play },
  { id: "node-settings", title: "Node settings", icon: Settings2 },
];
