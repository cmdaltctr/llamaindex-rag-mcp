import { useQuery } from "@tanstack/react-query";
import { useState, type ReactNode } from "react";
import { useApi } from "../api/ApiProvider";
import { ApiError } from "../api/client";
import type { ProfileDetail } from "../api/profiles";
import { pipelineQuery, profileQuery } from "../api/queries";
import { ErrorNotice } from "../components/ErrorNotice";
import { NotFound } from "../components/NotFound";
import { PageHeader } from "../components/PageHeader";
import { formatRoute, type Purpose } from "../lib/routes";
import { CanvasEditor } from "./CanvasEditor";
import { NewProfileDialog } from "./NewProfileDialog";
import { ProfileHeader } from "./ProfileHeader";

const GALLERY = formatRoute({ area: "studio", profileId: null, purpose: null });

const isMissing = (error: unknown) => error instanceof ApiError && error.kind === "http" && error.status === 404;

function Shell({ children }: { children: ReactNode }) {
  return (
    <section className="p-4 md:p-6">
      <PageHeader title="Studio" />
      {children}
    </section>
  );
}

/** A user profile: the pipeline of the open purpose, editable. A tab switch swaps the keyed editor, and drafts live per pipeline. */
function UserCanvas({ profile, purpose, onDuplicate }: { profile: ProfileDetail; purpose: Purpose; onDuplicate: () => void }) {
  const pipelineId = profile.slots[purpose];
  const query = useQuery({ ...pipelineQuery(useApi(), pipelineId ?? ""), enabled: pipelineId !== null });
  // While the pipeline loads or fails, the header stays so that the other purposes remain one click away.
  const beside = (content: ReactNode) => (
    <section className="flex flex-col gap-4 p-4 md:p-6">
      <ProfileHeader profile={profile} purpose={purpose} onDuplicate={onDuplicate} />
      {content}
    </section>
  );
  if (pipelineId === null || (query.isError && isMissing(query.error))) {
    return beside(<NotFound what="pipeline" name={pipelineId ?? purpose} backHref={GALLERY} backLabel="Back to Studio" />);
  }
  if (query.isError) return beside(<ErrorNotice error={query.error} onRetry={() => void query.refetch()} backHref={GALLERY} />);
  if (query.data === undefined) {
    return beside(
      <p role="status" className="text-meta text-muted-foreground">
        Loading the pipeline.
      </p>,
    );
  }
  return (
    <CanvasEditor
      key={pipelineId}
      profile={profile}
      purpose={purpose}
      source={{ kind: "pipeline", pipeline: query.data.pipeline, revision: query.data.current_revision }}
      onDuplicate={onDuplicate}
    />
  );
}

/**
 * Loads the profile the route names, then opens the canvas of the open purpose
 * (Ingest when the route names none). A user profile opens the pipeline of that
 * slot; a built-in profile opens its standard graph, read-only. A profile the
 * server does not return is "not found".
 */
export function CanvasPage({ profileId, purpose }: { profileId: string; purpose: Purpose | null }) {
  const query = useQuery(profileQuery(useApi(), profileId));
  const [duplicating, setDuplicating] = useState(false);
  const open = purpose ?? "ingest";

  if (query.isError) {
    return (
      <Shell>
        {isMissing(query.error) ? (
          <NotFound what="profile" name={profileId} backHref={GALLERY} backLabel="Back to Studio" />
        ) : (
          <ErrorNotice error={query.error} onRetry={() => void query.refetch()} backHref={GALLERY} />
        )}
      </Shell>
    );
  }
  const profile = query.data;
  if (profile === undefined) {
    return (
      <Shell>
        <p role="status" className="text-meta text-muted-foreground">
          Loading the profile.
        </p>
      </Shell>
    );
  }
  const onDuplicate = () => setDuplicating(true);
  const canvas =
    profile.kind === "builtin" && profile.standard_graphs !== null ? (
      <CanvasEditor
        key={`${profile.profile_id}:${open}`}
        profile={profile}
        purpose={open}
        source={{ kind: "standard", key: `${profile.profile_id}:${open}`, document: profile.standard_graphs[open] }}
        onDuplicate={onDuplicate}
      />
    ) : (
      <UserCanvas profile={profile} purpose={open} onDuplicate={onDuplicate} />
    );
  return (
    <>
      {canvas}
      <NewProfileDialog source={profile} open={duplicating} onOpenChange={setDuplicating} />
    </>
  );
}
