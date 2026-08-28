# TDR-011: Pre-calibration audit and executable experiment-plan validation

**Date:** 2026-08-18
**Status:** Accepted
**Deciders:** Dr Muhammad Aizat Md Hawari with AI agent
**Tags:** experiments | audit | testing | pre-calibration

## Context

Stage 0 of `harden-pipeline-correctness-before-calibration` established two
conventions that outlive the change itself:

1. **Audit provenance rules** — `audit-baseline.md` pins the parent commit,
   dependency versions, and the interpretation rule for archived OpenSpecs.
2. **Executable experiment plans** — `experiments/_lib/plan.py` provides a
   machine-readable plan representation (experiment ID, factors, cells,
   controlled variables, manifest assertions) with contract tests in
   `tests/test_experiment_plan_contract.py`.

Historical experiments 10b/13/14 drifted from their declared protocols because
declared cells and runner-generated cells were never compared mechanically.
Archived OpenSpecs were treated as implementation evidence even when their
task lists were unchecked and production code never landed the behaviour.

## Decision

- Treat **archived OpenSpec status as design intent, not implementation
  evidence**. Only current source and executable tests confirm a contract.
- Experiment runners must declare their cell matrix in the shared plan
  representation, and a lightweight unit test must compare declared cells
  against runner-generated cells **without loading models or corpora**.
- Audit baselines for future hardening changes must record parent SHA, exact
  locked dependency versions, and intended-red test inventories before any
  production fix lands.

## Consequences

### Positive

- Protocol/runner drift becomes a deterministic test failure instead of an
  invalid experiment discovered after compute is spent.
- "Archived means implemented" ambiguity is resolved by an explicit rule.

### Negative

- New experiment runners carry a small declaration burden before running.

### Neutral

- The plan helper is deliberately minimal (no orchestration, no model
  loading); it is a contract, not a framework.

## Alternatives Considered

| Option | Rejected Because |
|--------|-----------------|
| Trust archived OpenSpecs as evidence | Proven wrong by `add-ingestion-change-detection` (unchecked tasks, unimplemented design) |
| Compare cells inside full experiment runners | Requires loading models/corpora; too slow for CI contract tests |

## How to Recognise / Handle This Again

1. Experiment conclusions look unstable across reruns.
2. Check `tests/test_experiment_plan_contract.py` still passes and the
   runner's declared plan matches its cell generator.
3. Re-run the contract test; if it fails, the runner drifted from protocol.

## Revisit Triggers

- A future experiment framework replaces `experiments/_lib/plan.py`.
- OpenSpec archiving gains machine-verifiable task completion.

## References

- `openspec/changes/harden-pipeline-correctness-before-calibration/audit-baseline.md`
- `openspec/changes/harden-pipeline-correctness-before-calibration/audit-findings.md`
