import { afterEach, describe, expect, it } from "vitest";
import { applyTheme, DEFAULT_PREFERENCES, PREFERENCES_KEY, readPreferences, updatePreferences } from "./preferences";

afterEach(() => {
  window.localStorage.clear();
  delete document.documentElement.dataset.theme;
});

describe("preferences", () => {
  it("defaults to the system theme and no last collection", () => {
    expect(readPreferences()).toEqual({ theme: "system", lastCollection: null });
    expect(DEFAULT_PREFERENCES).toEqual({ theme: "system", lastCollection: null });
  });

  it("stores only theme and lastCollection under one key", () => {
    updatePreferences({ theme: "dark" });
    updatePreferences({ lastCollection: "papers" });
    expect(PREFERENCES_KEY).toBe("omrg-preferences");
    expect(JSON.parse(window.localStorage.getItem("omrg-preferences") ?? "null")).toEqual({ theme: "dark", lastCollection: "papers" });
    expect(readPreferences()).toEqual({ theme: "dark", lastCollection: "papers" });
  });

  it("falls back to defaults and removes a value that fails validation", () => {
    window.localStorage.setItem(PREFERENCES_KEY, JSON.stringify({ theme: "neon", lastCollection: 4 }));
    expect(readPreferences()).toEqual(DEFAULT_PREFERENCES);
    expect(window.localStorage.getItem(PREFERENCES_KEY)).toBeNull();
  });

  it("falls back to defaults for malformed JSON", () => {
    window.localStorage.setItem(PREFERENCES_KEY, "{oops");
    expect(readPreferences()).toEqual(DEFAULT_PREFERENCES);
  });

  it("does not read the retired workspace keys", () => {
    window.localStorage.setItem("omrg-workspace-ui", JSON.stringify({ version: 1, view: "runs", theme: "dark", inspectorOpen: true }));
    expect(readPreferences()).toEqual(DEFAULT_PREFERENCES);
  });

  it("applies and clears the theme on the document root", () => {
    applyTheme("dark");
    expect(document.documentElement.dataset.theme).toBe("dark");
    applyTheme("system");
    expect(document.documentElement.dataset.theme).toBeUndefined();
  });
});
