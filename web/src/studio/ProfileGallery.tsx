import { useQuery } from "@tanstack/react-query";
import { Plus } from "lucide-react";
import { useState, type ReactNode } from "react";
import { useApi } from "../api/ApiProvider";
import type { ProfileRecord } from "../api/profiles";
import { profilesQuery } from "../api/queries";
import { ErrorNotice } from "../components/ErrorNotice";
import { Button } from "../components/ui/button";
import { GalleryCard } from "./GalleryCard";
import { NewProfileDialog } from "./NewProfileDialog";
import { ProfileCard } from "./ProfileCard";
import { StudioHeader } from "./StudioHeader";

const CARD_GRID = "grid items-start gap-3 sm:grid-cols-2 xl:grid-cols-3";

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="mt-6 flex flex-col gap-3 first:mt-0" aria-label={title}>
      <h2 className="text-section-title font-semibold">{title}</h2>
      {children}
    </section>
  );
}

/** The dialog the gallery has open: a copy of `source`, or an empty profile when `source` is `null`. */
type OpenDialog = { source: ProfileRecord | null } | null;

/** The Studio gallery: built-in profiles, your profiles and a card that starts an empty one. */
export function ProfileGallery() {
  const api = useApi();
  const profiles = useQuery(profilesQuery(api));
  const [dialog, setDialog] = useState<OpenDialog>(null);
  const [deleted, setDeleted] = useState(false);
  const builtIn = (profiles.data ?? []).filter((profile) => profile.kind === "builtin");
  const yours = (profiles.data ?? []).filter((profile) => profile.kind === "user");

  const card = (profile: ProfileRecord) => (
    <li key={profile.profile_id}>
      <ProfileCard profile={profile} onDuplicate={(source) => setDialog({ source })} onDeleted={() => setDeleted(true)} />
    </li>
  );

  return (
    <section>
      <StudioHeader />
      {profiles.isError && (
        <div className="mb-4">
          <ErrorNotice error={profiles.error} onRetry={() => void profiles.refetch()} />
        </div>
      )}
      {profiles.isPending && (
        <p role="status" className="text-meta text-muted-foreground">
          Loading profiles.
        </p>
      )}
      {deleted && (
        <p role="status" className="mb-4 text-meta text-status-success-label">
          Profile deleted.
        </p>
      )}
      {profiles.data !== undefined && (
        <Section title="Built-in profiles">
          <ul className={CARD_GRID}>{builtIn.map(card)}</ul>
        </Section>
      )}
      <Section title="Your profiles">
        {profiles.data !== undefined && yours.length === 0 && (
          <p className="text-meta text-muted-foreground">You have no profiles yet. Duplicate a built-in profile or start an empty one.</p>
        )}
        <ul className={CARD_GRID}>
          {yours.map(card)}
          <li>
            <GalleryCard
              title="New empty profile"
              description="Start with no steps and build your own pipelines."
              action={
                <Button variant="outline" onClick={() => setDialog({ source: null })}>
                  <Plus aria-hidden="true" />
                  New empty profile
                </Button>
              }
            />
          </li>
        </ul>
      </Section>
      <NewProfileDialog
        source={dialog?.source ?? null}
        open={dialog !== null}
        onOpenChange={(open) => !open && setDialog(null)}
      />
    </section>
  );
}
