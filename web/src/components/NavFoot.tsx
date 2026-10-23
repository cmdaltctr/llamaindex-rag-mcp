import { Settings } from "lucide-react";
import { formatRoute } from "../lib/routes";
import { cn } from "../lib/utils";
import { PowerMenu } from "./PowerMenu";
import { ThemeToggle } from "./ThemeControls";
import { Button } from "./ui/button";

const REPOSITORY_URL = "https://github.com/cmdaltctr/omrs";

// lucide-react 1.x ships no brand icons, so the GitHub mark is inline.
function GitHubMark() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true" fill="currentColor" className="size-4">
      <path d="M12 .5C5.65.5.5 5.65.5 12c0 5.08 3.29 9.39 7.86 10.91.58.1.79-.25.79-.56v-2.15c-3.2.7-3.88-1.36-3.88-1.36-.52-1.33-1.28-1.69-1.28-1.69-1.04-.71.08-.7.08-.7 1.15.08 1.76 1.18 1.76 1.18 1.03 1.76 2.69 1.25 3.35.96.1-.74.4-1.25.73-1.54-2.55-.29-5.24-1.28-5.24-5.69 0-1.26.45-2.28 1.18-3.09-.12-.29-.51-1.46.11-3.05 0 0 .97-.31 3.17 1.18a11 11 0 0 1 5.77 0c2.2-1.49 3.17-1.18 3.17-1.18.62 1.59.23 2.76.11 3.05.74.81 1.18 1.83 1.18 3.09 0 4.42-2.69 5.39-5.25 5.68.41.36.78 1.06.78 2.14v3.17c0 .31.21.67.8.56A11.5 11.5 0 0 0 23.5 12C23.5 5.65 18.35.5 12 .5Z" />
    </svg>
  );
}

/**
 * Four icon controls at the foot of the side navigation: theme, Settings,
 * the server's power light and the GitHub repository. The power light follows
 * `GET /v1/health`; the panel holds Turn off and Restart, each behind a
 * confirmation (see `PowerMenu`). Icons only, so the same strip fits the
 * collapsed column and the row below the `md` breakpoint.
 */
export function NavFoot({ collapsed, onSettings }: { collapsed: boolean; onSettings: boolean }) {
  return (
    <div
      role="group"
      aria-label="Quick controls"
      className={cn(
        "flex items-center justify-around border-t border-border p-1 md:mt-auto",
        collapsed ? "md:flex-col md:gap-1 md:p-2" : "md:justify-between md:p-3",
      )}
    >
      <ThemeToggle />
      <Button asChild variant="ghost" size="icon">
        <a href={formatRoute({ area: "settings", section: null })} aria-label="Settings" aria-current={onSettings ? "page" : undefined} className="aria-[current=page]:bg-selection">
          <Settings aria-hidden="true" />
        </a>
      </Button>
      <PowerMenu />
      <Button asChild variant="ghost" size="icon">
        <a href={REPOSITORY_URL} target="_blank" rel="noopener noreferrer" aria-label="OMRS on GitHub">
          <GitHubMark />
        </a>
      </Button>
    </div>
  );
}
