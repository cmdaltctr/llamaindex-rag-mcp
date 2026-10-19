import type { LucideIcon } from "lucide-react";
import type { ReactNode } from "react";

interface EmptyStateProps {
  icon: LucideIcon;
  /** One sentence. */
  message: string;
  /** One action: a button or a link. */
  action?: ReactNode;
}

/** The shared empty state: an icon, one sentence and one action. */
export function EmptyState({ icon: Icon, message, action }: EmptyStateProps) {
  return (
    <div className="flex flex-col items-center gap-3 rounded-panel border border-dashed border-border px-4 py-10 text-center" data-testid="empty-state">
      <Icon aria-hidden="true" className="size-8 text-muted-foreground" />
      <p className="max-w-prose text-ui text-foreground">{message}</p>
      {action}
    </div>
  );
}
