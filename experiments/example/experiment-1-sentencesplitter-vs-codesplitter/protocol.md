# Experiment 1 — SentenceSplitter vs CodeSplitter execution and structural integrity

**Template ID:** `example/experiment-1-sentencesplitter-vs-codesplitter`  
**Status:** PLANNED  
**Role:** correctness gate before code-retrieval calibration

## 1. Research question

After repairing the CodeSplitter adapter, does the production code path genuinely execute AST-aware LlamaIndex CodeSplitter, and does it preserve code structure more reliably than the SentenceSplitter fallback on small controlled source fixtures?

This experiment is primarily a **component correctness experiment**, not a claim that CodeSplitter improves end-to-end retrieval on every codebase.

## 2. Pre-registered hypotheses

- **H1 — execution:** every CodeSplitter treatment fixture reports `requested=code`, `effective=code`, no fallback, and the expected AST parser language.
- **H2 — structural integrity:** CodeSplitter yields fewer chunks that cut through a top-level function/class syntactic unit than SentenceSplitter.
- **H3 — boundedness:** every CodeSplitter chunk respects the configured `code_max_chars` contract or the documented upstream exception semantics.
- **H4 — retrieval sanity (secondary/optional):** on a tiny labelled identifier query set, CodeSplitter is non-inferior to SentenceSplitter for Hit@5, with a pre-registered non-inferiority margin of 5 percentage points. This secondary arm is not required to establish H1-H3.

## 3. Experimental unit

Primary unit: one source file fixture.  
Secondary retrieval unit: one labelled query against the frozen fixture corpus.

Use at least:

- 10 Python files;
- 5 JavaScript/TypeScript or another brace-based supported language;
- functions/classes deliberately sized near splitter boundaries;
- nested functions/classes and long function bodies;
- comments/docstrings and adjacent small definitions.

Fixtures should be synthetic or licence-safe repository fixtures committed with the experiment.

## 4. Manipulated / independent variable

`chunker` with two levels:

1. `sentence` — force the SentenceSplitter fallback/control using the same source text;
2. `code` — production CodeSplitter configured with explicit code-specific units.

No other pipeline factor changes between cells.

## 5. Controlled variables

- exact source bytes;
- detected language supplied to the splitter;
- CodeSplitter line/character settings across all `code` repetitions;
- SentenceSplitter token settings across all `sentence` repetitions;
- metadata attachment logic;
- Python/LlamaIndex/tree-sitter versions;
- no LLM metadata extraction for the structural arm;
- no vector store for the structural arm;
- if retrieval sanity is run: same embed model/provider, store backend, index settings, query set, top_k, no reranker, no hybrid.

## 6. Blocking / stratification variables

Report results by:

- language;
- fixture complexity (`simple`, `nested`, `long-body`);
- source length bucket.

The same files appear in both chunker treatments.

## 7. Dependent variables

### Primary correctness measures

- `effective_strategy_matches_requested` — boolean;
- `fallback_count` — must be zero in CodeSplitter treatment;
- `structural_cut_rate` — fraction of emitted chunk boundaries falling inside a labelled top-level function/class span;
- `whole_definition_coverage` — fraction of labelled definitions whose complete source appears in at least one chunk when size permits;
- `max_chars_violation_count`;
- chunk count and chunk-size distribution as diagnostics.

### Optional retrieval measures

- Hit@1/5;
- MRR@5;
- relevant-definition coverage@5.

## 8. Cell matrix

| Cell | Chunker | Files | Purpose |
|---|---|---|---|
| S | SentenceSplitter | all fixtures | control/fallback behaviour |
| C | CodeSplitter | same fixtures | AST-aware treatment |

Run structural analysis deterministically once per cell; no stochastic repetition is needed. If retrieval is added, query every labelled query against both indexes.

## 9. Corpus / labels

Before running, commit a fixture manifest containing for every source file:

- SHA-256;
- language;
- labelled top-level definition start/end byte or line spans;
- definitions expected to fit under `code_max_chars`;
- optional identifier queries and relevant definition IDs.

Labels must be written before inspecting treatment output.

## 10. Randomisation / counterbalancing

Not needed for deterministic structural output. If retrieval timing is measured, alternate/counterbalance S/C query order and warm both indexes before measurement.

## 11. Repetitions and warm-up

Structural: one deterministic execution per cell is sufficient; rerun only to verify exact reproducibility.  
Optional retrieval latency: one warm-up pass then >=3 measured repetitions per query/cell.

## 12. Preflight assertions

Before scoring:

- locked LlamaIndex CodeSplitter signature contains the fields expected by the repaired adapter;
- `code` cell diagnostics show CodeSplitter actually instantiated;
- no fallback occurred in `code` cell;
- both cells received byte-identical source files;
- chunk settings have explicit units in the runtime manifest.

## 13. Abort / invalid-cell criteria

Mark `INVALID` and stop if:

- CodeSplitter treatment falls back to SentenceSplitter;
- an unsupported/misdetected language reaches the treatment unknowingly;
- treatment and control receive different source bytes;
- structural labels were edited after inspecting treatment output.

## 14. Success gates

- H1: **100%** of supported CodeSplitter fixtures run `effective=code` with zero fallback.
- H2: `structural_cut_rate(code) < structural_cut_rate(sentence)` and ideally zero for definitions that fit within the configured ceiling.
- H3: zero unexplained character-ceiling violations.
- H4 optional: `Hit@5(code) - Hit@5(sentence) >= -0.05`.

A failure of H2 does not prove SentenceSplitter is globally better; inspect fixture/CodeSplitter semantics. A failure of H1/H3 is a correctness blocker.

## 15. Analysis plan

Use paired per-file differences for structural metrics. Report raw boundary locations for every violation. Do not collapse languages into one mean without also reporting strata.

Optional retrieval results are paired by query; report exact query-level outcomes and a paired bootstrap CI if query count is sufficient.

## 16. Threats to validity

- synthetic fixtures may not represent large real repositories;
- AST splitting can legitimately split a definition exceeding the size ceiling;
- different languages have different tree-sitter grammars;
- retrieval quality can be dominated by embedding/model choice, hence it is secondary here.

## 17. Reproduction command placeholder

```bash
uv run python experiments/<promoted-dir>/run_eval.py --structural
# optional
uv run python experiments/<promoted-dir>/run_eval.py --retrieval
```

## 18. Required raw artefacts

- fixture manifest + labels;
- per-file emitted chunk spans/text hashes for both cells;
- runtime manifest;
- structural metrics JSON;
- optional per-query retrieval rows;
- `results.md` with every H1-H4 gate.

## 19. Interpretation rules

- H1/H3 fail -> fix implementation; do not calibrate code retrieval.
- H1/H3 pass, H2 pass -> AST splitter behaves as intended; proceed.
- H1/H3 pass, H2 inconclusive -> expand structural fixtures before making quality claims.
- Optional H4 fail -> keep component correctness result but open a separate retrieval-quality investigation before changing code-profile defaults.

## 20. Cleanup

No large corpus is required. Delete only generated indexes/output caches; keep fixture labels and raw result JSON.
