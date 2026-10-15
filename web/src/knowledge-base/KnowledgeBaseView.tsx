import { useState } from "react";
import type { Job } from "../api/documents";
import { CollectionGate } from "../components/CollectionGate";
import { CollectionPicker } from "../components/CollectionPicker";
import { PageHeader } from "../components/PageHeader";
import { usePreferences } from "../lib/PreferencesProvider";
import { useRoute } from "../lib/RouteProvider";
import { areaById } from "../lib/views";
import { AddSources } from "./AddSources";
import { JobList, type TrackedJob } from "./JobList";
import { Project } from "./Project";

/** `#/knowledge-base` (project picker) and `#/knowledge-base/<collection>` (one project). */
export function KnowledgeBaseView() {
  const { route, navigate } = useRoute();
  const { setLastCollection } = usePreferences();
  const routeCollection = route.area === "knowledge-base" ? route.collection : null;
  const [jobs, setJobs] = useState<TrackedJob[]>([]);
  const [notice, setNotice] = useState<string | null>(null);

  const addJob = (job: Job, label: string) => setJobs((current) => [{ job, label }, ...current]);
  const select = (name: string) => {
    setNotice(null);
    navigate({ area: "knowledge-base", collection: name });
  };

  function leaveDeleted(name: string) {
    setLastCollection(null);
    setNotice(`Collection ${name} deleted.`);
    navigate({ area: "knowledge-base", collection: null }, { replace: true });
  }

  return (
    <section>
      <PageHeader title="Knowledge Base" summary={areaById("knowledge-base").summary} />
      {notice !== null ? (
        <p role="status" className="mb-4 text-status-success-label">
          {notice}
        </p>
      ) : null}
      <CollectionGate
        area="knowledge-base"
        routeCollection={routeCollection}
        backLabel="Choose a project"
        picker={(collections) => (
          <div className="flex flex-col gap-6">
            {collections.length > 0 ? (
              <section aria-labelledby="kb-pick-title" className="flex flex-col gap-3">
                <h2 id="kb-pick-title" className="text-section-title font-semibold">
                  Choose a project
                </h2>
                <CollectionPicker label="Projects" collections={collections} selected={null} onSelect={select} />
              </section>
            ) : null}
            <section aria-labelledby="kb-new-title" className="flex flex-col gap-3">
              <h2 id="kb-new-title" className="text-section-title font-semibold">
                Start a new project
              </h2>
              <AddSources active={null} onJob={addJob} />
            </section>
          </div>
        )}
      >
        {(project, collections) => (
          <Project
            project={project}
            collections={collections}
            onJob={addJob}
            onSelect={select}
            onCollectionDeleted={() => leaveDeleted(project.name)}
          />
        )}
      </CollectionGate>
      {jobs.length > 0 ? (
        <section aria-labelledby="kb-jobs-title" className="mt-6 flex flex-col gap-2">
          <h2 id="kb-jobs-title" className="text-section-title font-semibold">
            Ingest jobs
          </h2>
          <JobList jobs={jobs} />
        </section>
      ) : null}
    </section>
  );
}
