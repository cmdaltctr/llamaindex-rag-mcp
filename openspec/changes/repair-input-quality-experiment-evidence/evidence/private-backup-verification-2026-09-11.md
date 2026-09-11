# Private backup verification (2026-09-11)

## Summary

The existing independent backup of the Experiment 22/25 databases, shared
corpus and ignored ground truth is present and readable. Sampled SHA-256
checksums match the live source. No data was copied, rebuilt or regenerated
for this record; the backup predates this wording update.

## Source and backup locations

| Item | Source | Backup |
| --- | --- | --- |
| Experiment 22 database | `~/Development/DATA/omrg/experiments/exp22-lancedb` | `~/Development/DATA/omrg/experiments/backup-20260910-consolidation/exp22-lancedb` |
| Experiment 25 database | `~/Development/DATA/omrg/experiments/exp25-lancedb` | `~/Development/DATA/omrg/experiments/backup-20260910-consolidation/exp25-lancedb` |
| Shared corpus | `~/Development/DATA/omrg/experiments/freshstack-corpus` | `~/Development/DATA/omrg/experiments/backup-20260910-consolidation/freshstack-corpus` |
| Ignored ground truth | `experiments/22-raw-query-qwen4b-baseline-2026-09-07/output/ground-truth.json` | `~/Development/DATA/omrg/experiments/backup-20260910-consolidation/ground-truth-exp22.json` |

The backup directory `backup-20260910-consolidation` lives outside the
pushable tree. The source index locations match `evidence/historical-input-inventory.md`.

## Sampled checksum verification

Checksums were sampled, not exhaustively recomputed, to avoid repeating
work. Every sampled file matched byte-for-byte.

- Ground truth (full SHA-256, both 5,646,091 bytes):
  `3860314c74a5c0be4d10f7cdd4d9d55d1daea4cfedf9dcd60d8fbe20d43b4fe8`.
- Experiment 22 `exp22.lance`: 3 of N data fragments sampled, all matched
  (e.g. `08e7de506ec240393c81dd9022afd8435769cae8b471c53ae3b3c0fb72946f5c`).
- Experiment 25 `exp25_model_token.lance`: 3 of N data fragments sampled,
  all matched (e.g. `371f1bd187b693c9c523b58cb72f547245d9bca4ef05e5f576b809c3810ccb1a`).
- Shared corpus: file count matches exactly (10,025 source = 10,025 backup);
  one sampled markdown fragment matched
  (`3854a44c2b3f97abd92024ba576e75629b34efa0ae673a58d70596b8c31e8293`).

## Boundary

This record confirms the existing backup only. It does not rebuild missing
data, copy fresh data, or modify any source or backup. GitHub source
inspection can verify tracked evidence only; this local check establishes the
external backup that GitHub cannot. The historical plan/raw file hashes in
`evidence/historical-input-inventory.md` remain the tracked identity record.
