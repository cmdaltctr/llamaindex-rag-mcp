import { ChevronDown, ChevronUp, Database, FileSearch, Quote, type LucideIcon } from "lucide-react";
import { useState, type ReactNode } from "react";
import type { CollectionInfo } from "../api/documents";
import { CollectionPicker } from "../components/CollectionPicker";
import { Button } from "../components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "../components/ui/tabs";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "../components/ui/tooltip";
import { CitationList, EvidenceList } from "./SourcesPanel";
import { cn } from "../lib/utils";
import type { LatestAnswer } from "./useLatestAnswer";

interface KnowledgePanelProps {
  collections: readonly CollectionInfo[];
  activeName: string;
  onSelect: (name: string) => void;
  latest: LatestAnswer | null;
  onShowChunk: (collection: string, chunkId: string) => void;
  /** The card's hide chevron, placed at the end of the tab row. */
  hide: ReactNode;
}

function IconTab({ value, label, icon: Icon }: { value: string; label: string; icon: LucideIcon }) {
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <TabsTrigger value={value} aria-label={label}>
          <Icon aria-hidden="true" />
        </TabsTrigger>
      </TooltipTrigger>
      <TooltipContent>{label}</TooltipContent>
    </Tooltip>
  );
}

/** The right-hand card: the knowledge bases, and the citations and evidence of the latest answer, as icon tabs. */
export function KnowledgePanel({ collections, activeName, onSelect, latest, onShowChunk, hide }: KnowledgePanelProps) {
  // In the single column the card is pinned under the top bar, so it folds to
  // its icon row to give the chat the room. The wide layout ignores the fold.
  const [folded, setFolded] = useState(false);
  const Fold = folded ? ChevronDown : ChevronUp;
  return (
    <TooltipProvider>
      <Tabs defaultValue="knowledge" className="flex flex-col gap-2" onValueChange={() => setFolded(false)}>
        <div className="flex items-center gap-1">
          <TabsList aria-label="Knowledge base panel views" className="min-w-0 flex-1">
            <IconTab value="knowledge" label="Knowledge base" icon={Database} />
            <IconTab value="citations" label="Citations" icon={Quote} />
            <IconTab value="evidence" label="Evidence" icon={FileSearch} />
          </TabsList>
          {hide}
          <Button
            variant="ghost"
            size="icon-xs"
            className="shrink-0 lg:hidden"
            aria-label={folded ? "Unfold knowledge bases" : "Fold knowledge bases"}
            aria-expanded={!folded}
            onClick={() => setFolded(!folded)}
          >
            <Fold aria-hidden="true" />
          </Button>
        </div>
        <div data-testid="knowledge-panel-views" className={cn("flex flex-col gap-2", folded && "max-lg:hidden")}>
          {/* Kept mounted while hidden, so an opened file list survives a visit to another tab. */}
          <TabsContent value="knowledge" forceMount className="data-[state=inactive]:hidden">
            <CollectionPicker label="Knowledge bases" collections={collections} selected={activeName} onSelect={onSelect} stacked showFiles />
          </TabsContent>
          <TabsContent value="citations" className="max-h-[60vh] overflow-y-auto">
            {latest === null ? (
              <p className="text-meta text-muted-foreground">Citations of the latest answer appear here.</p>
            ) : (
              <CitationList citations={latest.result.citations} evidence={latest.result.evidence} collection={latest.collection} onShowChunk={onShowChunk} />
            )}
          </TabsContent>
          <TabsContent value="evidence" className="max-h-[60vh] overflow-y-auto">
            {latest === null ? (
              <p className="text-meta text-muted-foreground">Evidence of the latest answer appears here.</p>
            ) : (
              <EvidenceList evidence={latest.result.evidence} citations={latest.result.citations} collection={latest.collection} onShowChunk={onShowChunk} />
            )}
          </TabsContent>
        </div>
      </Tabs>
    </TooltipProvider>
  );
}
