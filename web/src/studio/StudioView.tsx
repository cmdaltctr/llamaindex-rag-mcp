import { useQuery } from "@tanstack/react-query";
import { Workflow } from "lucide-react";
import { useId, useState } from "react";
import { useApi } from "../api/ApiProvider";
import type { PipelineRecord, PipelineTemplate } from "../api/pipelines";
import { collectionsQuery, pipelinesQuery, pipelineTemplatesQuery } from "../api/queries";
import { EmptyState } from "../components/EmptyState";
import { ErrorNotice } from "../components/ErrorNotice";
import { PageHeader } from "../components/PageHeader";
import { Badge } from "../components/ui/badge";
import { Button } from "../components/ui/button";
import { CardContent } from "../components/ui/card";
import { Label } from "../components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../components/ui/select";
import { usePreferences } from "../lib/PreferencesProvider";
import { formatRoute } from "../lib/routes";
import { areaById } from "../lib/views";
import { CanvasPage } from "./CanvasPage";
import { blankDraft, presetDraft, presetTitle, PRESET_PROFILES, templateDraft, type PresetProfile } from "./drafts";
import { GalleryCard } from "./GalleryCard";
import { useStartPipeline } from "./useStartPipeline";

const HOST_DEFAULT = "__host__";
const BLANK_TITLE = "Empty pipeline";

const PRESET_TEXT: Record<PresetProfile, string> = {
  documents: "The search template with the documents profile. The reranker is on.",
  codebase: "The search template with the codebase profile. The reranker is off, for speed.",
};

const CARD_GRID = "grid items-start gap-3 sm:grid-cols-2 xl:grid-cols-3";

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="mt-6 flex flex-col gap-3 first:mt-0" aria-label={title}>
      <h2 className="text-section-title font-semibold">{title}</h2>
      {children}
    </section>
  );
}

function PresetCard({ profile, search, collections, disabled, onCreate }: { profile: PresetProfile; search: PipelineTemplate | undefined; collections: readonly string[]; disabled: boolean; onCreate: (collection: string | null) => void }) {
  const { preferences } = usePreferences();
  const fieldId = useId();
  const [chosen, setChosen] = useState<string | null>(null);
  const remembered = preferences.lastCollection !== null && collections.includes(preferences.lastCollection) ? preferences.lastCollection : HOST_DEFAULT;
  const value = chosen ?? remembered;
  return (
    <GalleryCard
      title={presetTitle(profile)}
      description={search ? PRESET_TEXT[profile] : "The search template is not available on this server."}
      badge={<Badge variant="hue">{profile}</Badge>}
      action={
        <Button disabled={disabled || search === undefined} onClick={() => onCreate(value === HOST_DEFAULT ? null : value)}>
          Create pipeline
        </Button>
      }
    >
      <CardContent>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor={fieldId}>Collection</Label>
          <Select value={value} onValueChange={setChosen}>
            <SelectTrigger id={fieldId}>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={HOST_DEFAULT}>Host default</SelectItem>
              {collections.map((name) => (
                <SelectItem key={name} value={name}>
                  {name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      </CardContent>
    </GalleryCard>
  );
}

function SavedCard({ pipeline }: { pipeline: PipelineRecord }) {
  return (
    <GalleryCard
      title={pipeline.title}
      description={pipeline.current_revision_id ? "Has a saved revision." : "No saved revision yet."}
      action={
        <Button asChild variant="outline">
          <a href={formatRoute({ area: "studio", pipelineId: pipeline.pipeline_id })}>Open pipeline</a>
        </Button>
      }
    />
  );
}

/** The gallery: engine templates, profile presets and saved pipelines. Each card makes or opens a pipeline. */
function Gallery() {
  const api = useApi();
  const templates = useQuery(pipelineTemplatesQuery(api));
  const pipelines = useQuery(pipelinesQuery(api));
  const collections = useQuery(collectionsQuery(api));
  const starter = useStartPipeline();
  const search = templates.data?.find((template) => template.name === "search");
  const collectionNames = (collections.data ?? []).map((collection) => collection.name);
  const area = areaById("studio");

  return (
    <section>
      <PageHeader title={area.label} summary={area.summary} />
      {starter.error && (
        <div className="mb-4">
          <ErrorNotice error={starter.error} onRetry={starter.retry} />
        </div>
      )}
      <Section title="Templates">
        {templates.isError && <ErrorNotice error={templates.error} onRetry={() => void templates.refetch()} />}
        {templates.isPending && <p className="text-meta text-muted-foreground">Loading the templates.</p>}
        <ul className={CARD_GRID}>
          {(templates.data ?? []).map((template) => (
            <li key={template.name}>
              <GalleryCard
                title={template.title}
                description={template.description}
                badge={<Badge variant="hue">{template.name}</Badge>}
                action={
                  <Button disabled={starter.pending} onClick={() => starter.start(template.title, templateDraft(template))}>
                    Create pipeline
                  </Button>
                }
              />
            </li>
          ))}
          <li>
            <GalleryCard
              title={BLANK_TITLE}
              description="No operations yet. Add them from the catalogue and connect them yourself."
              action={
                <Button disabled={starter.pending} onClick={() => starter.start(BLANK_TITLE, blankDraft(BLANK_TITLE))}>
                  Create pipeline
                </Button>
              }
            />
          </li>
        </ul>
      </Section>
      <Section title="Profile presets">
        <ul className={CARD_GRID}>
          {PRESET_PROFILES.map((profile) => (
            <li key={profile}>
              <PresetCard
                profile={profile}
                search={search}
                collections={collectionNames}
                disabled={starter.pending}
                onCreate={(collection) => search && starter.start(presetTitle(profile), presetDraft(search, profile, collection))}
              />
            </li>
          ))}
        </ul>
      </Section>
      <Section title="Saved pipelines">
        {pipelines.isError && <ErrorNotice error={pipelines.error} onRetry={() => void pipelines.refetch()} />}
        {pipelines.data?.length === 0 && <EmptyState icon={Workflow} message="No saved pipelines yet. Create one from a card above." />}
        <ul className={CARD_GRID}>
          {(pipelines.data ?? []).map((pipeline) => (
            <li key={pipeline.pipeline_id}>
              <SavedCard pipeline={pipeline} />
            </li>
          ))}
        </ul>
      </Section>
    </section>
  );
}

/** The Studio area: the gallery, or the canvas of the pipeline the route names. */
export function StudioView({ pipelineId }: { pipelineId: string | null }) {
  return pipelineId === null ? <Gallery /> : <CanvasPage pipelineId={pipelineId} />;
}
