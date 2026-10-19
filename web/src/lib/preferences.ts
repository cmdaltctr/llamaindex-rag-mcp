import { readStored, writeStored } from "./storage";

/**
 * Per-browser preferences: the theme, and the last collection as a
 * navigation default. Nothing here is a source of truth for workspace data.
 */
export const PREFERENCES_KEY = "omrg-preferences";

export const THEMES = ["system", "light", "dark"] as const;
export type ThemePreference = (typeof THEMES)[number];

export interface Preferences {
  theme: ThemePreference;
  lastCollection: string | null;
}

export const DEFAULT_PREFERENCES: Preferences = { theme: "system", lastCollection: null };

function isTheme(value: unknown): value is ThemePreference {
  return typeof value === "string" && (THEMES as readonly string[]).includes(value);
}

function isPreferences(value: unknown): value is Preferences {
  if (typeof value !== "object" || value === null) return false;
  const record = value as Record<string, unknown>;
  return isTheme(record.theme) && (record.lastCollection === null || typeof record.lastCollection === "string");
}

export function readPreferences(): Preferences {
  return readStored(PREFERENCES_KEY, isPreferences) ?? DEFAULT_PREFERENCES;
}

/** Merges a change into the stored preferences and returns the result. */
export function updatePreferences(change: Partial<Preferences>): Preferences {
  const next: Preferences = { ...readPreferences(), ...change };
  writeStored(PREFERENCES_KEY, next);
  return next;
}

/** Applies a theme preference to the document root. `system` follows the operating system. */
export function applyTheme(theme: ThemePreference): void {
  const root = document.documentElement;
  if (theme === "system") delete root.dataset.theme;
  else root.dataset.theme = theme;
}
