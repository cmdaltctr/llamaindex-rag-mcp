/**
 * Canonical pipeline templates from `GET /v1/pipeline-templates`.
 *
 * A template is an editable starting point: loading one gives a new unsaved
 * draft. The saved revision, not the template, decides execution.
 */
import { getJson, type RequestOptions } from "../api/client";
import type { GraphDocument } from "../api/pipelines";
import { fromDocument, type Draft } from "./graph";

export interface PipelineTemplate {
  name: string;
  title: string;
  description: string;
  standard_operation: string;
  document: GraphDocument;
  outputs: { name: string; description: string }[];
}

export async function listTemplates(options: RequestOptions = {}): Promise<PipelineTemplate[]> {
  return (await getJson<{ templates: PipelineTemplate[] }>("/v1/pipeline-templates", options)).templates;
}

/** A new draft from a template document. Nodes are laid out on the grid that `addNode` uses. */
export function templateDraft(template: PipelineTemplate): Draft {
  const positions = Object.fromEntries(
    template.document.nodes.map((node, index) => [node.id, { x: 40 + 260 * (index % 4), y: 40 + 180 * Math.floor(index / 4) }]),
  );
  return fromDocument(template.document, { title: template.title, positions });
}
