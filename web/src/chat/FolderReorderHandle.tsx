import { GripVertical } from "lucide-react";
import { Button } from "../components/ui/button";

interface FolderReorderHandleProps {
  name: string;
  onDragStart: (event: React.DragEvent) => void;
  onDragEnd: () => void;
  /** Moves the folder one place: -1 up, +1 down. */
  onStep: (step: -1 | 1) => void;
}

/** The select-mode grip on a folder. Drag it onto another folder, or press Up or Down arrow. */
export function FolderReorderHandle({ name, onDragStart, onDragEnd, onStep }: FolderReorderHandleProps) {
  return (
    <Button
      variant="ghost"
      size="icon-xs"
      aria-label={`Reorder folder ${name}`}
      aria-keyshortcuts="ArrowUp ArrowDown"
      className="cursor-grab active:cursor-grabbing"
      draggable
      onDragStart={onDragStart}
      onDragEnd={onDragEnd}
      onKeyDown={(event) => {
        if (event.key !== "ArrowUp" && event.key !== "ArrowDown") return;
        event.preventDefault();
        onStep(event.key === "ArrowUp" ? -1 : 1);
      }}
    >
      <GripVertical aria-hidden="true" />
    </Button>
  );
}
