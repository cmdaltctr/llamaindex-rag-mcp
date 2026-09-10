# Repair input-quality evidence without repeating the studies

## Why

Experiments 25–28 informed the input-quality decisions recorded in ADR-063
and ADR-064. Their historical records must remain available. The experiment
tooling must also distinguish complete, supported evidence from partial data
and later reconstruction.

Static inspection at `afe151e93dd9b79e18618811dc15e35c6a96b16d` found:

- Experiment 26's summariser checks equal arm sizes, then pairs their
  intersection. Equal sizes do not establish exact query membership.
- Experiment 27 checks the sizes of its two measured arms only. Its two
  reference cells can be incomplete without that check detecting the problem.
- Both summarisers round some aggregates before gate comparisons and write
  over the original summary and report.
- Both runners construct manifests from declared constants. The committed
  manifests omit important provenance required by TDR-014. Recomputing a
  metric now cannot establish which provider or configuration ran historically.
- Experiment 28 assigns sequential IDs after sorting the current digest set.
  Adding or removing a document can change existing IDs before resume.
  Its public error rows include `str(exc)[:300]`; shortening text does not
  remove private paths. Discovery and setup failures can also expose paths.

The four committed Experiment 26/27 checkpoints each contain 223 rows and
223 unique query IDs. This inspection does not prove missing historical rows,
nor does it independently verify execution. The defects are inadequate
validity checks and stronger execution claims than the retained provenance
can establish.

Experiment 25 remains **closed: COMPLETE — PASS**. The operator declined a
rerun on 2026-09-10. Its existing unconditional paid-build refusal remains.
Its original plans, indexes, raw evidence, results and ADR-063 are preserved.
The possibility of a future estimator mentioned in older records is not an
obligation under this change.

## What Changes

1. Record Experiment 25's declined rerun in a concise additive close-out
   record. Do not change its code, plans, evidence or historical verdict.
2. Repair Experiment 26's evidence checks and gate precision. Produce a
   separate amended report from verified existing inputs, without paid calls.
3. Apply the corresponding checks to all four Experiment 27 cells. Preserve
   the distinction between historical reference cells, historical measured
   cells and later offline recomputations.
4. Add Experiment 28's private immutable digest-to-ID mapping, safe resume
   refusal and bounded public errors. Test only with synthetic private paths.
5. Stop for operator decisions before personal-document work or routing work.
6. Complete local validation of the repaired tree and report remaining gaps.

For Experiments 26 and 27, the local agent must compare recovery candidates
with the committed state before selective restoration. Recovery is evidence
to inspect, not an instruction to replace the tree. Missing content must
remain missing unless an identifiable source supplies it.

## Capabilities

### New Capabilities

- `private-experiment-identity`: immutable private document identity,
  compatible resume, bounded public errors and the Experiment 28 operator gate.

### Modified Capabilities

- `experiment-validity-gates`: add scoped requirements for Experiment 25
  closure and Experiment 26/27 evidence repair, provenance, precision and
  separate amended outputs. Existing general requirements remain in force.

## Impact

This commit creates planning files only under this change directory.
Implementation has not started.

Later implementation is limited to experiment tooling, focused tests, additive
repair records and separate amended outputs. Likely code targets are the
Experiment 26/27 `summarise_eval.py` files and small experiment-local evidence
helpers, plus Experiment 28 `classify.py` and local-only file exclusions.
No general experiment framework rewrite is needed.

Existing tests provide conventions, not coverage of these specific defects:
`tests/test_experiment_plan_contract.py`,
`tests/test_experiment_preflight.py`, `tests/test_experiment_stats.py`,
and Experiment 25's accounting tests. New focused regression files are named
in `tasks.md`.

There are no dependencies, application changes, production routing changes,
NiftyPM changes, pull requests or ADR edits in this change. ADR-063 and
ADR-064 remain byte-identical.

## Deferred Work and Operator Decisions

Experiment 25 implementation is excluded: no `BudgetStopEmbedder` or
`BaseEmbedding` compatibility work, live builder activation, paid-build
authorisation machinery, `estimate_gate`, `offline_preparation_estimator`,
rerun, or reusable paid-run infrastructure.

Experiments 26 and 27 have no paid repeats. Missing historical runtime
observations cannot be repaired by assigning current settings to old rows.

The operator must explicitly approve each applicable next step before reading
personal PDFs, scanning personal documents, running a repeat study, selecting
a candidate routing policy, changing production routing, adopting a mixed
patch, promoting any OCR default, replacing the current routing policy, or
making claims from new private-document measurements. Passing synthetic tests
does not provide this approval. These operations require a separately agreed
scope and are not implementation tasks in this change.

## Ownership and Completion

ChatGPT owns this remote planning commit. The local agent owns recovery
comparison, implementation, fail-before proof, pass-after checks, authorised
offline experiment checks and all runtime validation.

Complete the six stages in order. Stage 5 records the mandatory stop; stage 6
validates already-authorised tooling without crossing it. Unresolved evidence
may produce an honest INVALID or INCOMPLETE amended assessment. It must never
be hidden by a PASS. See `validation.md` for exact local commands.
