import { Trash2 } from "lucide-react";
import type { DocumentInfo } from "../api/documents";
import { Badge } from "../components/ui/badge";
import { Button } from "../components/ui/button";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "../components/ui/table";
import { availabilityLabel } from "../lib/labels";

interface SourceTableProps {
  collection: string;
  /** Display label of the vector database. One collection lives in one database. */
  storeLabel: string;
  sources: DocumentInfo[];
  onDelete: (source: DocumentInfo) => void;
}

/** Unknown availability stays neutral: it never reads as a lost source. */
function availabilityVariant(orphaned: boolean | null) {
  if (orphaned === true) return "warning";
  if (orphaned === false) return "success";
  return "neutral";
}

/** Sources of one collection with chunk counts, stable ids, database and machine-local availability. */
export function SourceTable({ collection, storeLabel, sources, onDelete }: SourceTableProps) {
  return (
    <Table aria-label={`Sources in ${collection}`}>
      <TableHeader>
        <TableRow>
          <TableHead scope="col">Source</TableHead>
          <TableHead scope="col">Stable ID</TableHead>
          <TableHead scope="col">Chunks</TableHead>
          <TableHead scope="col">Database</TableHead>
          <TableHead scope="col">On this machine</TableHead>
          <TableHead scope="col">
            <span className="sr-only">Actions</span>
          </TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {sources.map((source) => (
          <TableRow key={source.source_id ?? `legacy:${source.source}`}>
            <TableCell dir="ltr" className="min-w-48 font-mono text-code break-all">
              {source.source}
            </TableCell>
            <TableCell dir="ltr" className="font-mono text-code break-all">
              {source.source_id ?? "No stable ID (legacy row)"}
            </TableCell>
            <TableCell>{source.chunks}</TableCell>
            <TableCell className="whitespace-nowrap">{storeLabel}</TableCell>
            <TableCell>
              <Badge variant={availabilityVariant(source.orphaned)}>{availabilityLabel(source.orphaned)}</Badge>
            </TableCell>
            <TableCell>
              <Button variant="ghost" size="sm" aria-label={`Delete ${source.source}`} onClick={() => onDelete(source)}>
                <Trash2 aria-hidden="true" />
                Delete
              </Button>
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}
