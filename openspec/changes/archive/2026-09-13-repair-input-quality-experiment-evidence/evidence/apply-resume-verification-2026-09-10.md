# Apply-resume verification (2026-09-10)

## Worktree and command route

The preflight command confirmed:

- Repository root: `/Users/aizat/Development/PROJECTS/llamaindex-rag-mcp-v3-feat-repair-input-quality-experiment-evidence`
- Branch: `feat/repair-input-quality-experiment-evidence`
- HEAD before these checks: `23389f7`
- Initial tracked changes: only the three OpenSpec planning edits from the completed update workflow.

Desktop Commander file edits use explicit absolute paths. Its `start_process` tool has no working-directory parameter. The focused offline test command used an absolute `cd` after this preflight. This is a recorded limitation, not a replacement for the explicit-working-directory command path in task 1.2. Do not use this route for installations, migrations, key generation, or other destructive commands.

## Fresh section 4 verification

Command:

```sh
uv run --no-sync pytest tests/test_exp26_verdict_validity.py \
  tests/test_exp27_verdict_validity.py -q -rs
```

Result: **38 passed in 2.28s**. Pytest reported no skipped tests.

`evidence/task-4-checkpoint-repair.md` records the required fail-before result: 24 failures before the safeguards, including the experiment 26 four-query prefix and experiment 27 one-query prefix incorrectly producing PASS.

A fresh SHA-256 comparison of every path in
`repair/evidence/task-4-recompute/hashes-after.json` reported:

```text
ok=25 bad=0 missing=0 total=25
```

The recomputed reports remain in distinct destinations:

- `repair/evidence/task-4-recompute/exp26/`
- `repair/evidence/task-4-recompute/exp27/`

They report complete 223-query cells and the preserved FAIL verdicts.

## Fresh task 5.1 check

`experiments/26-query-instruction-ablation-2026-09-08/discussion.md` contains the dated correction that equal R@5 does not prove deterministic execution. It records 65 ranking differences. It labels absolute latency attribution inconclusive. The separately regenerated experiment 26 report contains the same rank-stability and latency wording.

## NiftyPM availability check

This worktree has no `niftypm/` directory or tracked NiftyPM file. The current MCP server inventory exposes no NiftyPM server. Cloud synchronisation remains blocked. `evidence/decision-tracking-sync.md` remains the local-state and cloud-blocker record; no cloud receipt is claimed.

## Task 1.5 mitigation backup (2026-09-10)

The push in task 1.6 already happened, so pre-push proof of full ignored-file coverage is permanently unavailable and task 1.5 stays unchecked. As mitigation, a fresh verified backup now protects the current uncommitted state:

- `/Users/aizat/Development/PROJECTS/repair-resume-backup-23389f7-20260910/uncommitted-planning-20260910.tar.gz` — the three amended planning files plus this evidence file. SHA-256 `b2135c156fe8f929f8cd41013e105578d8fb06bd38736785842ed02c3821b968`.
- `/Users/aizat/Development/PROJECTS/repair-resume-backup-23389f7-20260910/ignored-state-20260910.tar.gz` — `.env`, `.pi/hindsight/*` and `.pytest_cache/*`. SHA-256 `0b09638746004a72472ed252252b493009acfc816d04ef72c83375a20cfa3fc3`.

Byte verification after extraction: `same=12 diff=0 missing=0` across every archived file. `.venv/` is excluded by design: it is reproducible from the tracked `uv.lock` via `uv sync` and holds no source state; the exclusion is recorded here rather than silently applied. Both archives live outside the pushable tree. Operator direction (2026-09-10): keep the backup in place; task 1.5 stays open with this mitigation recorded beside the permanent pre-push proof gap.

## Tripwire re-baseline and full fast suite (tasks 8.1–8.2)

The clean-base tripwire (`tests/test_clean_base_tripwire.py`) pinned the bare-CI executed count at 2,774. The committed suite now executes 2,816 in the tripwire subprocess (outer run 2,820 passed + 1 failed before the fix). The +42 delta is exactly the 38 experiment 26/27 verdict-validity cases (`e5240d1`) plus the 4 mixed-routing regression cases (`9bf4810`); skipped (131) and deselected (19) counts never drifted. The pin was re-baselined 2,774 → 2,816 with a dated comment. The earlier objection to counting the routing tests applied only while the four-file patch was unapproved; it is now the committed, reviewed defect fix.

