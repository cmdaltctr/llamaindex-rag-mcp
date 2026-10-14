import { useCallback, useEffect, useRef, useState } from "react";
import { CanvasView } from "./canvas/CanvasView";
import { AppNav } from "./components/AppNav";
import { Inspector } from "./components/Inspector";
import { ThemeSelect } from "./components/ThemeSelect";
import { ViewShell } from "./components/ViewShell";
import { applyTheme, readUiState, writeUiState, type ThemePreference, type UiState } from "./lib/preferences";
import { viewById, viewFromHash, type ViewId } from "./lib/views";
import { DocumentView, isDocumentView } from "./views/DocumentView";
import { RunsView } from "./runs/RunsView";
import { ExperimentsView } from "./experiments/ExperimentsView";

const INSPECTOR_ID = "workspace-inspector";

function initialState(): UiState {
  const stored = readUiState();
  return { ...stored, view: viewFromHash(window.location.hash) ?? stored.view };
}

export default function App() {
  const [state, setState] = useState<UiState>(initialState);
  const [navigated, setNavigated] = useState(false);
  const inspectorToggleRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    applyTheme(state.theme);
    writeUiState(state);
  }, [state]);

  // Keep the view in step with the address bar (back, forward, typed hashes).
  useEffect(() => {
    function syncFromHash() {
      const view = viewFromHash(window.location.hash);
      if (view !== null) setState((current) => (current.view === view ? current : { ...current, view }));
    }
    window.addEventListener("hashchange", syncFromHash);
    window.addEventListener("popstate", syncFromHash);
    return () => {
      window.removeEventListener("hashchange", syncFromHash);
      window.removeEventListener("popstate", syncFromHash);
    };
  }, []);

  const navigate = useCallback((view: ViewId) => {
    if (viewFromHash(window.location.hash) !== view) window.history.pushState(null, "", `#/${view}`);
    setNavigated(true);
    setState((current) => ({ ...current, view }));
  }, []);

  const setTheme = useCallback((theme: ThemePreference) => {
    setState((current) => ({ ...current, theme }));
  }, []);

  const toggleInspector = useCallback(() => {
    setState((current) => ({ ...current, inspectorOpen: !current.inspectorOpen }));
  }, []);

  const closeInspector = useCallback(() => {
    setState((current) => ({ ...current, inspectorOpen: false }));
    inspectorToggleRef.current?.focus();
  }, []);

  const view = viewById(state.view);

  return (
    <div className="app" data-inspector={state.inspectorOpen ? "open" : "closed"}>
      <a className="skip-link" href="#workspace-main">
        Skip to content
      </a>
      <header className="topbar">
        <p className="topbar__brand">
          <span className="topbar__name">OMRG</span>
          <span className="topbar__subtitle type-meta">Local workspace</span>
        </p>
        <div className="topbar__actions">
          <ThemeSelect value={state.theme} onChange={setTheme} />
          <button
            ref={inspectorToggleRef}
            type="button"
            className="button button--tinted"
            aria-expanded={state.inspectorOpen}
            aria-controls={INSPECTOR_ID}
            onClick={toggleInspector}
          >
            Inspector
          </button>
        </div>
      </header>
      <AppNav current={state.view} onNavigate={navigate} />
      <main id="workspace-main" className="main" tabIndex={-1}>
        {view.id === "canvas" ? (
          <CanvasView key={view.id} focusHeading={navigated} />
        ) : view.id === "runs" ? (
          <RunsView key={view.id} focusHeading={navigated} />
        ) : view.id === "experiments" ? (
          <ExperimentsView key={view.id} focusHeading={navigated} />
        ) : isDocumentView(view.id) ? (
          <DocumentView key={view.id} id={view.id} focusHeading={navigated} theme={state.theme} onThemeChange={setTheme} />
        ) : (
          <ViewShell key={view.id} view={view} focusHeading={navigated} />
        )}
      </main>
      <Inspector id={INSPECTOR_ID} open={state.inspectorOpen} onClose={closeInspector} />
    </div>
  );
}
