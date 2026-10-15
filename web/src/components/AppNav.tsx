import { formatRoute, type RouteArea } from "../lib/routes";
import { AREAS } from "../lib/views";
import { cn } from "../lib/utils";

/**
 * The seven workspace areas. From the `md` breakpoint it is a side column;
 * below it, one row of icons with short labels and 44px targets. Links are
 * plain hash anchors, so the browser pushes the history entry.
 */
export function AppNav({ current }: { current: RouteArea }) {
  return (
    <nav aria-label="Workspace" className="border-b border-border bg-card md:border-e md:border-b-0 md:p-3">
      <ul className="flex md:flex-col md:gap-1">
        {AREAS.map((area) => {
          const Icon = area.icon;
          return (
            <li key={area.id} className="min-w-0 flex-1 md:flex-none">
              <a
                href={formatRoute(area.route)}
                aria-current={area.id === current ? "page" : undefined}
                className={cn(
                  "flex min-h-11 flex-col items-center justify-center gap-0.5 px-0 text-meta text-foreground transition-colors duration-150 hover:bg-interactive-hover aria-[current=page]:bg-selection",
                  "md:flex-row md:justify-start md:gap-2 md:rounded-control md:px-3 md:text-ui",
                )}
              >
                <Icon aria-hidden="true" className="size-4 shrink-0" />
                <span aria-hidden="true" className="w-full truncate text-center md:hidden">
                  {area.shortLabel}
                </span>
                <span className="sr-only md:not-sr-only md:truncate">{area.label}</span>
              </a>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
