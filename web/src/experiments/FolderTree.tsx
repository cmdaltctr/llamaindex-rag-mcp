import { Folder } from "lucide-react";
import type { ExperimentEntry, FolderNode } from "../api/experiments";
import { ExperimentRow } from "./ExperimentRow";

interface FolderTreeProps {
  nodes: readonly FolderNode[];
  entries: ReadonlyMap<string, ExperimentEntry>;
}

/** Folders with their sub-experiments. A folder with nothing in it says so. */
export function FolderTree({ nodes, entries }: FolderTreeProps) {
  return (
    <ul className="flex flex-col gap-3">
      {nodes.map((node) => {
        const entry = node.context_id === null ? undefined : entries.get(node.context_id);
        return (
          <li key={node.path} className="min-w-0">
            {entry !== undefined ? (
              <ExperimentRow entry={entry} />
            ) : (
              <div role="group" aria-label={`Folder ${node.path}`} className="flex flex-col gap-2 rounded-panel border border-border p-3">
                <p className="flex items-center gap-2 font-medium">
                  <Folder aria-hidden="true" className="size-4 shrink-0 text-muted-foreground" />
                  <span dir="ltr" className="[overflow-wrap:anywhere]">
                    {node.path}
                  </span>
                </p>
                {node.children.length === 0 ? (
                  <p className="text-meta text-muted-foreground">Empty folder. Create a sub-experiment in it.</p>
                ) : (
                  <FolderTree nodes={node.children} entries={entries} />
                )}
              </div>
            )}
          </li>
        );
      })}
    </ul>
  );
}
