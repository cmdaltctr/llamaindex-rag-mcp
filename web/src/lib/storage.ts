/**
 * Guarded browser storage. Storage can be missing or throw (private windows,
 * blocked site data), so every access is wrapped and the app always falls
 * back to defaults. Values carry no version field: one that fails its
 * validator is ignored and removed, so a changed shape resets to defaults
 * instead of being migrated.
 */
function storage(): Storage | null {
  try {
    return window.localStorage;
  } catch {
    return null;
  }
}

export function removeStored(key: string): void {
  try {
    storage()?.removeItem(key);
  } catch {
    // Storage is optional. Nothing to clear.
  }
}

export function readStored<T>(key: string, validate: (value: unknown) => value is T): T | null {
  let raw: string | null;
  try {
    raw = storage()?.getItem(key) ?? null;
  } catch {
    return null;
  }
  if (raw === null) return null;

  let parsed: unknown;
  try {
    parsed = JSON.parse(raw);
  } catch {
    removeStored(key);
    return null;
  }
  if (!validate(parsed)) {
    removeStored(key);
    return null;
  }
  return parsed;
}

export function writeStored(key: string, value: unknown): void {
  try {
    storage()?.setItem(key, JSON.stringify(value));
  } catch {
    // Storage is optional. The current session keeps working without it.
  }
}