Full command (green run, after the re-baseline):

```sh
uv run --no-sync pytest -m 'not slow' -q --cov=omrg --cov-branch
```

Result at `23389f7`: **2,821 passed, 131 skipped, 19 deselected, 0 failed in 551.82 s**. The tripwire passed inside this run, validating the new pin against its own subprocess recount.

Targeted fail-before evidence for the repaired tooling: `evidence/task-4-checkpoint-repair.md` records 24 fail-before failures (including the four-query and one-query prefix PASS defects) and four mutation checks; the tripwire failure above is itself a fail-before record for the count-drift guard.

## Coverage (task 8.2a)

Same command as 8.2 at `23389f7` (lock provenance: `uv run --no-sync`, installed dependency set unchanged from the recorded environment):

- Overall branch coverage: **91%** (9,662 statements, 754 missed; 2,860 branches, 281 partial) — above the 90% floor.
- Orchestration tier: **94%** — above the 85% floor.
- Core+MCP tier: **91%** — **below the 95% floor**. The Core+MCP exception remains unresolved and visible; no unrelated coverage fix was attempted, per the change non-goals. The prior recorded measurement at `afe151e` (90.65%) used the identical command and configuration, so branch attribution does not require a further earlier-revision run: both measurements are on file and the suite is green at both.

## Security scan and file lengths (task 8.3)

Fresh scanner run (opengrep CLI, 312 rules, 25 tracked files, `--sarif --experimental`; saved as `evidence/aikido-scan-2026-09-10.sarif`, SHA-256 `bbde0c4c9a5e4306d6e9224238362f6b0a3ea1032527a8f0ec3e291ade2299d5`): **21 findings, all `AIK_py_LFI`**, in the experiment 26/27 runners, summarisers and their tests. Dispositions:

- Runner sinks (`_save_checkpoint` and neighbours) sit behind `resolve_checkpoint_base`, which rejects zero/negative limits, existing smoke directories, `""`/`.`/`..`, any multi-component or absolute run name, and refuses to resume the legacy `output/cells` evidence.
- Summariser writes go only into the operator-supplied `--out-dir` under the experiment directory; no network-facing boundary exists.
- The flagged test lines are the pytest-tmp fixtures carrying the `../evil` regression strings themselves.
- Residual risk is unchanged from `evidence/aikido-reassessment.md`: LOW, requiring a local actor who can write inside the checkout (symlink race). No secret or credential finding appeared. All findings stay visible in the SARIF.

File lengths: no `src/omrg` file exceeds 500 lines (`lancedb.py` and `compose.py` sit at exactly 500). The two named violators (`estimate_gate.py` 506, `test_exp25_estimator_repair.py` 515) no longer exist; the descoped scaffold removal already resolved them. Experiment 28 privacy and checkpoint-identity work is deferred with section 6 and stays open there.

## Final validation and preserved state (task 8.4)

- `openspec validate repair-input-quality-experiment-evidence --strict` — valid.
- `openspec validate improve-rag-input-quality-5 --strict` — valid.
- 25/25 recompute-manifest paths re-hashed byte-identical (includes the 21 inventoried historical plan/raw files).
- Preserved outputs present read-only: experiment 22 output and the experiment 25 `output/lancedb` index directory.
- Packaged defaults unchanged: `.env.example` keeps `OCR_FALLBACK_ENABLED=false` commented off; the reranker default path is untouched.

## Operator decisions recorded (2026-09-10)

- Task 7.1: the operator confirmed the routing-policy deferral ("confirm deferral"). The presentation stated plainly that experiment 28's measurements predate the fix and no post-fix field evidence exists; the deferral keeps the policy decision behind the future preregistered study.
- Task 7.3: the operator decided `OCR_FALLBACK_ENABLED=false` stays. Original tasks 5.5c/6.9b closed with that decision; ADR-062/ADR-064 recovery corrections stand.
- Section 6 deferral to the separate future routing-study change: confirmed by the operator ("yes").
- Task 1.5 remains the only open item, pending the operator's acceptance of the mitigation backup described above.
