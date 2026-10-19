import { Brand } from "./Brand";
import { EngineStatus } from "./EngineStatus";
import { ThemeToggle } from "./ThemeControls";

/** From `md` the brand lives in the side navigation, so the bar shows it on narrow screens only. */
export function TopBar() {
  return (
    <header className="sticky top-0 z-10 flex min-h-12 items-center justify-between gap-3 border-b border-border bg-card px-4 shadow-floating md:col-start-2">
      <p className="flex items-center gap-2">
        <Brand className="md:hidden" />
        <span className="hidden text-meta text-muted-foreground sm:inline">Local workspace</span>
      </p>
      <div className="flex items-center gap-2">
        <EngineStatus />
        <ThemeToggle />
      </div>
    </header>
  );
}
