import { ArrowLeft, Copy, PanelTopClose, PanelTopOpen } from "lucide-react";
import type { ProfileRecord } from "../api/profiles";
import { Badge } from "../components/ui/badge";
import { Button } from "../components/ui/button";
import { cn } from "../lib/utils";
import { formatRoute, PURPOSES, type Purpose } from "../lib/routes";
import { InfoPopover } from "./InfoPopover";
import { CANVAS_INTRO, PURPOSE_LABELS, PURPOSE_LINES, READ_ONLY_NOTICE } from "./profileCopy";
import { ProfileTitleEditor } from "./ProfileTitleEditor";

interface ProfileHeaderProps {
  profile: ProfileRecord;
  /** The purpose that is open. A route with no purpose opens Ingest. */
  purpose: Purpose;
  /** Opens the duplicate dialog for a built-in profile. */
  onDuplicate: () => void;
  /** True while the intro line and the pipeline tabs are slid up. The title row always stays. */
  collapsed?: boolean;
  /** Slides the intro line and the tabs up or down. Only the canvas editor passes it, because only it has room to gain. */
  onToggle?: () => void;
}

/**
 * The page header of the canvas: the profile, the three pipelines it holds and
 * the way back to the gallery. One visible line says how to edit the canvas.
 * Each pipeline tab has an info button that opens what that pipeline does, and
 * for a built-in profile why the canvas is read-only. The Duplicate to edit
 * button sits beside the way back.
 */
export function ProfileHeader({ profile, purpose, onDuplicate, collapsed = false, onToggle }: ProfileHeaderProps) {
  const builtin = profile.kind === "builtin";
  return (
    <div className="flex flex-col">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <header className="flex min-w-0 flex-col gap-1.5">
          <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
            <ProfileTitleEditor profile={profile} level={1} />
            <Badge variant={builtin ? "neutral" : "accent"}>{builtin ? "Built-in" : "Your profile"}</Badge>
            {!profile.ready && <Badge variant="warning">Not ready</Badge>}
            {builtin && <span className="font-mono text-code text-muted-foreground [overflow-wrap:anywhere]">{profile.profile_id}</span>}
          </div>
          {!profile.ready && (
            <ul className="flex flex-col gap-0.5">
              {profile.not_ready_reasons.map((reason) => (
                <li key={reason} className="text-meta text-status-warning-label">
                  {reason}
                </li>
              ))}
            </ul>
          )}
        </header>
        <div className="flex flex-wrap items-center gap-2">
          {builtin && (
            <Button variant="outline" onClick={onDuplicate}>
              <Copy aria-hidden="true" />
              Duplicate to edit
            </Button>
          )}
          <Button asChild variant="outline">
            <a href={formatRoute({ area: "studio", profileId: null, purpose: null })}>
              <ArrowLeft aria-hidden="true" />
              All profiles
            </a>
          </Button>
          {onToggle && (
            <Button variant="ghost" size="icon-sm" aria-label={collapsed ? "Show header" : "Hide header"} aria-expanded={!collapsed} onClick={onToggle}>
              {collapsed ? <PanelTopOpen aria-hidden="true" /> : <PanelTopClose aria-hidden="true" />}
            </Button>
          )}
        </div>
      </div>
      {/* The intro line and the tabs slide up by animating their grid row to zero. `inert` keeps them out of the tab order. */}
      <div className={cn("grid transition-[grid-template-rows] duration-200 motion-reduce:transition-none", collapsed ? "grid-rows-[0fr]" : "grid-rows-[1fr]")}>
        <div inert={collapsed} className="min-h-0 overflow-hidden">
          <div className="flex flex-col gap-1.5 pt-1.5">
            <p className="py-1 text-meta text-muted-foreground">{CANVAS_INTRO}</p>
            <nav aria-label="Pipelines of this profile" className="relative flex flex-wrap items-center gap-1.5">
              {PURPOSES.map((candidate) => (
                <span key={candidate} className="inline-flex items-center gap-0.5">
                  <Button asChild variant="chip" size="sm" data-selected={candidate === purpose}>
                    <a href={formatRoute({ area: "studio", profileId: profile.profile_id, purpose: candidate })} aria-current={candidate === purpose ? "page" : undefined}>
                      {PURPOSE_LABELS[candidate]}
                    </a>
                  </Button>
                  <InfoPopover label={`About the ${PURPOSE_LABELS[candidate]} pipeline`}>
                    <p>{PURPOSE_LINES[candidate]}</p>
                    {builtin && <p className="text-muted-foreground">{READ_ONLY_NOTICE}</p>}
                  </InfoPopover>
                </span>
              ))}
            </nav>
          </div>
        </div>
      </div>
    </div>
  );
}
