# TDR-022: Token counting is contract-sensitive — three traps in the exp 25 pre-build gate

**Date:** 2026-09-08
**Status:** Accepted
**Deciders:** Aizat
**Tags:** experiments | chunking | tokenization | embedding-cost | gates

## Context

Experiment 25 (model-token chunking ablation) freezes a cost gate before any
paid embedding work: candidate embedded tokens must not exceed 1.15 ×
baseline. Validating that gate found three independent counting defects, two
of them mine, one in production code. Root cause analysis for each:

### Defect 1 — production code: post-processor specials break the cap check

`model_token._token_count` called `tokenizer.encode(text)` with
`add_special_tokens=True` (the default). Qwen tokenizers carry a `Sequence`
post-processor that appends special tokens on every encode, while
`semantic-text-splitter.from_huggingface_tokenizer` counts **without** them.
Every chunk the splitter sized to exactly the cap (1024) verified at 1025 →
hard `ValueError` → ~12% of real Markdown sources failed chunking outright
(59/500 files in the calibration sample).

**Fix:** count with `add_special_tokens=False`, matching the splitter's
semantics (commit `a40ae42`; regression test grows a real cached-Qwen chunk
to exactly the cap).

### Defect 2 — experiment tooling: manifest contamination + non-cancelling ratio

The standalone pre-build counter re-chunked `corpus/` with `rglob("*")`,
which included the 52 MB `langchain_manifest.jsonl` that production's
`gather_supported_files` never selects. One file ≈ 40–43k chunks ≈ 59% of
the count. I then made it worse with bad maths: I claimed the shared
overcount "cancels in the ratio". It does not — a shared **additive**
contaminant squashes the ratio toward 1, loosening the nominal 1.15 cap to
an effective ≈ 1.37 on genuine body tokens. An external model review caught
both and reconciled the arithmetic exactly.

### Defect 3 — experiment tooling: body text ≠ embedding payload

The counter tokenised chunk body text. Production embeds
`node.get_content(metadata_mode=MetadataMode.EMBED)` — body plus retained
metadata keys (`file_name`, `header_path`, `category`, `keywords`,
`summary`, `document_title`, `content_type`) with lineage keys excluded by
`source_state`. Body-only counting undercounts by ~7–8% and misses that
full payloads exceed the body cap (candidate max 1,125 vs cap 1,024;
baseline max 2,087 — the legacy splitter had no payload awareness at all).

## Decision

1. **Token counting must reuse the production contract, never re-implement
   it.** Counting code builds a `TextNode`, sets
   `excluded_embed_metadata_keys = set(metadata) - _RETAINED_EMBED_METADATA_KEYS`,
   and tokenises `get_content(metadata_mode=MetadataMode.EMBED)` with
   `add_special_tokens=False`. Implemented in
   `experiments/25-.../verify_accounting.py`.
2. **Verify built artefacts instead of re-simulating them.** The corrected
   accounting reads the actual LanceDB stores, reconstructs payloads, and
   reconciles per-file chunk counts against each build's `file_details`
   record — 0 mismatches over 10,024 files per side. Re-chunking the corpus
   separately from the pipeline is banned; it drifts (path-dependent
   metadata budgets, detection boundaries).
3. **Pre-spend gates must reject contaminated input by construction.**
   File selection comes from production (`gather_supported_files`); a
   shared additive contaminant in both sides of a ratio invalidates the
   gate, not just the totals. Strict aborts: missing index/build record,
   any per-file mismatch, tokenizer fallback, incomplete coverage.
4. **Future pre-build estimates** (when no built store exists yet) reuse
   the production preparation functions with an in-memory store and a
   network-blocked request recorder, per the external review — do not grow
   a second ingestion framework.

## Consequences

**Positive**

- Corrected cost verdict from real stores: 13,780,416 / 14,066,499 = 0.980 —
  the completed candidate build passes without a rebuild or re-spend.
- Worst-case payload finding (2,087 → 1,125) recorded for task 5.2.
- Two regression tests pin the contracts (`tests/test_exp25_accounting_contracts.py`).
- The defective counter is kept, marked deprecated with its defects
  enumerated — the failure stays auditable.

**Negative**

- ~4 h of operator time lost to the manifest-contaminated runs and the
  review cycle; the invalid gate briefly guarded a paid build.
- My "ratio cancels" claim reached you before the review caught it.

**Neutral**

- Billing/retry-level token verification remains unverified (local
  reconstruction only); payload reconstruction carries a documented ±1.4%
  method sensitivity between two independent implementations.

## Alternatives considered

| Option | Rejected because |
| --- | --- |
| Raise `MARKDOWN_CHUNK_SIZE` past the specials overshoot | Masks the semantics mismatch; cap and splitter would count in different units |
| Keep the standalone counter, subtract the manifest chunk count | Whack-a-mole; the payload and selection defects remain, arithmetic fixes one symptom |
| Trust the ratio because both sides share the contaminant | Mathematically wrong for additive contamination (see Defect 2) |
| Rebuild the candidate index under the corrected counter | Unnecessary — store-based verification needs no re-spend |

## How to recognise / handle this again

- Chunker raises `Markdown chunk is 1025 tokenizer units...` at scale →
  suspect specials asymmetry: compare
  `len(tok.encode(t).ids)` vs `len(tok.encode(t, add_special_tokens=False).ids)`.
- Any counter whose chunk total diverges from the build's
  `chunks_created` → stop, reconcile per file against `file_details`; do
  not proceed on a hand-wave.
- Corpus directory iteration for ingestion-adjacent tooling → always
  `gather_supported_files`, never raw `rglob`.
- Re-verify any past token estimate with:
  `uv run python experiments/25-token-chunking-ablation-2026-09-08/verify_accounting.py --side baseline|candidate`
  (exits non-zero on any mismatch).

## Revisit triggers

- A `semantic-text-splitter` major bump (its counting semantics are the
  contract counterpart).
- A tokenizer whose post-processor changes under a pinned revision.
- Any new pre-build estimator requirement → implement the in-memory-store
  + network-blocked recorder pattern before trusting another gate.

## References

- Commit `a40ae42` — specials fix + regression test
- Commit `6d1ed4a` — corrected accounting, deprecation, tests, index preservation
- `experiments/25-token-chunking-ablation-2026-09-08/{verify_accounting.py,protocol.md}`
- `src/omrg/core/chunking/model_token.py` (`_token_count`),
  `src/omrg/core/ingestion/source_state.py` (`_RETAINED_EMBED_METADATA_KEYS`)
- External model review, 2026-09-08 (relayed by the operator)
- ADR-063 (model-token-aware Markdown chunking, Proposed)
