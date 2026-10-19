import { useRemoveProviderKey, useSaveProviderKey } from "../api/settingsMutations";
import type { ProviderField } from "../api/settings";
import { KeySettingRow } from "./SettingRow";

const STATE_LINES: Record<string, string> = {
  "keychain-missing": "The saved key was removed from the keychain, maybe by another workspace. Save it again to use it.",
  "keychain-unreadable": "The keychain could not be read. Allow access when the system asks, then reload this page.",
};

interface ProviderKeyFieldProps {
  provider: string;
  field: ProviderField;
  keychain: "available" | "unavailable";
  /** The key being typed, or `null` when the input closes. The card uses it for Test. */
  onTyped: (text: string | null) => void;
}

/**
 * The key of one provider as a summary row. The page shows at most "Key set"
 * and the last four characters. Where the key can be put by hand follows the
 * naming rule `secrets/<provider>.key` and `<PROVIDER>_API_KEY`.
 */
export function ProviderKeyField({ provider, field, keychain, onTyped }: ProviderKeyFieldProps) {
  const save = useSaveProviderKey(provider);
  const remove = useRemoveProviderKey(provider);
  const keyFile = `secrets/${provider}.key`;
  const stateLine = field.state !== null ? STATE_LINES[field.state] : undefined;
  const error = save.isError ? save.error : remove.isError ? remove.error : null;

  return (
    <div className="flex flex-col gap-1.5">
      {stateLine !== undefined ? <p className="text-meta text-muted-foreground">{stateLine}</p> : null}
      <KeySettingRow
        label={field.label}
        set={field.set}
        last4={field.last4}
        source={field.source}
        detail={field.source === "key-file" ? keyFile : null}
        keychain={keychain}
        keyFile={keyFile}
        envVar={`${provider.toUpperCase()}_API_KEY`}
        required={field.required}
        pending={save.isPending || remove.isPending}
        error={error}
        onTyped={onTyped}
        onSave={(key, done) => save.mutate(key, { onSuccess: done })}
        onRemove={() => remove.mutate()}
        onRetry={() => {
          save.reset();
          remove.reset();
        }}
      />
    </div>
  );
}
