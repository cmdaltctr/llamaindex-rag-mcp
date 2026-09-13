# Proposal: promote-ocr-fallback-defaults

## Why

Experiment 29 (`29-pdf-routing-repeat-2026-09-13`, PASS) validated the
committed OCR routing fix on an operator-approved 17-PDF collection:
zero false routes across 14 held-out papers, both needy documents still
caught, and the 991-page book that Experiment 28 would have sent to ~30
hours of OCR stays on the fast path. ADR-064 deferred promotion pending
exactly this study; the promotion gates are now met. Meanwhile the
packaged default (flag `false`, thresholds `0.0`) leaves Kerr-class
scanned PDFs ingesting as zero characters.

## What Changes

- Flip the packaged default `ocr_fallback_enabled` from `false` to
  `true` in `config/` and the mirrored `EffectiveSettings` model in
  `core/settings.py`.
- Set the packaged thresholds to the Experiment 29 approved pair:
  `ocr_fallback_min_confidence=0.5`,
  `ocr_fallback_page_fraction=0.10`. The report's condition: the
  thresholds ship with the flag — a bare enable silently misses the
  hardest case (Sloman) at the `0.0` sentinels.
- Correct `.env.example` (currently shows `PAGE_FRACTION=0.5`,
  superseded by the approved 0.10) and the configuration guide's
  default-value table.
- New ADR superseding ADR-064's settled items 1–2, citing Experiment 29
  as the promotion evidence.
- Baseline spec fix (done with this proposal, per AGENTS.md gotcha #12):
  the `pdf-reader` requirement's "Packaged default keeps the fallback
  off" scenario expired by its own sunset clause ("until the promotion
  gates are met") — the baseline now carries the promoted-default
  scenarios instead, so the MODIFIED delta validates without carrying a
  false scenario name.

## Capabilities

### New Capabilities

(none)

### Modified Capabilities

- `pdf-reader`: modifies the requirement "The OCR routing gate SHALL be
  calibrated evidence expressed as injected configuration" — the
  packaged-default clause and its "Packaged default keeps the fallback
  off" scenario change to the promoted defaults now that the promotion
  gates are met.

## Impact

- **Code**: `src/omrg/config/__init__.py` (3 defaults),
  `src/omrg/core/settings.py` (3 mirrored defaults).
- **Behaviour**: fresh installations route OCR-required PDFs to the
  worker by default. With no worker provisioned, files degrade
  deterministically to the existing task-2.7 path (partial Markdown,
  actionable warning) — no crash, no regression for worker-less users.
- **Tests**: default-value assertions in the settings/config suites;
  seam tests that assumed `false` defaults.
- **Docs**: `.env.example`, `docs/guides/configuration.md`,
  `docs/guides/reranker.md` untouched; new ADR in `docs/adr/`.
- **Index identity**: routing configuration is already part of source
  index identity — prior ingests re-ingest on the changed defaults by
  design; no migration.
