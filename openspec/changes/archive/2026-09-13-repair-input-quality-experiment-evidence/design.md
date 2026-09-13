## Context

See `proposal.md` for scope. This is a recovery change in the existing worktree, not a reset of the original implementation.

### Starting evidence

At proposal time, HEAD is `afe151e93dd9b79e18618811dc15e35c6a96b16d`. The remote-tracking feature ref is `2c58b4530fe4ea432f39c1e7bfd2a63a2f5fed97`. Recheck both before apply; they are provenance, not reset targets.

Four files already contain an unapproved mixed-routing patch:

- `.env.example`
- `docs/guides/ingestion.md`
- `src/omrg/integrations/pdf/ocr_routing.py`
- `tests/test_ocr_routing_gate.py`

Continuation note (2026-09-10): execution moved from the `feat/improve-rag-input-quality-5` worktree into this change's own worktree on branch `feat/repair-input-quality-experiment-evidence`, HEAD `23389f7`. That commit adds the routing defect fix `9bf4810`, the experiment 26/27 guard commit `e5240d1`, a gitleaks allowlist commit and this change's planning artefacts on top of the starting evidence recorded above. The recovered repair work is committed there and the working tree is clean. The starting-evidence figures are retained as provenance, and the four-file patch statement above is historical: its disposition is recorded in decision 7 and the register.

The audit verified the complete experiment 26 and 27 numeric results. Both contain 223 expected queries. Partial prefixes can incorrectly receive PASS. Experiment 28 contains 79 records and no errors, but resume regenerates sequential IDs and public errors can contain private exception messages.

Experiment 25's `build_index.py` skips when its marker exists and otherwise refuses paid work, including `--force`. TDR-023 explains why: the earlier estimator counted the wrong inputs. `verify_accounting.py` checks completed indexes and cannot authorise future spending. The existing refusal is intentional protection until a correct replacement exists.

Relevant evidence:

- `docs/tdr/022-token-counting-is-contract-sensitive.md`, superseded accounting sections identified there.
- `docs/tdr/023-reconstructed-nodes-are-not-stored-nodes.md`, current accounting contract.
- `tests/test_exp25_request_accounting.py`, adapter request-text tests and current forced-build refusal test.
- Experiment 26 `summarise_eval.py:338–340`; experiment 27 `summarise_eval.py:405–409`.
- Experiment 28 `classify.py:95–107,173–200` and `summarise_eval.py:88–104`.
- `docs/adr/064-input-quality-promotion-decisions.md` and original change tasks 5.5 and 6.9.

### Operator approval received on 2026-09-09

> User explicitly approved all three gaps with safeguards: push existing ten commits after secrets/private-data inspection and local backup of ALL uncommitted changes; no PR; fresh full fast-suite coverage measurement with comparable earlier revision check if needed, do not expand into unrelated coverage fixes; explicitly reassess both prior AIK_py_LFI checkpoint/tempfile findings using fresh scan and reachable input paths. Mixed patch unapproved, all remaining operator gates remain.

## Goals / Non-Goals

**Goals:**

- Make the existing evidence reproducible without new embedding spending.
- Preserve a clear record of what the operator has approved and what remains pending.
- Create the approved remote backup without including or losing uncommitted work.
- Refresh comparable coverage and security evidence without expanding repair scope.

Scope amendment (2026-09-10): two original goals are removed here. "Restore a guarded rebuild option for experiment 25" is descoped by the operator's task 3.7 decision not to rerun experiment 25. "Evaluate routing on an operator-selected collection with independently checked pages" is deferred to a separate change. Both are recorded as non-goals below. The deferred study moved to `repeat-pdf-routing-study` on 2026-09-13.

**Non-goals:**

