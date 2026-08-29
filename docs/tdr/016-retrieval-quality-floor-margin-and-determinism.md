# TDR-016: Pin retrieval-quality floors to identity-bound measurements

**Date:** 2026-08-29
**Status:** Proposed
**Deciders:** Repository maintainers
**Supersedes:** None
**Tags:** retrieval | testing | ci | ollama

## Context

Ranking can regress while type, unit, and integration tests remain green. The
gate needs one deterministic pull-request signal and one production-like signal
without turning a small synthetic corpus into a model-quality benchmark.

Tier 1 therefore uses test-owned fake embeddings. Tier 2 uses the real
`qwen3-embedding:0.6b` Ollama model. Real-model results are valid only for an
identified model digest, Ollama version, operating system, architecture, corpus,
and query set. Tier 2 measurements cannot be inferred from code inspection and
must be recorded from at least three real runs.

## Decision

Use Recall@10 and MRR@10 from the Experiment 19 metric semantics:

- Tier 1 commits its exact deterministic measurement as each floor.
- Tier 2 records at least three repeated measurements and preserves every
  per-query rank. Each floor is 0.02–0.03 below the selected measured value.
  Use 0.03 when only one runner architecture is available.
- `tests/quality/baseline.json` is the sole machine-readable baseline. Fixture
  hashes and runtime identity are part of its validity, not supplementary
  notes.
- Tier 2 fails when Ollama, the exact model tag, the recorded digest, runtime
  identity, fixture identity, or baseline is absent or different. It never
  skips those failures.
- The initial Tier 2 fields remain `null` until the required real measurements
  are performed. No unmeasured Recall@10 or MRR@10 value may be committed.

### Measurement evidence

| Tier | Run | OS / architecture | Recall@10 | MRR@10 |
| --- | --- | --- | --- | --- |
| 1 | GitHub Actions baseline | ubuntu-latest / x86_64 | 1.000000 | 1.000000 |
| 2 | Repetition 1 | Pending local runtime | Pending | Pending |
| 2 | Repetition 2 | Pending local runtime | Pending | Pending |
| 2 | Repetition 3 | Pending local runtime | Pending | Pending |

Tier 1 uses the exact 1.000000 measurements as its deterministic floors. The
Tier 2 model digest and Ollama version are pending the real runs. Once
measured, update this table and the baseline in the same commit. If two
architectures are available, record both and state whether their per-query
ranks agree before selecting the 0.02 or 0.03 margin.

## Consequences

### Positive

- Pull requests receive fast, deterministic ranking-regression feedback.
- Nightly runs exercise normal chunking and the production retrieval path with
  the real reference model.
- A changed fixture or runtime cannot silently reuse an unrelated baseline.

### Negative

- Tier 2 requires Ollama and model-download time.
- Any intentional corpus, query, model, Ollama, or runner change requires a new
  explicit measurement.

### Neutral

- The gate detects score conversion, reciprocal rank fusion, threshold
  handling, and final-ranking regressions over this corpus.
- Subtle model drift and production-corpus relevance still require experiments.

## Alternatives Considered

| Option | Rejected Because |
| --- | --- |
| One real-model pull-request gate | It is slow, network-dependent, and less deterministic. |
| Fake embeddings only | They cannot exercise the production embedding model. |
| Floors without fixture and runtime identity | They can compare unrelated measurements and appear valid. |
| Auto-accept a new baseline | It converts a regression into an unreviewed update. |

## How to Recognise / Handle This Again

1. A floor failure prints the measured baseline, required floor, and actual
   value. Inspect the per-query rankings before changing any baseline.
2. For a deliberate fixture or runtime change, run Tier 1 and then run Tier 2
   at least three times:

   ```bash
   uv run pytest tests/quality/test_metrics.py tests/quality/test_retrieval_quality_tier1.py -m slow --tb=short -q -s
   uv run pytest tests/quality/test_retrieval_quality_tier2.py -m slow --tb=short -q -s
   ```

3. Preserve every printed `TIER1_MEASUREMENT` or `TIER2_MEASUREMENT` record.
   Verify the model tag and digest, Ollama version, operating system,
   architecture, corpus hash, and query-set hash.
4. Update the baseline and this record in one reviewed commit. Do not loosen a
   floor until the ranking change is understood.

## Revisit Triggers

Re-evaluate this decision when the production embedding model changes, Ollama
changes ranking-relevant behaviour, a second runner architecture reveals
different ranks, the corpus or golden queries change, recurring variance exceeds
the selected margin, or production evaluation shows that these synthetic
queries no longer catch relevant failures.

## References

- `openspec/changes/retrieval-quality-tripwire-3/`
- `tests/quality/baseline.json`
- `tests/quality/runner.py`
- `.github/workflows/ci.yml`
- `experiments/19-native-fts-vs-bm25-sparse-2026-08-29/summarise_eval.py`
