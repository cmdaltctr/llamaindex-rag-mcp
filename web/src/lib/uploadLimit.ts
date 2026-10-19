/**
 * Sizes for upload messages. The per-file limit itself comes from the server
 * only (`GET /v1/settings/upload-limit`); the client keeps no copy of it.
 */
const MIB = 1024 * 1024;

/** A size in mebibytes, for example "60 MiB" or "1.5 MiB". */
export function formatMiB(bytes: number): string {
  return `${Number((bytes / MIB).toFixed(1))} MiB`;
}
