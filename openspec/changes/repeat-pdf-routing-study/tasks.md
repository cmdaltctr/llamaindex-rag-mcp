# Tasks: repeat-pdf-routing-study

This change continues work deferred from `repair-input-quality-experiment-evidence` (its section 6, dated 2026-09-10). The concrete routing defect experiment 28 exposed is already fixed by commit `9bf4810`; this study produces the preregistered evidence for the deferred OCR default-promotion decision.

Tick each task immediately after its verification succeeds. Add the evidence pointer beside the task. Leave blocked work unchecked and name the blocker. Sections 2 and 3 contain explicit operator-approval checkpoints: tooling preparation may proceed before approval, but no PDF is read, no candidate is selected and no paid or private-document work begins until the matching approval is recorded in the design decision register.

## 1. Make the classification tooling safe

- [ ] 1.1 Repair checkpoint identity and private mapping preservation for PDF classification. Verify added, removed or replaced documents and a changed policy refuse unsafe resume.
- [ ] 1.2 Remove unrestricted exception text from public outputs and check serialised artefacts for leaks. Verify an exception containing a synthetic private path cannot expose it in checkpoints or reports.

## 2. Approve the collection and labels

- [ ] 2.1 Ask the operator to approve the document list or precise selection rule, including the known book. Verify the approval is recorded privately before reading any selected PDF.
- [ ] 2.2 Create a separate repeat-study directory and immutable private digest-to-ID mapping. Verify discovery processes only the approved collection and leaves experiment 28's original output unchanged.
- [ ] 2.3 Agree an independent page-annotation method and development/held-out split. Record labels and uncertainty; verify the known book is development evidence and held-out outcomes do not guide candidate design.

## 3. Freeze the protocol

- [ ] 3.1 Ask the operator to approve missing-page tolerance, whole-file routing behaviour and enable-only zero-threshold behaviour. Record the precise candidate and acceptance criteria; stop if undecided.
- [ ] 3.2 Freeze the new protocol, labels/split and criteria in a separate commit before held-out scoring. Verify the commit precedes candidate measurement; preserve all old gates.
- [ ] 3.3 Add tests for comparing the pinned historical policy with the approved candidate, using synthetic evidence first. Verify the uncommitted patch cannot silently become the baseline and removing a guard fails its regression test.

## 4. Measure and publish

- [ ] 4.1 Run the approved classification/routing evaluation and record elapsed classification time. Verify complete membership, stable resume and public-output privacy; report uncertain labels explicitly.
- [ ] 4.2 Record whether real OCR measurement is authorised, including selected documents, timeout and runtime budget. If authorised, add and verify explicit execution tasks; otherwise label OCR cost as projected and recovery quality unmeasured.
- [ ] 4.3 Publish the routing comparison with missing-page evidence, hold-out results and limitations. Verify fixture-based time estimates are labelled, convenience selection is disclosed, and negative results are retained.
