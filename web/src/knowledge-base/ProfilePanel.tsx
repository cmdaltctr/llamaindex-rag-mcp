import { useId, useState } from "react";
import type { Profile, ProfileChangeResult, ProfilePreview } from "../api/documents";
import { useChangeProfile } from "../api/mutations";
import { Badge } from "../components/ui/badge";
import { Button } from "../components/ui/button";
import { Card } from "../components/ui/card";
import { Label } from "../components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "../components/ui/table";
import { plural } from "../lib/labels";
import { ConfirmationNote, FlowButtons } from "./FlowControls";
import { usePreviewConfirm } from "./usePreviewConfirm";

const TIMING: Record<string, string> = { "query-time": "Next query", "ingest-time": "Next ingestion only" };
const PROFILES: readonly Profile[] = ["documents", "codebase"];

function selectable(stored: string | null): Profile | null {
  return PROFILES.find((name) => name === stored) ?? null;
}

interface ProfilePanelProps {
  collection: string;
  /** Profile stored in the collection metadata, from the collection list. */
  storedProfile: string | null;
}

/**
 * Stored collection profile change: preview the lever impacts, then confirm
 * with the preview token. Stored chunks stay unchanged until a later ingest.
 */
export function ProfilePanel({ collection, storedProfile }: ProfilePanelProps) {
  const selectId = useId();
  // Start on the stored profile when it is selectable, else on no selection,
  // so the list never suggests a profile that is not stored.
  const [profile, setProfile] = useState<Profile | null>(selectable(storedProfile));
  const [open, setOpen] = useState(false);
  const change = useChangeProfile(collection);
  const flow = usePreviewConfirm(
    async () => (await change.mutateAsync({ profile: profile as Profile, step: { preview: true } })) as ProfilePreview,
    async (token) => (await change.mutateAsync({ profile: profile as Profile, step: { token } })) as ProfileChangeResult,
  );

  function start() {
    setOpen(true);
    void flow.runPreview();
  }

  return (
    <section aria-label="Collection profile" className="flex flex-col gap-3">
      <h2 className="text-section-title font-semibold">Collection profile</h2>
      <p className="flex flex-wrap items-center gap-2">
        Stored profile
        {storedProfile !== null ? <Badge variant="hue">{storedProfile}</Badge> : <Badge variant="neutral">No profile</Badge>}
      </p>
      <div className="flex flex-wrap items-end gap-3">
        <div className="flex w-48 max-w-full flex-col gap-1.5">
          <Label htmlFor={selectId}>New profile</Label>
          <Select value={profile ?? ""} disabled={open} onValueChange={(value) => setProfile(value as Profile)}>
            <SelectTrigger id={selectId}>
              <SelectValue placeholder="Choose a profile" />
            </SelectTrigger>
            <SelectContent>
              {PROFILES.map((name) => (
                <SelectItem key={name} value={name}>
                  {name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <Button onClick={start} disabled={open || profile === null}>
          Preview profile change
        </Button>
      </div>
      {open ? <ProfileFlow flow={flow} onClose={() => setOpen(false)} /> : null}
    </section>
  );
}

type Flow = ReturnType<typeof usePreviewConfirm<ProfilePreview, ProfileChangeResult>>;

function ProfileFlow({ flow, onClose }: { flow: Flow; onClose: () => void }) {
  const { phase, preview, result } = flow.state;
  const contract = preview?.contract;
  return (
    <Card role="region" aria-label="Profile change preview">
      {contract && (phase === "ready" || phase === "confirming") ? (
        <>
          <p>
            Change {contract.collection} from {contract.old_profile ?? "no stored profile"} to {contract.new_profile}.{" "}
            {plural(contract.chunk_count, "stored chunk")} stay unchanged.
          </p>
          <Table aria-label="Setting changes">
            <TableHeader>
              <TableRow>
                <TableHead scope="col">Setting</TableHead>
                <TableHead scope="col">Change</TableHead>
                <TableHead scope="col">Applies from</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {contract.lever_impacts.map((impact) => (
                <TableRow key={impact.lever}>
                  <TableCell className="font-mono text-code">{impact.lever}</TableCell>
                  <TableCell className="font-mono text-code">{impact.change}</TableCell>
                  <TableCell>{TIMING[impact.timing] ?? impact.timing}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
          <p className="text-meta text-muted-foreground">{contract.reingest_pointer}</p>
          <ConfirmationNote confirmation={preview?.confirmation} />
        </>
      ) : null}
      {phase === "done" && result ? (
        <p role="status" className="text-status-success-label">
          Profile changed to {result.profile}. {plural(result.chunk_count_unchanged, "chunk")} unchanged.
        </p>
      ) : null}
      <FlowButtons
        state={flow.state}
        confirmLabel="Confirm profile change"
        canConfirm
        onConfirm={() => void flow.runConfirm()}
        onPreviewAgain={() => void flow.runPreview()}
        onCancel={onClose}
      />
    </Card>
  );
}
