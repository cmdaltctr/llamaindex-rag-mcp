import { useCallback, useId, useState } from "react";
import type { FetchLike } from "../../api/client";
import { listCollections, listDocuments, listRoots, type CollectionInfo, type Job } from "../../api/documents";
import { ErrorNotice, ViewHeader } from "../shared/controls";
import { plural } from "../shared/labels";
import { useLoad } from "../shared/useLoad";
import { DeletePanel, type DeleteTarget } from "./DeletePanel";
import { IngestPanel } from "./IngestPanel";
import { JobList, type TrackedJob } from "./JobList";
import { ProfilePanel } from "./ProfilePanel";
import { SourceTable } from "./SourceTable";
import { UploadPanel } from "./UploadPanel";

interface LibraryViewProps {
  fetchImpl?: FetchLike;
  focusHeading?: boolean;
  /** Job polling interval in milliseconds. */
  pollMs?: number;
}

interface Deletion {
  collection: string;
  target: DeleteTarget;
}

/** Collections, sources, uploads, ingestion jobs and confirmed destructive changes. */
export function LibraryView({ fetchImpl, focusHeading = false, pollMs = 1000 }: LibraryViewProps) {
  const targetId = useId();
  const collections = useLoad(() => listCollections({ fetchImpl }), "collections");
  const roots = useLoad(() => listRoots({ fetchImpl }), "roots");
  const [selected, setSelected] = useState<string | null>(null);
  const [target, setTarget] = useState("");
  const [jobs, setJobs] = useState<TrackedJob[]>([]);
  const [deletion, setDeletion] = useState<Deletion | null>(null);

  const list = collections.data;
  const active = list?.find((c) => c.name === selected)?.name ?? list?.[0]?.name ?? null;
  const sources = useLoad(() => listDocuments(active ?? "", { fetchImpl }), active);
  const destination = target.trim() || active || "documents";

  const { reload: reloadCollections } = collections;
  const { reload: reloadSources } = sources;
  const refresh = useCallback(() => {
    reloadCollections();
    reloadSources();
  }, [reloadCollections, reloadSources]);

  const addJob = (job: Job, label: string) => setJobs((current) => [{ job, label }, ...current]);

  return (
    <section className="view view--documents" aria-labelledby="view-library-title">
      <ViewHeader id="library" focusHeading={focusHeading} />
      <ErrorNotice message={collections.error} />
      <CollectionList collections={list} active={active} loading={collections.loading} onSelect={setSelected} />

      {active !== null ? (
        <section className="panel" aria-labelledby={`${targetId}-sources`}>
          <header className="panel__header">
            <h2 id={`${targetId}-sources`} className="type-section-title">
              Sources in {active}
            </h2>
            <button
              type="button"
              className="button button--ghost button--small"
              aria-label={`Delete collection ${active}`}
              onClick={() => setDeletion({ collection: active, target: { kind: "collection" } })}
            >
              Delete collection
            </button>
          </header>
          <ErrorNotice message={sources.error} />
          {sources.data ? (
            <SourceTable
              collection={active}
              sources={sources.data}
              onDelete={(source) => setDeletion({ collection: active, target: { kind: "source", source } })}
            />
          ) : (
            <p className="type-meta">Loading sources.</p>
          )}
        </section>
      ) : null}

      {deletion !== null ? (
        <DeletePanel
          key={JSON.stringify(deletion)}
          collection={deletion.collection}
          target={deletion.target}
          fetchImpl={fetchImpl}
          onClose={() => setDeletion(null)}
          onDeleted={refresh}
        />
      ) : null}

      {active !== null ? (
        <ProfilePanel
          key={active}
          collection={active}
          storedProfile={list?.find((c) => c.name === active)?.profile ?? null}
          fetchImpl={fetchImpl}
          onChanged={reloadCollections}
        />
      ) : null}

      <section className="panel" aria-labelledby={`${targetId}-add`}>
        <h2 id={`${targetId}-add`} className="type-section-title">
          Add sources
        </h2>
        <div className="field">
          <label className="field__label" htmlFor={targetId}>
            Target collection
          </label>
          <input id={targetId} className="control" value={target} placeholder={active ?? "documents"} onChange={(e) => setTarget(e.target.value)} />
        </div>
        <ErrorNotice message={roots.error} />
        <UploadPanel collection={destination} managedRoot={roots.data?.find((r) => r.kind === "managed")} fetchImpl={fetchImpl} onJob={addJob} />
        <IngestPanel collection={destination} roots={roots.data ?? []} fetchImpl={fetchImpl} onJob={addJob} />
        <JobList jobs={jobs} pollMs={pollMs} fetchImpl={fetchImpl} onFinished={refresh} />
      </section>
    </section>
  );
}

interface CollectionListProps {
  collections: CollectionInfo[] | undefined;
  active: string | null;
  loading: boolean;
  onSelect: (name: string) => void;
}

function CollectionList({ collections, active, loading, onSelect }: CollectionListProps) {
  if (collections === undefined || collections.length === 0) {
    const title = collections === undefined ? (loading ? "Loading collections" : "Collections are not available") : "No collections yet";
    return (
      <div className="empty-state" data-testid="empty-state">
        <p className="empty-state__title">{title}</p>
        <p className="type-meta">Upload a file or ingest from an approved folder to create a collection.</p>
      </div>
    );
  }
  return (
    <ul className="collection-list" aria-label="Collections">
      {collections.map((c) => (
        <li key={c.name}>
          <button type="button" className="collection-list__item" aria-pressed={c.name === active} onClick={() => onSelect(c.name)}>
            <span className="collection-list__name">{c.name}</span>
            <span className="type-meta">
              {plural(c.document_count, "source")}, {plural(c.chunk_count, "chunk")}
            </span>
          </button>
        </li>
      ))}
    </ul>
  );
}
