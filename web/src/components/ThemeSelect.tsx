import { useId } from "react";
import { THEMES, type ThemePreference } from "../lib/preferences";

const LABELS: Record<ThemePreference, string> = { system: "System", light: "Light", dark: "Dark" };

interface ThemeSelectProps {
  value: ThemePreference;
  onChange: (theme: ThemePreference) => void;
}

export function ThemeSelect({ value, onChange }: ThemeSelectProps) {
  const id = useId();
  return (
    <div className="field-inline">
      <label className="field-inline__label" htmlFor={id}>
        Theme
      </label>
      <select
        id={id}
        className="control control--select"
        value={value}
        onChange={(event) => onChange(event.target.value as ThemePreference)}
      >
        {THEMES.map((theme) => (
          <option key={theme} value={theme}>
            {LABELS[theme]}
          </option>
        ))}
      </select>
    </div>
  );
}
