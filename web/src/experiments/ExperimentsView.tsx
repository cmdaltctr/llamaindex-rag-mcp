import { useMemo } from "react";
import type { FetchLike } from "../api/client";
import { listExperiments } from "../api/experiments";
import { listPlugins } from "../api/plugins";
import { ErrorNotice, ViewHeader } from "../views/shared/controls";
import { useLoad } from "../views/shared/useLoad";
import { ContextTable } from "./ContextTable";
import { CredentialPanel } from "./CredentialPanel";
import { ExperimentRuns } from "./ExperimentRuns";
import { contextLabel } from "./labels";
import { NotebookPanel } from "./NotebookPanel";
import { RegisterForm } from "./RegisterForm";

interface ExperimentsViewProps {
  fetchImpl?: FetchLike;
  focusHeading?: boolean;
}

/** Experiment workspaces, bound notebook credentials, the optional notebook editor and experiment runs. */
export function ExperimentsView({ fetchImpl, focusHeading = false }: ExperimentsViewProps) {
  const experiments = useLoad(() => listExperiments({ fetchImpl }), "experiments");
  const plugins = useLoad(() => listPlugins({ fetchImpl }), "plugins");
  const entries = useMemo(() => experiments.data?.experiments ?? [], [experiments.data]);
  const active = entries.map((entry) => entry.experiment).filter((record) => record.status === "active");
  const names = useMemo(
    () => Object.fromEntries(entries.map(({ experiment }) => [experiment.context_id, contextLabel(experiment)])),
    [entries],
  );
  const trustNotice = experiments.data?.trust_notice ?? plugins.data?.trust_notice ?? null;

  return (
    <section className="view view--documents" aria-labelledby="view-experiments-title">
      <ViewHeader id="experiments" focusHeading={focusHeading} />
      <section className="notice notice--warning trust-notice" aria-label="Trust notice">
        <h2 className="type-section-title">Trust notice</h2>
        {trustNotice !== null ? <p className="server-text">{trustNotice}</p> : <p className="type-meta">Loading the trust notice.</p>}
      </section>

      <RegisterForm roots={experiments.data?.roots} fetchImpl={fetchImpl} onRegistered={experiments.reload} />

      <section className="panel" aria-labelledby="experiments-contexts">
        <h2 id="experiments-contexts" className="type-section-title">
          Experiment contexts
        </h2>
        <ErrorNotice message={experiments.error === null ? null : `Could not load experiment contexts: ${experiments.error}`} />
        <ContextTable entries={entries} fetchImpl={fetchImpl} onChanged={experiments.reload} />
      </section>

      <CredentialPanel active={active} fetchImpl={fetchImpl} />
      <NotebookPanel plugins={plugins} active={active} names={names} fetchImpl={fetchImpl} />
      <ExperimentRuns fetchImpl={fetchImpl} names={names} />
    </section>
  );
}
