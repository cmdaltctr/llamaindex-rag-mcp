# Recompute evidence (moved)

These files were first committed under a top-level `repair/evidence/` folder.
On 2026-10-13 they moved here, next to the change they belong to. The bytes
are unchanged (SHA-256 checked before and after the move).

The files record the paths in use when the commands ran. For example,
`task-4-recompute/exp26/eval_results.summary.json` names
`repair/evidence/task-4-recompute/exp26` as its `out_dir`. That is the
original location. It is history, not a link, and was left as written.

| Path | Content |
|---|---|
| `fresh-fast-coverage.md` | Fresh full fast-suite branch coverage (task 8.2a). |
| `task-4-recompute/hashes-before.json`, `hashes-after.json` | SHA-256 manifests of the frozen experiment inputs. |
| `task-4-recompute/exp26/`, `exp27/` | Offline recomputed summaries and results (task 4). |
