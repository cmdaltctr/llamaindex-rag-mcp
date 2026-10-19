import { SendHorizontal } from "lucide-react";
import { useId, useState, type FormEvent } from "react";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";

/** The longest question the answer route accepts. */
export const MAX_QUESTION = 4096;

interface ComposerProps {
  collection: string;
  busy: boolean;
  /** True while Chat has no ready model. Send stays off. */
  unavailable?: boolean;
  onSend: (question: string) => void;
}

/** The question field, docked at the bottom of the column. It sends on the Send action or Enter. */
export function Composer({ collection, busy, unavailable = false, onSend }: ComposerProps) {
  const id = useId();
  const [text, setText] = useState("");

  function submit(event: FormEvent) {
    event.preventDefault();
    const question = text.trim();
    if (question === "" || busy || unavailable) return;
    setText("");
    onSend(question);
  }

  return (
    <form onSubmit={submit} className="sticky bottom-0 mt-auto flex flex-col gap-1.5 bg-background pt-3 pb-1">
      <Label htmlFor={id} className="sr-only">
        Question
      </Label>
      <div className="flex gap-2">
        <Input
          id={id}
          maxLength={MAX_QUESTION}
          autoComplete="off"
          placeholder={`Ask ${collection} a question`}
          value={text}
          onChange={(e) => setText(e.target.value)}
        />
        <Button type="submit" disabled={busy || unavailable || text.trim() === ""}>
          <SendHorizontal aria-hidden="true" />
          Send
        </Button>
      </div>
    </form>
  );
}
