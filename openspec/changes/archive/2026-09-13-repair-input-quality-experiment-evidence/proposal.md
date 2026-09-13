## Why

The session audit found unsafe experiment completion checks, unsupported conclusions, and an OCR decision recorded without operator approval. Repair the evidence and record the remaining decisions so another session can continue without repeating those mistakes.

## What Changes

- Work in the existing `feat/improve-rag-input-quality-5` worktree. Preserve the commits, historical failed results, frozen gates and existing indexes.
- Continuation (2026-09-10): execution moved into this change's own worktree on branch `feat/repair-input-quality-experiment-evidence` at `23389f7`, carrying the committed repair work. No reset or history rewrite occurred; the bullet above is superseded for location only.
- Reopen the OCR part of original task 5.5 and the unapproved acceptance in task 6.9 and ADR-064. Correct ADR-062's newly attributed acceptance. Leave packaged defaults unchanged.
- Experiment 25 is not rerun (operator decision, task 3.7). Its historical PASS, tokenizer promotion and existing index stand unchanged. The offline estimate, spending-approval and budget-stop rebuild path is descoped and its scaffold removed. The gate principle (a paid rebuild needs a current estimate and explicit approval) stays recorded in the spec for any future rebuild.
- Make experiment 26 and 27 reject incomplete, duplicate, mismatched or incompatible checkpoints before issuing a verdict. Correct their conclusions from the existing complete results.
- Rewrite experiment 27's purpose in plain English. Ask whether the combination is still wanted before scheduling another paid run.
- The repeat PDF routing study (approved corpus, independent page labels, held-out split, real OCR run) moved to `repeat-pdf-routing-study` (2026-09-13). It is new paid measurement, not evidence repair.
- The concrete routing defect experiment 28 exposed is fixed: `mixed` PDFs route by the calibrated thresholds, not unconditionally (commit `9bf4810`). This changes no packaged default. Enabling OCR by default remains an operator decision, deferred to `repeat-pdf-routing-study`.
- The four previously uncommitted routing files are adopted as that bug fix, with regression tests. Schema 5 includes the unconditional routing types in source identity, even when OCR is off. A later ingestion attempt can reprocess existing sources; preserved experiment indexes must not be re-ingested.
- Separate experiment verdicts from operator decisions. Record blocked work and tick tasks only after verification.
- Push the existing ten commits only as a remote backup. First inspect committed content for secrets and private data, then preserve all uncommitted changes in a verified local backup. Do not create a pull request.
- Measure coverage with a fresh full fast-suite run. Compare a named earlier revision only if attribution needs it, and do not expand into unrelated coverage fixes.
- Reassess both prior `AIK_py_LFI` checkpoint and temporary-file findings using a fresh scan and traced reachable input paths.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `experiment-validity-gates`: Require complete identified measurements, safe checkpoint reuse, guarded paid rebuilds, and explicit approval of decisions arising from results. The approved-cohort, independent-label and public-output-privacy gates moved to `repeat-pdf-routing-study` with the study itself (2026-09-13).

## Impact

- Experiment tooling and reports under `experiments/25-*`, `26-*`, `27-*` and `28-*`; new evidence uses separate run locations.
- Focused offline tests under `tests/`; reuse `experiments/_lib/` where its existing contracts fit.
- Decision records, configuration guidance, original OpenSpec task status and existing project tracking.
- Conditional production scope: PDF routing, OCR index identity and tests, only after the operator approves a precise policy and the planning artefacts are updated.
- No new worktree, dependency, model, cloud backend, default promotion, paid execution or corpus-wide scan is authorised by this proposal. Mistral OCR remains a separate future change.
- The approved remote backup does not authorise a pull request or any other pending operator decision. The routing bug fix is adopted separately as commit `9bf4810`.