- Rewrite git history, create a worktree or delete historical runs. (Amended 2026-09-10: execution later moved into this change's own worktree `feat/repair-input-quality-experiment-evidence` carrying the committed repair work; no history was rewritten.)
- Create a pull request as part of the approved remote backup.
- Promote any packaged default during evidence repair.
- Implement a replacement routing policy before its approval and specification.
- Introduce page stitching, a new OCR backend, Mistral integration or a new ingestion framework.
- Repeat experiments 25–27 merely because their reporting needs correction.
- Repair unrelated coverage debt or experiment 24 tooling in this change. Their audit findings remain unresolved and must not be described as fixed.
- Rebuild experiment 25's index or restore its estimate-approval path (descoped 2026-09-10; the operator decided at task 3.7 not to rerun it).
- Run the repeat PDF routing study in this change; it lives in `repeat-pdf-routing-study` (deferred 2026-09-10, moved 2026-09-13).

## Decisions

### 1. Preserve state before applying repairs

Use this worktree only. Record HEAD and a digest inventory of historical plans, raw results, index locations and the existing patch. Save the existing patch to an explicitly named local preservation location before touching any overlapping file. Do not reset or discard it.

Use path-scoped file tools for edits. Commands that write, including tests, require a tool with an explicit working-directory parameter. The audit session lacked such a tool; make availability an apply prerequisite rather than bypassing the guard. Verify repository and branch before launch. Do not install extras or synchronise dependencies without approval.

The operator approved a remote backup of the existing ten commits only. Before pushing, inspect the complete committed range for secrets and private data. Stop on any unresolved finding. Preserve all uncommitted changes in a local backup, including staged, unstaged, untracked and intentionally edited ignored files. Keep the backup outside the pushable tree, record its inventory and hashes, and verify it is readable. Push only the inspected HEAD. Verify the remote ref matches that HEAD and confirm that no pull request was created.

Alternative rejected: rolling back to the session base. The unconditional mixed rule predates that point, so rollback would retain the routing problem and remove useful evidence.

### 2. Reopen the original decision without inventing another one

During apply, use `openspec-update-change` to reconcile the original change's planning artefacts. Reopen the OCR portion of task 5.5 and the unapproved decision-record completion at 6.9. Preserve earlier tokenizer approval and completed measurements. Correct ADR-064's attribution and ADR-062's newly asserted acceptance.

Settled (2026-09-10): the operator settled the OCR routing/default disposition. ADR-064 now records the settled decision (OCR off by default, `mixed` removed from `OCR_UNCONDITIONAL_TYPES`, further promotion deferred). ADR-062 stays Proposed for the worker architecture. The packaged OCR switch remains false and both thresholds remain zero.

Synchronise decision status with the existing local project-tracking bundle and NiftyPM through its normal workflow when available. Report an unavailable sync explicitly; never claim it happened.

Alternative rejected: treating a failed gate as permission to write an Accepted ADR under the operator's name.

### 3. Replace experiment 25's refusal only after a valid offline estimate exists

DESCOPED (2026-09-10): the operator decided at task 3.7 not to rerun experiment 25. Its historical PASS, tokenizer promotion and existing index stand. The unconditional refusal in `build_index.py` remains the live behaviour, and the historical estimator and approval scaffold is absent from the consolidated tree. Preserve its recovery records; do not restore it. The gate principle is preserved for any future rebuild in the `experiment-validity-gates` spec requirement "Paid rebuilds require current estimates and approval". The text below is retained as that future design basis.

Reuse production document selection and preparation with an in-memory sink and a network-blocked embedding-request recorder. Exercise the installed adapter's normal request preparation using a fake transport; do not rebuild payloads from row text and metadata or revive the deprecated standalone counter.

The estimate records corpus and plan identity, code/lock provenance, effective tokenizer identity/revision, relevant settings, request tokens and maximum request size. It includes the baseline/candidate comparison required by the frozen cost rule. A missing comparison, incomplete preparation or fallback invalidates the estimate.

The operator confirmed that the 15% threshold evaluates the experiment result. It asks whether the candidate uses more than 15% extra embedding tokens compared with the baseline. Display estimated tokens, percentage increase and approximate monetary cost before asking for spending approval. An increase above 15% must not invalidate an otherwise valid estimate or block an approved build. Preserve the frozen acceptance threshold and report a failed cost gate if the measured increase exceeds it.

Pricing is explicit operator-provided or verified pricing with a recorded date. Counts alone must not be called a monetary estimate. State that provider retries and billing can differ. Bind approval to the estimate digest, a separate destination and a spending ceiling; stop before launching further paid batches if the approved estimate would be exceeded. Do not claim a provider-side billing cap.

Keep the marker's reuse behaviour only for a matching run identity. `--force` can request a new build but cannot override spending approval or overwrite preserved indexes. Update `overnight.sh` and other documented entry points so none retains the deprecated approval path. Retrospective verification remains separate.

Prove dry-run/request-text parity on synthetic fixtures using the existing adapter-test approach. Read-only verification of the historical index can follow. An actual rebuild is optional and requires a new question, destination and cost approval from the operator.

Alternative rejected: removing the refusal alone. It would reopen the same unguarded spending path described in TDR-023.

### 4. Validate experiment 26 and 27 inputs before computing a verdict

Reuse `_lib` validation contracts where practical. Keep a small shared helper only for genuinely shared validation, not a general experiment framework.

For each cell, validate the exact expected query IDs, uniqueness, category labels, completed-row consistency and compatible manifest identity. Join paired rows by ID. Reject malformed or non-finite measurements. Distinguish INCOMPLETE from INVALID; neither can produce PASS, FAIL or promotion advice. Keep smoke outputs separate from completed historical results.

Old complete checkpoints remain historical evidence. They lack some execution provenance, so document those limits. Do not fabricate timestamps or silently resume them into new sessions. New runs record session identity and timing, including interruptions, before claiming a shared execution period.

Regression cases include the actual four-query experiment 26 prefix that currently passes, the one-query experiment 27 prefix, equal counts with different IDs, duplicates, category drift and mismatched manifests. Complete historical cells must reproduce their existing failed gates without modifying raw files.

Alternative rejected: rerunning paid queries first. The current results can verify the repairs offline.

### 5. Explain experiments 26 and 27 in plain English

Experiment 26 asks: "Does this instruction improve retrieval from the same index?" Keep its measured negative result. Report equal R@5 alongside changed rankings; remove claims of proven endpoint determinism. Explain that the latency cause is unresolved.

Experiment 27 asks: "When we combine the new chunking with the query instruction, is retrieval still acceptable?" Keep the failed result. Explain the historical cells and uncertain interaction. Its positive interaction estimate describes less-than-additive harm; it does not prove a protective mechanism. Retain the limitation that no PDFs were exercised.

Keep original frozen plan files unchanged. Add dated corrections for wrong rationale, including the inherited latency arithmetic. Do not adjust thresholds to match measurements. Correct reports from saved checkpoints into a separate amended report or a clearly dated generated section, preserving original report provenance.

Ask whether another combined run serves a desired candidate. If the operator declines, record that decision and finish the repair without running it. If a repeat is requested, update this change with its precise protocol, immutable inputs, execution controls and cost approval before measurement. Apply the same rule to any requested repeat of experiment 26.

### 6. Repeat experiment 28 as a routing study

DEFERRED (2026-09-10), moved (2026-09-13): this study is new paid measurement, not evidence repair. It now lives in `openspec/changes/repeat-pdf-routing-study/`, which carries the full design basis, spec gates and tasks formerly held here (tasks 6.1–6.11). The concrete routing defect it targeted is already fixed by commit `9bf4810`, which routes `mixed` PDFs by the calibrated thresholds instead of unconditionally. Do not start the study under this change.

### 7. Adopt a routing change only through a later explicit amendment

Disposition (2026-09-10): the four-file mixed patch was adopted as the standalone defect-fix commit `9bf4810` ("route mixed PDFs by threshold, not unconditionally") with regression tests, on design grounds. It changes no packaged default. The consolidation correction includes the unconditional routing types in source identity and advances schema 4 to 5. This invalidates prior identities even when OCR is off; only a later ingestion attempt can reprocess a source. Preserved experiment indexes must not be re-ingested. The broader OCR default-promotion decision (`OCR_FALLBACK_ENABLED`) stays deferred to `repeat-pdf-routing-study`. Any future default change still follows this section's amendment rule.

The settled defect fix is recorded above. For any further production rule, after the operator approves it, run `openspec-update-change` on `repeat-pdf-routing-study` (or a later change if that one is archived) to add its exact PDF behaviour, scenarios and implementation tasks, and reconcile the design there. Then seek approval to apply that amended scope.

If the existing mixed removal is selected, its adoption must cover enable-only behaviour, fixed test cases at zero and calibrated thresholds, reader diagnostics, whole-request failure handling and routing-policy identity. A policy change affecting extractor output must prevent stale `skipped_unchanged` results. Reconcile the ingestion guide, configuration guide, environment comments and ADR together.

The patch is preserved in commit history and its adoption is settled. Further routing-policy changes require a separate explicit decision.

### 8. Record completion honestly

Each checked task needs a command/result or a reviewed document pointer. Confirm new tests fail with the protection removed before marking their fix complete. Keep blocked tasks unchecked and name the blocker beside them. A decision task can complete with a recorded decision to defer; an unperformed experiment must never be labelled measured.

Measure coverage through a fresh full fast-suite run with the repository's branch-coverage settings. Record the exact command, revision, lock provenance, test counts, skips and applicable coverage totals. If branch attribution remains unclear, run the same command and configuration at a named comparable earlier revision in a separate clean location. Treat that comparison as evidence only. Do not add unrelated coverage fixes.

Run a fresh security scan and reassess both prior `AIK_py_LFI` findings independently. Trace every reachable input path from public or experiment boundaries to the checkpoint and temporary-file path operations. Record trust boundaries, path controls and the evidence for each disposition. Keep reachable or unresolved findings open.

Final checks include targeted tests, the user-requested fast suite, OpenSpec validation and a before/after evidence inventory. Code changes also require the normal security review. Preserve the core+MCP coverage exception as unresolved unless the operator explicitly accepts it; an empty Chroma diff alone does not prove an aggregate baseline.

## Risks / Trade-offs

- Selected documents limit generalisation. Report the selection and annotation coverage; avoid population claims.
- The known book can bias candidate design. Keep it in development and use a separate hold-out.
- Offline accounting can drift from real requests. Test adapter parity and invalidate estimates when preparation changes.
- Editing shared guide files can absorb the unapproved patch. Save the patch first and review each changed hunk.
- Missing runtime tools or optional dependencies can block tests. Stop and request the required tool or installation approval.
- Approval may remain pending across sessions. Keep the decision register below and link each task to it.

## Decision register

Updated during apply to record the operator's approvals and their safeguards. The quoted approval above is the controlling record for this amendment.

| Item                                 | Status                                                                         | Action before proceeding                                                                                  |
| ------------------------------------ | ------------------------------------------------------------------------------ | --------------------------------------------------------------------------------------------------------- |
| Existing worktree                    | Approved by operator; moved 2026-09-10 to this change's own worktree           | Stay on `feat/repair-input-quality-experiment-evidence`; no reset or further worktree change              |
| Evidence/tooling repair              | Approved by operator                                                           | Apply within the existing safeguards                                                                      |
| Existing ten-commit remote backup    | Approved with safeguards                                                       | Inspect committed content; verify a local backup of all uncommitted changes; push only the inspected HEAD |
| Pull request                         | Not approved                                                                   | Do not create one                                                                                         |
| Full fast-suite coverage measurement | Approved with safeguards                                                       | Run fresh coverage; compare a named earlier revision only if needed; do not fix unrelated debt            |
| Two prior `AIK_py_LFI` findings      | Approved for reassessment                                                      | Run a fresh scan and trace reachable input paths for the checkpoint and temporary-file findings           |
| Experiment 25 estimate and 15% rule  | Confirmed by operator                                                          | Display estimated tokens and cost; use 15% only to judge the result; allow an approved build above it     |
| Experiment 25 paid rebuild           | Decided: not rerun (2026-09-10, task 3.7)                                      | Keep the unconditional refusal; remove the orphaned estimator scaffold                                    |
| Experiment 26 repeat                 | No paid repeat authorised (2026-09-10)                                         | Record the formal purpose or close decision; no new tasks without an operator request                     |
| Experiment 27 repeat                 | No paid repeat authorised (2026-09-10)                                         | Record the formal purpose or close decision; no new tasks without an operator request                     |
| Selected PDF collection              | Moved to `repeat-pdf-routing-study` (2026-09-13)                               | Obtain the explicit list or selection, including the book, in that change                                 |
| Independent page labels and hold-out | Moved to `repeat-pdf-routing-study` (2026-09-13)                               | Agree coverage and reserve unseen outcomes in that change                                                 |
| Replacement routing rule             | Defect fixed via `9bf4810`; policy deferral confirmed by operator (2026-09-10) | Keep the settled mixed/zero-threshold behaviour; approve any further policy change in `repeat-pdf-routing-study`          |
| Real OCR measurement                 | Moved to `repeat-pdf-routing-study` (2026-09-13)                               | Agree documents, runtime budget and timeout in that change                                                |
| Four-file mixed patch                | Adopted as defect-fix commit `9bf4810` (2026-09-10)                            | None here; broader default promotion remains deferred                                                     |
| OCR default promotion                | Decided: stays off (2026-09-10)                                                | Keep `OCR_FALLBACK_ENABLED=false`; any promotion requires the `repeat-pdf-routing-study` evidence         |

## Migration Plan

Apply the evidence repairs before any new measurement. Keep historical plans and raw outputs immutable. Write new run data to distinct locations. There is no production migration in the initial scope.

If a later approved amendment changes routing, its migration must include index invalidation and a rollback plan. Do not rewrite the historical record to make the new policy appear pre-registered for experiment 28.
