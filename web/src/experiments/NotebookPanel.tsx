import type { ExperimentRecord } from "../api/experiments";
import type { PluginList } from "../api/plugins";
import { Badge } from "../components/ui/badge";
import { EditorList } from "./EditorList";
import { OpenEditorForm } from "./OpenEditorForm";
import { pluginStatusLabel, pluginStatusVariant, WITHOUT_PLUGIN } from "./labels";
import { Panel } from "./Panel";

interface NotebookPanelProps {
  list: PluginList | undefined;
  loading: boolean;
  active: ExperimentRecord[];
  names: Record<string, string>;
}

/**
 * Opens a registered notebook editor in a separate browser tab. Without a
 * compatible plugin, it shows the server's message and how to install the
 * editor outside OMRS. It never installs or updates anything.
 */
export function NotebookPanel({ list, loading, active, names }: NotebookPanelProps) {
  const launchable = (list?.plugins ?? []).filter((plugin) => plugin.launchable && plugin.status === "compatible");
  const blocked = (list?.plugins ?? []).filter((plugin) => !launchable.includes(plugin));

  return (
    <Panel title="Notebook editor" description="Opens a registered notebook tool in its own browser tab.">
      {list !== undefined && list.plugins.length === 0 ? <p className="text-ui">No notebook plugin is registered. Register one in the Plugins panel.</p> : null}
      {blocked.length > 0 ? (
        <ul aria-label="Plugins that cannot open an editor" className="flex flex-col gap-2">
          {blocked.map((plugin) => (
            <li key={plugin.name} className="flex flex-col gap-1">
              <span className="flex flex-wrap items-center gap-2">
                <strong>{plugin.display_name ?? plugin.name}</strong>
                <Badge variant={pluginStatusVariant(plugin.status)}>{pluginStatusLabel(plugin.status)}</Badge>
              </span>
              <p className="text-meta [overflow-wrap:anywhere]">{plugin.message}</p>
            </li>
          ))}
        </ul>
      ) : null}
      {launchable.length === 0 && !loading ? (
        <>
          {list?.install_hint ? <p className="text-meta [overflow-wrap:anywhere]">{list.install_hint}</p> : null}
          <p className="text-meta text-muted-foreground">{WITHOUT_PLUGIN}</p>
        </>
      ) : null}
      {launchable.length > 0 ? <OpenEditorForm plugins={launchable} active={active} /> : null}
      <EditorList editors={list?.editors ?? []} names={names} />
    </Panel>
  );
}
