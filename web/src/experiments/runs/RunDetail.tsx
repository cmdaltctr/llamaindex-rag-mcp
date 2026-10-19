import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { useApi } from "../../api/ApiProvider";
import { runResultQuery } from "../../api/queries";
import { ACTIVE_RUN_STATUSES, type RunDetailRecord } from "../../api/runs";
import { ErrorNotice } from "../../components/ErrorNotice";
import { Card } from "../../components/ui/card";
import { maskText } from "../../runs/redact";
import type { RunMonitor } from "../../runs/useRunMonitor";
import { RunProgress } from "../../studio/RunProgress";
import { Panel } from "../Panel";
import { EvidenceInspector } from "./EvidenceInspector";
import { NodeOutcomes } from "./NodeOutcomes";
import { outcomeRows } from "./outcomeRows";
import { Replay } from "./Replay";
import { RunSnapshot } from "./RunSnapshot";

function strings(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === "string") : [];
}

function Failure({ failure }: { failure: Record<string, unknown> }) {
  return (
    <Panel title="Failure" level={3}>
      {typeof failure.failed_node === "string" && <p>{`Failed node: ${failure.failed_node}`}</p>}
      {typeof failure.error === "string" && <p className="[overflow-wrap:anywhere]">{`Error: ${maskText(failure.error)}`}</p>}
      {typeof failure.reason === "string" && <p className="text-meta text-muted-foreground">{`Reason: ${failure.reason}`}</p>}
    </Panel>
  );
}

interface RunDetailProps {
  run: RunDetailRecord;
  /** The live view of an active run; idle for a finished one. */
  monitor: RunMonitor;
  status: string;
}

/** One run: snapshot, live progress or replay, node outcomes, completed effects and evidence. */
export function RunDetail({ run, monitor, status }: RunDetailProps) {
  const api = useApi();
  const [selectedNode, setSelectedNode] = useState<string | null>(null);
  const active = ACTIVE_RUN_STATUSES.has(run.status);
  const stored = useQuery({ ...runResultQuery(api, run.run_id), enabled: !active });
  const result = stored.data ?? null;

  const failure = run.failure;
  const effects = [...new Set([...strings(result?.completed_effects), ...strings(failure?.completed_effects), ...monitor.view.effects])];
  const wallTimeS = typeof result?.wall_time_s === "number" ? result.wall_time_s : monitor.view.wallTimeS;
  const rows = outcomeRows(result?.nodes, monitor.view);
  const collections = Object.keys(run.settings);

  return (
    <div className="flex flex-col gap-4">
      {stored.isError && <ErrorNotice error={stored.error} onRetry={() => void stored.refetch()} />}
      {failure && <Failure failure={failure} />}
      <RunSnapshot run={run} />
      {active ? (
        <Card>
          <RunProgress runId={run.run_id} status={status} view={monitor.view} mode={monitor.mode} live={monitor.live} error={monitor.error} />
        </Card>
      ) : (
        <Replay runId={run.run_id} nodeIds={rows.map((row) => row.nodeId)} />
      )}
      <NodeOutcomes runId={run.run_id} rows={rows} wallTimeS={wallTimeS} selected={selectedNode} onSelect={setSelectedNode} />
      {effects.length > 0 && (
        <Panel
          title="Completed effects"
          level={3}
          description={run.status === "succeeded" ? "Sources this run committed." : "Sources committed before the run stopped. They stay committed; a retry starts a new run."}
        >
          <ul className="flex flex-col gap-1">
            {effects.map((effect) => (
              <li key={effect}>
                <code className="font-mono text-code [overflow-wrap:anywhere]">{maskText(effect)}</code>
              </li>
            ))}
          </ul>
        </Panel>
      )}
      {result?.outputs && <EvidenceInspector runId={run.run_id} outputs={result.outputs} fallbackCollection={collections.length === 1 ? collections[0]! : null} />}
    </div>
  );
}
