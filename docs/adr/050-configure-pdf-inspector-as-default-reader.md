# ADR-050: Configure pdf-inspector as the Default PDF Reader

**Date:** 2026-08-24
**Status:** Accepted
**Deciders:** Dr Muhammad Aizat Bin Md Hawari

## Context

ADR-020 introduced a pluggable PDF-reader factory and selected LiteParse as
the preferred reader through the packaged `PDF_READER=auto` setting. The
reader registry now includes pdf-inspector as a lazy adapter, but the packaged
configuration still resolves to LiteParse.

Experiment 14 evaluated pypdf, LiteParse, and pdf-inspector on 35 frozen
Qasper PDFs. All readers completed without parser errors. pdf-inspector had
the shortest approved ingestion run at 346.7 seconds and the highest reranked
Hit@5 score at 0.6250. It emitted one document per PDF, while pypdf and
LiteParse emitted per-page documents; downstream markdown chunking preserved
retrieval quality. The experiment used pdf-inspector 1.17.0.

The RAG architecture requires configuration to select strategies. A reader
promotion must not add a reader-specific priority rule to runtime code.

## Decision

Set the packaged `PDF_READER` value to `pdf_inspector` in `config/`. Keep
`PDF_READER` as the operator override for `auto`, `liteparse`, `pypdfium2`,
and `pypdf`.

Promote the existing pdf-inspector package to the base dependency set. This
makes the packaged default available after a normal `uv sync`.

Resolve configured concrete readers through registry metadata. Keep `auto` as
its existing capability-resolution policy. Do not add pdf-inspector to the
hard-coded `auto` preference sequence.

## Consequences

### Positive

- The base installation uses the Experiment 14 winner by default.
- Operators change readers through configuration without source changes.
- The registry remains the sole dispatch mechanism for reader adapters.

### Negative

- The base installation includes an additional native wheel.
- Version 1.17.0 was three days old on the decision date, so its audit history is limited.
- pdf-inspector emits whole-document markdown, which changes source-document
  boundaries before normal markdown chunking.

### Neutral

- `auto` keeps its existing LiteParse-first fallback policy.
- Existing explicit reader selections keep their meaning.

## Alternatives Considered

| Option | Rejected Because |
| --- | --- |
| Keep LiteParse as the packaged default | Experiment 14 favoured pdf-inspector on timing and reranked Hit@5. |
| Put pdf-inspector first in `auto` | It embeds a default-selection policy in runtime code instead of configuration. |
| Keep pdf-inspector optional | A normal base installation would not use the configured default. |
| Restore pypdf as the packaged default | It was the slowest Experiment 14 reader and had lower reranked Hit@5. |

## References

- Experiment 14: `experiments/14-liteparse-qasper-promotion-2026-06-29/`
- Results: `experiments/14-liteparse-qasper-promotion-2026-06-29/output/results.md`
- Dependency lock: `uv.lock` (`pdf-inspector` 1.17.0)
- ADR-020: `docs/adr/020-use-liteparse-as-pdf-reader.md`
- PDF-reader contract: `openspec/specs/pdf-reader/spec.md`
- OpenSpec change: `openspec/changes/archive/2026-08-24-promote-pdf-inspector-default-reader/`
