import { useState } from "react";
import type { ProfileRecord } from "../api/profiles";
import { Badge } from "../components/ui/badge";
import { Button } from "../components/ui/button";
import { CardContent } from "../components/ui/card";
import { plural } from "../lib/labels";
import { formatRoute } from "../lib/routes";
import { DeleteProfileDialog, inUseLine } from "./DeleteProfileDialog";
import { GalleryCard } from "./GalleryCard";
import { ProfileTitleEditor } from "./ProfileTitleEditor";

interface ProfileCardProps {
  profile: ProfileRecord;
  onDuplicate: (profile: ProfileRecord) => void;
  onDeleted: () => void;
}

const usedByLine = (names: readonly string[]): string =>
  names.length === 0 ? "Not used by any collection" : `Used by ${plural(names.length, "collection")}`;

/** One profile in the gallery: title, ID, use, readiness and its actions. */
export function ProfileCard({ profile, onDuplicate, onDeleted }: ProfileCardProps) {
  const [deleting, setDeleting] = useState(false);
  const builtIn = profile.kind === "builtin";
  const inUse = profile.used_by.length > 0;

  return (
    <GalleryCard
      title={profile.title}
      heading={builtIn ? undefined : <ProfileTitleEditor profile={profile} level={3} />}
      subtitle={
        builtIn ? <span className="font-mono text-meta text-muted-foreground break-all">Profile ID: {profile.profile_id}</span> : undefined
      }
      description={profile.description}
      badge={profile.ready ? undefined : <Badge variant="warning">Not ready</Badge>}
      action={
        <>
          <Button asChild>
            <a href={formatRoute({ area: "studio", profileId: profile.profile_id, purpose: null })}>Open profile</a>
          </Button>
          <Button variant="outline" onClick={() => onDuplicate(profile)}>
            Duplicate
          </Button>
          {builtIn ? null : (
            <Button variant="destructive" disabled={inUse} onClick={() => setDeleting(true)}>
              Delete
            </Button>
          )}
        </>
      }
    >
      <CardContent className="gap-2">
        <p className="text-meta text-muted-foreground">{usedByLine(profile.used_by)}</p>
        {profile.ready ? null : (
          <ul className="flex flex-col gap-1 text-meta text-status-warning-label">
            {profile.not_ready_reasons.map((reason) => (
              <li key={reason}>{reason}</li>
            ))}
          </ul>
        )}
        {!builtIn && inUse ? (
          <p className="text-meta text-muted-foreground">{`${inUseLine(profile.used_by)} Pick another profile for them in Knowledge Base first.`}</p>
        ) : null}
      </CardContent>
      {builtIn ? null : <DeleteProfileDialog profile={profile} open={deleting} onOpenChange={setDeleting} onDeleted={onDeleted} />}
    </GalleryCard>
  );
}
