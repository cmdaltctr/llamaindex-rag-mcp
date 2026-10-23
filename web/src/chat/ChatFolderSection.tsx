import { Pencil } from "lucide-react";
import { useState, type ReactNode } from "react";
import type { ChatFolder } from "../api/chats";
import { Button } from "../components/ui/button";
import { cn } from "../lib/utils";
import { FolderNameField } from "./FolderNameField";

/** Where a dragged folder lands relative to this one. */
export type DropEdge = "before" | "after";

interface ChatFolderSectionProps {
  /** `null` is the "No folder" group: it cannot be renamed. */
  folder: ChatFolder | null;
  onRename?: (folderId: string, name: string) => void;
  /** A chat or, in select mode, a folder was dropped on this section. `edge` is set for a folder drop. */
  onDrop: (folderId: string | null, event: React.DragEvent, edge: DropEdge | null) => void;
  /** Another folder is being dragged, so this section shows a line where it would land. */
  folderDragOver?: boolean;
  /** Shown before the name, such as the select-mode reorder handle. */
  leading?: ReactNode;
  /** Extra header actions, such as the folder delete button. */
  actions?: ReactNode;
  children: ReactNode;
}

/** A folder, or the "No folder" group, as a drop target that lists its chats. */
export function ChatFolderSection({ folder, onRename, onDrop, folderDragOver = false, leading, actions, children }: ChatFolderSectionProps) {
  const [renaming, setRenaming] = useState(false);
  const [over, setOver] = useState(false);
  const [edge, setEdge] = useState<DropEdge | null>(null);
  // The top half of the section means "above it", the bottom half "below it".
  const edgeAt = (event: React.DragEvent<HTMLElement>): DropEdge => {
    const box = event.currentTarget.getBoundingClientRect();
    return event.clientY < box.top + box.height / 2 ? "before" : "after";
  };
  const name = folder?.name ?? "No folder";
  return (
    <section
      aria-label={folder === null ? "No folder" : `Folder ${name}`}
      data-drop-edge={edge ?? undefined}
      onDragOver={(event) => {
        event.preventDefault();
        if (folderDragOver) setEdge(edgeAt(event));
        else setOver(true);
      }}
      onDragLeave={() => {
        setOver(false);
        setEdge(null);
      }}
      onDrop={(event) => {
        event.preventDefault();
        setOver(false);
        setEdge(null);
        onDrop(folder?.folder_id ?? null, event, folderDragOver ? edgeAt(event) : null);
      }}
      className={cn("relative flex flex-col gap-1 rounded-small border border-transparent p-1", over && "border-ring bg-interactive-hover")}
    >
      {edge === null ? null : (
        <span aria-hidden="true" className={cn("pointer-events-none absolute inset-x-1 h-0.5 rounded-full bg-ring", edge === "before" ? "-top-1" : "-bottom-1")} />
      )}
      <div className="flex min-h-8 items-center gap-1">
        {leading}
        {renaming && folder !== null ? (
          <FolderNameField
            initial={folder.name}
            onCancel={() => setRenaming(false)}
            onSave={(next) => {
              setRenaming(false);
              onRename?.(folder.folder_id, next);
            }}
          />
        ) : (
          <h3 className="min-w-0 flex-1 truncate text-meta font-semibold text-muted-foreground">{name}</h3>
        )}
        {folder !== null && !renaming ? (
          <Button variant="ghost" size="icon-xs" aria-label={`Rename folder ${name}`} onClick={() => setRenaming(true)}>
            <Pencil aria-hidden="true" />
          </Button>
        ) : null}
        {renaming ? null : actions}
      </div>
      <ul className="flex flex-col gap-1">{children}</ul>
    </section>
  );
}
