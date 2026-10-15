import type { ExperimentEntry } from "../api/experiments";
import { Badge } from "../components/ui/badge";
import { ConfirmAction } from "./ConfirmAction";
import { useRevokeExperiment } from "./mutations";

/** One registered sub-experiment: status, declared factors, permitted actions and backend identity. */
export function ExperimentRow({ entry }: { entry: ExperimentEntry }) {
  const revoke = useRevokeExperiment();
  const { experiment, identity } = entry;
  const name = experiment.name || experiment.context_id;
  const active = experiment.status === "active";
  return (
    <div role="group" aria-label={`Experiment ${name}`} className="flex flex-col gap-2 rounded-small border border-border bg-card p-3">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
        <span className="font-medium break-words">{name}</span>
        <Badge variant={active ? "success" : "neutral"}>{experiment.status}</Badge>
        <code dir="ltr" className="font-mono text-code text-muted-foreground">
          {experiment.context_id}
        </code>
        {active ? (
          <span className="ms-auto">
            <ConfirmAction
              label={`Revoke ${name}`}
              text="Revoke"
              warning="Revoking stops new runs in this context. A run that already started finishes. Bound credentials stop working. Workspace files are not touched."
              confirmLabel="Confirm revoke"
              cancelLabel="Keep context"
              onConfirm={() => revoke.mutateAsync(experiment.context_id)}
            />
          </span>
        ) : null}
      </div>
      <div className="flex flex-wrap items-center gap-2 text-meta text-muted-foreground">
        <span>Factors:</span>
        {experiment.declared_factors.length === 0 ? (
          <span>none declared</span>
        ) : (
          experiment.declared_factors.map((factor) => (
            <Badge key={factor} variant="hue">
              {factor}
            </Badge>
          ))
        )}
        <span>Permitted: {experiment.actions.join(", ")}</span>
      </div>
      <dl className="grid grid-cols-[auto_minmax(0,1fr)] gap-x-4 gap-y-1 text-meta">
        <dt className="text-muted-foreground">Workspace</dt>
        <dd dir="ltr" className="font-mono text-code [overflow-wrap:anywhere]">
          {experiment.workspace}
        </dd>
        <dt className="text-muted-foreground">Store</dt>
        <dd dir="ltr" className="font-mono text-code [overflow-wrap:anywhere]">
          {identity.store_kind} at {identity.store_path}
        </dd>
        <dt className="text-muted-foreground">Index identity</dt>
        <dd dir="ltr" className="font-mono text-code [overflow-wrap:anywhere]">
          {identity.index_identity}
        </dd>
        <dt className="text-muted-foreground">Embedding</dt>
        <dd dir="ltr" className="font-mono text-code [overflow-wrap:anywhere]">
          {identity.embedding_provider} / {identity.embedding_model}
        </dd>
      </dl>
    </div>
  );
}
