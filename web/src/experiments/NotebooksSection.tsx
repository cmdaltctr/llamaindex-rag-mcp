import { useQuery } from "@tanstack/react-query";
import { useMemo } from "react";
import { useApi } from "../api/ApiProvider";
import type { ExperimentList } from "../api/experiments";
import { pluginsQuery } from "../api/queries";
import { CredentialPanel } from "./CredentialPanel";
import { contextLabel } from "./labels";
import { NotebookPanel } from "./NotebookPanel";
import { PluginPanel } from "./PluginPanel";

/** Notebook tool registration, bound credentials and editor launch. */
export function NotebooksSection({ experiments }: { experiments: ExperimentList | undefined }) {
  const plugins = useQuery(pluginsQuery(useApi()));
  const entries = experiments?.experiments;
  const active = useMemo(() => (entries ?? []).map((entry) => entry.experiment).filter((record) => record.status === "active"), [entries]);
  const names = useMemo(() => Object.fromEntries((entries ?? []).map(({ experiment }) => [experiment.context_id, contextLabel(experiment)])), [entries]);

  return (
    <div className="flex flex-col gap-4">
      <PluginPanel list={plugins.data} loadError={plugins.isError ? plugins.error : null} loading={plugins.isPending} onRetry={() => void plugins.refetch()} />
      <CredentialPanel active={active} />
      <NotebookPanel list={plugins.data} loading={plugins.isPending} active={active} names={names} />
    </div>
  );
}
