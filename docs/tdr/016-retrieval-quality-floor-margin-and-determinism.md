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
- Tier 2 fails when Ollama, the exact model tag, the recorded digest, fixture
  identity, or baseline is absent or different. It never skips those failures.
  The Ollama version, operating system, and architecture are recorded with
  each measurement as evidence; they do not fail the run, because the nightly
  job uses a different pinned Ollama build on a different platform and the
  floor margin exists to absorb that variation.
- The initial Tier 2 fields remain `null` until the required real measurements
  are performed. No unmeasured Recall@10 or MRR@10 value may be committed.

### Measurement evidence

| Tier | Run | OS / architecture | Recall@10 | MRR@10 |
| --- | --- | --- | --- | --- |
| 1 | GitHub Actions baseline | ubuntu-latest / x86_64 | 1.000000 | 1.000000 |
| 2 | Repetition 1 | Darwin / arm64 | 1.000000 | 1.000000 |
| 2 | Repetition 2 | Darwin / arm64 | 1.000000 | 1.000000 |
| 2 | Repetition 3 | Darwin / arm64 | 1.000000 | 1.000000 |

Tier 1 uses the exact 1.000000 measurements as its deterministic floors. Tier 2
was measured on one machine with Ollama 0.32.13 and model digest
`ac6da0dfba84a81fdbfbaf330198c33cd77c4cdfc53e8bc50eb581914a15621d`. Docker is
unavailable on the measurement host, so no second architecture was measured;
single-architecture runs take the larger 0.03 margin, giving floors of 0.97.
The nightly job runs `ubuntu-latest` with its own pinned Ollama build, and the
floor margin carries exactly that cross-platform variation.

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

## Local Measurement Evidence (2026-08-29)

Three repeated Tier 2 measurements on one machine, all identical:

- Machine: Darwin, arm64; Ollama 0.32.13.
- Model: `qwen3-embedding:0.6b`, digest
  `ac6da0dfba84a81fdbfbaf330198c33cd77c4cdfc53e8bc50eb581914a15621d`.
- Runs 1-3: `recall@10 = 1.000000`, `mrr@10 = 1.000000`. Every expected
  source ranked first in every run, and the full top-10 orderings were
  identical across runs. Per-query ranks are preserved in each
  `TIER2_MEASUREMENT` record from the verification session logs.
- Margin: measured values sit at the ceiling, so the floor uses the larger
  single-architecture margin of 0.03: `floor = 0.97` for both metrics.

### Identity binding

The baseline binds the exact model tag and digest. A silently repointed tag or
a different build under the same name fails the gate before metric comparison.
The Ollama version, operating system, and architecture travel with the
baseline as recorded evidence only. The nightly job runs `ubuntu-latest` with
its own pinned Ollama build, so those fields must not be pass conditions; the
0.02–0.03 floor margin is the spec's mechanism for cross-platform ranking
variation. The first post-merge `workflow_dispatch` (task 7.1) must therefore
pass when metrics meet their floors; treat any digest mismatch it reveals as a
model-movement investigation, not a baseline refresh.

## Post-merge Dispatch Evidence (2026-08-29)

The first `workflow_dispatch` Tier 2 run executed on the merged integration
head `v3` and completed successfully:
https://github.com/cmdaltctr/llamaindex-rag-mcp/actions/runs/33280036117.
Linux / x86_64 with Ollama 0.33.2 measured Recall@10 = 1.000000 and
MRR@10 = 1.000000, with every expected source at rank 1. The resolved model
digest matched `ac6da0dfba84a81fdbfbaf330198c33cd77c4cdfc53e8bc50eb581914a15621d`
exactly, so tag+digest binding absorbed the cross-platform change as designed
(task 7.1).

Task 7.2 remains open: GitHub fires scheduled workflows only from the default
branch (`main`), so the nightly cron stays dormant until `v3` merges to
`main`. Confirm then that the scheduled event starts Tier 2 only.

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
