import { ChevronDown, ChevronRight } from "lucide-react";
import { useId, useState } from "react";
import { Button } from "../components/ui/button";

/**
 * The model's reasoning above the answer, closed at first. It opens with the
 * same disclosure button as the chat folders and shows plain text, with no
 * citation buttons.
 */
export function ReasoningBox({ text }: { text: string }) {
  const [open, setOpen] = useState(false);
  const id = useId();
  const Chevron = open ? ChevronDown : ChevronRight;
  return (
    <div className="flex flex-col items-start gap-1">
      <Button variant="ghost" size="xs" aria-expanded={open} aria-controls={id} onClick={() => setOpen(!open)}>
        <Chevron aria-hidden="true" />
        Reasoning
      </Button>
      {open ? (
        <p id={id} className="whitespace-pre-wrap break-words ps-2 text-meta text-muted-foreground">
          {text}
        </p>
      ) : null}
    </div>
  );
}
