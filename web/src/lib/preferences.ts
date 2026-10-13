import { isViewId, type ViewId } from "./views";

/**
 * Per-browser UI state. Storage can be missing or throw (private windows,
 * blocked site data), so every access is guarded and the app always falls
 * back to defaults. Nothing here is a source of truth for workspace data.
 */
export const STORAGE_KEY = "omrg-workspace-ui";
const VERSION = 1;

export const THEMES = ["system", "light", "dark"] as const;
export type ThemePreference = (typeof THEMES)[number];

export interface UiState {
  view: ViewId;
  inspectorOpen: boolean;
  theme: ThemePreference;
}

export const DEFAULT_UI_STATE: UiState = { view: "canvas", inspectorOpen: false, theme: "system" };

function isTheme(value: unknown): value is ThemePreference {
  return typeof value === "string" && (THEMES as readonly string[]).includes(value);
}

function storage(): Storage | null {
  try {
    return window.localStorage;
  } catch {
    return null;
  }
}

export function readUiState(): UiState {
  let raw: string | null;
  try {
    raw = storage()?.getItem(STORAGE_KEY) ?? null;
  } catch {
    return DEFAULT_UI_STATE;
  }
  if (raw === null) return DEFAULT_UI_STATE;

  let parsed: unknown;
  try {
    parsed = JSON.parse(raw);
  } catch {
    return DEFAULT_UI_STATE;
  }
  if (typeof parsed !== "object" || parsed === null) return DEFAULT_UI_STATE;
  const record = parsed as Record<string, unknown>;
  if (record.version !== VERSION) return DEFAULT_UI_STATE;

  return {
    view: isViewId(record.view) ? record.view : DEFAULT_UI_STATE.view,
    inspectorOpen: typeof record.inspectorOpen === "boolean" ? record.inspectorOpen : DEFAULT_UI_STATE.inspectorOpen,
    theme: isTheme(record.theme) ? record.theme : DEFAULT_UI_STATE.theme,
  };
}

export function writeUiState(state: UiState): void {
  try {
    storage()?.setItem(STORAGE_KEY, JSON.stringify({ version: VERSION, ...state }));
  } catch {
    // Storage is optional. The current session keeps working without it.
  }
}

/** Applies a theme preference to the document root. `system` follows the operating system. */
export function applyTheme(theme: ThemePreference): void {
  const root = document.documentElement;
  if (theme === "system") delete root.dataset.theme;
  else root.dataset.theme = theme;
}
