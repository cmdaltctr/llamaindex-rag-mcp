import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { useApi } from "../api/ApiProvider";
import { experimentsQuery, pluginsQuery } from "../api/queries";
import { ErrorNotice } from "../components/ErrorNotice";
import { PageHeader } from "../components/PageHeader";
import { Button } from "../components/ui/button";
import { areaById } from "../lib/views";
import { FoldersSection } from "./FoldersSection";
import { NotebooksSection } from "./NotebooksSection";
import { RunPage } from "./runs/RunPage";
import { RunsSection } from "./runs/RunsSection";
import { TrustNotice } from "./TrustNotice";

const SECTIONS = [
  { id: "experiments", label: "Experiments" },
  { id: "notebooks", label: "Notebooks" },
  { id: "runs", label: "Runs" },
] as const;

type SectionId = (typeof SECTIONS)[number]["id"];

/**
 * Experiment folders, notebook tools and pipeline runs. A run id in the
 * route opens that run's detail; otherwise one chip-switched section shows.
 */
export function ExperimentsView({ runId }: { runId: string | null }) {
  const api = useApi();
  const experiments = useQuery(experimentsQuery(api));
  const plugins = useQuery(pluginsQuery(api));
  const [section, setSection] = useState<SectionId>("experiments");
  const trustNotice = experiments.data?.trust_notice ?? plugins.data?.trust_notice ?? null;

  if (runId !== null) return <RunPage runId={runId} />;

  return (
    <section className="flex flex-col gap-4">
      <PageHeader title="Experiments" summary={areaById("experiments").summary} />
      <TrustNotice text={trustNotice} />
      <div role="group" aria-label="Sections" className="flex flex-wrap gap-2">
        {SECTIONS.map(({ id, label }) => (
          <Button key={id} variant="chip" aria-pressed={section === id} onClick={() => setSection(id)}>
            {label}
          </Button>
        ))}
      </div>
      {section === "experiments" ? (
        experiments.isError ? (
          <ErrorNotice error={experiments.error} onRetry={() => void experiments.refetch()} />
        ) : experiments.data === undefined ? (
          <p role="status" className="text-meta text-muted-foreground">
            Loading experiments.
          </p>
        ) : (
          <FoldersSection list={experiments.data} />
        )
      ) : null}
      {section === "notebooks" ? <NotebooksSection experiments={experiments.data} /> : null}
      {section === "runs" ? <RunsSection experiments={experiments.data} /> : null}
    </section>
  );
}
