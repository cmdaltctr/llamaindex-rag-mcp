import { useId, type FormEvent } from "react";
import { useSaveProviderFields } from "../api/settingsMutations";
import type { ProviderField } from "../api/settings";
import { ErrorNotice } from "../components/ErrorNotice";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";

const CODE = "text-code font-mono [overflow-wrap:anywhere]";

interface ProviderAddressFieldProps {
  provider: string;
  field: ProviderField;
  /** The unsaved text, or `undefined` when the user has typed nothing. */
  typed: string | undefined;
  onTyped: (value: string | null) => void;
}

/** One editable address with its source line, Save and Reset. A locked address shows its value and the reason. */
export function ProviderAddressField({ provider, field, typed, onTyped }: ProviderAddressFieldProps) {
  const id = useId();
  const save = useSaveProviderFields(provider);
  const value = typed ?? field.value ?? "";
  const dirty = typed !== undefined && typed !== (field.value ?? "");

  if (field.locked) {
    return (
      <div className="flex flex-col gap-1">
        <p className="text-meta text-muted-foreground">{field.label}</p>
        <code dir="ltr" className={CODE}>
          {field.value}
        </code>
        <p className="text-meta text-muted-foreground">
          <span>{field.source === "env" ? "Set from environment (read-only here)" : "Read-only"}</span>
          {field.lock_reason !== null ? ` ${field.lock_reason}` : ""}
        </p>
      </div>
    );
  }

  function submit(event: FormEvent) {
    event.preventDefault();
    if (!dirty) return;
    save.mutate({ [field.id]: value }, { onSuccess: () => onTyped(null) });
  }

  return (
    <form onSubmit={submit} className="flex flex-col gap-1.5">
      <Label htmlFor={id}>{field.label}</Label>
      <Input id={id} dir="ltr" autoComplete="off" spellCheck={false} value={value} onChange={(event) => onTyped(event.target.value)} />
      <p className="text-meta text-muted-foreground">{`Source: ${field.source}`}</p>
      <div className="flex flex-wrap items-center gap-2">
        <Button type="submit" size="sm" disabled={!dirty || save.isPending}>
          Save address
        </Button>
        {field.source === "saved" ? (
          <Button type="button" variant="outline" size="sm" disabled={save.isPending} onClick={() => save.mutate({ [field.id]: null }, { onSuccess: () => onTyped(null) })}>
            Reset to default
          </Button>
        ) : null}
      </div>
      {save.isError ? <ErrorNotice error={save.error} onRetry={() => save.reset()} /> : null}
    </form>
  );
}
