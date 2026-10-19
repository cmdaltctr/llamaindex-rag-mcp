import { ShieldAlert } from "lucide-react";

/** The server's trust notice, verbatim, in a warning panel. Notebook Python runs with the user's own permissions. */
export function TrustNotice({ text }: { text: string | null }) {
  return (
    <section aria-label="Trust notice" className="flex items-start gap-3 rounded-panel border border-status-warning bg-status-warning/10 px-4 py-3">
      <ShieldAlert aria-hidden="true" className="mt-0.5 size-4 shrink-0 text-status-warning-label" />
      <div className="flex flex-col gap-1">
        <h2 className="text-subsection-title font-semibold">Trust notice</h2>
        {text !== null ? <p className="text-ui">{text}</p> : <p className="text-meta text-muted-foreground">Loading the trust notice.</p>}
      </div>
    </section>
  );
}
