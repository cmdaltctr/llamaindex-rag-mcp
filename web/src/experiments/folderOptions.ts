import type { ExperimentEntry, FolderNode, FolderRoot } from "../api/experiments";
import type { FolderOption } from "./ExperimentForm";

/** A sub-experiment lives at most this many levels down, so its parent may be at most three deep. */
const MAX_PARENT_DEPTH = 3;

/** Every folder that can hold a new sub-experiment: not a registered workspace, and not too deep. */
export function parentOptions(folders: readonly FolderRoot[]): FolderOption[] {
  const found: FolderOption[] = [];
  const visit = (root: string, nodes: readonly FolderNode[], depth: number) => {
    for (const node of nodes) {
      if (node.context_id !== null || depth > MAX_PARENT_DEPTH) continue;
      found.push({ root, path: node.path });
      visit(root, node.children, depth + 1);
    }
  };
  for (const { root, tree } of folders) visit(root, tree, 1);
  return found;
}

/** Contexts the folder trees do not show, for example when a tree hit the server's node cap. */
export function unlistedEntries(folders: readonly FolderRoot[], entries: readonly ExperimentEntry[]): ExperimentEntry[] {
  const listed = new Set<string>();
  const visit = (nodes: readonly FolderNode[]) => {
    for (const node of nodes) {
      if (node.context_id !== null) listed.add(node.context_id);
      visit(node.children);
    }
  };
  for (const { tree } of folders) visit(tree);
  return entries.filter(({ experiment }) => !listed.has(experiment.context_id));
}
