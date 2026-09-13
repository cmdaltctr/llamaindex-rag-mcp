# Selective restoration (2026-09-10)

## Summary

The operator authorised controlled recovery after the session rollback. The
Experiment 25 writer received an explicit stop instruction and returned
“Stopped; no further work.” Its latest message and those of its descendants
then recorded `finish: stop`. No implementation was resumed for recovery.

The verified snapshot `468391ac9b838cffb07e25baecfd7e0003b7f862` is preserved at:
`/Users/aizat/Development/PROJECTS/input-quality-recovery-468391ac-20260910/`.

Before restoration, all 37 current modified/untracked files were archived as
`current-before-restore.tar.gz` in that folder and compared byte-for-byte.
SHA-256: `b8b79138ae45d16a972123c8ea12298fd5f3516783c8d0d7e9356329a8a4ae91`.
No staged files existed. The credential `.env` was excluded.

## Restored scope

Restored 27 files exactly from `recovered-work.tar.gz`: the Experiment 25
estimator and request-token fragments, Experiment 26/27 guards and tests,
shared helpers, amended reports and historical security-review evidence.
All 27 restored files matched the archive byte-for-byte after extraction.
All current files outside that set matched the pre-restoration backup.

Six snapshot files remain preserved separately, with their current disabled-path
versions retained in the worktree:

- `docs/tdr/023-reconstructed-nodes-are-not-stored-nodes.md`
- `experiments/25-token-chunking-ablation-2026-09-08/build_index.py`
- `experiments/25-token-chunking-ablation-2026-09-08/overnight.sh`
- `experiments/25-token-chunking-ablation-2026-09-08/protocol.md`
- `experiments/25-token-chunking-ablation-2026-09-08/results.md`
- `tests/test_exp25_build_authorisation.py`

The newer `offline_preparation_estimator.py` and its tests were retained without
changes. They are separate partial work, not a replacement verified by recovery.

## Verification

- All 21 inventoried historical plan/raw files remain byte-identical.
- Mixed-routing source, test and preserved patch retain their apply-start hashes.
- All 12 restored Python files parse without importing or executing them.
- Scoped Ruff checks passed on those 12 files.
- Strict OpenSpec validation passed for both changes.
- `git diff --check` passed.
- Pytest: NOT RUN during restoration. No prior pass count is a fresh result.

## Execution hold

Static inspection found a configuration path that can read the real `.env`:
`estimate_requests.py:114-117` calls `settings_to_effective()`; config imports
`load_dotenv()` and also declares `env_file=".env"`. The recovered estimator
test calls the same settings conversion. No credential file was read during
these checks. Isolate both dotenv and settings-file loading before execution.

The recovered `risks.md` is a historical review of the snapshot builder, not
approval of today's partially restored worktree. Its spending-control findings
remain unresolved. The retained builder has no runtime/embedding imports and
refuses forced rebuilds before estimate or approval reads.

Recovery does not complete tasks 3.2–3.6 or certify the recovered section 4 code.
Task text about a missing adapter is stale: the declared optional adapter was
installed before the rollback. No task checkbox was changed by this restoration.
No paid run, index mutation, production change, commit or push occurred.
