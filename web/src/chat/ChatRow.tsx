import { Trash2 } from "lucide-react";
import type { ChatFolder, ChatSummary } from "../api/chats";
import { Button } from "../components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../components/ui/select";
import { cn } from "../lib/utils";

/** Radix Select cannot hold an empty item value, so "No folder" has its own. */
const NO_FOLDER = "__no_folder__";

interface ChatRowProps {
  chat: ChatSummary;
  folders: ChatFolder[];
  active: boolean;
  onOpen: (chat: ChatSummary) => void;
  onMove: (chatId: string, folderId: string | null) => void;
  onDragStart: (chatId: string, event: React.DragEvent) => void;
  onDelete: (chat: ChatSummary) => void;
  /** In Select mode a checkbox shows before the title. */
  selectMode: boolean;
  selected: boolean;
  onToggle: (chatId: string) => void;
}

/** One chat in the history list: open it, drag it, or move it with the menu. */
export function ChatRow({ chat, folders, active, onOpen, onMove, onDragStart, onDelete, selectMode, selected, onToggle }: ChatRowProps) {
  const targets = folders.filter((folder) => folder.folder_id !== chat.folder_id);
  const canMove = targets.length > 0 || chat.folder_id !== null;
  return (
    <li
      draggable
      onDragStart={(event) => onDragStart(chat.chat_id, event)}
      className={cn("flex flex-col gap-1 rounded-small border border-transparent p-1", active && "border-border bg-selection")}
    >
      <div className="flex items-center gap-1">
        {selectMode ? (
          <input type="checkbox" className="size-4 shrink-0 accent-primary" aria-label={`Select ${chat.title}`} checked={selected} onChange={() => onToggle(chat.chat_id)} />
        ) : null}
        <Button variant="ghost" size="sm" className="min-w-0 flex-1 justify-start" aria-current={active ? "true" : undefined} onClick={() => onOpen(chat)}>
          <span className="truncate">{chat.title}</span>
        </Button>
        {selectMode ? null : (
          <Button variant="ghost" size="icon-xs" aria-label={`Delete ${chat.title}`} onClick={() => onDelete(chat)}>
            <Trash2 aria-hidden="true" />
          </Button>
        )}
      </div>
      {canMove ? (
        <Select value="" onValueChange={(value) => onMove(chat.chat_id, value === NO_FOLDER ? null : value)}>
          <SelectTrigger aria-label={`Move ${chat.title} to`} className="h-8 text-meta">
            <SelectValue placeholder="Move to" />
          </SelectTrigger>
          <SelectContent>
            {chat.folder_id !== null ? <SelectItem value={NO_FOLDER}>No folder</SelectItem> : null}
            {targets.map((folder) => (
              <SelectItem key={folder.folder_id} value={folder.folder_id}>
                {folder.name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      ) : null}
    </li>
  );
}
