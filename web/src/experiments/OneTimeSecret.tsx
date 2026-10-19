import { Copy, EyeOff } from "lucide-react";
import { useState, type ReactNode } from "react";
import { Button } from "../components/ui/button";

interface OneTimeSecretProps {
  title: string;
  secret: string;
  children?: ReactNode;
  onHide: () => void;
}

/**
 * Shows a secret that the server returns only once. The secret lives in
 * component state only: never in a URL, browser storage or a log.
 */
export function OneTimeSecret({ title, secret, children, onHide }: OneTimeSecretProps) {
  const [copy, setCopy] = useState("");

  async function copySecret() {
    try {
      await navigator.clipboard.writeText(secret);
      setCopy("Copied.");
    } catch {
      setCopy("Copy failed. Select the token and copy it by hand.");
    }
  }

  return (
    <section aria-label={title} className="flex flex-col gap-2 rounded-panel border border-status-warning bg-status-warning/10 p-4">
      <h3 className="text-subsection-title font-semibold">{title}</h3>
      <code dir="ltr" className="rounded-small border border-border bg-card px-2 py-1.5 font-mono text-code [overflow-wrap:anywhere]">
        {secret}
      </code>
      <p className="text-meta">Shown once. OMRG cannot show it again. Copy it now, then hide it.</p>
      {children}
      <div className="flex flex-wrap gap-2">
        <Button size="sm" onClick={() => void copySecret()}>
          <Copy aria-hidden="true" />
          Copy token
        </Button>
        <Button size="sm" variant="outline" onClick={onHide}>
          <EyeOff aria-hidden="true" />
          Hide token
        </Button>
      </div>
      <p role="status" className="text-meta text-muted-foreground">
        {copy}
      </p>
    </section>
  );
}
