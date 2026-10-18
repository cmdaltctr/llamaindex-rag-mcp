import { useQuery } from "@tanstack/react-query";
import { useId, useState } from "react";
import { useApi } from "../api/ApiProvider";
import { embeddingLockOf, embeddingRefusalReason, type EmbeddingCheck, type EmbeddingLockCollection } from "../api/embedding";
import { useCheckEmbeddingModel, useSaveProfileEmbedding } from "../api/mutations";
import type { ProfileRecord } from "../api/profiles";
import { embeddingProvidersQuery } from "../api/queries";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../components/ui/select";
import { describeError } from "../lib/errors";

const CREATE_NEW = "Create a new collection to use another model.";

/** The lock text. It names the first blocking collection and its model, or says the model is not recorded. */
export function lockText(collections: readonly EmbeddingLockCollection[]): string {
  const first = collections[0];
  if (first === undefined) return `Locked: this profile already holds vectors. ${CREATE_NEW}`;
  if (first.model === null || first.model === "") {
    return `Locked: ${first.collection} already holds vectors, but the model that made them is not recorded. ${CREATE_NEW}`;
  }
  return `Locked: ${first.collection} already holds vectors made with ${first.model}. ${CREATE_NEW}`;
}

interface EmbeddingModelSectionProps {
  profile: ProfileRecord;
}

function Controls({ profile, onLocked }: { profile: ProfileRecord; onLocked: (collections: EmbeddingLockCollection[]) => void }) {
  const api = useApi();
  const providers = useQuery(embeddingProvidersQuery(api));
  const current = profile.embedding;
  const [provider, setProvider] = useState(current?.provider ?? "");
  const [model, setModel] = useState(current?.model ?? "");
  const [check, setCheck] = useState<EmbeddingCheck | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const checker = useCheckEmbeddingModel();
  const saver = useSaveProfileEmbedding(profile.profile_id);
  const modelId = useId();
  const chosenProvider = provider || providers.data?.server_default.provider || "";
  const ready = chosenProvider !== "" && model.trim() !== "";

  function change(update: () => void) {
    update();
    setCheck(null);
    setProblem(null);
  }

  async function save(choice: { provider: string | null; model: string | null }) {
    setProblem(null);
    try {
      await saver.mutateAsync(choice);
      if (choice.provider === null) {
        setProvider("");
        setModel("");
      }
    } catch (error) {
      const blocking = embeddingLockOf(error);
      if (blocking !== null) return onLocked(blocking);
      setProblem(embeddingRefusalReason(error) ?? describeError(error).message);
    }
  }

  async function runCheck() {
    setProblem(null);
    try {
      setCheck(await checker.mutateAsync({ provider: chosenProvider, model: model.trim() }));
    } catch (error) {
      setCheck(null);
      setProblem(describeError(error).message);
    }
  }

  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-col gap-1">
        <Label>Provider</Label>
        <Select value={chosenProvider} onValueChange={(next) => change(() => setProvider(next))}>
          <SelectTrigger aria-label="Provider">
            <SelectValue placeholder="Choose a provider" />
          </SelectTrigger>
          <SelectContent>
            {(providers.data?.providers ?? []).map((entry) => (
              <SelectItem key={entry.name} value={entry.name} disabled={!entry.available}>
                {entry.available ? entry.name : `${entry.name} (${entry.reason ?? "unavailable"})`}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
      <div className="flex flex-col gap-1">
        <Label htmlFor={modelId}>Model</Label>
        <Input id={modelId} value={model} onChange={(event) => change(() => setModel(event.target.value))} />
      </div>
      <div className="flex flex-wrap gap-2">
        <Button variant="outline" disabled={!ready || checker.isPending} onClick={() => void runCheck()}>
          Check model
        </Button>
        <Button disabled={!ready || saver.isPending} onClick={() => void save({ provider: chosenProvider, model: model.trim() })}>
          Save model
        </Button>
        {current?.source === "profile" && (
          <Button variant="ghost" disabled={saver.isPending} onClick={() => void save({ provider: null, model: null })}>
            Use server default
          </Button>
        )}
      </div>
      {check?.ok === true && (
        <p className="text-meta text-status-success-label">
          Vector size: {check.dimensions}
          {check.norm === null ? "" : `. Vector length: ${check.norm}`}
        </p>
      )}
      {check?.ok === false && <p className="text-meta text-status-error-label">{check.reason ?? "The model check failed."}</p>}
      {problem !== null && <p className="text-meta text-status-error-label">{problem}</p>}
    </div>
  );
}

/**
 * The embedding model of the open profile, shown in the Embed chunks step.
 * A built-in profile shows the server default as text. A user profile shows
 * the controls, or the lock text when a bound collection already holds vectors.
 */
export function EmbeddingModelSection({ profile }: EmbeddingModelSectionProps) {
  const [refused, setRefused] = useState<EmbeddingLockCollection[] | null>(null);
  const blocking = refused ?? (profile.embedding_lock?.locked ? profile.embedding_lock.collections : null);
  const embedding = profile.embedding;

  if (profile.kind === "builtin") {
    return (
      <p className="text-meta text-muted-foreground">
        Embedding model: {embedding ? <code className="font-mono text-code">{embedding.model}</code> : "unknown"} (server default, read-only).
      </p>
    );
  }
  if (blocking !== null) return <p className="text-meta text-muted-foreground">{lockText(blocking)}</p>;
  return <Controls profile={profile} onLocked={setRefused} />;
}
