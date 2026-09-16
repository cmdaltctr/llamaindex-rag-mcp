# ADR-068: Pin Magika Content Detection

**Date:** 2026-09-16
**Status:** Accepted (gate passed 2026-09-16)
**Deciders:** Dr Muhammad Aizat Bin Md Hawari
**Related:** [ADR-037](037-layered-modular-architecture.md), [TDR-025](../tdr/025-magika-content-type-detection-settings-injection.md)

## Context

Content detection controls early binary skipping, code routing, and part of
index identity. It must remain safe when detection is unavailable or a result
cannot be validated.

Historical references named `google-magika`. That package does not exist on
PyPI. The official PyPI base dependency is `magika==1.0.3`. The exact pin is
recorded in `pyproject.toml` and `uv.lock`. Package metadata confirmed version
1.0.3.

The package bundles a Rust CLI core that self-reports
`magika 1.1.0 standard_v3_3`. This identifies the core inside the 1.0.3 wheel.
It is provenance, not a separate dependency.

## Decision

1. Use the official base dependency `magika==1.0.3`. Keep the exact pin in
   `pyproject.toml` and `uv.lock`.
2. Keep one subprocess CLI transport. Inject `MAGIKA_BINARY` through settings,
   as specified by TDR-025 and ADR-037. Run
   `magika -r <path> --jsonl` with a 30-second timeout.
3. Accept only JSONL rows where `result.status == "ok"`. Read the detected
   label from `result.value.output`, never `dl`. Require non-empty string
   `group` and `label` fields plus a boolean `is_text` field. Ignore blank
   JSONL lines.
4. Raise `ValueError` for any invalid row. A failed status, malformed JSON,
   malformed envelope, or invalid required field fails the complete scan.
   The caller uses the existing warned suffix fallback. It does not fabricate
   `unknown/unknown` or return partial detection results.

5. Apply only the following boundary normalisation:
   - Set `group="binary"` only when `is_text is False` and the group is not
     `document`, `code`, or `text`. Preserve `label` and `is_text`.
   - Map `text/markdown` to `document/markdown`.
   - Map `text/txt` to `document/text`.

   Do not consult suffixes, edit `_SUFFIX_MAP`, backfill stored labels, or add
   other aliases.
6. Keep the detector optional at runtime. A missing binary, non-zero exit,
   timeout, or parser failure uses the existing warned suffix fallback.
7. Keep index identity unchanged only when the previous explicit label and all
   other inputs equal the normalised label. A previous `None` or `unknown`
   label can rebuild during a later explicit ingest. Do not backfill.

## Consequences

### Positive

- The base install uses verified ONNX Runtime inference. It does not add
  PyTorch, which respects the base-install prohibition.
- The CLI subprocess keeps model lifecycle outside the application process.
- A validated result controls content routing. A broken result fails closed to
  the existing suffix map.
- `scripts/magika_label_smoke.py` is detection-only. Static AST guards and
  isolated-process import blockers ban ingestion, store, embedder, and
  composition-root imports.

### Negative

- A substantial Python source behind a `.txt` name detects as `code/python`.
  It differs from the suffix map and exits 1 by design.
- A four-byte Python source (`x=1`) can lose its code label. Magika returns
  `text/txt`, which normalises to `document/text`, and the diagnostic exits 1.
- A four-byte text source matches `document/text`. The three probes are
  predesignated diagnostics. They are excluded from acceptance and are not
  repaired by suffix override, padding, retry, or threshold changes.

### Neutral

- `magika 1.1.0 standard_v3_3` identifies the bundled Rust core only.
- Existing suffix routing remains the runtime fallback path.

## Alternatives Considered

| Option | Rejected because |
| --- | --- |
| `google-magika` dependency | It does not exist on PyPI. The historical package name is superseded. |
| Python API transport | It removes the injected executable contract and introduces in-process object lifecycle. |
| Permissive or partial JSONL parsing | It could treat an invalid result as detection success. |
| Suffix-based correction or broad aliases | It would hide content evidence, alter taxonomy outside the verified boundary, or force identity churn. |

## Verification

- Package metadata, `pyproject.toml`, and `uv.lock` confirmed
  `magika==1.0.3`. Uninstall and reinstall evidence proved base-install tests
  fail, rather than skip, when the package is absent.
- The frozen acceptance corpus contains 16 files: 5 PDF, 4 Python, 4 Markdown,
  and 3 text files. The smoke command exited 0 with 16/16 all-match, zero
  mismatches, and identical path sets.
- The measured whole-run cost was 1.00 s for 16 explicit files, including 16
  CLI model startups. This is the whole invocation measurement.
- The smoke tool rejects detector errors, empty input, invalid records, and
  missing, extra, or duplicate paths. Its guards prevent forbidden imports.
- No collection, embedding, store, or ingest operation ran during the gate.
- Experiment 32 (`experiments/32-misnamed-extension-detection-2026-09-16/`,
  PASS 5/5 gates) scaled the misnamed-file evidence to corpus size: all 19
  Experiment 31 PDFs renamed to `.py`/`.md`/`.txt` still detected as
  `document/pdf`, and all 11 text or code files renamed to `.pdf` kept their
  content-true labels. Detection-only; no ingest ran.

## References

- `openspec/changes/pin-magika-detection/proposal.md`
- `openspec/changes/pin-magika-detection/design.md`
- `openspec/changes/pin-magika-detection/acceptance-corpus.md`
- `experiments/32-misnamed-extension-detection-2026-09-16/report.md`
- [TDR-025](../tdr/025-magika-content-type-detection-settings-injection.md)
- `src/omrg/integrations/magika.py`
- `scripts/magika_label_smoke.py`
