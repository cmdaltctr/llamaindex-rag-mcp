import { FolderTree as FolderIcon } from "lucide-react";
import { useMemo } from "react";
import type { ExperimentList } from "../api/experiments";
import { EmptyState } from "../components/EmptyState";
import { ExperimentForm } from "./ExperimentForm";
import { ExperimentRow } from "./ExperimentRow";
import { FolderForm } from "./FolderForm";
import { FolderTree } from "./FolderTree";
import { parentOptions, unlistedEntries } from "./folderOptions";
import { Panel } from "./Panel";

/** Experiment folders with their sub-experiments, and the forms that create them. */
export function FoldersSection({ list }: { list: ExperimentList }) {
  const entries = useMemo(() => new Map(list.experiments.map((entry) => [entry.experiment.context_id, entry])), [list.experiments]);
  const { folders } = list;
  const unlisted = useMemo(() => unlistedEntries(folders, list.experiments), [folders, list.experiments]);
  const options = useMemo(() => parentOptions(folders), [folders]);
  const several = list.roots.length > 1;

  if (list.roots.length === 0) {
    return (
      <Panel title="No experiment root" description="Experiment folders live below a root that the server approves at launch.">
        <p className="text-ui">
          No experiment root is approved on this server. Restart it with <code className="font-mono text-code">omrs web --experiment-root &lt;directory&gt;</code>, then create a folder here.
        </p>
      </Panel>
    );
  }

  const empty = folders.every((item) => item.tree.length === 0) && unlisted.length === 0;
  return (
    <div className="flex flex-col gap-4">
      <div className="grid grid-cols-1 items-start gap-4 lg:grid-cols-2">
        <FolderForm roots={list.roots} />
        <ExperimentForm folders={options} sendRoot={several} />
      </div>
      <Panel title="Folders" description="Each folder lists its sub-experiments. Contexts last until the server stops.">
        {empty ? <EmptyState icon={FolderIcon} message="No folder exists yet. Create one to group your sub-experiments." /> : null}
        {folders.map(({ root, tree }) =>
          tree.length === 0 ? null : (
            <div key={root} className="flex flex-col gap-2">
              {several ? (
                <h3 dir="ltr" className="font-mono text-code text-muted-foreground [overflow-wrap:anywhere]">
                  {root}
                </h3>
              ) : null}
              <FolderTree nodes={tree} entries={entries} />
            </div>
          ),
        )}
        {unlisted.length > 0 ? (
          <section aria-label="Other experiments" className="flex flex-col gap-2">
            <h3 className="text-subsection-title font-semibold">Other experiments</h3>
            {unlisted.map((entry) => (
              <ExperimentRow key={entry.experiment.context_id} entry={entry} />
            ))}
          </section>
        ) : null}
      </Panel>
    </div>
  );
}
