import type { RunDetailRecord, RunEventRecord, RunResultRecord } from "../../api/runs";
import { json } from "../../runs/test/fakes";

export interface RunRouterOptions {
  runs: RunDetailRecord[];
  results: Record<string, RunResultRecord>;
  events: Record<string, RunEventRecord[]>;
}

/** The run list, detail, result, events, cancel, retry and stored-chunk routes, as fixture data. */
export function runRouter(options: RunRouterOptions) {
  const runs = new Map(options.runs.map((run) => [run.run_id, { ...run }]));

  function handles(pathname: string): boolean {
    return pathname.startsWith("/v1/runs") || /^\/v1\/collections\/[^/]+\/chunks\/[^/]+$/.test(pathname);
  }

  function route(method: string, url: URL): Response {
    const path = url.pathname;
    if (path === "/v1/runs") {
      const statuses = url.searchParams.getAll("status");
      return json({ status: "ok", runs: [...runs.values()].filter((run) => statuses.length === 0 || statuses.includes(run.status)) });
    }
    const chunk = /^\/v1\/collections\/([^/]+)\/chunks\/([^/]+)$/.exec(path);
    if (chunk) {
      const text = `Full text of ${decodeURIComponent(chunk[2]!)} <script>alert(1)</script>`;
      const view = { chunk_id: chunk[2], source_id: null, source_version: null, source_chunk_index: 2, source_chunk_count: 4, source: "notes.md", page_label: null, text, metadata: {} };
      return json({ status: "ok", collection: decodeURIComponent(chunk[1]!), text_format: "plain", chunk: view, previous: [], next: [] });
    }
    const match = /^\/v1\/runs\/([^/]+)(\/[a-z]+)?$/.exec(path);
    const run = match ? runs.get(match[1]!) : undefined;
    if (!match || !run) return json({ status: "error", message: "Unknown run." }, 404);
    const rest = match[2] ?? "";
    if (method === "GET" && rest === "") return json({ status: "ok", run });
    if (rest === "/result") {
      const result = options.results[run.run_id];
      return result ? json({ status: "ok", run_id: run.run_id, result }) : json({ status: "error", message: "This run has no stored result." }, 404);
    }
    if (rest === "/events") {
      const after = Number(url.searchParams.get("after_sequence") ?? 0);
      const list = (options.events[run.run_id] ?? []).filter((e) => e.sequence > after);
      const done = !["queued", "running", "cancelling"].includes(run.status);
      return json({ status: "ok", run_id: run.run_id, run_status: run.status, events: list, last_sequence: list.at(-1)?.sequence ?? after, complete: done });
    }
    if (method === "POST" && rest === "/cancel") {
      run.status = "cancelling";
      return json({ status: "ok", run });
    }
    if (method === "POST" && rest === "/retry") {
      const retry = { ...run, run_id: "r9", status: "queued", origin: "retry", source_run_id: run.run_id, failure: null, result_ref: null };
      runs.set(retry.run_id, retry);
      return json({ status: "ok", run: retry }, 202);
    }
    return json({ status: "error", message: "Not found." }, 404);
  }

  return { handles, route, runs };
}
