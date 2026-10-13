import { useCallback, useEffect, useMemo, useState } from "react";
import type { FetchLike } from "../api/client";
import * as api from "../api/pipelines";
import { emptyDraft, fromDocument, sameDocument, toDocument, toLayout, type Draft } from "./graph";
import { readDraft, readSession, writeSession, type SubmittedRun } from "./storage";
import { NEW_DRAFT_KEY, useDraft } from "./useDraft";

export type Notice = { kind: "status" | "error"; text: string };

const ACTIVE = new Set(["queued", "running", "cancelling"]);

function errorText(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

/** Canvas state that involves the server: catalogue, pipeline, revision, validation and the submitted run. */
export function useCanvasSession(fetchImpl?: FetchLike) {
  const options = useMemo(() => ({ fetchImpl }), [fetchImpl]);
  const [initial] = useState(readSession);
  const { draftKey, draft, update, replace, adoptNew } = useDraft(initial.pipelineId ?? NEW_DRAFT_KEY);
  const [operations, setOperations] = useState<api.OperationDescriptor[] | null>(null);
  const [catalogueError, setCatalogueError] = useState<string | null>(null);
  const [pipelines, setPipelines] = useState<api.PipelineRecord[]>([]);
  const [pipelineId, setPipelineId] = useState<string | null>(initial.pipelineId);
  const [revision, setRevision] = useState<api.RevisionRecord | null>(null);
  const [issues, setIssues] = useState<api.ValidationIssue[]>([]);
  const [report, setReport] = useState<api.ValidationReport | null>(null);
  const [run, setRun] = useState<SubmittedRun | null>(initial.run);
  const [inputValues, setInputValues] = useState<Record<string, string>>({});
  const [notice, setNotice] = useState<Notice | null>(null);
  const [busy, setBusy] = useState(false);

  /** Shows a loaded pipeline: its unsaved draft, or its current revision and layout. */
  const showPipeline = useCallback(
    (id: string, loaded: Awaited<ReturnType<typeof api.getPipeline>>) => {
      const current = loaded.current_revision;
      setIssues([]);
      setReport(null);
      setPipelineId(id);
      setRevision(current);
      replace(id, readDraft(id) ?? fromDocument(current?.document ?? null, loaded.pipeline.layout));
    },
    [replace],
  );

  const loadFailed = useCallback(
    (error: unknown) => setNotice({ kind: "error", text: `Could not open the pipeline: ${errorText(error)}` }),
    [],
  );

  const loadPipeline = useCallback(
    (id: string) => api.getPipeline(id, options).then((loaded) => showPipeline(id, loaded), loadFailed),
    [options, showPipeline, loadFailed],
  );

  const openPipeline = useCallback(
    (id: string | null) => {
      if (id !== null) return void loadPipeline(id);
      setIssues([]);
      setReport(null);
      setPipelineId(null);
      setRevision(null);
      replace(NEW_DRAFT_KEY, readDraft(NEW_DRAFT_KEY) ?? emptyDraft());
    },
    [loadPipeline, replace],
  );

  /** Starts a new unsaved draft, for example from a template. Saved pipelines and revisions do not change. */
  const startDraft = useCallback(
    (next: Draft) => {
      setIssues([]);
      setReport(null);
      setPipelineId(null);
      setRevision(null);
      replace(NEW_DRAFT_KEY, next);
    },
    [replace],
  );

  useEffect(() => {
    let live = true;
    api.listOperations(options).then(
      (found) => live && setOperations(found),
      (error: unknown) => live && setCatalogueError(`Could not load the operation catalogue: ${errorText(error)}`),
    );
    api.listPipelines(options).then(
      (found) => live && setPipelines(found),
      () => undefined,
    );
    const restored = initial.pipelineId;
    if (restored) {
      api.getPipeline(restored, options).then(
        (loaded) => live && showPipeline(restored, loaded),
        (error: unknown) => live && loadFailed(error),
      );
    }
    return () => {
      live = false;
    };
  }, [options, initial.pipelineId, showPipeline, loadFailed]);

  useEffect(() => writeSession({ pipelineId, run }), [pipelineId, run]);

  const dirty = revision ? !sameDocument(fromDocument(revision.document, {}).graph, draft.graph) : draft.graph.nodes.length > 0;
  const controls = useMemo(
    () => Object.fromEntries((report?.nodes ?? []).map((node) => [node.node_id, node.controls])),
    [report],
  );

  async function act(work: () => Promise<void>) {
    setBusy(true);
    try {
      await work();
    } catch (error) {
      if (error instanceof api.PipelineIssuesError) {
        setIssues(error.issues);
        setNotice({ kind: "error", text: `${error.message} ${error.issues.length} issue(s) are listed below.` });
      } else setNotice({ kind: "error", text: errorText(error) });
    } finally {
      setBusy(false);
    }
  }

  async function ensurePipeline(): Promise<string> {
    if (pipelineId) return pipelineId;
    const record = await api.createPipeline(draft.layout.title.trim() || "Untitled pipeline", toLayout(draft), options);
    adoptNew(record.pipeline_id);
    setPipelineId(record.pipeline_id);
    setPipelines((current) => [...current, record]);
    return record.pipeline_id;
  }

  function inputsFor(names: string[]): Record<string, string> {
    return Object.fromEntries(names.filter((name) => inputValues[name]?.trim()).map((name) => [name, inputValues[name]!]));
  }

  const actions = {
    saveLayout: () =>
      act(async () => {
        const id = await ensurePipeline();
        await api.saveLayout(id, toLayout(draft), options);
        setNotice({ kind: "status", text: "Layout saved. The execution revision did not change." });
      }),
    saveRevision: () =>
      act(async () => {
        const id = await ensurePipeline();
        const saved = await api.saveRevision(id, toDocument(draft), options);
        setRevision(saved.revision);
        const number = saved.revision.revision_number;
        setNotice({ kind: "status", text: saved.created ? `Saved revision ${number}.` : `Revision ${number} already holds this graph.` });
      }),
    validate: () =>
      act(async () => {
        const required = draft.graph.inputs.filter((input) => input.required !== false).map((input) => input.name);
        const inputs = inputsFor(draft.graph.inputs.map((input) => input.name));
        const admit = required.length > 0 && required.every((name) => name in inputs);
        setIssues([]);
        const result = await api.validatePipeline(toDocument(draft), admit ? { inputs } : {}, options);
        setReport(result);
        setNotice({
          kind: "status",
          text: result.admitted
            ? `The graph is valid and admissible. Order: ${result.order.join(", ")}.`
            : `The draft graph is valid. Order: ${result.order.join(", ")}. Enter run inputs to check admission and see effective values.`,
        });
      }),
    run: () =>
      act(async () => {
        if (!revision) return;
        const names = (revision.document.inputs ?? []).map((input) => input.name);
        const record = await api.submitRun(revision.revision_id, inputsFor(names), options);
        setRun({
          runId: record.run_id,
          status: record.status,
          revisionId: revision.revision_id,
          revisionNumber: revision.revision_number,
          document: JSON.parse(JSON.stringify(revision.document)) as api.GraphDocument,
        });
        setNotice({ kind: "status", text: `Submitted run ${record.run_id} for revision ${revision.revision_number}.` });
      }),
    cancel: () =>
      act(async () => {
        if (!run) return;
        const record = await api.cancelRun(run.runId, options);
        setRun((current) => (current && current.runId === record.run_id ? { ...current, status: record.status } : current));
      }),
    refresh: () =>
      act(async () => {
        if (!run) return;
        const record = await api.getRun(run.runId, options);
        setRun((current) => (current && current.runId === record.run_id ? { ...current, status: record.status } : current));
      }),
  };

  return {
    operations: operations ?? null,
    catalogueError,
    pipelines,
    pipelineId,
    openPipeline,
    startDraft,
    draftKey,
    draft,
    update,
    revision,
    dirty,
    issues,
    report,
    controls,
    run,
    runActive: run !== null && ACTIVE.has(run.status),
    inputValues,
    setInputValue: (name: string, value: string) => setInputValues((current) => ({ ...current, [name]: value })),
    notice,
    setNotice,
    busy,
    actions,
  };
}
