import { useMutation } from "@tanstack/react-query";
import { List, Plug } from "lucide-react";
import { useId, useState, type FormEvent } from "react";
import { useApi } from "../api/ApiProvider";
import { listProviderModels, testChatModel, type ChatSettings, type Connection } from "../api/settings";
import { useSetChatSettings } from "../api/settingsMutations";
import { ErrorNotice } from "../components/ErrorNotice";
import { Badge } from "../components/ui/badge";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../components/ui/select";
import { cloudHost, isKnownReason, reasonSentence } from "./connectionWords";

/** Why a provider cannot answer yet, from the cards, or `null` when it can. */
function notReady(connection: Connection): string | null {
  if (!connection.installed) return "not installed";
  const key = connection.fields.find((field) => field.kind === "secret");
  return key !== undefined && !key.set ? "no key" : null;
}

interface ChatModelFormProps {
  settings: ChatSettings;
  connections: Connection[];
}

/** The provider select, the model name, List models, Test, Save and Clear. Only Save and Clear write. */
export function ChatModelForm({ settings, connections }: ChatModelFormProps) {
  const api = useApi();
  const modelId = useId();
  const [provider, setProvider] = useState(settings.provider ?? "");
  const [model, setModel] = useState(settings.model ?? "");
  const choice = { provider, model: model.trim() };
  const ready = provider !== "" && choice.model !== "";
  const selected = connections.find((connection) => connection.provider === provider);

  const save = useSetChatSettings();
  const list = useMutation({ mutationFn: () => listProviderModels(api, provider), gcTime: 0 });
  const test = useMutation({ mutationFn: () => testChatModel(api, choice), gcTime: 0 });
  const names = list.data?.reachable ? list.data.models : [];
  const reason = list.data?.reason;
  const result = test.data;
  const known = result?.reason != null && isKnownReason(result.reason);

  function changeProvider(next: string) {
    setProvider(next);
    list.reset();
    test.reset();
  }

  function submit(event: FormEvent) {
    event.preventDefault();
    if (ready) save.mutate(choice);
  }

  return (
    <form onSubmit={submit} className="flex flex-col gap-3">
      <div className="flex flex-col gap-1.5">
        <Label>Chat provider and model</Label>
        <Select value={provider} onValueChange={changeProvider}>
          <SelectTrigger aria-label="Provider" className="max-w-xs">
            <SelectValue placeholder="Choose a provider" />
          </SelectTrigger>
          <SelectContent>
            {connections.map((connection) => {
              const why = notReady(connection);
              return (
                <SelectItem key={connection.provider} value={connection.provider} disabled={why !== null}>
                  {why === null ? connection.display_name : `${connection.display_name} (${why})`}
                </SelectItem>
              );
            })}
          </SelectContent>
        </Select>
      </div>
      <div className="flex flex-col gap-1.5">
        <Label htmlFor={modelId}>Model name</Label>
        <Input id={modelId} dir="ltr" autoComplete="off" spellCheck={false} className="max-w-md" value={model} onChange={(event) => setModel(event.target.value)} />
        <p className="text-meta text-muted-foreground">Type the model name exactly as the provider spells it, or use List models.</p>
      </div>
      <p className="text-meta text-muted-foreground">{`Source: ${settings.source}`}</p>
      <div className="flex flex-wrap items-center gap-2">
        <Button type="button" variant="outline" size="sm" disabled={provider === "" || list.isPending} onClick={() => list.mutate()}>
          <List aria-hidden="true" />
          List models
        </Button>
        <Button type="button" variant="outline" size="sm" disabled={!ready || test.isPending} onClick={() => test.mutate()}>
          <Plug aria-hidden="true" />
          {test.isPending ? "Testing" : "Test"}
        </Button>
        <Button type="submit" size="sm" disabled={!ready || save.isPending}>
          Save
        </Button>
        {settings.source === "saved" ? (
          <Button type="button" variant="outline" size="sm" disabled={save.isPending} onClick={() => save.mutate(null)}>
            Clear
          </Button>
        ) : null}
      </div>
      {names.length > 0 ? (
        <div className="flex max-w-md flex-col gap-1.5">
          <Select value="" onValueChange={setModel}>
            <SelectTrigger aria-label="Models">
              <SelectValue placeholder="Pick a model" />
            </SelectTrigger>
            <SelectContent>
              {names.map((name) => (
                <SelectItem key={name} value={name}>
                  {name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          {list.data?.truncated ? <p className="text-meta text-muted-foreground">The list was cut. Type the name if yours is missing.</p> : null}
        </div>
      ) : null}
      {list.data !== undefined && !list.data.reachable ? (
        <p role="status" className="text-ui">
          {reason != null && isKnownReason(reason) ? reasonSentence(reason) : "The model list could not be read."}
        </p>
      ) : null}
      <div role="status">
        {result !== undefined ? (
          <div className="flex flex-wrap items-center gap-2">
            {result.ok ? (
              <Badge variant="success">Working</Badge>
            ) : (
              <>
                <Badge variant="error">Not working</Badge>
                {known ? <Badge variant="neutral">{result.reason}</Badge> : null}
                <span className="text-ui">{known ? reasonSentence(result.reason!) : "The test failed."}</span>
              </>
            )}
          </div>
        ) : null}
      </div>
      {selected?.locality === "cloud" ? (
        <p className="text-meta text-muted-foreground">{`Questions and retrieved passages are sent to ${cloudHost(selected)}.`}</p>
      ) : null}
      {save.isError ? <ErrorNotice error={save.error} onRetry={() => save.reset()} /> : null}
      {list.isError ? <ErrorNotice error={list.error} onRetry={() => list.mutate()} /> : null}
      {test.isError ? <ErrorNotice error={test.error} onRetry={() => test.mutate()} /> : null}
    </form>
  );
}
