# ADR-065: OCR Fallback Gate Promoted to Packaged Default

**Date:** 2026-09-13
**Status:** Accepted (evidence: Experiment 29, all frozen gates PASS)
**Deciders:** Dr Muhammad Aizat Bin Md Hawari
**Change:** `promote-ocr-fallback-defaults`
**Supersedes:** items 1–2 of the settled decision in [ADR-064](064-input-quality-promotion-decisions.md)
**Related:** [ADR-062](062-isolate-paddleocr-vl-in-a-versioned-ocr-worker.md) (worker boundary), [ADR-050](050-configure-pdf-inspector-as-default-reader.md) (default reader)

## Context

ADR-064 kept `OCR_FALLBACK_ENABLED=false` and both routing thresholds at
the `0.0` never-trigger sentinels, deferring promotion to "a future
preregistered routing study on a fresh corpus". Experiment 29
(`experiments/29-pdf-routing-repeat-2026-09-13/`) is that study: an
operator-approved 17-PDF collection (3 dev + 14 held-out) replayed
through four policy arms against frozen gates.

The study passed every gate. The fixed policy wrongly routes zero of 14
held-out born-digital papers, still catches both genuinely-needy dev
documents (Kerr, scanned; Sloman, `text_based` at confidence 1.0
extracting zero characters), and keeps the 991-page book — which
Experiment 28's policy would have sent to a projected ~30.5 hours of
OCR — on the fast path.

Meanwhile the unpromoted default leaves Kerr-class scanned PDFs
ingesting as zero characters on fresh installations.

## Decision

1. **The packaged default is the validated gate, shipped whole.**
   `OCR_FALLBACK_ENABLED` defaults to `true`,
   `OCR_FALLBACK_MIN_CONFIDENCE` to `0.5`, and
   `OCR_FALLBACK_PAGE_FRACTION` to `0.10`, in both mirrored settings
   models (`config/` and `core/settings.py`). This supersedes ADR-064's
   settled items 1–2. Item 3 (`mixed` routes by the threshold gate, not
   unconditionally) stands unchanged — it is the fix Experiment 29
   validated.

2. **The flag and the thresholds ship together, in one commit.** The
   `enable_only` arm showed a bare enable at the `0.0` sentinels misses
   Sloman entirely — the hardest case in the collection. A packaged
   default of "enabled with sentinel thresholds" is strictly worse than
   disabled, so the defaults must move as a unit. Splitting the flip
   would leave an intermediate commit carrying exactly the
   configuration the study warns against.

3. **Worker-less installs degrade, they do not regress.** With
   `OCR_FALLBACK_ENABLED=true` and no worker provisioned
   (`OCR_WORKER_COMMAND` empty), an OCR-required PDF keeps its partial
   pdf-inspector extraction with degraded diagnostics, the batch
   continues, and the per-file warning names the provisioning step.
   No startup banner is added: "routing on, worker missing" is now the
   common fresh-install state, and the existing per-file warning already
   carries the actionable information (change design D4).

4. **No routing code changes.** The gate function, the seam, the
   unconditional-type set, and the capability probe are untouched. Only
   packaged values and the records that cite them move.

## Consequences

### Positive

- Scanned and image-based PDFs route to the worker by default on a
  provisioned install; Kerr-class documents no longer ingest as zero
  characters out of the box.
- The promoted pair is the exact configuration Experiment 29 measured —
  not an interpolation. The bare-enable hazard is foreclosed by shipping
  the thresholds with the flag.
- `.env.example` no longer advertises the superseded `0.5` page-fraction
  fraction alongside the approved `0.10`.

### Negative

- A fresh install now routes OCR-required PDFs toward a worker that may
  not exist. The deterministic degrade path bounds the cost: partial
  Markdown plus an actionable warning, identical to today's
  operator-enabled behaviour.
- Where a worker IS provisioned, OCR'd pages cost ~34–106 s each on CPU
  (Experiment 29 projected ~71 minutes for its two needy documents).
  The accepted alternative is zero-character ingestion.
- Routing configuration participates in source index identity (schema
  5), so existing collections re-ingest OCR-required sources once after
  upgrade. Correct by design; no migration.

### Neutral

- Experiment 29's held-out recall gate passed vacuously (0 needy of 14;
  Wilson upper bound ~21.5%). The promotion rests on the dev-set catches
  plus the safety gate, as the frozen rules required.
- Whether OCR actually recovers the text remains unmeasured by design —
  no real OCR run was authorised in the study.

## Alternatives Considered

- **Keep the fallback off (status quo).** Rejected: leaves the validated
  defect — scanned PDFs indexing as empty documents — as the packaged
  behaviour, against direct evidence that the gate now routes correctly.
- **Enable the flag only, thresholds later.** Rejected on the study's
  central finding: `enable_only` missed Sloman entirely while appearing
  to provide protection.
- **Edit ADR-064 in place.** Rejected per its own recovery-correction
  precedent: a settled record's history is not rewritten. This ADR
  supersedes items 1–2 and links back; ADR-064's evidence and its
  remaining items stand.

## References

- `experiments/29-pdf-routing-repeat-2026-09-13/report.md` — the
  promotion evidence and the bare-enable warning
- `experiments/28-pdf-classification-prevalence-2026-09-09/` — the
  failure that motivated the fix this promotion validates
- `openspec/changes/promote-ocr-fallback-defaults/` — proposal, design
  (D1–D5), and the modified `pdf-reader` spec delta
- `src/omrg/integrations/pdf/ocr_routing.py` — the unchanged gate
- `docs/guides/ingestion.md` — operator-facing routing documentation
