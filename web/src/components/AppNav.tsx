import type { MouseEvent } from "react";
import { VIEWS, type ViewId } from "../lib/views";

interface AppNavProps {
  current: ViewId;
  onNavigate: (view: ViewId) => void;
}

export function AppNav({ current, onNavigate }: AppNavProps) {
  function handleClick(event: MouseEvent<HTMLAnchorElement>, view: ViewId) {
    // Let modified clicks open a new tab as normal.
    if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey || event.button !== 0) return;
    event.preventDefault();
    onNavigate(view);
  }

  return (
    <nav className="app-nav" aria-label="Workspace">
      <ul className="app-nav__list">
        {VIEWS.map((view) => (
          <li key={view.id}>
            <a
              className="app-nav__link"
              href={`#/${view.id}`}
              aria-current={view.id === current ? "page" : undefined}
              onClick={(event) => handleClick(event, view.id)}
            >
              {view.label}
            </a>
          </li>
        ))}
      </ul>
    </nav>
  );
}
