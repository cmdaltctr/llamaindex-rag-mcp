import { RefreshCw } from "lucide-react";
import type { PluginList, PluginState } from "../api/plugins";
import { ErrorNotice } from "../components/ErrorNotice";
import { Badge } from "../components/ui/badge";
import { Button } from "../components/ui/button";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "../components/ui/table";
import { ConfirmAction } from "./ConfirmAction";
import { pluginStatusLabel, pluginStatusVariant, WITHOUT_PLUGIN } from "./labels";
import { useRecheckPlugin, useUnregisterPlugin } from "./mutations";
import { Panel } from "./Panel";
import { PluginRegisterForm } from "./PluginRegisterForm";

function pluginName(plugin: PluginState): string {
  return plugin.display_name ? `${plugin.display_name} (${plugin.name})` : plugin.name;
}

interface PluginPanelProps {
  list: PluginList | undefined;
  loadError: unknown;
  loading: boolean;
  onRetry: () => void;
}

/** Notebook plugin states with register, recheck and unregister. OMRS never installs or updates a plugin. */
export function PluginPanel({ list, loadError, loading, onRetry }: PluginPanelProps) {
  const recheck = useRecheckPlugin();
  const unregister = useUnregisterPlugin();
  const rows = list?.plugins ?? [];

  return (
    <Panel title="Plugins" description="A plugin is a notebook tool that you approve. It runs only when you open an editor.">
      {loadError !== null ? <ErrorNotice error={loadError} onRetry={onRetry} /> : null}
      {list ? <p className="text-meta [overflow-wrap:anywhere]">{list.install_hint}</p> : null}
      {rows.length === 0 ? (
        <p className="text-meta text-muted-foreground">
          {loading ? "Loading plugins." : `No plugin is registered. ${WITHOUT_PLUGIN}`}
        </p>
      ) : (
        <Table aria-label="Registered plugins">
          <TableHeader>
            <TableRow>
              <TableHead scope="col">Plugin</TableHead>
              <TableHead scope="col">Status</TableHead>
              <TableHead scope="col">Detail</TableHead>
              <TableHead scope="col">Version</TableHead>
              <TableHead scope="col">Executable</TableHead>
              <TableHead scope="col">Manage</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {rows.map((plugin) => (
              <TableRow key={plugin.name}>
                <TableCell>{pluginName(plugin)}</TableCell>
                <TableCell>
                  <Badge variant={pluginStatusVariant(plugin.status)}>{pluginStatusLabel(plugin.status)}</Badge>
                </TableCell>
                <TableCell className="min-w-48 whitespace-normal [overflow-wrap:anywhere]">{plugin.message}</TableCell>
                <TableCell>{plugin.version ?? "Unknown"}</TableCell>
                <TableCell dir="ltr" className="font-mono text-code [overflow-wrap:anywhere]">
                  {plugin.executable}
                </TableCell>
                <TableCell>
                  <div className="flex flex-wrap items-start gap-2">
                    <Button variant="ghost" size="sm" aria-label={`Recheck ${plugin.name}`} onClick={() => recheck.mutate(plugin.name)}>
                      <RefreshCw aria-hidden="true" />
                      Recheck
                    </Button>
                    <ConfirmAction
                      label={`Unregister ${plugin.name}`}
                      text="Unregister"
                      warning="Unregistering removes only this registration. Stop its editors first. Files are not touched."
                      confirmLabel="Confirm unregister"
                      cancelLabel="Keep plugin"
                      onConfirm={() => unregister.mutateAsync(plugin.name)}
                    />
                  </div>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}
      {recheck.isError ? <ErrorNotice error={recheck.error} /> : null}
      <PluginRegisterForm />
    </Panel>
  );
}
