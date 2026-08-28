# TDR-010: Separate code chunking units and make metadata budget node-exact

**Date:** 2026-08-18
**Status:** Accepted — Stage 1 validation gate passed 2026-08-18
**Deciders:** Dr Muhammad Aizat Md Hawari with AI agent
**Tags:** chunking | llamaindex | metadata | correctness | pre-calibration

## Context

The pre-calibration audit found two deterministic correctness problems that do
not require a retrieval-quality experiment to resolve.

First, the production code passed the generic document settings
`chunk_size`/`chunk_overlap` to LlamaIndex `CodeSplitter`.  In the supported
LlamaIndex 0.14.x API, `SentenceSplitter` uses tokenizer-oriented
`chunk_size`/`chunk_overlap`, while `CodeSplitter` uses `chunk_lines`,
`chunk_lines_overlap`, and `max_chars`.  The constructor error was caught by
the broad fallback handler, so code ingestion could silently become sentence
chunking while tests merely asserted that some nodes were returned.

Second, `LLAMANDEX_EXTRACTOR_MAX_CHUNKS` was implemented as:

```python
text[: max_chunks * chunk_size]
```

That mixed a token-oriented chunk size with Python character slicing.  A
setting named "max chunks" therefore did not bound the actual number of split
nodes sent to LLM-backed metadata extractors.

This TDR records the implementation choices for Stage 1 of
`harden-pipeline-correctness-before-calibration`.  It does not claim Stage 1
has passed until the pause-gate tests are run.

## Decision 1 — Separate sentence and code unit vocabularies

Keep the existing generic document settings:

- `chunk_size` — SentenceSplitter tokenizer units;
- `chunk_overlap` — SentenceSplitter tokenizer units;
- `markdown_chunk_size` — Markdown SentenceSplitter tokenizer units.

Add code-specific settings with the upstream-compatible vocabulary:

- `code_chunk_lines` — default `40` lines;
- `code_chunk_lines_overlap` — default `15` lines;
- `code_max_chars` — default `1500` characters.

`chunk_code_file_async()` constructs `CodeSplitter` only with those
code-specific values.  The generic token settings remain available to the
SentenceSplitter fallback and are not reinterpreted as lines or characters.

### Why not reuse the old two integers?

Reusing the same numeric values under different physical units makes the
configuration look swappable while silently changing semantics.  Explicit
settings are slightly more verbose but make invalid unit conversion difficult
to express.

## Decision 2 — Make code fallback observable

Production keeps graceful fallback from AST-aware CodeSplitter to
SentenceSplitter for unsupported/malformed code, but the returned list-like
result records:

- `chunk_strategy_requested = "code"`;
- `chunk_strategy_effective = "code" | "sentence"`;
- `fallback_reason` when fallback occurs.

Warnings also name requested/effective strategy and the reason.  Tests for the
success path must assert `effective == code`; fallback tests must assert the
fallback explicitly.  `len(nodes) > 0` alone is not a valid CodeSplitter test.

The diagnostics are list attributes rather than persisted node metadata so
internal execution state does not leak into the vector-store metadata schema.

## Decision 3 — Cap metadata extraction after splitting

Interpret `LLAMANDEX_EXTRACTOR_MAX_CHUNKS=N` literally:

1. create a `Document` from the full input text;
2. split it using the same configured `SentenceSplitter` contract;
3. take the first `N` split nodes;
4. run `TitleExtractor`, `KeywordExtractor`, and `SummaryExtractor` only on
   those bounded nodes.

This uses the real chunker as the unit of work and avoids a second token-count
approximation.

The current persistence model remains file-level metadata: temporary
per-node extractor outputs are aggregated to one file-level dict, which the
ingestion chunker copies to final stored chunks.  Changing to true persisted
per-chunk LLM metadata would require a separate design and experiment.

## Decision 4 — Keep Markdown helper behaviour identical across entry points

The standalone `chunk_sentence_file_async()` helper must forward
`markdown_heading_prepend` and `markdown_min_chunk_fraction` exactly as the
main ingestion path does.  A chunking strategy cannot have different
behaviour merely because a different internal entry point invoked it.

## Evidence and validation

Implementation branch:
`harden-pipeline-correctness-before-calibration`

Relevant deterministic tests added during Stage 0/1:

- `tests/test_precalibration_audit_regressions.py`;
- `tests/test_chunking_hardening.py`;
- `tests/test_metadata_cap_hardening.py`.

External API verification used during implementation:

- LlamaIndex 0.14.x CodeSplitter API (`chunk_lines`,
  `chunk_lines_overlap`, `max_chars`);
- LlamaIndex IngestionPipeline support for running transformations on
  pre-existing `nodes`.

**Validation record (2026-08-18, local worktree):**

- targeted Stage 1 tests — 21 passed
  (`test_chunking_hardening.py`, `test_metadata_cap_hardening.py`,
  `test_experiment_plan_contract.py`, `tests/unit/test_type_aware_ingestion.py`);
- `ruff check` / `ruff format --check` clean for touched files
  (one import-sort and three format drifts fixed during the gate);
- manual structural-fixture inspection through `read_and_chunk_file_async`
  with default settings: 148-line Python fixture split into 3 chunks at
  `def function_0/6/12` boundaries; 163-line JavaScript fixture split into
  3 chunks at `function handler0/5/10` boundaries; every chunk under
  `code_max_chars=1500`; `chunk_strategy_effective == "code"` and
  `fallback_reason is None` throughout;
- full fast suite: 1575 passed, 17 skipped; the only 8 failures are the
  intentionally red Stage 2/4 audit regressions;
- `openspec validate --all --strict`: 38 passed, 0 failed.

Implementation commits surviving those checks: `7a3840d`, `4bdc8bc`,
`d38dbb5`, `9736d01`, `9191d60`, `18b8f77`, `d8fca13`, `95046fc`, plus the
Stage 1 test/docs commits `40b5451`, `a39fbf0`, `40ecb04`, `adf67ff`,
`b8b6359`.

## Consequences

### Positive

- AST-aware code chunking can no longer silently fail because sentence-token
  arguments were passed to a line/character API.
- Code and document chunking configuration now states its physical units.
- Metadata LLM cost is bounded by actual split-node count.
- Silent code fallback is visible to callers/tests without polluting stored
  metadata.
- Markdown helper and main ingestion behaviour become consistent.

### Negative

- Three additional chunking settings become part of the configuration
  surface.
- Existing operators who expected `CHUNKING__CHUNK_SIZE` to tune code AST
  chunks must use the new code-specific settings instead; the generic values
  now tune only the sentence fallback for code.

### Follow-up

If Stage 1 validation reveals that the new code settings need a broader public
compatibility/migration policy, this technical decision should be promoted to
or cross-referenced from the appropriate ADR before v3 release.
