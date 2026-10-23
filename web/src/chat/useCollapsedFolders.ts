import { useCallback, useState } from "react";
import { readStored, writeStored } from "../lib/storage";

/** Per-browser list of the chat folders the user closed. */
export const COLLAPSED_FOLDERS_KEY = "omrs-collapsed-chat-folders";

function isIdList(value: unknown): value is string[] {
  return Array.isArray(value) && value.every((item) => typeof item === "string");
}

/** Which folders are closed, and a toggle that remembers the choice in this browser. */
export function useCollapsedFolders(): [Set<string>, (folderId: string) => void] {
  const [collapsed, setCollapsed] = useState(() => new Set(readStored(COLLAPSED_FOLDERS_KEY, isIdList) ?? []));
  const toggle = useCallback((folderId: string) => {
    setCollapsed((current) => {
      const next = new Set(current);
      if (!next.delete(folderId)) next.add(folderId);
      writeStored(COLLAPSED_FOLDERS_KEY, [...next]);
      return next;
    });
  }, []);
  return [collapsed, toggle];
}
