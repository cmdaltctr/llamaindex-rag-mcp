import { useState } from "react";
import { PageHeader } from "../components/PageHeader";
import { Button } from "../components/ui/button";
import { AppearanceSection } from "./AppearanceSection";
import { ConnectionsSection } from "./ConnectionsSection";
import { LogSection } from "./LogSection";
import { McpSection } from "./McpSection";
import { RuntimeSection } from "./RuntimeSection";
import { WorkspaceSection } from "./WorkspaceSection";

const SECTIONS = [
  { id: "appearance", label: "Appearance" },
  { id: "connections", label: "Connections" },
  { id: "mcp", label: "MCP" },
  { id: "log", label: "Server log" },
  { id: "runtime", label: "Runtime" },
  { id: "workspace", label: "Workspace" },
] as const;

type SectionId = (typeof SECTIONS)[number]["id"];

/** Settings. Sections are view state: one shows at a time and the route stays put. */
export function SettingsView() {
  const [section, setSection] = useState<SectionId>("appearance");
  return (
    <div className="flex flex-col gap-4">
      <PageHeader title="Settings" summary="Appearance, connections, MCP access, server log and runtime." />
      <div role="group" aria-label="Sections" className="flex flex-wrap gap-2">
        {SECTIONS.map(({ id, label }) => (
          <Button key={id} variant="chip" aria-pressed={section === id} onClick={() => setSection(id)}>
            {label}
          </Button>
        ))}
      </div>
      {section === "appearance" ? <AppearanceSection /> : null}
      {section === "connections" ? <ConnectionsSection /> : null}
      {section === "mcp" ? <McpSection /> : null}
      {section === "log" ? <LogSection /> : null}
      {section === "runtime" ? <RuntimeSection /> : null}
      {section === "workspace" ? <WorkspaceSection /> : null}
    </div>
  );
}
