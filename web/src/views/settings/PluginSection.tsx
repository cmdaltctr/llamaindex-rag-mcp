import { useState } from "react";
import type { FetchLike } from "../../api/client";
import { listPlugins, recheckPlugin, unregisterPlugin, type PluginState } from "../../api/plugins";
import { ConfirmAction } from "../../experiments/ConfirmAction";
import { pluginStatusLabel, WITHOUT_PLUGIN } from "../../experiments/labels";
import { ErrorNotice } from "../shared/controls";
import { messageOf } from "../shared/labels";
import { useLoad } from "../shared/useLoad";
import { PluginRegisterForm } from "./PluginRegisterForm";

interface PluginSectionProps {
  fetchImpl?: FetchLike;
}

function pluginName(plugin: PluginState): string {
  return plugin.display_name ? `${plugin.display_name} (${plugin.name})` : plugin.name;
}

/** Notebook plugin states with register, recheck and unregister. OMRG never installs or updates a plugin. */
export function PluginSection({ fetchImpl }: PluginSectionProps) {
  const plugins = useLoad(() => listPlugins({ fetchImpl }), "plugins");
  const [rechecked, setRechecked] = useState<Record<string, PluginState>>({});
  const [error, setError] = useState<string | null>(null);
  const rows = (plugins.data?.plugins ?? []).map((plugin) => rechecked[plugin.name] ?? plugin);

  /** Reloads from the server; a later listing replaces earlier recheck results. */
  function reload() {
    setRechecked({});
    plugins.reload();
  }

  async function recheck(name: string) {
    setError(null);
    try {
      const state = await recheckPlugin(name, { fetchImpl });
      setRechecked((current) => ({ ...current, [name]: state }));
    } catch (failure) {
      setError(messageOf(failure));
    }
  }

  return (
    <section className="panel" aria-labelledby="settings-plugins">
      <h2 id="settings-plugins" className="type-section-title">
        Plugins
      </h2>
      <ErrorNotice message={plugins.error === null ? null : `Could not load plugins: ${plugins.error}`} />
      {plugins.data ? <p className="notice notice--warning server-text">{plugins.data.trust_notice}</p> : null}
      {plugins.data ? <p className="server-text">{plugins.data.install_hint}</p> : null}
      {rows.length === 0 ? (
        <div className="empty-state empty-state--compact" data-testid="empty-state">
          <p className="empty-state__title">{plugins.loading ? "Loading plugins" : "No plugin is registered"}</p>
          <p className="type-meta">{WITHOUT_PLUGIN}</p>
        </div>
      ) : null}
      <ErrorNotice message={error} />
      {rows.length > 0 ? (
        <div className="table-scroll">
          <table className="data-table" aria-label="Registered plugins">
            <thead>
              <tr>
                <th scope="col">Plugin</th>
                <th scope="col">Status</th>
                <th scope="col">Detail</th>
                <th scope="col">Version</th>
                <th scope="col">Executable</th>
                <th scope="col">Manage</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((plugin) => (
                <tr key={plugin.name}>
                  <td>{pluginName(plugin)}</td>
                  <td>{pluginStatusLabel(plugin.status)}</td>
                  <td className="server-text">{plugin.message}</td>
                  <td>{plugin.version ?? "Unknown"}</td>
                  <td className="type-code" dir="ltr">
                    {plugin.executable}
                  </td>
                  <td>
                    <div className="button-row">
                      <button
                        type="button"
                        className="button button--small button--ghost"
                        aria-label={`Recheck ${plugin.name}`}
                        onClick={() => void recheck(plugin.name)}
                      >
                        Recheck
                      </button>
                      <ConfirmAction
                        label={`Unregister ${plugin.name}`}
                        text="Unregister"
                        warning="Unregistering removes only this registration. Stop its editors first. Files are not touched."
                        confirmLabel="Confirm unregister"
                        cancelLabel="Keep plugin"
                        onConfirm={async () => {
                          await unregisterPlugin(plugin.name, { fetchImpl });
                          reload();
                        }}
                      />
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
      <PluginRegisterForm fetchImpl={fetchImpl} onRegistered={reload} />
    </section>
  );
}
