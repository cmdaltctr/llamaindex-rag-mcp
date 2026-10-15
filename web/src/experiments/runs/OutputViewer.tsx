import { useQuery } from "@tanstack/react-query";
import { Download } from "lucide-react";
import { useMemo } from "react";
import { useApi } from "../../api/ApiProvider";
import { runArtefactQuery } from "../../api/queries";
import { artefactName } from "../../api/runs";
import { ErrorNotice } from "../../components/ErrorNotice";
import { Button } from "../../components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle, DialogTrigger } from "../../components/ui/dialog";
import { boundText } from "../../runs/evidence";
import { maskValue } from "../../runs/redact";
import { isCut, serverCut } from "./cut";

/** The most text the viewer renders. Download covers the rest. */
const MAX_VIEW_BYTES = 256 * 1024;

/** A value the browser already holds, or the name of a stored artefact of the run, read on demand. */
export type OutputSource = { value: unknown } | { artefact: string };

function kib(bytes: number): string {
  return `${Math.ceil(bytes / 1024)} KiB`;
}

/** Saves the whole text as a file. The object address is revoked at once, so the blob is freed. */
function download(text: string, fileName: string) {
  const url = URL.createObjectURL(new Blob([text], { type: "application/json" }));
  const link = document.createElement("a");
  link.href = url;
  link.download = fileName;
  link.click();
  URL.revokeObjectURL(url);
}

function OutputText({ runId, name, value }: { runId: string; name: string; value: unknown }) {
  // Masked on the client too, so a value the server let through still shows the marker.
  const text = useMemo(() => JSON.stringify(maskValue(value), null, 2) ?? "null", [value]);
  const shown = useMemo(() => boundText(text, MAX_VIEW_BYTES), [text]);
  const bytes = new TextEncoder().encode(text).length;
  return (
    <>
      <p className="text-meta text-muted-foreground">
        {shown.truncated ? `The value is ${kib(bytes)}. Only the first ${kib(MAX_VIEW_BYTES)} are shown. Download it to read the rest.` : "The whole value is shown."}
      </p>
      <pre
        dir="ltr"
        tabIndex={0}
        aria-label="Output text"
        className="max-h-[60dvh] overflow-auto rounded-small border border-border bg-muted p-3 font-mono text-code whitespace-pre-wrap [overflow-wrap:anywhere]"
      >
        {shown.text}
      </pre>
      <DialogFooter className="sm:justify-start">
        <Button type="button" variant="outline" onClick={() => download(text, `run-${runId}-${name}.json`)}>
          <Download aria-hidden="true" />
          Download
        </Button>
      </DialogFooter>
    </>
  );
}

function ArtefactText({ runId, name }: { runId: string; name: string }) {
  const query = useQuery(runArtefactQuery(useApi(), runId, name));
  if (query.isError) return <ErrorNotice error={query.error} onRetry={() => void query.refetch()} />;
  if (query.isPending) {
    return (
      <p role="status" className="text-meta text-muted-foreground">
        Loading the full output.
      </p>
    );
  }
  return <OutputText runId={runId} name={name} value={query.data} />;
}

interface OpenFullOutputProps {
  runId: string;
  /** Names the download, `run-<run_id>-<name>.json`. For an artefact source it is the artefact name. */
  name: string;
  source: OutputSource;
}

/**
 * "Open full output" and its dialog. The value shows as plain JSON text,
 * never as markup. An artefact loads only when the dialog opens; Radix
 * unmounts the content when it closes.
 */
export function OpenFullOutput({ runId, name, source }: OpenFullOutputProps) {
  return (
    <Dialog>
      <DialogTrigger asChild>
        <Button type="button" variant="outline" size="sm">
          Open full output
        </Button>
      </DialogTrigger>
      <DialogContent className="sm:max-w-3xl">
        <DialogHeader>
          <DialogTitle>Full output</DialogTitle>
          <DialogDescription>
            The redacted value of <code className="font-mono text-code">{name}</code> in run <code className="font-mono text-code">{runId}</code>, as plain text.
          </DialogDescription>
        </DialogHeader>
        {"artefact" in source ? <ArtefactText runId={runId} name={source.artefact} /> : <OutputText runId={runId} name={name} value={source.value} />}
      </DialogContent>
    </Dialog>
  );
}

/**
 * Says that a preview was cut and offers the full output. A summary the
 * server cut opens through the artefact route, but only for an artefact of
 * the run shown; a value the browser cut opens from memory. Renders nothing
 * when nothing was cut.
 */
export function OutputCut({ runId, name, value }: { runId: string; name: string; value: unknown }) {
  const server = serverCut(value);
  if (server) {
    const artefact = artefactName(server.ref, runId);
    return (
      <div className="flex flex-wrap items-center gap-2 text-meta text-muted-foreground">
        {artefact !== null ? (
          <>
            <span>The server cut this output.</span>
            <OpenFullOutput runId={runId} name={artefact} source={{ artefact }} />
          </>
        ) : typeof server.ref === "string" && !server.ref.startsWith(`${runId}/`) ? (
          <span>The server cut this output. The full output belongs to another run, so it cannot be opened here.</span>
        ) : typeof server.ref === "string" ? (
          <span>The server cut this output. Its reference to the full output is not valid, so it cannot be opened here.</span>
        ) : (
          <span>The server cut this output and kept no full copy.</span>
        )}
      </div>
    );
  }
  if (!isCut(value)) return null;
  return (
    <div className="flex flex-wrap items-center gap-2 text-meta text-muted-foreground">
      <span>Part of this output is not shown here.</span>
      <OpenFullOutput runId={runId} name={name} source={{ value }} />
    </div>
  );
}
