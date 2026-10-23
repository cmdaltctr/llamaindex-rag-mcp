import { FileText, Upload, X } from "lucide-react";
import { useRef, useState, type DragEvent } from "react";
import { Button } from "../components/ui/button";
import { formatSize } from "../lib/uploadLimit";

interface FileDropZoneProps {
  files: File[];
  onChange: (files: File[]) => void;
  disabled?: boolean;
}

/** The same file picked twice is listed once. */
function fileKey(file: File): string {
  return `${file.name}|${file.size}|${file.lastModified}`;
}

function merge(current: File[], added: File[]): File[] {
  const seen = new Set(current.map(fileKey));
  return [...current, ...added.filter((file) => !seen.has(fileKey(file)))];
}

/**
 * Pick files by dropping them on the zone or with Choose files. Each pick adds
 * to the list, and each file can be removed before the upload. The hidden
 * input keeps the label "Files to upload" for screen readers and tests.
 */
export function FileDropZone({ files, onChange, disabled = false }: FileDropZoneProps) {
  const input = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);

  function onDragOver(event: DragEvent) {
    if (disabled) return;
    event.preventDefault();
    setDragging(true);
  }

  function onDragLeave(event: DragEvent) {
    if (!(event.relatedTarget instanceof Node && event.currentTarget.contains(event.relatedTarget))) setDragging(false);
  }

  function onDrop(event: DragEvent) {
    event.preventDefault();
    setDragging(false);
    if (!disabled) onChange(merge(files, Array.from(event.dataTransfer.files)));
  }

  return (
    <div className="flex flex-col gap-2">
      <div
        role="group"
        aria-label="Drop files to upload"
        data-dragging={dragging ? "true" : undefined}
        onDragOver={onDragOver}
        onDragLeave={onDragLeave}
        onDrop={onDrop}
        className="flex flex-col items-center gap-2 rounded-control border border-dashed border-border-hover bg-background/60 px-4 py-6 text-center transition-colors duration-150 data-[dragging=true]:border-ring data-[dragging=true]:bg-selection"
      >
        <Upload aria-hidden="true" className="size-5 text-muted-foreground" />
        <p className="text-ui">Drag files here</p>
        <Button type="button" variant="outline" size="sm" disabled={disabled} onClick={() => input.current?.click()}>
          Choose files
        </Button>
        <input
          ref={input}
          type="file"
          multiple
          aria-label="Files to upload"
          tabIndex={-1}
          className="sr-only"
          disabled={disabled}
          onChange={(event) => {
            onChange(merge(files, Array.from(event.target.files ?? [])));
            // Clearing lets the same file be picked again after a removal.
            event.target.value = "";
          }}
        />
      </div>
      {files.length > 0 ? (
        <ul aria-label="Files to send" className="flex flex-col gap-1">
          {files.map((file) => (
            <li key={fileKey(file)} className="flex min-w-0 items-center gap-2 rounded-control border border-border bg-background/60 py-1 ps-3 pe-1 text-ui">
              <FileText aria-hidden="true" className="size-4 shrink-0 text-muted-foreground" />
              <span className="min-w-0 flex-1 truncate" title={file.name}>
                {file.name}
              </span>
              <span className="shrink-0 text-meta text-muted-foreground">{formatSize(file.size)}</span>
              <Button
                type="button"
                variant="ghost"
                size="icon-xs"
                aria-label={`Remove ${file.name}`}
                disabled={disabled}
                onClick={() => onChange(files.filter((other) => fileKey(other) !== fileKey(file)))}
              >
                <X aria-hidden="true" />
              </Button>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}
