## Why

Experiment 28's routing measurements were taken before the `mixed`-PDF routing defect was fixed (commit `9bf4810`) and used a convenience corpus with classifier-derived labels and no held-out split. They cannot support the still-open decision of whether OCR routing should ever be enabled by default. The `repair-input-quality-experiment-evidence` change deferred this repeat study here because it is new paid measurement, not evidence repair.

## What Changes

- Run a preregistered repeat of the experiment 28 routing study in a new sibling experiment directory. Experiment 28's frozen plan, raw output and original report remain unchanged.
- Repair the classification tooling first: checkpoint identity bound to the approved collection and policy, private digest-to-ID mapping, and public outputs that cannot leak private paths or exception text.
- Obtain an operator-approved document list or precise selection rule, including the previously identified book as a development/stress case, before reading any selected PDF.
- Record independent page-level labels and an agreed development/held-out split. The book and any document used to design a candidate rule count as development evidence only.
- Obtain explicit operator approval for missing-page tolerance, whole-document routing behaviour and enable-only zero-threshold behaviour before freezing the candidate.
- Freeze the protocol, labels, split and acceptance criteria in a separate commit before held-out scoring. Compare the pinned historical policy against the approved candidate; the working tree is never an unnamed baseline.
- Run the approved classification/routing evaluation, then ask separately whether real OCR measurement is authorised (documents, timeout, runtime budget). A classification-only run reports OCR cost as projected and recovery quality as unmeasured.
- Publish the routing comparison with missing-page evidence, held-out results, disclosed convenience selection and retained negative results.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `experiment-validity-gates`: Add the study-execution gates this repeat study must satisfy — an operator-approved collection boundary with private identity mapping, a protocol freeze before held-out measurement, and separately authorised real OCR measurement.

## Impact

- New experiment directory under `experiments/` chosen at apply time; repairs to the experiment 28 classification tooling under `experiments/28-*` and `experiments/_lib/` where its contracts fit.
- Focused offline tests under `tests/`.
- Experiment 28's frozen plan, raw results and original report are preserved read-only.
- No production routing change, packaged-default promotion, corpus-wide scan or paid run follows automatically from this proposal. Real OCR measurement requires its own recorded authorisation.
- Private document names, paths and content stay in ignored local storage; public records carry opaque identifiers only.
