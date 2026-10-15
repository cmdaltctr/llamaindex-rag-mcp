import { Check, Copy } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Button } from "../components/ui/button";

const RESET_MS = 2000;

interface CopyButtonProps {
  /** The text that goes to the clipboard. */
  text: string;
  /** What the text is, for the accessible name and the confirmation: "stdio configuration". */
  what: string;
}

/** Copies text. The result shows as text and a polite announcement, so the confirmation never depends on colour. */
export function CopyButton({ text, what }: CopyButtonProps) {
  const [state, setState] = useState<"idle" | "copied" | "failed">("idle");
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => () => {
    if (timer.current !== null) clearTimeout(timer.current);
  }, []);

  async function copy() {
    try {
      await navigator.clipboard.writeText(text);
      setState("copied");
    } catch {
      setState("failed");
    }
    if (timer.current !== null) clearTimeout(timer.current);
    timer.current = setTimeout(() => setState("idle"), RESET_MS);
  }

  const Icon = state === "copied" ? Check : Copy;
  return (
    <span className="inline-flex flex-wrap items-center gap-2">
      <Button variant="outline" size="sm" aria-label={`Copy ${what}`} onClick={() => void copy()}>
        <Icon aria-hidden="true" />
        {state === "copied" ? "Copied" : "Copy"}
      </Button>
      <span role="status" className="text-meta text-muted-foreground">
        {state === "copied" ? `Copied ${what}.` : state === "failed" ? "Could not copy. Select the text and copy it by hand." : ""}
      </span>
    </span>
  );
}
