import type { FetchLike } from "../api/client";
import type { ExperimentRecord } from "../api/experiments";
import type { LoadState } from "../views/shared/useLoad";
import type { PluginList } from "../api/plugins";
import { ErrorNotice } from "../views/shared/controls";
import { EditorList } from "./EditorList";
import { OpenEditorForm } from "./OpenEditorForm";
import { pluginStatusLabel, WITHOUT_PLUGIN } from "./labels";

interface NotebookPanelProps {
  plugins: LoadState<PluginList>;
  active: ExperimentRecord[];
  names: Record<string, string>;
  fetchImpl?: FetchLike;
}

/**
 * Opens a registered notebook editor in a separate browser tab. Without a
 * compatible plugin, it shows the server's message and how to install the
 * editor outside OMRG. It never installs or updates anything.
 */
export function NotebookPanel({ plugins, active, names, fetchImpl }: NotebookPanelProps) {
  const list = plugins.data;
  const launchable = (list?.plugins ?? []).filter((plugin) => plugin.launchable && plugin.status === "compatible");
  const blocked = (list?.plugins ?? []).filter((plugin) => !launchable.includes(plugin));

  return (
    <section className="panel" aria-labelledby="experiments-notebook">
      <h2 id="experiments-notebook" className="type-section-title">
        Notebook editor
      </h2>
      <ErrorNotice message={plugins.error === null ? null : `Could not load notebook plugins: ${plugins.error}`} />
      {list?.trust_notice ? <p className="server-text">{list.trust_notice}</p> : null}
      {list !== undefined && list.plugins.length === 0 ? <p>No notebook plugin is registered. Register one in Settings.</p> : null}
      {blocked.length > 0 ? (
        <ul className="plain-list" aria-label="Plugins that cannot open an editor">
          {blocked.map((plugin) => (
            <li key={plugin.name}>
              <strong>{plugin.display_name ?? plugin.name}</strong>: <span>{pluginStatusLabel(plugin.status)}</span>
              <p className="server-text">{plugin.message}</p>
            </li>
          ))}
        </ul>
      ) : null}
      {launchable.length === 0 && plugins.loading === false ? (
        <>
          {list?.install_hint ? <p className="server-text">{list.install_hint}</p> : null}
          <p className="type-meta">{WITHOUT_PLUGIN}</p>
        </>
      ) : null}
      {launchable.length > 0 ? (
        <OpenEditorForm plugins={launchable} active={active} fetchImpl={fetchImpl} onOpened={plugins.reload} />
      ) : null}
      <EditorList
        editors={list?.editors ?? []}
        names={names}
        fetchImpl={fetchImpl}
        onChanged={plugins.reload}
      />
    </section>
  );
}
