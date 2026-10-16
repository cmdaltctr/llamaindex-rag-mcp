import { useQuery } from "@tanstack/react-query";
import { useApi } from "../api/ApiProvider";
import { ApiError } from "../api/client";
import { pipelineQuery } from "../api/queries";
import { ErrorNotice } from "../components/ErrorNotice";
import { NotFound } from "../components/NotFound";
import { PageHeader } from "../components/PageHeader";
import { formatRoute } from "../lib/routes";
import { CanvasEditor } from "./CanvasEditor";

const GALLERY = formatRoute({ area: "studio", pipelineId: null });

/** Loads the pipeline the route names, then opens its canvas. A pipeline the server does not return is "not found". */
export function CanvasPage({ pipelineId }: { pipelineId: string }) {
  const query = useQuery(pipelineQuery(useApi(), pipelineId));

  if (query.isError) {
    const missing = query.error instanceof ApiError && query.error.kind === "http" && query.error.status === 404;
    return (
      <section className="p-4 md:p-6">
        <PageHeader title="Studio" />
        {missing ? (
          <NotFound what="pipeline" name={pipelineId} backHref={GALLERY} backLabel="Back to Studio" />
        ) : (
          <ErrorNotice error={query.error} onRetry={() => void query.refetch()} backHref={GALLERY} />
        )}
      </section>
    );
  }
  if (query.data === undefined) {
    return (
      <section className="p-4 md:p-6">
        <PageHeader title="Studio" />
        <p role="status" className="text-meta text-muted-foreground">
          Loading the pipeline.
        </p>
      </section>
    );
  }
  return <CanvasEditor key={pipelineId} pipeline={query.data.pipeline} revision={query.data.current_revision} />;
}
