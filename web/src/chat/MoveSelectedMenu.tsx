import { FolderInput } from "lucide-react";
import type { ChatFolder } from "../api/chats";
import { Button } from "../components/ui/button";
import { Popover } from "../components/ui/popover";

interface MoveSelectedMenuProps {
  count: number;
  folders: ChatFolder[];
  /** Called with the chosen folder id, or `null` for No folder. */
  onMove: (folderId: string | null) => void;
}

/** The select-mode button that moves every selected chat to one folder, or out of its folder. */
export function MoveSelectedMenu({ count, folders, onMove }: MoveSelectedMenuProps) {
  const targets = [{ id: null, name: "No folder" }, ...folders.map((folder) => ({ id: folder.folder_id, name: folder.name }))];
  return (
    <Popover
      slot="move-selected-panel"
      width={224}
      trigger={(props) => (
        <Button variant="outline" size="sm" disabled={count === 0} {...props}>
          <FolderInput aria-hidden="true" />
          {`Move selected (${count})`}
        </Button>
      )}
    >
      {({ close }) => (
        <ul className="flex flex-col gap-0.5" aria-label="Move to">
          {targets.map((target) => (
            <li key={target.id ?? "none"}>
              <Button
                variant="ghost"
                size="sm"
                className="w-full justify-start"
                onClick={() => {
                  close();
                  onMove(target.id);
                }}
              >
                <span className="truncate">{target.name}</span>
              </Button>
            </li>
          ))}
        </ul>
      )}
    </Popover>
  );
}
