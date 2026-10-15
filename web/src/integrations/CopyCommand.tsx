import { Check, Copy } from "lucide-react";
import { useEffect, useState } from "react";
import { Button } from "../components/ui/button";

type CopyState = "idle" | "copied" | "failed";

const RESET_MS = 2500;

interface CopyCommandProps {
  command: string;
  /** What the command belongs to; part of the button's accessible name. */
  subject: string;
}

/**
 * A command in a selectable monospace block with a copy button. When the
 * browser has no clipboard or refuses the write, the command stays
 * selectable and a line says so.
 */
export function CopyCommand({ command, subject }: CopyCommandProps) {
  const [state, setState] = useState<CopyState>("idle");

  useEffect(() => {
    if (state === "idle") return;
    const timer = window.setTimeout(() => setState("idle"), RESET_MS);
    return () => window.clearTimeout(timer);
  }, [state]);

  async function copy() {
    try {
      await navigator.clipboard.writeText(command);
      setState("copied");
    } catch {
      setState("failed");
    }
  }

  return (
    <div className="flex flex-col gap-1">
      <div className="flex items-start gap-2">
        <code className="min-w-0 flex-1 select-all rounded-small border border-border bg-muted px-2 py-1.5 text-code [overflow-wrap:anywhere]">
          {command}
        </code>
        <Button type="button" variant="outline" size="sm" aria-label={`Copy install command for ${subject}`} onClick={() => void copy()}>
          {state === "copied" ? <Check size={16} aria-hidden="true" /> : <Copy size={16} aria-hidden="true" />}
          {state === "copied" ? "Copied" : "Copy"}
        </Button>
      </div>
      {state === "copied" && (
        <p role="status" className="text-meta text-muted-foreground">
          Copied. Run it in a terminal.
        </p>
      )}
      {state === "failed" && (
        <p role="status" className="text-meta text-muted-foreground">
          Could not copy. Select the command and copy it yourself.
        </p>
      )}
    </div>
  );
}
