import { useMutation } from "@tanstack/react-query";
import { Plug } from "lucide-react";
import { useApi } from "../api/ApiProvider";
import { testConnection } from "../api/settings";
import { ErrorNotice } from "../components/ErrorNotice";
import { Badge } from "../components/ui/badge";
import { Button } from "../components/ui/button";
import { isKnownReason, reasonSentence } from "./connectionWords";

interface ProviderTestProps {
  provider: string;
  /** Unsaved field values. They are tested and not saved. */
  typed: Record<string, string>;
  cloud: boolean;
}

/** The Test action. It is the only call here that contacts a provider, and it sends typed values when a field is dirty. */
export function ProviderTest({ provider, typed, cloud }: ProviderTestProps) {
  const api = useApi();
  const test = useMutation({ mutationFn: () => testConnection(api, provider, typed), gcTime: 0 });
  const result = test.data;
  const known = result?.reason != null && isKnownReason(result.reason);

  return (
    <>
      <div className="flex flex-wrap items-center gap-3">
        <Button variant="outline" size="sm" disabled={test.isPending} onClick={() => test.mutate()}>
          <Plug aria-hidden="true" />
          {test.isPending ? "Testing" : "Test"}
        </Button>
        {cloud ? <p className="text-meta text-muted-foreground">Sends one request to the provider when you press Test.</p> : null}
      </div>
      <div role="status">
        {result !== undefined ? (
          <div className="flex flex-wrap items-center gap-2">
            {result.reachable ? (
              <Badge variant="success">Reachable</Badge>
            ) : (
              <>
                <Badge variant="error">Not reachable</Badge>
                {known ? <Badge variant="neutral">{result.reason}</Badge> : null}
                <span className="text-ui">{known ? reasonSentence(result.reason!) : "The test failed."}</span>
              </>
            )}
          </div>
        ) : null}
      </div>
      {test.isError ? <ErrorNotice error={test.error} onRetry={() => test.mutate()} /> : null}
    </>
  );
}
