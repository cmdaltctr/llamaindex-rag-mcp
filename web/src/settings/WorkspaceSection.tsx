import { useQuery } from "@tanstack/react-query";
import { useApi } from "../api/ApiProvider";
import type { Root } from "../api/documents";
import { rootsQuery, sessionQuery } from "../api/queries";
import { ErrorNotice } from "../components/ErrorNotice";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "../components/ui/table";
import { UploadLimitPanel } from "./UploadLimitPanel";

const ROOT_KINDS: Record<Root["kind"], string> = { operator: "Approved at launch", managed: "Managed uploads" };
const PATH = "text-code font-mono [overflow-wrap:anywhere]";

/** The workspace folder, the folders the server may read and the upload limit. */
export function WorkspaceSection() {
  const api = useApi();
  const session = useQuery(sessionQuery(api));
  const roots = useQuery(rootsQuery(api));

  return (
    <section aria-labelledby="settings-workspace" className="flex flex-col gap-4">
      <h2 id="settings-workspace" className="text-section-title font-semibold">
        Workspace
      </h2>
      <div className="flex flex-col gap-1">
        <h3 className="text-subsection-title font-semibold">Workspace folder</h3>
        {session.data !== undefined ? (
          session.data.workspace !== null ? (
            <code dir="ltr" className={PATH}>
              {session.data.workspace}
            </code>
          ) : (
            <p className="text-meta text-muted-foreground">The server did not report the workspace folder.</p>
          )
        ) : session.isError ? (
          <ErrorNotice error={session.error} onRetry={() => void session.refetch()} />
        ) : (
          <p className="text-meta text-muted-foreground">Loading.</p>
        )}
      </div>
      <div className="flex flex-col gap-2">
        <h3 className="text-subsection-title font-semibold">File access</h3>
        <p className="text-meta text-muted-foreground">Only these folders are readable. Paths stored in the index never grant access.</p>
        {roots.isError ? <ErrorNotice error={roots.error} onRetry={() => void roots.refetch()} /> : null}
        {roots.data !== undefined ? (
          <Table aria-label="File access">
            <TableHeader>
              <TableRow>
                <TableHead scope="col">Folder</TableHead>
                <TableHead scope="col">Kind</TableHead>
                <TableHead scope="col">ID</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {roots.data.map((root) => (
                <TableRow key={root.id}>
                  <TableCell>
                    <code dir="ltr" className={PATH}>
                      {root.path}
                    </code>
                  </TableCell>
                  <TableCell>{ROOT_KINDS[root.kind] ?? root.kind}</TableCell>
                  <TableCell>
                    <code className="text-code font-mono">{root.id}</code>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        ) : null}
      </div>
      <UploadLimitPanel />
    </section>
  );
}
