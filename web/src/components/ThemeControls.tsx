import { Moon, Sun } from "lucide-react";
import { useEffect, useState } from "react";
import { usePreferences } from "../lib/PreferencesProvider";
import { THEMES, type ThemePreference } from "../lib/preferences";
import { Button } from "./ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "./ui/select";

const LABELS: Record<ThemePreference, string> = { system: "System", light: "Light", dark: "Dark" };
const DARK_QUERY = "(prefers-color-scheme: dark)";

function systemPrefersDark(): boolean {
  return typeof window.matchMedia === "function" && window.matchMedia(DARK_QUERY).matches;
}

/** The theme in effect: the preference, or the operating system's choice for System. */
export function useEffectiveTheme(): "light" | "dark" {
  const { preferences } = usePreferences();
  const [systemDark, setSystemDark] = useState(systemPrefersDark);

  useEffect(() => {
    if (typeof window.matchMedia !== "function") return;
    const query = window.matchMedia(DARK_QUERY);
    const update = () => setSystemDark(query.matches);
    query.addEventListener("change", update);
    return () => query.removeEventListener("change", update);
  }, []);

  if (preferences.theme === "system") return systemDark ? "dark" : "light";
  return preferences.theme;
}

/** The Select with System, Light and Dark. Settings shows it. */
export function ThemeSelect() {
  const { preferences, setTheme } = usePreferences();
  return (
    <Select value={preferences.theme} onValueChange={(value) => setTheme(value as ThemePreference)}>
      <SelectTrigger aria-label="Theme" className="w-28">
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        {THEMES.map((theme) => (
          <SelectItem key={theme} value={theme}>
            {LABELS[theme]}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}

/** One click between Light and Dark. It shows the theme in effect and names the one it switches to. */
export function ThemeToggle() {
  const { setTheme } = usePreferences();
  const effective = useEffectiveTheme();
  const target = effective === "dark" ? "light" : "dark";
  const Icon = effective === "dark" ? Moon : Sun;
  return (
    <Button variant="ghost" size="icon" aria-label={`Switch to ${target} theme`} onClick={() => setTheme(target)}>
      <Icon aria-hidden="true" />
    </Button>
  );
}
