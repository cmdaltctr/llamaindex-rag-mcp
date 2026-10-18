import { Pencil } from "lucide-react";
import { useState, type ReactNode } from "react";
import type { ChatFolder } from "../api/chats";
import { Button } from "../components/ui/button";
import { cn } from "../lib/utils";
import { FolderNameField } from "./FolderNameField";

interface ChatFolderSectionProps {
  /** `null` is the "No folder" group: it cannot be renamed. */
  folder: ChatFolder | null;
  onRename?: (folderId: string, name: string) => void;
  onDropChat: (folderId: string | null, event: React.DragEvent) => void;
  /** Extra header actions, such as the folder delete button. */
  actions?: ReactNode;
  children: ReactNode;
}

/** A folder, or the "No folder" group, as a drop target that lists its chats. */
export function ChatFolderSection({ folder, onRename, onDropChat, actions, children }: ChatFolderSectionProps) {
  const [renaming, setRenaming] = useState(false);
  const [over, setOver] = useState(false);
  const name = folder?.name ?? "No folder";
  return (
    <section
      aria-label={folder === null ? "No folder" : `Folder ${name}`}
      onDragOver={(event) => {
        event.preventDefault();
        setOver(true);
      }}
      onDragLeave={() => setOver(false)}
      onDrop={(event) => {
        event.preventDefault();
        setOver(false);
        onDropChat(folder?.folder_id ?? null, event);
      }}
      className={cn("flex flex-col gap-1 rounded-small border border-transparent p-1", over && "border-ring bg-interactive-hover")}
    >
      <div className="flex min-h-8 items-center gap-1">
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
