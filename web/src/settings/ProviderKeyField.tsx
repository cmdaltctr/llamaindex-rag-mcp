import { useId, type FormEvent } from "react";
import { useRemoveProviderKey, useSaveProviderKey } from "../api/settingsMutations";
import type { ProviderField } from "../api/settings";
import { ErrorNotice } from "../components/ErrorNotice";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";

const STATE_LINES: Record<string, string> = {
  "keychain-missing": "The saved key was removed from the keychain, maybe by another workspace. Save it again to use it.",
  "keychain-unreadable": "The keychain could not be read. Allow access when the system asks, then reload this page.",
};

interface ProviderKeyFieldProps {
  provider: string;
  field: ProviderField;
  keychain: "available" | "unavailable";
  typed: string;
  onTyped: (value: string) => void;
}

/**
 * The key of one provider. The input is a password field that empties after
 * a save. The page shows at most "Key set" and the last four characters.
 */
export function ProviderKeyField({ provider, field, keychain, typed, onTyped }: ProviderKeyFieldProps) {
  const id = useId();
  const save = useSaveProviderKey(provider);
  const remove = useRemoveProviderKey(provider);
  const busy = save.isPending || remove.isPending;
  const stateLine = field.state !== null ? STATE_LINES[field.state] : undefined;

  const status = (
    <p className="text-ui">
      {field.set ? (
        <>
          <span className="font-medium">Key set</span>
          {field.last4 !== null ? <span>{`, ending ${field.last4}`}</span> : null}
          <span className="text-meta text-muted-foreground">{field.source === "keychain" ? ` (kept in the system keychain as omrg / ${provider})` : ""}</span>
        </>
      ) : (
        <span>No key</span>
      )}
    </p>
  );

  if (field.source === "env") {
    return (
      <div className="flex flex-col gap-1">
        <p className="text-meta text-muted-foreground">{field.label}</p>
        {status}
        <p className="text-meta text-muted-foreground">
          <span>Set from environment (read-only here)</span>
          {field.lock_reason !== null ? ` ${field.lock_reason}` : ""}
        </p>
      </div>
    );
  }

  if (keychain === "unavailable") {
    return (
      <div className="flex flex-col gap-1">
        <p className="text-meta text-muted-foreground">{field.label}</p>
        <p className="text-ui">{field.lock_reason ?? "No system keychain is available on this machine."}</p>
      </div>
    );
  }

  function submit(event: FormEvent) {
    event.preventDefault();
    if (typed.trim() === "") return;
    save.mutate(typed.trim(), { onSuccess: () => onTyped("") });
  }

  return (
    <form onSubmit={submit} className="flex flex-col gap-1.5">
      <Label htmlFor={id}>{field.label}</Label>
      {status}
      {stateLine !== undefined ? <p className="text-meta text-muted-foreground">{stateLine}</p> : null}
      <Input id={id} type="password" dir="ltr" autoComplete="off" spellCheck={false} value={typed} onChange={(event) => onTyped(event.target.value)} />
      <div className="flex flex-wrap items-center gap-2">
        <Button type="submit" size="sm" disabled={busy || typed.trim() === ""}>
          Save key
        </Button>
        {field.source === "keychain" && field.set ? (
          <Button type="button" variant="outline" size="sm" disabled={busy} onClick={() => remove.mutate()}>
            Remove key
          </Button>
        ) : null}
      </div>
      {save.isError ? <ErrorNotice error={save.error} onRetry={() => save.reset()} /> : null}
      {remove.isError ? <ErrorNotice error={remove.error} onRetry={() => remove.reset()} /> : null}
    </form>
  );
}
