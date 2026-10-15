import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { applyTheme, readPreferences, updatePreferences, type Preferences, type ThemePreference } from "./preferences";

interface PreferencesState {
  preferences: Preferences;
  setTheme: (theme: ThemePreference) => void;
  setLastCollection: (name: string | null) => void;
}

const PreferencesContext = createContext<PreferencesState | null>(null);

export function PreferencesProvider({ children }: { children: ReactNode }) {
  const [preferences, setPreferences] = useState<Preferences>(readPreferences);

  useEffect(() => applyTheme(preferences.theme), [preferences.theme]);

  const change = useCallback((next: Partial<Preferences>) => setPreferences(updatePreferences(next)), []);
  const value = useMemo<PreferencesState>(
    () => ({
      preferences,
      setTheme: (theme) => change({ theme }),
      setLastCollection: (lastCollection) => change({ lastCollection }),
    }),
    [preferences, change],
  );
  return <PreferencesContext.Provider value={value}>{children}</PreferencesContext.Provider>;
}

export function usePreferences(): PreferencesState {
  const state = useContext(PreferencesContext);
  if (state === null) throw new Error("usePreferences must be used inside a PreferencesProvider.");
  return state;
}
