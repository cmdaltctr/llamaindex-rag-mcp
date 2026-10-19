import { useQuery } from "@tanstack/react-query";
import { KeyRound, Trash2 } from "lucide-react";
import { useState } from "react";
import { useApi } from "../api/ApiProvider";
import { mcpQuery } from "../api/queries";
import { useRevokeMcpToken, useRotateMcpToken } from "../api/settingsMutations";
import { ErrorNotice } from "../components/ErrorNotice";
import { Button } from "../components/ui/button";
import { Card, CardHeader, CardTitle } from "../components/ui/card";
import { CopyButton } from "./CopyButton";

function when(iso: string | null): string {
  if (iso === null) return "";
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? iso : date.toLocaleString("en-GB", { dateStyle: "medium", timeStyle: "short" });
}

/**
 * Create, rotate and revoke the MCP token. A new token lives in this
 * component's state only: it is never cached or stored, so leaving the
 * section drops it and the server cannot show it again.
 */
export function McpTokenPanel() {
  const query = useQuery(mcpQuery(useApi()));
  const rotate = useRotateMcpToken();
  const revoke = useRevokeMcpToken();
  const [shown, setShown] = useState<string | null>(null);
  const [revokedNote, setRevokedNote] = useState<string | null>(null);
  const exists = query.data?.token.exists ?? false;

  function create() {
    rotate.mutate(undefined, {
      onSuccess: (created) => {
        setShown(created.token);
        setRevokedNote(null);
      },
    });
  }

  function remove() {
    revoke.mutate(undefined, {
      onSuccess: (result) => {
        setShown(null);
        setRevokedNote(
          result.revoked ? "The token was revoked. Clients that hold it lose access at their next request." : "No token existed.",
        );
      },
    });
  }

  return (
    <Card role="region" aria-labelledby="mcp-token-title">
      <CardHeader>
        <CardTitle id="mcp-token-title">MCP token</CardTitle>
        <p className="text-meta text-muted-foreground">The token works on the MCP address only. The server keeps a digest, so it cannot show the token again.</p>
      </CardHeader>
      {query.data === undefined ? (
        query.isError ? (
          <ErrorNotice error={query.error} onRetry={() => void query.refetch()} />
        ) : (
          <p role="status" className="text-meta text-muted-foreground">
            Loading.
          </p>
        )
      ) : (
        <>
          <p className="text-ui">{exists ? `A token exists, created ${when(query.data.token.created_at)}.` : "No token exists."}</p>
          {exists ? (
            <p className="text-meta text-muted-foreground">Rotating the token stops every client that holds the old one. Update each client with the new token.</p>
          ) : null}
          <div className="flex flex-wrap gap-2">
            <Button variant="default" size="sm" disabled={rotate.isPending} onClick={create}>
              <KeyRound aria-hidden="true" />
              {exists ? "Rotate token" : "Create token"}
            </Button>
            {exists ? (
              <Button variant="destructive" size="sm" disabled={revoke.isPending} onClick={remove}>
                <Trash2 aria-hidden="true" />
                Revoke token
              </Button>
            ) : null}
          </div>
        </>
      )}
      {rotate.isError ? <ErrorNotice error={rotate.error} onRetry={create} /> : null}
      {revoke.isError ? <ErrorNotice error={revoke.error} onRetry={remove} /> : null}
      {shown !== null ? (
        <div className="flex flex-col gap-2 rounded-control border border-border bg-muted p-3">
          <p className="text-meta text-muted-foreground">Copy this token now. It is shown once.</p>
          <code dir="ltr" className="text-code font-mono [overflow-wrap:anywhere]">
            {shown}
          </code>
          <div>
            <CopyButton text={shown} what="MCP token" />
          </div>
        </div>
      ) : null}
      {revokedNote !== null && shown === null ? (
        <p role="status" className="text-meta text-muted-foreground">
          {revokedNote}
        </p>
      ) : null}
    </Card>
  );
}
