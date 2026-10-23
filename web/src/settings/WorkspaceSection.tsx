import { useQuery } from "@tanstack/react-query";
import { useApi } from "../api/ApiProvider";
import type { Root } from "../api/documents";
import { rootsQuery, sessionQuery } from "../api/queries";
import { ErrorNotice } from "../components/ErrorNotice";
import { Card, CardInset, CardTitle } from "../components/ui/card";
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
    <section aria-labelledby="settings-workspace" className="flex flex-col gap-3">
      <h2 id="settings-workspace" className="text-section-title font-semibold">
        Workspace
      </h2>
      <Card>
        <CardTitle>Workspace folder</CardTitle>
        {session.data !== undefined ? (
          session.data.workspace !== null ? (
            <CardInset>
              <code dir="ltr" className={PATH}>
                {session.data.workspace}
              </code>
            </CardInset>
          ) : (
            <p className="text-meta text-muted-foreground">The server did not report the workspace folder.</p>
          )
        ) : session.isError ? (
          <ErrorNotice error={session.error} onRetry={() => void session.refetch()} />
        ) : (
          <p className="text-meta text-muted-foreground">Loading.</p>
        )}
      </Card>
      <Card>
        <CardTitle>File access</CardTitle>
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
      </Card>
      <UploadLimitPanel />
    </section>
  );
}
