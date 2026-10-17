import type { KeyboardEvent } from "react";
import type { ValidationIssue } from "../api/pipelines";
import { Button } from "../components/ui/button";
import { edgeKey, removeEdge, removeNode, setSelection, type Draft } from "./graph";

interface GraphOutlineProps {
  draft: Draft;
  issues: readonly ValidationIssue[];
  onChange: (change: (draft: Draft) => Draft) => void;
  onAnnounce: (message: string) => void;
  /** A read-only graph: items can be selected, never removed. */
  readOnly?: boolean;
}

const plural = (count: number, word: string) => `${count} ${word}${count === 1 ? "" : "s"}`;

/**
 * Keyboard route to every node and connection. Enter or Space selects an
 * item; Delete or Backspace removes the focused item (not on a read-only graph).
 */
export function GraphOutline({ draft, issues, onChange, onAnnounce, readOnly = false }: GraphOutlineProps) {
  const selected = new Set(draft.layout.selection);

  function select(id: string) {
    onChange((current) => setSelection(current, [id]));
  }

  function removeOnKey(event: KeyboardEvent<HTMLButtonElement>, remove: () => void) {
    if (readOnly || (event.key !== "Delete" && event.key !== "Backspace")) return;
    event.preventDefault();
    event.stopPropagation();
    remove();
  }

  function dropNode(id: string) {
    onChange((current) => removeNode(current, id));
    onAnnounce(`Removed node ${id} and its connections.`);
  }

  function dropEdge(key: string, label: string) {
    onChange((current) => removeEdge(current, key));
    onAnnounce(`Removed connection ${label}.`);
  }

  return (
    <>
      <h3 className="text-subsection-title font-semibold">Nodes</h3>
      {draft.graph.nodes.length === 0 ? (
        <p className="text-meta text-muted-foreground">No nodes yet.</p>
      ) : (
        <ul className="flex flex-col gap-1">
          {draft.graph.nodes.map((node) => {
            const count = issues.filter((issue) => issue.node_id === node.id).length;
            const suffix = `${node.enabled === false ? ", bypassed" : ""}${count > 0 ? `, ${plural(count, "issue")}` : ""}`;
            return (
              <li key={node.id}>
                <Button
                  variant="chip"
                  size="sm"
                  className="h-auto min-h-8 w-full flex-wrap justify-start py-1 text-start whitespace-normal [overflow-wrap:anywhere]"
                  aria-pressed={selected.has(node.id)}
                  aria-label={`Node ${node.id} (${node.operation})${suffix}`}
                  data-invalid={count > 0 || undefined}
                  onClick={() => select(node.id)}
                  onKeyDown={(event) => removeOnKey(event, () => dropNode(node.id))}
                >
                  <code className="font-mono text-code">{node.id}</code>
                  <span className="text-meta text-muted-foreground">{node.operation}</span>
                  {count > 0 && <span className="text-meta text-status-error-label">{plural(count, "issue")}</span>}
                </Button>
              </li>
            );
          })}
        </ul>
      )}
      <h3 className="text-subsection-title font-semibold">Connections</h3>
      {draft.graph.edges.length === 0 ? (
        <p className="text-meta text-muted-foreground">No connections yet.</p>
      ) : (
        <ul className="flex flex-col gap-1">
          {draft.graph.edges.map((edge) => {
            const key = edgeKey(edge);
            const label = `${edge.source.node}.${edge.source.port} to ${edge.target.node}.${edge.target.port}`;
            return (
              <li key={key} className="flex items-center gap-2">
                <Button
                  variant="chip"
                  size="sm"
                  className="h-auto min-h-8 min-w-0 flex-1 justify-start py-1 text-start whitespace-normal [overflow-wrap:anywhere]"
                  aria-pressed={selected.has(key)}
                  aria-label={`Connection ${label}`}
                  onClick={() => select(key)}
                  onKeyDown={(event) => removeOnKey(event, () => dropEdge(key, label))}
                >
                  <code className="font-mono text-code">{label}</code>
                </Button>
                {!readOnly && (
                  <Button variant="ghost" size="sm" aria-label={`Remove connection ${label}`} onClick={() => dropEdge(key, label)}>
                    Remove
                  </Button>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </>
  );
}
