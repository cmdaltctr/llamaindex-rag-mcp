import { MoreHorizontal } from "lucide-react";
import { useRef } from "react";
import type { ChatFolder, ChatSummary } from "../api/chats";
import {
  ContextMenu,
  ContextMenuContent,
  ContextMenuItem,
  ContextMenuRadioGroup,
  ContextMenuRadioItem,
  ContextMenuSub,
  ContextMenuSubContent,
  ContextMenuSubTrigger,
  ContextMenuTrigger,
} from "../components/ui/context-menu";
import { Button } from "../components/ui/button";
import { cn } from "../lib/utils";

/** A radio item needs a value, so "No folder" has its own. */
const NO_FOLDER = "__no_folder__";

interface ChatRowProps {
  chat: ChatSummary;
  folders: ChatFolder[];
  active: boolean;
  onOpen: (chat: ChatSummary) => void;
  onMove: (chatId: string, folderId: string | null) => void;
  onDragStart: (chatId: string, event: React.DragEvent) => void;
  onDragEnd: () => void;
  onDelete: (chat: ChatSummary) => void;
  /** In Select mode a checkbox shows before the title. */
  selectMode: boolean;
  selected: boolean;
  onToggle: (chatId: string) => void;
}

/** One chat in the history list: open it, drag it, or right-click it to move or delete it. */
export function ChatRow({ chat, folders, active, onOpen, onMove, onDragStart, onDragEnd, onDelete, selectMode, selected, onToggle }: ChatRowProps) {
  const rowRef = useRef<HTMLLIElement>(null);
  const current = chat.folder_id ?? NO_FOLDER;

  /** The more button asks the row for the same menu a right-click opens, placed under the button. */
  function openMenu(event: React.MouseEvent<HTMLButtonElement>) {
    const box = event.currentTarget.getBoundingClientRect();
    rowRef.current?.dispatchEvent(new MouseEvent("contextmenu", { bubbles: true, cancelable: true, clientX: box.left, clientY: box.bottom }));
  }

  return (
    <ContextMenu>
      <ContextMenuTrigger asChild>
        <li
          ref={rowRef}
          draggable
          onDragStart={(event) => onDragStart(chat.chat_id, event)}
          onDragEnd={onDragEnd}
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
              <Button variant="ghost" size="icon-xs" aria-label={`More actions for ${chat.title}`} onClick={openMenu}>
                <MoreHorizontal aria-hidden="true" />
              </Button>
            )}
          </div>
        </li>
      </ContextMenuTrigger>
      <ContextMenuContent>
        <ContextMenuSub>
          <ContextMenuSubTrigger>Move to a folder</ContextMenuSubTrigger>
          <ContextMenuSubContent>
            <ContextMenuRadioGroup
              value={current}
              onValueChange={(value) => {
                if (value !== current) onMove(chat.chat_id, value === NO_FOLDER ? null : value);
              }}
            >
              <ContextMenuRadioItem value={NO_FOLDER}>No folder</ContextMenuRadioItem>
              {folders.map((folder) => (
                <ContextMenuRadioItem key={folder.folder_id} value={folder.folder_id}>
                  {folder.name}
                </ContextMenuRadioItem>
              ))}
            </ContextMenuRadioGroup>
          </ContextMenuSubContent>
        </ContextMenuSub>
        <ContextMenuItem className="text-status-error-label" onSelect={() => onDelete(chat)}>
          Delete
        </ContextMenuItem>
      </ContextMenuContent>
    </ContextMenu>
  );
}
