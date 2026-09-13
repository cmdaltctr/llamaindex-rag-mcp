## Context

See `proposal.md` for scope. This change is the deferred study recorded in `repair-input-quality-experiment-evidence` (design decision 6, tasks 6.1–6.11). The concrete routing defect experiment 28 exposed is already fixed: commit `9bf4810` routes `mixed` PDFs by the calibrated thresholds instead of unconditionally. ADR-064 records the settled disposition — OCR off by default, `mixed` removed from `OCR_UNCONDITIONAL_TYPES`, further promotion deferred to this study.

What remains open is whether `OCR_FALLBACK_ENABLED` should ever be promoted. Answering that needs a preregistered evaluation on an operator-approved corpus with independently labelled pages and a held-out split. Experiment 28's frozen plan, raw results and original report are preserved read-only.

## Goals / Non-Goals

**Goals:**

- Repair the classification tooling so resumed runs cannot mix collection or policy identities and public outputs cannot leak private paths.
- Evaluate the approved candidate against the pinned historical policy on an operator-approved collection with independent page labels.
- Produce honest evidence for the OCR default-promotion decision, including negative results and disclosed limitations.

**Non-goals:**

- Re-run experiment 28 in place or modify its frozen plan, raw output or original report.
- Promote any packaged default, including `OCR_FALLBACK_ENABLED`, inside this change. Promotion is a separate later decision informed by this study.
- Introduce page stitching, a new OCR backend, Mistral integration or a new ingestion framework.
- Scan Zotero, Downloads, Documents, Desktop or any other location automatically. The collection comes only from an explicit operator approval.
- Perform real OCR requests without a separate recorded authorisation.

## Decisions

### 1. Use a separate repeat-study directory

Use a new sibling experiment directory with the next available identifier, chosen at apply time. Keep experiment 28's frozen plan and original output intact.

### 2. Bind the collection to an explicit approval

The collection must include the previously identified book as a known development/stress case, plus explicitly approved documents. No automatic scan of Zotero, Downloads, Documents or Desktop is permitted. Ask the operator to supply or approve a path list or a precisely defined collection. Preserve content-digest-to-ID mappings privately and validate them before resume. Public records carry opaque IDs and safe counts only.

### 3. Label pages independently of the classifier

Independent page assessment records whether important text is readable and whether extraction misses content. Check all flagged pages and an agreed sample of unflagged pages, with the inspection coverage disclosed. Label uncertain cases explicitly. Automated density is supporting evidence, never the sole truth label. Freeze annotations before scoring candidate outcomes where possible.

### 4. Separate development evidence from held-out evidence

Use the book to develop the rule and test the known regression. Choose separate held-out documents; prevent their outcomes from guiding the candidate. Do not call this convenience collection a prevalence estimate for all academic libraries.

### 5. Treat the routing judgements as operator approvals

Before measurement, ask the operator to approve:

- How much missing text warrants whole-document OCR, given that this change does not stitch selected pages.
- What happens with mixed PDFs when only the enable switch is set.
- Acceptable missed-page and unnecessary-routing outcomes, including ambiguous cases.
- Whether the run classifies and replays routing only, or also runs OCR for selected documents.
- The local runtime budget and timeout for any real OCR measurement.

These are explicit approval checkpoints, not decisions delegated to the implementer. Apply can prepare the safe runner and label format before approval; it must stop before scanning or selecting a candidate.

### 6. Freeze before scoring, and pin the baseline

Freeze the approved candidate and acceptance criteria in a separate commit before held-out measurement. Compare the committed historical policy, pinned at the original revision, with the approved candidate. Never use the current dirty working tree as an unnamed baseline. Retain negative results and separate exploratory changes from held-out evidence.

### 7. Report measured and projected quantities separately

Record actual classification duration. Label fixture-based OCR projections, including both sides of slowdown ratios, as estimates. If real OCR is authorised, measure timeout/failure behaviour and extraction outcomes. A classification-only run cannot establish OCR completion time or recovered-text quality.

Alternative rejected: rerunning the whole library with a different density threshold. That would repeat the population and labelling weaknesses.

## Risks / Trade-offs

- Selected documents limit generalisation → report the selection and annotation coverage; avoid population claims.
- The known book can bias candidate design → keep it in development and use a separate hold-out.
- Approval may remain pending across sessions → keep the decision register below and link each task to it.
- Private material can leak through public checkpoints → validate serialised outputs against a synthetic private path, not only the code that writes them.

## Decision register

Updated during apply to record the operator's approvals. Each approval must be recorded before the work it gates begins.

| Item | Status | Action before proceeding |
| ---- | ------ | ------------------------ |
| Selected PDF collection | Pending | Obtain the explicit list or selection rule, including the book |
| Independent page labels and hold-out | Pending | Agree coverage and reserve unseen outcomes |
| Missing-page tolerance | Pending | Agree how much missing text warrants whole-document OCR |
| Whole-document routing behaviour | Pending | Agree behaviour for documents above the tolerance |
| Enable-only zero-threshold behaviour | Pending | Agree `mixed` behaviour when only the enable switch is set |
| Real OCR measurement | Pending | Agree documents, runtime budget and timeout |
| OCR default promotion | Out of scope here | Any promotion requires this study's evidence plus a separate later decision |
