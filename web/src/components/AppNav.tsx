import { PanelLeftClose, PanelLeftOpen } from "lucide-react";
import { formatRoute, type RouteArea } from "../lib/routes";
import { AREAS } from "../lib/views";
import { cn } from "../lib/utils";
import { Button } from "./ui/button";

interface AppNavProps {
  current: RouteArea;
  /** From the `md` breakpoint, show icons only. Below it the nav is always one row. */
  collapsed: boolean;
  onToggle: () => void;
}

/**
 * The seven workspace areas. From the `md` breakpoint it is a side column
 * that collapses to an icon column; below it, one row of icons with short
 * labels and 44px targets. Links are plain hash anchors, so the browser
 * pushes the history entry.
 */
export function AppNav({ current, collapsed, onToggle }: AppNavProps) {
  const ToggleIcon = collapsed ? PanelLeftOpen : PanelLeftClose;
  return (
    <nav
      aria-label="Workspace"
      className={cn("border-b border-border bg-card md:border-e md:border-b-0", collapsed ? "md:p-2" : "md:p-3")}
    >
      <div className={cn("hidden md:mb-2 md:flex", collapsed ? "md:justify-center" : "md:justify-end")}>
        <Button
          variant="ghost"
          size="icon-sm"
          aria-label={collapsed ? "Expand navigation" : "Collapse navigation"}
          aria-expanded={!collapsed}
          onClick={onToggle}
        >
          <ToggleIcon aria-hidden="true" />
        </Button>
      </div>
      <ul className="flex md:flex-col md:gap-1">
        {AREAS.map((area) => {
          const Icon = area.icon;
          return (
            <li key={area.id} className="min-w-0 flex-1 md:flex-none">
              <a
                href={formatRoute(area.route)}
                aria-current={area.id === current ? "page" : undefined}
                title={collapsed ? area.label : undefined}
                className={cn(
                  "flex min-h-11 flex-col items-center justify-center gap-0.5 px-0 text-meta text-foreground transition-colors duration-150 hover:bg-interactive-hover aria-[current=page]:bg-selection",
                  "md:flex-row md:gap-2 md:rounded-control md:text-ui",
                  collapsed ? "md:justify-center md:px-0" : "md:justify-start md:px-3",
                )}
              >
                <Icon aria-hidden="true" className="size-4 shrink-0" />
                <span aria-hidden="true" className="w-full truncate text-center md:hidden">
                  {area.shortLabel}
                </span>
                <span className={cn("sr-only", !collapsed && "md:not-sr-only md:truncate")}>{area.label}</span>
              </a>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
