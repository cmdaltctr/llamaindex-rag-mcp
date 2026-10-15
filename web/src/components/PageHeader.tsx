import type { ReactNode } from "react";

/** The heading of a view. The shell moves focus here after navigation. */
export function PageHeader({ title, summary, actions }: { title: string; summary?: string; actions?: ReactNode }) {
  return (
    <header className="mb-4 flex flex-wrap items-start justify-between gap-3">
      <div className="min-w-0">
        <h1 tabIndex={-1} className="text-page-title font-semibold outline-none [overflow-wrap:anywhere]">
          {title}
        </h1>
        {summary !== undefined && <p className="text-meta text-muted-foreground">{summary}</p>}
      </div>
      {actions}
    </header>
  );
}
