import type { KeyboardEvent } from "react";

interface InspectorProps {
  id: string;
  open: boolean;
  onClose: () => void;
}

/** Right-hand inspector region. Content arrives with the canvas and run views. */
export function Inspector({ id, open, onClose }: InspectorProps) {
  function handleKeyDown(event: KeyboardEvent<HTMLElement>) {
    if (event.key !== "Escape") return;
    event.stopPropagation();
    onClose();
  }

  return (
    <aside id={id} className="inspector" aria-label="Inspector" hidden={!open} onKeyDown={handleKeyDown}>
      <div className="inspector__header">
        <h2 className="type-section-title">Inspector</h2>
        <button type="button" className="button button--ghost button--small" onClick={onClose}>
          Close inspector
        </button>
      </div>
      <div className="empty-state empty-state--compact">
        <p className="empty-state__title">Nothing selected</p>
        <p className="type-meta">Select a node, run or result to see its details here.</p>
      </div>
    </aside>
  );
}
