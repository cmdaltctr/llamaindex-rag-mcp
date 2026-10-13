import { useId, useState } from "react";
import type { FetchLike } from "../../api/client";
import { changeProfile, type Profile, type ProfileChangeResult, type ProfilePreview } from "../../api/documents";
import { plural } from "../shared/labels";
import { ConfirmationNote, FlowButtons } from "./FlowControls";
import { usePreviewConfirm } from "./usePreviewConfirm";

const TIMING: Record<string, string> = { "query-time": "Next query", "ingest-time": "Next ingestion only" };

interface ProfilePanelProps {
  collection: string;
  /** Profile stored in the collection metadata, from the collection list. */
  storedProfile: string | null;
  fetchImpl?: FetchLike;
  /** Called after a confirmed change, so the collection list (and stored profile) reloads. */
  onChanged: () => void;
}

/**
 * Stored collection profile change: preview the lever impacts, then confirm
 * with the preview token. Stored chunks stay unchanged until a later ingest.
 */
export function ProfilePanel({ collection, storedProfile, fetchImpl, onChanged }: ProfilePanelProps) {
  const selectId = useId();
  const [profile, setProfile] = useState<Profile>("documents");
  const [open, setOpen] = useState(false);
  const flow = usePreviewConfirm(
    async () => (await changeProfile(collection, profile, { preview: true }, { fetchImpl })) as ProfilePreview,
    async (token) => {
      const result = (await changeProfile(collection, profile, { token }, { fetchImpl })) as ProfileChangeResult;
      onChanged();
      return result;
    },
  );

  function start() {
    setOpen(true);
    void flow.runPreview();
  }

  return (
    <section className="panel" aria-labelledby={`${selectId}-title`}>
      <h2 id={`${selectId}-title`} className="text-section-title">
        Collection profile
      </h2>
      <p>{storedProfile !== null ? `Stored profile: ${storedProfile}` : "No profile is stored for this collection."}</p>
      <div className="form-row">
        <div className="field">
          <label className="field__label" htmlFor={selectId}>
            New profile
          </label>
          <select
            id={selectId}
            className="control control--select"
            value={profile}
            disabled={open}
            onChange={(e) => setProfile(e.target.value as Profile)}
          >
            <option value="documents">documents</option>
            <option value="codebase">codebase</option>
          </select>
        </div>
        <button type="button" className="button button--tinted" onClick={start} disabled={open}>
          Preview profile change
        </button>
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
    <div className="panel panel--nested" role="region" aria-label="Profile change preview">
      {contract && (phase === "ready" || phase === "confirming") ? (
        <>
          <p>
            Change {contract.collection} from {contract.old_profile ?? "no stored profile"} to {contract.new_profile}.{" "}
            {plural(contract.chunk_count, "stored chunk")} stay unchanged.
          </p>
          <table className="data-table" aria-label="Setting changes">
            <thead>
              <tr>
                <th scope="col">Setting</th>
                <th scope="col">Change</th>
                <th scope="col">Applies from</th>
              </tr>
            </thead>
            <tbody>
              {contract.lever_impacts.map((impact) => (
                <tr key={impact.lever}>
                  <td className="text-code">{impact.lever}</td>
                  <td className="text-code">{impact.change}</td>
                  <td>{TIMING[impact.timing] ?? impact.timing}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="text-meta">{contract.reingest_pointer}</p>
          <ConfirmationNote confirmation={preview?.confirmation} />
        </>
      ) : null}
      {phase === "done" && result ? (
        <p className="notice notice--success">
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
    </div>
  );
}
