import type { KeyboardEvent } from "react";
import type { ValidationIssue } from "../api/pipelines";
import { edgeKey, removeEdge, removeNode, setSelection, type Draft } from "./graph";

interface GraphOutlineProps {
  draft: Draft;
  issues: readonly ValidationIssue[];
  onChange: (change: (draft: Draft) => Draft) => void;
  onAnnounce: (message: string) => void;
}

const plural = (count: number, word: string) => `${count} ${word}${count === 1 ? "" : "s"}`;

/**
 * Keyboard route to every node and connection. Enter or Space selects an
 * item; Delete or Backspace removes the focused item.
 */
export function GraphOutline({ draft, issues, onChange, onAnnounce }: GraphOutlineProps) {
  const selected = new Set(draft.layout.selection);

  function select(id: string) {
    onChange((current) => setSelection(current, [id]));
  }

  function removeOnKey(event: KeyboardEvent<HTMLButtonElement>, remove: () => void) {
    if (event.key !== "Delete" && event.key !== "Backspace") return;
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
    <section className="canvas-panel" aria-label="Graph outline">
      <h2 className="type-section-title">Nodes</h2>
      {draft.graph.nodes.length === 0 ? (
        <p className="type-meta">No nodes yet.</p>
      ) : (
        <ul className="outline__list">
          {draft.graph.nodes.map((node) => {
            const count = issues.filter((issue) => issue.node_id === node.id).length;
            const suffix = `${node.enabled === false ? ", bypassed" : ""}${count > 0 ? `, ${plural(count, "issue")}` : ""}`;
            return (
              <li key={node.id}>
                <button
                  type="button"
                  className="outline__item"
                  aria-pressed={selected.has(node.id)}
                  aria-label={`Node ${node.id} (${node.operation})${suffix}`}
                  data-invalid={count > 0 || undefined}
                  onClick={() => select(node.id)}
                  onKeyDown={(event) => removeOnKey(event, () => dropNode(node.id))}
                >
                  <code>{node.id}</code> <span className="type-meta">{node.operation}</span>
                  {count > 0 && <span className="outline__issues">{plural(count, "issue")}</span>}
                </button>
              </li>
            );
          })}
        </ul>
      )}
      <h2 className="type-section-title">Connections</h2>
      {draft.graph.edges.length === 0 ? (
        <p className="type-meta">No connections yet.</p>
      ) : (
        <ul className="outline__list">
          {draft.graph.edges.map((edge) => {
            const key = edgeKey(edge);
            const label = `${edge.source.node}.${edge.source.port} to ${edge.target.node}.${edge.target.port}`;
            return (
              <li key={key} className="outline__edge">
                <button
                  type="button"
                  className="outline__item"
                  aria-pressed={selected.has(key)}
                  aria-label={`Connection ${label}`}
                  onClick={() => select(key)}
                  onKeyDown={(event) => removeOnKey(event, () => dropEdge(key, label))}
                >
                  <code>{label}</code>
                </button>
                <button
                  type="button"
                  className="button button--ghost button--small"
                  aria-label={`Remove connection ${label}`}
                  onClick={() => dropEdge(key, label)}
                >
                  Remove
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
