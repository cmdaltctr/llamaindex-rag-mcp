import { useQuery } from "@tanstack/react-query";
import { useApi } from "../api/ApiProvider";
import { connectionsQuery } from "../api/queries";
import { ErrorNotice } from "../components/ErrorNotice";
import { Card, CardHeader, CardTitle } from "../components/ui/card";
import { CopyButton } from "./CopyButton";
import { McpHttpPanel } from "./McpHttpPanel";
import { McpTokenPanel } from "./McpTokenPanel";
import { WebPortPanel } from "./WebPortPanel";

/** The configuration a stdio client needs: it starts `omrg` in the folder whose `.env` the server read. */
export function stdioConfiguration(configDir: string): string {
  return JSON.stringify({ mcpServers: { omrg: { command: "uv", args: ["run", "--directory", configDir, "omrg"] } } }, null, 2);
}

function StdioPanel() {
  const query = useQuery(connectionsQuery(useApi()));
  const configDir = query.data?.config_dir;
  return (
    <Card role="region" aria-labelledby="mcp-stdio-title">
      <CardHeader>
        <CardTitle id="mcp-stdio-title">Stdio client</CardTitle>
        <p className="text-meta text-muted-foreground">The client starts its own omrg process, so no server needs to run.</p>
      </CardHeader>
      {configDir === undefined ? (
        query.isError ? (
          <ErrorNotice error={query.error} onRetry={() => void query.refetch()} />
        ) : (
          <p role="status" className="text-meta text-muted-foreground">
            Loading.
          </p>
        )
      ) : (
        <>
          <p className="text-ui">
            Starts omrg with{" "}
            <code dir="ltr" className="text-code font-mono [overflow-wrap:anywhere]">
              {`uv run --directory ${configDir} omrg`}
            </code>
            , so it reads the same .env as this server.
          </p>
          <pre dir="ltr" tabIndex={0} className="overflow-x-auto rounded-control border border-border bg-muted p-3 text-code font-mono">
            {stdioConfiguration(configDir)}
          </pre>
          <div>
            <CopyButton text={stdioConfiguration(configDir)} what="stdio configuration" />
          </div>
        </>
      )}
    </Card>
  );
}

/** How to connect an MCP client: over stdio, or over HTTP to this server. */
export function McpSection() {
  return (
    <section aria-labelledby="settings-mcp" className="flex flex-col gap-3">
      <h2 id="settings-mcp" className="text-section-title font-semibold">
        MCP
      </h2>
      <div className="grid grid-cols-1 items-start gap-3 lg:grid-cols-2">
        <div className="flex flex-col gap-3">
          <StdioPanel />
          <WebPortPanel />
        </div>
        <div className="flex flex-col gap-3">
          <McpHttpPanel />
          <McpTokenPanel />
        </div>
      </div>
    </section>
  );
}
