import { useEffect, useRef } from "react";
import type { ViewDefinition } from "../lib/views";

interface ViewShellProps {
  view: ViewDefinition;
  /** Moves focus to the heading so screen readers announce the new view. */
  focusHeading: boolean;
}

/** Placeholder shell for a workspace view: heading, summary and empty state. */
export function ViewShell({ view, focusHeading }: ViewShellProps) {
  const headingRef = useRef<HTMLHeadingElement>(null);

  useEffect(() => {
    if (focusHeading) headingRef.current?.focus();
  }, [focusHeading]);

  return (
    <section className="view" aria-labelledby={`view-${view.id}-title`}>
      <header className="view__header">
        <h1 id={`view-${view.id}-title`} className="type-page-title" ref={headingRef} tabIndex={-1}>
          {view.label}
        </h1>
        <p className="type-meta">{view.summary}</p>
      </header>
      <div className="empty-state" data-testid="empty-state">
        <p className="empty-state__title">{view.emptyTitle}</p>
        <p className="type-meta">{view.emptyBody}</p>
      </div>
    </section>
  );
}
