import { ArrowLeft, Copy } from "lucide-react";
import type { ProfileRecord } from "../api/profiles";
import { Badge } from "../components/ui/badge";
import { Button } from "../components/ui/button";
import { formatRoute, PURPOSES, type Purpose } from "../lib/routes";
import { PURPOSE_LABELS, PURPOSE_LINES, READ_ONLY_NOTICE } from "./profileCopy";
import { ProfileTitleEditor } from "./ProfileTitleEditor";

interface ProfileHeaderProps {
  profile: ProfileRecord;
  /** The purpose that is open. A route with no purpose opens Ingest. */
  purpose: Purpose;
  /** Opens the duplicate dialog for a built-in profile. */
  onDuplicate: () => void;
}

/**
 * The page header of the canvas: the profile, the three pipelines it holds and
 * the way back to the gallery. A built-in profile also shows why the canvas is
 * read-only, with the way to a copy.
 */
export function ProfileHeader({ profile, purpose, onDuplicate }: ProfileHeaderProps) {
  const builtin = profile.kind === "builtin";
  return (
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
        <nav aria-label="Pipelines of this profile" className="flex flex-wrap items-center gap-1.5">
          {PURPOSES.map((candidate) => (
            <Button key={candidate} asChild variant="chip" size="sm" data-selected={candidate === purpose}>
              <a href={formatRoute({ area: "studio", profileId: profile.profile_id, purpose: candidate })} aria-current={candidate === purpose ? "page" : undefined}>
                {PURPOSE_LABELS[candidate]}
              </a>
            </Button>
          ))}
        </nav>
        <p className="text-meta text-muted-foreground">{PURPOSE_LINES[purpose]}</p>
        {builtin && (
          <div className="flex flex-wrap items-center gap-2">
            <p className="text-meta text-muted-foreground">{READ_ONLY_NOTICE}</p>
            <Button variant="outline" size="sm" onClick={onDuplicate}>
              <Copy aria-hidden="true" />
              Duplicate to edit
            </Button>
          </div>
        )}
      </header>
      <Button asChild variant="outline">
        <a href={formatRoute({ area: "studio", profileId: null, purpose: null })}>
          <ArrowLeft aria-hidden="true" />
          All profiles
        </a>
      </Button>
    </div>
  );
}
