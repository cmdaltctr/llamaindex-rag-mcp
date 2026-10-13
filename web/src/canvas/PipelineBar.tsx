import type { PipelineRecord } from "../api/pipelines";
import { setCollection, setProfile, setTitle, type Draft } from "./graph";

interface PipelineBarProps {
  pipelines: readonly PipelineRecord[];
  pipelineId: string | null;
  draft: Draft;
  disabled: boolean;
  onOpen: (pipelineId: string | null) => void;
  onChange: (change: (draft: Draft) => Draft) => void;
}

/** Pipeline choice, title, operational profile and default collection. */
export function PipelineBar({ pipelines, pipelineId, draft, disabled, onOpen, onChange }: PipelineBarProps) {
  return (
    <div className="pipeline-bar">
      <label className="field">
        <span className="field__label">Pipeline</span>
        <select
          className="control control--select"
          value={pipelineId ?? ""}
          disabled={disabled}
          onChange={(event) => onOpen(event.target.value || null)}
        >
          <option value="">Unsaved pipeline</option>
          {pipelines.map((pipeline) => (
            <option key={pipeline.pipeline_id} value={pipeline.pipeline_id}>
              {pipeline.title}
            </option>
          ))}
        </select>
      </label>
      <label className="field">
        <span className="field__label">Title</span>
        <input className="control" value={draft.layout.title} onChange={(event) => onChange((d) => setTitle(d, event.target.value))} />
      </label>
      <label className="field">
        <span className="field__label">Profile</span>
        <select
          className="control control--select"
          value={draft.graph.profile ?? ""}
          onChange={(event) => onChange((d) => setProfile(d, event.target.value || null))}
        >
          <option value="">Inherit from each collection</option>
          <option value="documents">documents</option>
          <option value="codebase">codebase</option>
        </select>
      </label>
      <label className="field">
        <span className="field__label">Collection</span>
        <input
          className="control"
          value={draft.graph.collection ?? ""}
          placeholder="Host default"
          onChange={(event) => onChange((d) => setCollection(d, event.target.value))}
        />
      </label>
    </div>
  );
}
