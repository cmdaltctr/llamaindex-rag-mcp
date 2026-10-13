import type { FetchLike } from "../../api/client";
import { getHealth } from "../../api/client";
import { getSession, listRoots, type Root } from "../../api/documents";
import { listOperations } from "../../api/pipelines";
import { ThemeSelect } from "../../components/ThemeSelect";
import type { ThemePreference } from "../../lib/preferences";
import { ErrorNotice, ViewHeader } from "../shared/controls";
import { useLoad } from "../shared/useLoad";
import "../views.css";
import { PluginSection } from "./PluginSection";
import { RuntimeSection } from "./RuntimeSection";

interface SettingsViewProps {
  fetchImpl?: FetchLike;
  focusHeading?: boolean;
  theme: ThemePreference;
  onThemeChange: (theme: ThemePreference) => void;
}

const ROOT_KINDS: Record<Root["kind"], string> = { operator: "Approved at launch", managed: "Managed uploads" };

/** Workspace facts and plugin registration. It never edits `.env` and never switches models or providers. */
export function SettingsView({ fetchImpl, focusHeading = false, theme, onThemeChange }: SettingsViewProps) {
  const roots = useLoad(() => listRoots({ fetchImpl }), "roots");
  const health = useLoad(() => getHealth(fetchImpl), "health");
  const session = useLoad(() => getSession({ fetchImpl }), "session");
  const operations = useLoad(() => listOperations({ fetchImpl }), "operations");
  const workspace = session.data?.workspace ?? null;

  return (
    <section className="view view--documents" aria-labelledby="view-settings-title">
      <ViewHeader id="settings" focusHeading={focusHeading} />
      <p className="notice">
        Settings does not edit .env and does not switch models or providers. Change the environment, then restart omrg web. The
        only change made here is notebook plugin registration.
      </p>

      <section className="panel" aria-labelledby="settings-workspace">
        <h2 id="settings-workspace" className="text-section-title">
          Workspace
        </h2>
        {workspace !== null ? (
          <code dir="ltr">{workspace}</code>
        ) : (
          <p className="text-meta">{session.loading ? "Loading." : "The server did not report the workspace folder."}</p>
        )}
      </section>

      <RuntimeSection health={health} session={session} operations={operations} />

      <section className="panel" aria-labelledby="settings-files">
        <h2 id="settings-files" className="text-section-title">
          File access
        </h2>
        <p className="text-meta">Only these folders are readable. Paths stored in the index never grant access.</p>
        <ErrorNotice message={roots.error === null ? null : `Could not load file access: ${roots.error}`} />
        {roots.data ? (
          <div className="table-scroll">
            <table className="data-table" aria-label="File access">
              <thead>
                <tr>
                  <th scope="col">Folder</th>
                  <th scope="col">Kind</th>
                  <th scope="col">ID</th>
                </tr>
              </thead>
              <tbody>
                {roots.data.map((root) => (
                  <tr key={root.id}>
                    <td className="text-code" dir="ltr">
                      {root.path}
                    </td>
                    <td>{ROOT_KINDS[root.kind] ?? root.kind}</td>
                    <td className="text-code">{root.id}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : null}
      </section>

      <section className="panel" aria-labelledby="settings-appearance">
        <h2 id="settings-appearance" className="text-section-title">
          Appearance
        </h2>
        <ThemeSelect value={theme} onChange={onThemeChange} />
      </section>

      <PluginSection fetchImpl={fetchImpl} />
    </section>
  );
}
