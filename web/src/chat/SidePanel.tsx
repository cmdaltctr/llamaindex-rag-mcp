import { ChevronLeft, ChevronRight } from "lucide-react";
import type { ReactNode } from "react";
import { Button } from "../components/ui/button";
import { Card } from "../components/ui/card";
import { cn } from "../lib/utils";

interface SidePanelProps {
  /** Which side of the chat the card sits on. The chevron points toward that side to hide it. */
  side: "left" | "right";
  /** Names the card in the hide and show buttons, for example "chat history". */
  label: string;
  collapsed: boolean;
  onToggle: () => void;
  /** Receives the hide chevron, so the card decides where it sits in its own header row. */
  children: (hide: ReactNode) => ReactNode;
}

/**
 * A card beside the chat that can be hidden. On a wide screen a hidden card
 * leaves a narrow strip with a show button, so the chat can take the room.
 * Below that width the cards stack and are always shown, so the hide chevron
 * does not appear and the content stays mounted either way.
 */
export function SidePanel({ side, label, collapsed, onToggle, children }: SidePanelProps) {
  const Hide = side === "left" ? ChevronLeft : ChevronRight;
  const Show = side === "left" ? ChevronRight : ChevronLeft;
  const hide = (
    <Button variant="ghost" size="icon-xs" className="hidden shrink-0 lg:inline-flex" aria-label={`Hide ${label}`} aria-expanded={true} onClick={onToggle}>
      <Hide aria-hidden="true" />
    </Button>
  );
  return (
    <>
      <Card data-collapsed={collapsed} className={cn("gap-2 p-3", collapsed && "lg:hidden")}>
        {children(hide)}
      </Card>
      {collapsed ? (
        <div className="hidden lg:flex lg:justify-center">
          <Button variant="outline" size="icon-sm" aria-label={`Show ${label}`} aria-expanded={false} onClick={onToggle}>
            <Show aria-hidden="true" />
          </Button>
        </div>
      ) : null}
    </>
  );
}
