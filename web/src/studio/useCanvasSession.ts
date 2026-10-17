import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { useApi } from "../api/ApiProvider";
import { useCancelRun, useSaveLayout, useSaveRevision, useSubmitRun, useValidatePipeline } from "../api/mutations";
import { PipelineIssuesError, type GraphDocument, type PipelineRecord, type RevisionRecord, type ValidationIssue, type ValidationReport } from "../api/pipelines";
import { operationsQuery, queryKeys, revisionQuery, runsQuery } from "../api/queries";
import { initialDraft } from "./drafts";
import { fromDocument, sameDocument, toDocument, toLayout } from "./graph";
import type { Notice } from "./Notices";
import { savedStatus } from "./profileCopy";
import { useDraft } from "./useDraft";

/**
 * What the canvas opens: a saved pipeline with its current revision, or a
 * standard graph document of a built-in profile. A standard graph has no
 * pipeline, so it is read-only: no runs, no saves, no stored draft.
 */
export type CanvasSource =
  | { kind: "pipeline"; pipeline: PipelineRecord; revision: RevisionRecord | null }
  | { kind: "standard"; key: string; document: GraphDocument };

/** Stand-in records so a standard graph gets the same grid layout as a saved one. They never reach the server. */
function standardRecords(document: GraphDocument): { pipeline: PipelineRecord; revision: RevisionRecord } {
  const now = "";
  return {
    pipeline: { pipeline_id: "", title: "", current_revision_id: null, layout: {}, created_at: now, updated_at: now },
    revision: { revision_id: "", pipeline_id: "", revision_number: 0, content_hash: "", schema_version: document.schema_version, document, created_at: now },
  };
}

type ActionName = "saveLayout" | "saveRevision" | "validate" | "run" | "cancel" | "refresh";

/**
 * Canvas state for one opened graph. A pipeline and its current revision
 * come from the server (the route names the profile, the profile names the
 * pipeline), the operation catalogue and the latest run come from the query
 * cache, and the draft lives in browser storage. A standard graph has none of
 * that: the draft stays in memory. Mount with `key={pipelineId}` (or the
 * standard graph's key).
 */
export function useCanvasSession(source: CanvasSource) {
  const api = useApi();
  const queryClient = useQueryClient();
  const readOnly = source.kind === "standard";
  const revision = source.kind === "pipeline" ? source.revision : null;
  const pipelineId = source.kind === "pipeline" ? source.pipeline.pipeline_id : "";
  const { draft, update, markSaved } = useDraft(
    source.kind === "pipeline" ? pipelineId : source.key,
    () => {
      if (source.kind === "pipeline") return initialDraft(source.pipeline, source.revision);
      const records = standardRecords(source.document);
      return initialDraft(records.pipeline, records.revision);
    },
    { persist: !readOnly },
  );

  const operations = useQuery(operationsQuery(api));
  const latest = useQuery({ ...runsQuery(api, { pipelineId, limit: 1 }), enabled: !readOnly });
  const run = latest.data?.[0] ?? null;
  const runUsesCurrent = run !== null && run.revision_id === revision?.revision_id;
  const fetchedRevision = useQuery({ ...revisionQuery(api, pipelineId, run?.revision_id ?? ""), enabled: run !== null && !runUsesCurrent });
  const runRevision = runUsesCurrent ? revision : (fetchedRevision.data ?? null);

  const saveLayoutMutation = useSaveLayout(pipelineId);
  const saveRevisionMutation = useSaveRevision(pipelineId);
  const validateMutation = useValidatePipeline();
  const submitMutation = useSubmitRun();
  const cancelMutation = useCancelRun();
  const busy = [saveLayoutMutation, saveRevisionMutation, validateMutation, submitMutation, cancelMutation].some((m) => m.isPending);

  const [issues, setIssues] = useState<ValidationIssue[]>([]);
  const [report, setReport] = useState<ValidationReport | null>(null);
  const [inputValues, setInputValues] = useState<Record<string, string>>({});
  const [notice, setNotice] = useState<Notice | null>(null);

  const dirty = readOnly ? false : revision ? !sameDocument(fromDocument(revision.document, {}).graph, draft.graph) : draft.graph.nodes.length > 0;
  const controls = useMemo(() => Object.fromEntries((report?.nodes ?? []).map((node) => [node.node_id, node.controls])), [report]);

  const status = (text: string) => setNotice({ kind: "status", text });

  async function act(work: () => Promise<void>, retry: () => void) {
    try {
      await work();
    } catch (error) {
      if (error instanceof PipelineIssuesError) {
        setIssues(error.issues);
        const count = error.issues.length;
        setNotice({ kind: "refused", text: `The graph has ${count} ${count === 1 ? "issue" : "issues"}. They are listed under Revision and run.` });
      } else setNotice({ kind: "failure", error, retry });
    }
  }

  function inputsFor(names: string[]): Record<string, string> {
    return Object.fromEntries(names.filter((name) => inputValues[name]?.trim()).map((name) => [name, inputValues[name]!]));
  }

  const actions: Record<ActionName, () => Promise<void>> = {
    saveLayout: () =>
      act(async () => {
        await saveLayoutMutation.mutateAsync(toLayout(draft));
        status("Layout saved. The execution revision did not change.");
      }, () => void actions.saveLayout()),
    saveRevision: () =>
      act(async () => {
        const saved = await saveRevisionMutation.mutateAsync(toDocument(draft));
        queryClient.setQueryData(queryKeys.pipeline(pipelineId), (old: { pipeline: PipelineRecord } | undefined) =>
          old === undefined ? old : { ...old, current_revision: saved.revision },
        );
        markSaved();
        const number = saved.revision.revision_number;
        const affected = saved.affected_collections;
        if (!saved.created) status(`Revision ${number} already holds this graph.`);
        else status(affected.length > 0 ? savedStatus(number, affected) : `Saved revision ${number}.`);
      }, () => void actions.saveRevision()),
    validate: () =>
      act(async () => {
        const required = draft.graph.inputs.filter((input) => input.required !== false).map((input) => input.name);
        const inputs = inputsFor(draft.graph.inputs.map((input) => input.name));
        const admit = required.length > 0 && required.every((name) => name in inputs);
        setIssues([]);
        const result = await validateMutation.mutateAsync({ document: toDocument(draft), inputs: admit ? inputs : undefined });
        setReport(result);
        status(
          result.admitted
            ? `The graph is valid and admissible. Order: ${result.order.join(", ")}.`
            : `The draft graph is valid. Order: ${result.order.join(", ")}. Enter run inputs to check admission and see effective values.`,
        );
      }, () => void actions.validate()),
    run: () =>
      act(async () => {
        if (!revision) return;
        const inputs = inputsFor((revision.document.inputs ?? []).map((input) => input.name));
        const record = await submitMutation.mutateAsync({ revisionId: revision.revision_id, inputs });
        status(`Submitted run ${record.run_id} for revision ${revision.revision_number}.`);
      }, () => void actions.run()),
    cancel: () =>
      act(async () => {
        if (run) await cancelMutation.mutateAsync(run.run_id);
      }, () => void actions.cancel()),
    refresh: () =>
      act(async () => {
        const result = await latest.refetch();
        if (result.error) throw result.error;
      }, () => void actions.refresh()),
  };

  return {
    operations,
    draft,
    update,
    revision,
    readOnly,
    dirty,
    issues,
    controls,
    run,
    runRevision,
    inputValues,
    setInputValue: (name: string, value: string) => setInputValues((current) => ({ ...current, [name]: value })),
    notice,
    setNotice,
    busy,
    actions,
  };
}
