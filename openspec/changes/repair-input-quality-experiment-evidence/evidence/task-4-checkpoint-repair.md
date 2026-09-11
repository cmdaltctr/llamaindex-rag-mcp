# Checkpoint repair evidence (tasks 4.1-4.6 and 5.1)

## Summary

Date: 2026-09-10. This record covers the Experiment 26 and 27 checkpoint
repair work for `repair-input-quality-experiment-evidence`.

Root-cause delegation found the defect before implementation. `a-debug` showed
that both summarisers checked only between-arm row-count equality. They then
gated whatever rows existed and derived a verdict without a validity dimension.
`a-test` wrote fail-before regressions first.

The repair validates evidence before every gate. It binds new measurements to a
run identity and session record. It keeps historical evidence readable with its
provenance limits stated. The recorded `a-refactor` pass preserved behaviour.

## Task 4.1 - Fail-before regression tests

New files `tests/test_exp26_verdict_validity.py` and
`tests/test_exp27_verdict_validity.py` first produced 24 failures. The two key
failures were:

- Exp26: `expected INCOMPLETE for the four-query prefix; current verdict=PASS`.
- Exp27: `expected INCOMPLETE for one combined query; current verdict=PASS`.

The post-restore, pre-hardening baseline run passed all 24 tests. Security
hardening added state, name, and limit guards. The final focused suite has 38
passing tests:
26 for Exp26 and 12 for Exp27.

Four mutation checks were detected and then restored green:

- M1: forcing the Exp26 validation gate to complete failed the prefix test.
- M2: forcing the Exp27 validation gate to complete failed prefix and loaded-cell tests.
- M3: swallowing invalid `classify_cell` reasons caused 10 failures.
- M4: making `identity_mismatches` always empty failed the resume-contract test.

## Task 4.2 - Cell validity and gate refusal

`experiments/_lib/checkpoint_validity.py` adds `classify_cell` and
`validate_cells`. `classify_cell` rejects duplicates, unexpected identifiers,
category and ground-truth mismatches, malformed rows, non-finite latency, and
desynchronised done rows. A well-formed strict subset is incomplete. Exact
membership is complete.

`validate_cells` aggregates these results and checks cross-cell pairing. Equal
row counts with different identifier membership are invalid. Both summarisers
call it before any gate. Incomplete and invalid evidence produces neither a
verdict nor promotion wording.

## Task 4.3 - Provenance and pairing

`pairing_ids_mismatch` joins cells by their declared identifier sets. Equal
counts with different identifiers cannot produce a verdict. A regression test
proves this contract.

Each new checkpoint has a timestamp-free run identity. It is the SHA-256 of
`plan.json`, `ground-truth.json`, the Experiment 22 LangChain manifest, the
canonical runtime manifest, and `run_eval.py`, `uv.lock`,
`_lib/preflight.py`, and `_lib/checkpoint_validity.py`.

`run_identity`, `identity_mismatches`, and `evaluate_resume` check that
identity. A mismatch refuses resume. Legacy checkpoints without provenance
are labelled historical evidence and are "not resumable into new runs".

## Task 4.4 - Isolated runs and outputs

Both runners use `resolve_checkpoint_base`. `--limit N` writes only below
`output/smoke/limit-N/` and refuses an existing directory. A measured run
requires `--run-dir NAME` below `output/runs/`.

Legacy `output/cells` is never resumed, appended to, or overwritten. Each
summariser writes only to an explicit `--out-dir`. Its default is the dated
`output/recovery-2026-09-10/` recovery directory. It never writes the frozen
`output/eval_results.summary.json` or root `results.md`.

The security review in `evidence/task-4-security-review.md` returned NEEDS
FIXES: four MEDIUM findings and one LOW finding. The same-day repair validates
run-name components, rejects `../evil`, absolute paths, nested names, `..`,
and `.`. It rejects zero and negative limits, uses `allow_nan=False` for all
runner JSON writes, rejects non-object checkpoints, adds both shared helpers
to identity, and restamps the session ID on resume.

Finding 2 remains partly addressed. The identity omits summariser and
`assembly` reporting code. This is a documented limitation because runner and
imported helper code affect measurements. The generic `assembly` import risk
is accepted for these standalone experiment scripts and documented in its
module comment.

## Task 4.5 - Session recording

Both runners add `new_session_state`, `resume_session_state`, and
`execution_periods_text`. `session.json` records the session ID, UTC start and
end periods, and interruptions. Checkpoints include the run identity and
session ID.

Reports use execution-period language. Historical evidence says execution is
not recorded and states a provenance limit. New work reports a single period.
Resumed work reports mixed execution periods and claims no common network epoch.

## Task 4.6 - Offline historical recompute

