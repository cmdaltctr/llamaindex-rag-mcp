import { useMutation } from "@tanstack/react-query";
import { Plug } from "lucide-react";
import { useApi } from "../api/ApiProvider";
import { testConnection, type Connection } from "../api/settings";
import { ErrorNotice } from "../components/ErrorNotice";
import { Badge } from "../components/ui/badge";
import { Button } from "../components/ui/button";
import { Card, CardHeader, CardTitle } from "../components/ui/card";
import { isKnownReason, PROVIDER_NAMES, reasonSentence, ROLE_NAMES } from "./connectionWords";

const CODE = "text-code font-mono [overflow-wrap:anywhere]";

/** One provider: its addresses, models, key state and roles, plus a Test action. It has no edit control. */
export function ConnectionCard({ connection }: { connection: Connection }) {
  const api = useApi();
  const name = PROVIDER_NAMES[connection.provider];
  const titleId = `connection-${connection.provider}`;
  const test = useMutation({ mutationFn: () => testConnection(api, connection.provider), gcTime: 0 });
  const result = test.data;

  return (
    <Card role="region" aria-labelledby={titleId}>
      <CardHeader>
        <CardTitle id={titleId}>{name}</CardTitle>
        <div className="flex flex-wrap items-center gap-2">
          {connection.roles.length > 0 ? (
            connection.roles.map((role) => (
              <Badge key={role} variant="hue">
                {ROLE_NAMES[role]}
              </Badge>
            ))
          ) : (
            <span className="text-meta text-muted-foreground">No role uses this provider.</span>
          )}
        </div>
      </CardHeader>
      <dl className="grid grid-cols-[auto_minmax(0,1fr)] gap-x-3 gap-y-1 text-ui">
        {connection.urls.map((entry) => (
          <div key={`url-${entry.label}`} className="col-span-2 grid grid-cols-subgrid">
            <dt className="text-meta text-muted-foreground">Address ({entry.label})</dt>
            <dd>
              <code dir="ltr" className={CODE}>
                {entry.url}
              </code>
            </dd>
          </div>
        ))}
        {connection.models.map((entry) => (
          <div key={`model-${entry.label}`} className="col-span-2 grid grid-cols-subgrid">
            <dt className="text-meta text-muted-foreground">Model ({entry.label})</dt>
            <dd>
              <code dir="ltr" className={CODE}>
                {entry.name}
              </code>
            </dd>
          </div>
        ))}
        <div className="col-span-2 grid grid-cols-subgrid">
          <dt className="text-meta text-muted-foreground">Key</dt>
          <dd>{connection.key_set ? "Key set" : "No key"}</dd>
        </div>
      </dl>
      <div className="flex flex-wrap items-center gap-3">
        <Button variant="outline" size="sm" disabled={test.isPending} onClick={() => test.mutate()}>
          <Plug aria-hidden="true" />
          {test.isPending ? "Testing" : "Test"}
        </Button>
        {connection.provider === "openrouter" ? (
          <p className="text-meta text-muted-foreground">Sends one request to openrouter.ai when you press Test.</p>
        ) : null}
      </div>
      <div role="status">
        {result !== undefined ? (
          <div className="flex flex-wrap items-center gap-2">
            {result.reachable ? (
              <Badge variant="success">Reachable</Badge>
            ) : (
              <>
                <Badge variant="error">Not reachable</Badge>
                {result.reason !== null && isKnownReason(result.reason) ? <Badge variant="neutral">{result.reason}</Badge> : null}
                <span className="text-ui">{result.reason !== null && isKnownReason(result.reason) ? reasonSentence(result.reason) : "The test failed."}</span>
              </>
            )}
          </div>
        ) : null}
      </div>
      {test.isError ? <ErrorNotice error={test.error} onRetry={() => test.mutate()} /> : null}
    </Card>
  );
}
