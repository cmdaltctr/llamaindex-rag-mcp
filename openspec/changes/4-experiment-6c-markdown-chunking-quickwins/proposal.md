## Why

Experiment 6b (`experiments/6b-qasper-markdown-chunking-2026-05-28/`) recorded a real negative result for the heading-aware Markdown chunker (`MarkdownNodeParser → SentenceSplitter`) shipped under change `2-rag-retrieval-quality-improvements`. On Qasper-dev (20 NLP papers, 53 evidence-bearing QA records), Pass A (reranker off) lost −5.66 pp on Evidence Recall@5 and Pass B (reranker on) recovered most but stayed at −1.89 pp. The candidate consistently retrieves the right paper (+5.66 pp / +1.89 pp on source Hit@1) but the wrong section.

A multi-source follow-up investigation (per-query drill of Pass A's `eval_results.passA.json`, deep code read of `rag_mcp/ingestion.py`, LlamaIndex source review via DeepWiki, literature scan covering Zhou et al. 2026, Bhat et al. 2025, Lu et al. 2025, Prior et al. 2026, de Moura Júnior et al. 2026) ranked the failure modes:

1. **Dominant**: chunk fragmentation at fixed `top_k`. Chunk count rose 49% (284 → 424); mean tokens fell 41% (499 → 296). The reranker's wider candidate pool (Pass B fetches 50 candidates) already recovers ~67% of the loss without any chunker change, which proves the gold chunks exist in the index at ranks 6–15.
2. **Contributing**: smaller chunks lose embedder context for multi-keyword queries.
3. **Contributing-smaller**: short orienting `## Introduction`-style chunks displace evidence chunks at low ranks.
4. **Refuted**: the original "metadata propagation bug" hypothesis. LlamaIndex's `_postprocess_parsed_nodes` propagates `header_path` correctly through both merge paths; the 82.8% → 76.6% heading-coverage drop is a regex-on-text measurement artefact, not a structural bug.

The four interventions that the literature and the per-query drill agree on are independently cheap (under 30 LOC each, or one config flag). Experiment 6c tests them. Two larger interventions (`HierarchicalNodeParser` + `AutoMergingRetriever`, contextual retrieval via local Ollama `qwen3:0.6b`) are deliberately deferred to a future OpenSpec change pending 6c's outcome — both require cross-module changes that are disproportionate effort if the cheap fixes carry us.

## What Changes

This change is **scoped to Experiment 6c**. It does not change production defaults; the Markdown chunker continues to ship at `chunk_size=512` with no heading prepend and no min-size floor until 6c results justify a default change. The change adds an experiment scaffold and four small ingestion-side knobs that 6c's run matrix exercises.

- Add experiment scaffold under `experiments/6c-markdown-chunking-quickwins-2026-05-28/` (already in place: `protocol.md`, `README.md`).
- Add `MARKDOWN_CHUNK_SIZE` env var that overrides `CHUNK_SIZE` for the Markdown branch only. Defaults to `CHUNK_SIZE` for backward compatibility.
- Add `MARKDOWN_HEADING_PREPEND` boolean env var. When true, prepends `[heading_path] ` to each Markdown chunk's text before embedding. Default false.
- Add `MARKDOWN_MIN_CHUNK_FRACTION` float env var (default `0.0` = disabled). When >0, drops Markdown chunks shorter than `MARKDOWN_CHUNK_SIZE * fraction` chars-equivalent. Recommended 6c value: `0.5`.
- Add a defensive `_ensure_heading_metadata(nodes)` pass after `_split_sync()` that runs `node.metadata.setdefault("header_path", node.source_node.metadata.get("header_path", ""))`. No-op when `header_path` is already set; closes a `tests/test_markdown_chunking.py` coverage gap.
- Add `run_eval.py --top-k INT` and `--candidate-dir PATH` flags to the 6c evaluator.
- Add `ingest_candidate.py` to 6c, parameterised on `--chunk-size`, `--heading-prepend`, `--min-size-floor`, `--metadata-copy`, `--out-dir`. Forked from 6b's `ingest_both.py`.
- Document the 6b → 6c diagnosis trail in `experiments/6b-qasper-markdown-chunking-2026-05-28/results.md` (already updated) and add citations to the diagnosis-supporting literature.
- After 6c runs, write `experiments/6c-markdown-chunking-quickwins-2026-05-28/results.md` with the per-phase tables and a single production recommendation.

## Capabilities

### Modified Capabilities

- `markdown-aware-chunking`: gains four optional knobs (`MARKDOWN_CHUNK_SIZE`, `MARKDOWN_HEADING_PREPEND`, `MARKDOWN_MIN_CHUNK_FRACTION`, defensive `_ensure_heading_metadata`). All default to "no behaviour change" so production stays identical until 6c's outcome promotes one or more knobs to a new default.

### New Capabilities

None. This change is additive to `markdown-aware-chunking` only.

## Impact

- `src/rag_mcp/ingestion.py`: extend the `is_markdown` branch in `_read_and_chunk_file_async` to read the new env vars and call the optional heading-prepend / min-size-floor / metadata-copy hooks.
- `src/rag_mcp/config.py`: three new constants (`MARKDOWN_CHUNK_SIZE`, `MARKDOWN_HEADING_PREPEND`, `MARKDOWN_MIN_CHUNK_FRACTION`) with safe defaults.
- `experiments/6c-markdown-chunking-quickwins-2026-05-28/`: new experiment scaffold with `protocol.md`, `README.md`, `ingest_candidate.py`, `run_eval.py`, and (after run) `results.md`.
- `experiments/6b-qasper-markdown-chunking-2026-05-28/results.md`: diagnosis section rewritten and references extended (already done as part of this change).
- `tests/test_markdown_chunking.py`: add assertions on `header_path` for multi-chunk Markdown sections, plus tests for each new knob (heading-prepend on/off, min-size-floor on/off, defensive metadata copy idempotence).
- `.env.example`: document the three new env vars and their experimental status.
- `AGENTS.md`: add a one-line note in the Markdown chunking section pointing at 6c's open status.

The chunked-write protocol is preserved: no production default is changed by this OpenSpec change. Defaults move only after 6c writes its `results.md` and a follow-up `5-experiment-6c-promote-defaults` change reads the recommendation.
