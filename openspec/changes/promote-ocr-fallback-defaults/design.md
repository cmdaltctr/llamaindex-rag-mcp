# Design: promote-ocr-fallback-defaults

## Context

ADR-064 (settled 2026-09-10) kept `ocr_fallback_enabled=false` and both
thresholds at `0.0`, deferring promotion to "a future preregistered
[study]". Experiment 29 is that study: operator-approved 17-PDF
collection, four policy arms, safety and dev-recall gates passed, with
the finding that the thresholds must accompany the flag. Defaults live
in two mirrored places (`config/__init__.py` settings model,
`core/settings.py` EffectiveSettings model) plus three env-var layers
(`.env.example`, configuration guide table, ADR record). The routing
code itself is untouched — this change moves only packaged values and
the records that cite them.

## Goals / Non-Goals

**Goals**

- Ship the validated gate as the packaged default, flag and thresholds
  together.
- Keep worker-less installations on the existing deterministic degrade
  path.

**Non-Goals**

- Any change to `ocr_routing.py`, the gate function, or the seam.
- Provisioning the OCR worker or measuring OCR recovery quality
  (Experiment 29 left that unmeasured by design).
- The reader-fallback guard for text_based-empty files — separate
  change `pdf-reader-extraction-fallback`.

## Decisions

**D1 — Flag and thresholds move in one commit.**
The `enable_only` arm of Experiment 29 showed a bare enable misses the
hardest case entirely. Splitting the flip across commits would create a
window where the packaged default is the bare-enable configuration, and
any test snapshot in between would bless the wrong values.

**D2 — The page fraction is 0.10, replacing the 0.5 shown in
`.env.example`.**
The 0.5 in the example predates Experiments 28/29; the approved
tolerance in the frozen, archived plan is 10% flagged pages at ≥0.5
confidence. Correcting the example is part of this change, not a
follow-up, so no user copies a superseded value.

**D3 — Supersede via a new ADR, not an edit to ADR-064.**
ADR-064 records a settled operator decision with its evidence intact; a
new ADR citing Experiment 29 supersedes its items 1–2 and links back.
This preserves the recovery-correction precedent ADR-064 itself set
(never rewrite a settled record's history).

**D4 — No startup warning when the worker is absent.**
Promoting the default makes "OCR routing on, worker missing" the common
fresh-install state. The existing per-file degrade warning (task 2.7)
already fires once per OCR-required file and names the provisioning
step; a redundant startup banner would add noise without new
information.

**D5 — Both default sites move together, tests follow.**
`config/__init__.py` and `core/settings.py` defaults must stay
identical; the settings-resolver test that asserts equality between the
layers is the guard. Default-value assertions in the routing-gate and
seam suites flip from `false/0.0/0.0` to `true/0.5/0.10`.

## Risks / Trade-offs

- **Fresh installs route to a worker that may not exist**: mitigated by
  the deterministic degrade path (partial Markdown + actionable
  warning); behaviour for worker-less users is unchanged except the
  warning appears on OCR-required files instead of silence.
- **CPU cost when a worker IS provisioned**: ~34–106 s per OCR'd page —
  the cost basis Experiment 29 projected at 71 minutes for the two
  needy dev documents. That is the accepted trade: zero-character
  ingestion of scanned PDFs is the alternative.
- **Re-ingestion churn**: routing config is in source index identity;
  existing collections re-ingest OCR-required sources once after
  upgrade. Correct by design (identity schema 5 already carries the
  routing set).
