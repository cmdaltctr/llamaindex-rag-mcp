import { useQuery } from "@tanstack/react-query";
import { useApi } from "../api/ApiProvider";
import { mcpQuery } from "../api/queries";
import { useSetMcpEnabled } from "../api/settingsMutations";
import { ErrorNotice } from "../components/ErrorNotice";
import { Button } from "../components/ui/button";
import { Card, CardHeader, CardTitle } from "../components/ui/card";
import { CopyButton } from "./CopyButton";

/** The configuration of an HTTP client. The token placeholder is replaced by the token shown once. */
export function httpConfiguration(url: string): string {
  const config = { mcpServers: { omrg: { type: "http", url, headers: { Authorization: "Bearer omrg_mcp_<token>" } } } };
  return JSON.stringify(config, null, 2);
}

/** The MCP-over-HTTP switch, with the state the server returns, and the client configuration. */
export function McpHttpPanel() {
  const query = useQuery(mcpQuery(useApi()));
  const change = useSetMcpEnabled();
  const state = query.data;

  return (
    <Card role="region" aria-labelledby="mcp-http-title">
      <CardHeader>
        <CardTitle id="mcp-http-title">MCP over HTTP</CardTitle>
        <p className="text-meta text-muted-foreground">Clients share this running server and need a token. The endpoint is off until you turn it on.</p>
      </CardHeader>
      {state === undefined ? (
        query.isError ? (
          <ErrorNotice error={query.error} onRetry={() => void query.refetch()} />
        ) : (
          <p role="status" className="text-meta text-muted-foreground">
            Loading.
          </p>
        )
      ) : (
        <>
          <div>
            <Button
              variant="outline"
              role="switch"
              aria-checked={state.enabled}
              aria-label="MCP over HTTP"
              disabled={change.isPending}
              onClick={() => change.mutate(!state.enabled)}
            >
              {change.isPending ? "Saving" : state.enabled ? "On" : "Off"}
            </Button>
          </div>
          {change.isError ? <ErrorNotice error={change.error} onRetry={() => change.mutate(!state.enabled)} /> : null}
          <p className="text-ui">
            URL:{" "}
            <code dir="ltr" className="text-code font-mono [overflow-wrap:anywhere]">
              {state.url}
            </code>
          </p>
          <pre dir="ltr" tabIndex={0} className="overflow-x-auto rounded-control border border-border bg-muted p-3 text-code font-mono">
            {httpConfiguration(state.url)}
          </pre>
          <div>
            <CopyButton text={httpConfiguration(state.url)} what="HTTP configuration" />
          </div>
        </>
      )}
    </Card>
  );
}