Both complete historical cell sets were recomputed offline into
`repair/evidence/task-4-recompute/exp26/` and
`repair/evidence/task-4-recompute/exp27/`. Each contains an evaluation summary
and `results.md`.

Exp26 is complete with 223 queries per arm. Its verdict is FAIL. Its gates
match the historical record byte-for-byte: lift -0.024649 FAIL, identifier
R@10 0.256337 FAIL, p95 3542.8 ms FAIL, and bootstrap half-width 0.015502.

Exp27 is complete with 223 rows in each of four cells. The production baseline
comes from Experiment 22. The instruction-only cell comes from Experiment 26.
The other two cells were measured here. Its verdict is FAIL. Its gates match:
R@5 0.223686 FAIL, identifier R@10 0.269936 PASS, p95 4790.4 ms FAIL, and
interaction +0.011795.

SHA-256 records in `repair/evidence/task-4-recompute/hashes-before.json` and
`repair/evidence/task-4-recompute/hashes-after.json` cover 25 files. They
include 21 inventoried files plus four root `results.md` and `discussion.md`
files. All 25 are byte-identical. No inventoried JSON or frozen plan changed.

## Task 5.1 - Exp26 discussion and report generation

Exp26 `discussion.md` replaces "Why the raw arm reproduced Experiment 22
exactly" with "What the raw arm's agreement with Experiment 22 shows". The
replaced text said equal R@5 "confirms the embedding endpoint is
deterministic" and attributed the delta "to nothing else". A dated 2026-09-10
correction records that 65 of 223 per-query rankings differ, with first
differences from rank 1. Equal R@5 is aggregate coincidence. It does not show
rank-level stability or embedding-endpoint determinism.

Paired within-run attribution is bounded by the plus or minus 0.0155 bootstrap
half-width. The latency section now says "did not discriminate". The former
claim that the endpoint was simply slower now says results are consistent with
a slower provider period and cannot separate provider-side variance from any
other cause.

The summariser now uses execution-period wording. Its drift note says a
non-zero delta is consistent with provider-side or pipeline variance. It does
not identify a cause by itself. Equal aggregate values do not show rank-level
stability. Root `results.md` has the same dated corrections. Its hand-added
"Recovery clarification (2026-09-09)" sections remain. Regenerated reports
write only to the recovery directory. The same corrections appear in
`repair/evidence/task-4-recompute/exp26/results.md`.

### Remaining Exp27 wording

Exp27 `discussion.md` and root `results.md` replace "The combined failure is
entirely the instruction" with "The instruction takes the combined path below
the bar". A dated 2026-09-10 note gives the within-run -0.0128 paired model-
token-index difference as the isolated instruction effect. The four-cell table
is labelled a historical comparison. It cannot prove that the instruction
caused every difference. "Independent confirmation" is softened to
"corroboration".

## Verification

| Command or check | Result |
| --- | --- |
| `uv run --no-sync pytest tests/test_exp26_verdict_validity.py tests/test_exp27_verdict_validity.py -q` | 38 passed |
| Same focused command, pre-fix | 24 failed; the Exp26 and Exp27 incomplete-prefix messages are recorded above |
| `uv run --no-sync pytest tests/test_exp25_build_authorisation.py tests/test_exp25_estimate_gate_scaffold.py tests/test_exp25_request_accounting.py tests/test_exp25_accounting_contracts.py tests/test_exp26_verdict_validity.py tests/test_exp27_verdict_validity.py -q` | 61 passed; the Exp25 suite was unaffected |
| `uv run --no-sync ruff check tests/test_exp26_verdict_validity.py tests/test_exp27_verdict_validity.py` | All checks passed; `experiments/` is outside the repository lint scope |
| Exp26 summarise | Complete, 223 per arm, FAIL, gates byte-equal to history |
| Exp27 summarise | Complete, four cells of 223, FAIL, gates byte-equal to history |
| SHA-256 before and after | 25/25 byte-identical; see the recorded hash files |
| File sizes | All changed files below 500 lines: largest Exp26 `summarise_eval.py` 472; runners 432 and 447; shared library 270 and 99+; `assembly.py` 155; tests 348 and 199 |

## Limitations

1. Run identity hashes the runner, imported helpers, and lockfile. It does not hash summariser or `assembly` reporting code.
2. Historical checkpoints have no run identity or session record. They remain labelled historical evidence with provenance limits. They cannot resume into new runs.
3. The `a-refactor` pass preserved behaviour. Tests were green after each step. No ADR was created because no architectural decision changed.
4. Tasks 4.1-4.6 and 5.1 remain unticked in `tasks.md`. The Exp25 agent edits that file concurrently. This evidence is the completion record. Ticking follows that agent's landing.
5. Task 5.4, the operator rerun decision, was intentionally not approached.
