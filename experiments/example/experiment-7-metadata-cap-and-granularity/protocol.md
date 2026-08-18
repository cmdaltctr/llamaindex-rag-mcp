# Experiment 7 — Metadata extraction cap and persisted granularity

**Template ID:** `example/experiment-7-metadata-cap-and-granularity`  
**Status:** PLANNED  
**Role:** correctness gate for metadata workload units and stored metadata semantics

## 1. Research question

Does the LlamaIndex metadata path enforce `LLAMANDEX_EXTRACTOR_MAX_CHUNKS` in actual chunk units rather than accidental character units, and is the persisted metadata granularity correctly understood as file-level aggregation copied to final chunks?

## 2. Pre-registered hypotheses

- **H1 — cap unit:** with `max_chunks=N`, no more than N actual SentenceSplitter chunks enter the expensive Title/Keyword/Summary extractor pipeline.
- **H2 — prefix coverage:** the N selected chunks are exactly the first N chunks from the declared metadata splitting policy, not an arbitrary `N * chunk_size` character prefix.
- **H3 — file-level persisted semantics:** temporary extractor-node metadata may differ by chunk, but final stored chunks receive the declared aggregated file-level metadata consistently.
- **H4 — no accidental per-chunk claim:** runtime/docs/manifest identify the persisted granularity as `file_aggregate` unless a future design explicitly changes it.
- **H5 — bounded cost:** LLM extractor call count scales with capped chunk count rather than full-document length beyond the cap.

## 3. Experimental unit

One synthetic long document with labelled sections designed so character length and token count diverge strongly (short tokens, long tokens, whitespace/punctuation, Unicode if supported). Add a second realistic Markdown/article fixture.

Use a deterministic fake LLM/extractor for the primary correctness experiment; optional real LLM cost/timing is secondary.

## 4. Manipulated / independent variables

Factor A — `max_chunks`: e.g. `{1, 3, 10}`.  
Factor B — document shape: `{synthetic_token_char_divergence, realistic_long_document}`.

Optional diagnostic control cell: legacy character-slice implementation on the baseline commit, used only to demonstrate the bug and not as a quality treatment.

## 5. Controlled variables

- same SentenceSplitter token chunk size/overlap;
- same source bytes within each document block;
- same metadata extraction mode;
- same fake LLM/extractor outputs and call accounting;
- same final ingestion chunker settings;
- no changes to embedding/vector store for primary metadata semantics;
- same dependency lock/tokenizer.

## 6. Blocking / stratification variables

Document shape is a block. Compare max_chunks levels within each document.

## 7. Dependent variables

- number of temporary metadata chunks entering extractors;
- IDs/text hashes of those chunks;
- token count and character count of selected text;
- extractor/LLM call count;
- aggregated metadata dict;
- final chunk count;
- per-final-chunk stored metadata equality/variation;
- runtime `metadata_granularity` diagnostic;
- optional wall time/token/cost estimate.

## 8. Cell matrix

For each document shape:

| Cell | max_chunks | Expected metadata input chunks |
|---|---:|---:|
| M1 | 1 | 1 |
| M3 | 3 | min(3, total chunks) |
| M10 | 10 | min(10, total chunks) |

Run with a deterministic fake extractor first. Optional real LLM reruns use the same selected chunk IDs and are not required for correctness PASS.

## 9. Ground truth

Before execution, run the declared SentenceSplitter alone and commit/derive expected chunk hashes for the fixture. The expected metadata input for N is the first N hashes according to the protocol.

For aggregation, configure the fake extractor so temporary chunks emit intentionally different titles/keywords/summaries. Pre-register the expected aggregator output according to current selection rules.

## 10. Randomisation / counterbalancing

None for deterministic fake-extractor correctness. Optional real LLM timing should rotate max_chunks order or use fresh calls to reduce cache/order effects.

## 11. Repetitions and warm-up

Deterministic: one + exact rerun.  
Optional real LLM: >=3 repetitions only if making latency/cost claims; otherwise one smoke run is descriptive.

## 12. Preflight assertions

- document produces more than max tested N chunks;
- fixture shows a material token-vs-character divergence;
- fake extractor call counter is active;
- effective chunk_size/overlap and tokenizer identity are recorded;
- final metadata granularity is declared before run.

## 13. Abort / invalid-cell criteria

- fixture unexpectedly produces <=1 chunk;
- a real LLM is accidentally used in deterministic cells;
- chunk settings change between max_chunks cells;
- expected chunk hashes were generated after inspecting metadata treatment output in a way that changes labels.

## 14. Success gates

- H1/H2: exact selected chunk-count/hash equality for every N.
- H3: final persisted metadata matches the pre-registered aggregation rule across final chunks.
- H4: diagnostics/docs identify `file_aggregate` accurately.
- H5: extractor call count is bounded by the declared cap/transformations and does not continue scaling with document tail beyond the cap.

Any H1-H4 failure is a correctness blocker.

## 15. Analysis plan

Exact comparisons. Report token and character coverage side-by-side so the original unit bug remains visible. If optional real LLM is used, report cost/time descriptively per selected metadata chunk.

## 16. Threats to validity

- fake extractor does not test LLM quality, intentionally;
- aggregation policy may itself be a future quality question, but this experiment only verifies that implementation matches the declared file-level design;
- tokenizer changes can alter chunk hashes and must create a new protocol/runtime identity.

## 17. Reproduction command placeholder

```bash
uv run python experiments/<promoted-dir>/run_eval.py --fake-extractor
```

## 18. Required raw artefacts

- fixture documents;
- SentenceSplitter expected chunk hashes/tokens/chars;
- extractor input traces/call counts;
- temporary metadata rows;
- final aggregated/stored metadata rows;
- runtime manifest.

## 19. Interpretation rules

PASS means unit/cap/granularity semantics are correct; it does not prove the selected metadata fields improve retrieval. A future per-chunk-metadata design requires its own OpenSpec and quality experiment.

## 20. Cleanup

No large index needed; remove transient output only.
