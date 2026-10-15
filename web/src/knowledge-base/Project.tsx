import { useState } from "react";
import type { CollectionInfo, Job } from "../api/documents";
import { CollectionPicker } from "../components/CollectionPicker";
import { StoreBadge } from "../components/StoreBadge";
import { Badge } from "../components/ui/badge";
import { Button } from "../components/ui/button";
import { plural } from "../lib/labels";
import { AddSources } from "./AddSources";
import { ProfilePanel } from "./ProfilePanel";
import { SearchSection } from "./SearchSection";
import { SourcesSection } from "./SourcesSection";

const SECTIONS = [
  { id: "sources", label: "Sources" },
  { id: "search", label: "Search" },
  { id: "add", label: "Add" },
  { id: "profile", label: "Profile" },
] as const;

type SectionId = (typeof SECTIONS)[number]["id"];

interface ProjectProps {
  project: CollectionInfo;
  collections: readonly CollectionInfo[];
  onJob: (job: Job, label: string) => void;
  onSelect: (name: string) => void;
  onCollectionDeleted: () => void;
}

/** One project's Knowledge Base. Sections are view state: one shows at a time and the route stays put. */
export function Project({ project, collections, onJob, onSelect, onCollectionDeleted }: ProjectProps) {
  const [section, setSection] = useState<SectionId>("sources");
  return (
    <div className="flex flex-col gap-4">
      <CollectionPicker label="Projects" collections={collections} selected={project.name} onSelect={onSelect} />
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
        <h2 className="text-section-title font-semibold break-words">{project.name}</h2>
        {project.profile !== null ? <Badge variant="hue">{project.profile}</Badge> : <Badge variant="neutral">No profile</Badge>}
        <StoreBadge store={project.store} />
        <span className="text-meta text-muted-foreground">
          {plural(project.document_count, "document")}, {plural(project.chunk_count, "chunk")}
        </span>
      </div>
      <div role="group" aria-label="Sections" className="flex flex-wrap gap-2">
        {SECTIONS.map(({ id, label }) => (
          <Button key={id} variant="chip" aria-pressed={section === id} onClick={() => setSection(id)}>
            {label}
          </Button>
        ))}
      </div>
      {section === "sources" ? (
        <SourcesSection key={project.name} collection={project.name} storeLabel={project.store.label} onAdd={() => setSection("add")} onCollectionDeleted={onCollectionDeleted} />
      ) : null}
      {section === "search" ? <SearchSection key={project.name} collection={project.name} /> : null}
      {section === "add" ? <AddSources active={project.name} onJob={onJob} /> : null}
      {section === "profile" ? <ProfilePanel key={project.name} collection={project.name} storedProfile={project.profile} /> : null}
    </div>
  );
}
