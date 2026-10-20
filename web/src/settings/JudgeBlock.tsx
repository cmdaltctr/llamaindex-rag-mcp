import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { useApi } from "../api/ApiProvider";
import { judgeSettingsQuery } from "../api/queries";
import type { Connection, JudgeSettings } from "../api/settings";
import { useSetJudgeSettings } from "../api/settingsMutations";
import { ErrorNotice } from "../components/ErrorNotice";
import { Button } from "../components/ui/button";
import { ChatModelForm } from "./ChatModelForm";
import { ChoiceRow, SOURCE } from "./ChoiceRow";
import { isEnvironmentSource } from "./connectionWords";
import { SaveErrorNotice } from "./SaveErrorNotice";

const CLOUD_NOTE = "Claims and cited passages are sent off this machine";
const LOCK_NOTE =
  "Either variable locks both judge fields here, and the other field can still come from omrg.jsonc, where a hand edit applies only at the next launch.";

/** The provider as set. An alias (`cloud`, `local`) shows with the provider it resolves to. */
function providerText(judge: JudgeSettings, connections: Connection[]): string {
  const resolved = connections.find((connection) => connection.provider === judge.resolved_provider)?.display_name ?? judge.resolved_provider;
  return judge.provider === judge.resolved_provider ? resolved : `${judge.provider} (${resolved})`;
}

/** The judge rows, Edit and Remove. Remove shows only for a choice from `omrg.jsonc`; a locked choice has no buttons. */
function JudgeChoice({ judge, connections, onEdit }: { judge: JudgeSettings; connections: Connection[]; onEdit: () => void }) {
  const clear = useSetJudgeSettings();
  const locked = judge.locked || isEnvironmentSource(judge.source);
  const resolved = connections.find((connection) => connection.provider === judge.resolved_provider);
  return (
    <div className="flex flex-col gap-3">
      <ChoiceRow label="Judge provider" value={providerText(judge, connections)} source={judge.source} />
      <ChoiceRow label="Judge model" value={judge.model} source={judge.source} />
      {judge.reason === "no-model" ? <p className="text-ui">Claim checks are skipped until you set a judge model.</p> : null}
      {locked ? (
        <div className="flex flex-col gap-1">
          <p className={SOURCE}>{judge.lock_reason ?? "Read-only here."}</p>
          <p className={SOURCE}>{LOCK_NOTE}</p>
        </div>
      ) : (
        <div className="flex flex-wrap items-center gap-2">
          <Button type="button" variant="outline" size="sm" aria-label="Edit claim check judge" onClick={onEdit}>
            Edit
          </Button>
          {judge.source === "config-file" ? (
            <Button type="button" variant="outline" size="sm" aria-label="Remove claim check judge" disabled={clear.isPending} onClick={() => clear.mutate(null)}>
              Remove
            </Button>
          ) : null}
        </div>
      )}
      {resolved?.locality === "cloud" ? <p className={SOURCE}>{`${CLOUD_NOTE} to ${resolved.display_name}.`}</p> : null}
      {clear.isError ? <SaveErrorNotice error={clear.error} onRetry={() => clear.reset()} /> : null}
    </div>
  );
}

/** The judge form with its own save. It opens on the provider an alias resolves to, because a save never writes an alias. */
function JudgeForm({ judge, connections, onClose }: { judge: JudgeSettings; connections: Connection[]; onClose: () => void }) {
  const save = useSetJudgeSettings();
  return (
    <ChatModelForm
      initial={{ provider: judge.resolved_provider, model: judge.model }}
      connections={connections}
      save={save}
      label="Judge provider and model"
      cloudNote={(host) => `${CLOUD_NOTE} to ${host}.`}
      canClear={false}
      onClose={onClose}
    />
  );
}

/** The claim check judge of this web server. A saved choice is written to `omrg.jsonc` and applies from the next answer. */
export function JudgeBlock({ connections }: { connections: Connection[] }) {
  const api = useApi();
  const query = useQuery(judgeSettingsQuery(api));
  const [editing, setEditing] = useState(false);
  const judge = query.data;

  return (
    <section aria-labelledby="settings-judge" className="flex flex-col gap-3">
      <h3 id="settings-judge" className="text-subsection-title font-semibold">
        Claim check judge
      </h3>
      {judge === undefined ? (
        query.isError ? (
          <ErrorNotice error={query.error} onRetry={() => void query.refetch()} />
        ) : (
          <p className="text-meta text-muted-foreground">Loading the claim check judge.</p>
        )
      ) : editing ? (
        <JudgeForm key={`${judge.provider}|${judge.model}|${judge.source}`} judge={judge} connections={connections} onClose={() => setEditing(false)} />
      ) : (
        <JudgeChoice judge={judge} connections={connections} onEdit={() => setEditing(true)} />
      )}
      <ul className="list-disc ps-5 text-meta text-muted-foreground">
        <li>The judge runs only for collections whose profile turns on "Check claims" in Studio.</li>
        <li>A profile that sets its own judge overrides this choice.</li>
      </ul>
    </section>
  );
}
