# ADR-062: Isolate PaddleOCR-VL in a Versioned OCR Worker

**Date:** 2026-09-07
**Status:** Proposed
**Deciders:** Dr Muhammad Aizat Bin Md Hawari

## Context

OMRG must extract usable text from scanned or structurally degraded PDFs.
PaddleOCR-VL can perform this work, but PaddleOCR, PaddlePaddle, and PaddleX
are large native dependencies. Adding them to the main OMRG environment would
expand every installation, weaken dependency isolation, and make the normal
PDF path more expensive.

The normal reader must remain cheap. Clean PDFs should use pdf-inspector,
which extracts text without starting a document vision model. OCR should run
only when routing identifies an OCR-required PDF.

OCR output can change when the protocol, model, pipeline, output schema, or
any Paddle package changes. Reusing prior indexed chunks after such a change
would mix incompatible representations of the same source.

## Decision

1. Keep PaddleOCR, PaddlePaddle, and PaddleX outside OMRG's main
   environment, lockfile, dependency graph, and import graph.

2. Run OCR in `ocr-worker/`. The worker owns its `pyproject.toml`, `uv.lock`,
   virtual environment, and provisioning command.

3. Communicate with the worker through UTF-8 JSON Lines protocol 1.0. Requests
   and terminal responses carry a correlated request identifier. Standard
   output contains protocol messages only. Standard error contains diagnostics.

4. Include the exact PaddleOCR, PaddlePaddle, and PaddleX versions in the
   worker capability fingerprint. Include the protocol, model, pipeline, and
   output-schema identities. A changed resolved worker fingerprint changes the
   source index identity and requires re-ingestion.

5. Force Paddle cache paths into `ocr-worker/.model-cache` before Paddle
   imports or initialisation. The smoke runner must also pin uv project and
   environment selectors to worker-owned paths.

6. Construct the PaddleOCR-VL document pipeline once per worker process. Reuse
   it for later OCR-required files handled by that process.

7. Keep clean PDFs on the pdf-inspector path. Route only OCR-required PDFs to
   the worker. Before dispatch, an unavailable worker preserves partial
   pdf-inspector Markdown with degraded diagnostics. After dispatch, worker
   failures become structured per-file ingestion errors and preserve any prior
   indexed version.

8. Treat the Python 3.11, 3.12, and 3.13 provisioned smoke results as local
   Apple Silicon CPU evidence. They do not claim official Paddle hardware
   support or promote an OCR routing default.

## Consequences

### Positive

- Main OMRG installations remain free of Paddle dependencies.
- Clean PDFs avoid vision-model startup and remain on pdf-inspector.
- Versioned protocol and fingerprint data make OCR representation changes
  visible to re-ingestion logic.
- Worker failures retain per-file attribution instead of failing a batch.

### Negative

- The worker has a separate virtual environment, lockfile, model cache, and
  local disk cost.
- Worker lifecycle, protocol, and cache boundaries require dedicated tests.
- A fingerprint change reprocesses affected sources, including byte-identical
  sources.

### Neutral

- OCR routing policy remains configurable. This Proposed ADR does not claim a
  calibrated routing threshold or a retrieval-quality promotion.
- The next Stage 3 decision record uses ADR-063. OCR received ADR-062 because
  its implementation and evidence were completed first.

## Alternatives Considered

| Option | Rejected Because |
| --- | --- |
| Add Paddle packages to OMRG's main environment | Every installation would carry large native dependencies and a new import boundary risk. |
| Send all PDFs to PaddleOCR-VL | Clean PDFs would lose the cheap pdf-inspector fast path. |
| Use an unversioned subprocess protocol | OMRG could not safely identify incompatible worker output. |
| Create a pipeline for every document | Model initialisation would repeat for each OCR-required file. |

## Validation and Integration Notes

Provisioned smoke tests passed locally on Apple Silicon for Python 3.11,
3.12, and 3.13. Each run used the worker lockfile, loaded models from
`ocr-worker/.model-cache`, and returned the complete worker fingerprint.
The evidence is recorded in `ocr-worker/SMOKE_RESULTS.md`.

The final fast-suite run reported 2,739 passed, 8 failed, and 123 skipped.
The failures were present before the OCR review fixes and are existing branch
debt. They include stale retrieval test doubles, integration inventory drift,
a stale PDF-reader patch target, and the dependent clean-base manifest check.
This ADR does not change or disposition those failures.

## References

- `ocr-worker/pyproject.toml`, `ocr-worker/uv.lock`, and `ocr-worker/provision.py`
- `ocr-worker/src/omrg_ocr_worker/protocol.py`
- `ocr-worker/src/omrg_ocr_worker/capabilities.py`
- `ocr-worker/src/omrg_ocr_worker/worker.py`
- `src/omrg/integrations/ocr_worker/`
- `src/omrg/integrations/pdf/ocr_routing.py`
- `ocr-worker/SMOKE_RESULTS.md`
- `openspec/changes/improve-rag-input-quality-5/design.md`
- `openspec/changes/improve-rag-input-quality-5/tasks.md`
- ADR-048: `docs/adr/048-bounded-failure-safe-ingestion.md`
- ADR-050: `docs/adr/050-configure-pdf-inspector-as-default-reader.md`