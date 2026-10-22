import { useCallback, useState } from "react";
import { readStored, writeStored } from "./storage";

/** Per-browser choice to show the workspace navigation as a narrow icon column. */
export const NAV_COLLAPSED_KEY = "omrs-nav-collapsed";

function isBoolean(value: unknown): value is boolean {
  return typeof value === "boolean";
}

export function useNavCollapsed(): [boolean, () => void] {
  const [collapsed, setCollapsed] = useState(() => readStored(NAV_COLLAPSED_KEY, isBoolean) ?? false);
  const toggle = useCallback(() => {
    setCollapsed((current) => {
      writeStored(NAV_COLLAPSED_KEY, !current);
      return !current;
    });
  }, []);
  return [collapsed, toggle];
}
