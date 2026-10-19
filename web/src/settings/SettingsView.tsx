import { PageHeader } from "../components/PageHeader";
import { Button } from "../components/ui/button";
import { useRoute } from "../lib/RouteProvider";
import type { SettingsSection } from "../lib/routes";
import { AppearanceSection } from "./AppearanceSection";
import { ChatSection } from "./ChatSection";
import { ConfigurationSection } from "./ConfigurationSection";
import { LogSection } from "./LogSection";
import { McpSection } from "./McpSection";
import { ProvidersSection } from "./ProvidersSection";
import { RuntimeSection } from "./RuntimeSection";
import { WorkspaceSection } from "./WorkspaceSection";

const SECTIONS: { id: SettingsSection; label: string }[] = [
  { id: "appearance", label: "Appearance" },
  { id: "providers", label: "Providers" },
  { id: "chat", label: "Chat" },
  { id: "mcp", label: "MCP" },
  { id: "log", label: "Server log" },
  { id: "runtime", label: "Runtime" },
  { id: "workspace", label: "Workspace" },
  { id: "configuration", label: "Configuration" },
];

/** Settings. The address names the section (`#/settings/<section>`); `#/settings` shows Appearance. */
export function SettingsView() {
  const { route, navigate } = useRoute();
  const section: SettingsSection = (route.area === "settings" ? route.section : null) ?? "appearance";
  const setSection = (next: SettingsSection) => navigate({ area: "settings", section: next });
  return (
    <div className="flex flex-col gap-4">
      <PageHeader title="Settings" summary="Appearance, providers, Chat model, MCP access, server log, runtime and the settings file." />
      <div role="group" aria-label="Sections" className="flex flex-wrap gap-2">
        {SECTIONS.map(({ id, label }) => (
          <Button key={id} variant="chip" aria-pressed={section === id} onClick={() => setSection(id)}>
            {label}
          </Button>
        ))}
      </div>
      {section === "appearance" ? <AppearanceSection /> : null}
      {section === "providers" ? <ProvidersSection /> : null}
      {section === "chat" ? <ChatSection /> : null}
      {section === "mcp" ? <McpSection /> : null}
      {section === "log" ? <LogSection /> : null}
      {section === "runtime" ? <RuntimeSection /> : null}
      {section === "workspace" ? <WorkspaceSection /> : null}
      {section === "configuration" ? <ConfigurationSection /> : null}
    </div>
  );
}
