import { EngineStatus } from "./EngineStatus";
import { ThemeSelect, ThemeToggle } from "./ThemeControls";

export function TopBar() {
  return (
    <header className="sticky top-0 z-10 flex min-h-12 items-center justify-between gap-3 border-b border-border bg-card px-4 shadow-floating md:col-span-2">
      <p className="flex items-baseline gap-2">
        <span className="text-section-title font-semibold">OMRG</span>
        <span className="hidden text-meta text-muted-foreground sm:inline">Local workspace</span>
      </p>
      <div className="flex items-center gap-2">
        <EngineStatus />
        <ThemeSelect />
        <ThemeToggle />
      </div>
    </header>
  );
}
