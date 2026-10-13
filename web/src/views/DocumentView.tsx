import type { FetchLike } from "../api/client";
import type { ThemePreference } from "../lib/preferences";
import type { ViewId } from "../lib/views";
import { AskView } from "./ask/AskView";
import { LibraryView } from "./library/LibraryView";
import { SearchView } from "./search/SearchView";
import { SettingsView } from "./settings/SettingsView";

const DOCUMENT_VIEWS = ["library", "search", "ask", "settings"] as const;

export type DocumentViewId = (typeof DOCUMENT_VIEWS)[number];

export function isDocumentView(id: ViewId): id is DocumentViewId {
  return (DOCUMENT_VIEWS as readonly string[]).includes(id);
}

interface DocumentViewProps {
  id: DocumentViewId;
  focusHeading: boolean;
  theme: ThemePreference;
  onThemeChange: (theme: ThemePreference) => void;
  fetchImpl?: FetchLike;
}

/** Library, Search, Ask and Settings, selected by view id. */
export function DocumentView({ id, focusHeading, theme, onThemeChange, fetchImpl }: DocumentViewProps) {
  const common = { focusHeading, fetchImpl };
  switch (id) {
    case "library":
      return <LibraryView {...common} />;
    case "search":
      return <SearchView {...common} />;
    case "ask":
      return <AskView {...common} />;
    case "settings":
      return <SettingsView {...common} theme={theme} onThemeChange={onThemeChange} />;
  }
}
