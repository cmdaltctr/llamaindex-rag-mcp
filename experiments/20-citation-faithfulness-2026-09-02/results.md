# Experiment 20 Results: Citation Faithfulness — Does the Cited Evidence Support the Claim?

**ID**: `20-citation-faithfulness-2026-09-02`
**Date run**: 2026-09-02
**Operator**: Dr Muhammad Aizat with build agent (ran the judge cells, wrote this report)
**Status**: PASS
**Outcome**: All gates pass; propose a claim-verification stage behind `ANSWER__VERIFY_CLAIMS=true`.
**Raw data**: [`eval_results.json`](./output/eval_results.json)

---

## TL;DR / Decision

An LLM judge (Z.AI GLM-5.3) detects every unsupported claim in the 120-triple
set with zero false rejections and sub-5 s latency. A lexical baseline cannot
(recall 0.617 at the same false-rejection budget, and 0.0 on contradicted
claims). A second judge (DeepSeek V4 Flash 0731 via OpenRouter) agrees on all
120 verdicts. Security finding F4 moves from open residual to mitigated.

- Decision: propose an OpenSpec change adding an optional claim-verification
  stage, default decided there.
- Winning configuration: Z.AI GLM-5.3 as judge, temperature 0, judge prompt v1.
- Main measured effect: unsupported recall 1.0 (lexical 0.617, gap 0.383);
  false rejection 0.0; P95 3.33 s; cross-model agreement 1.0.
- Main caveat: the corpus is entity-disjoint per file; the swapped class has
  only one related-file pair (harbour ↔ meridian). Perfect swapped detection
  may not generalise to topically related evidence. A pipeline-derived
  faithful validation set (amendment 1) remains required before deployment.
- Follow-up required: yes — OpenSpec change for the verification stage, plus
  a pipeline-derived faithful claims validation set.

## Hypothesis / Purpose

> **H1 (judge):** an LLM judge evaluating (claim, cited-evidence-text) pairs
> detects unsupported claims with recall ≥ 0.80 while falsely rejecting ≤ 0.10
> of supported claims.
>
> **H2 (lexical gap):** a lexical-overlap baseline is materially weaker — at
> least 0.20 lower unsupported-claim recall than the judge.
>
> **H3 (latency):** judge verdicts add P95 ≤ 5 s per claim.

Verdict: **all three hypotheses supported.**

- H1: supported (recall 1.0 ≥ 0.80; false rejection 0.0 ≤ 0.10; per-class
  recall 1.0 on all three adversarial classes; paraphrase false rejection 0.0).
- H2: supported (lexical recall 0.617 at the constrained operating point;
  gap 0.383 ≥ 0.20).
- H3: supported (P95 3328 ms ≤ 5000 ms).

## Background

The answer pipeline's `ok` status means "answer text exists and at least one
ordinal resolves to supplied evidence" — a referential guarantee. Security
review F4 showed that an unsupported claim followed by `[1]` returns `ok` with
a real citation: the parser proves the ordinal maps to stored lineage, not
that the evidence entails the claim. This experiment measures whether an LLM
judge can close that gap.

- Protocol: [`protocol.md`](./protocol.md)
- Related OpenSpec: `openspec/changes/add-grounded-answer-synthesis-3` — task
  7.2, security finding F4
- Security review: `openspec/changes/add-grounded-answer-synthesis-3/security-review.md`

## Variables

| Type | Variable | Values actually run |
| --- | --- | --- |
| Independent | Verification method | `lexical` (Cell A), `judge-local` GLM-5.3 (Cell B), `judge-cross` DeepSeek V4 Flash 0731 (Cell C) |
| Dependent | Unsupported-claim recall | per method, overall and per adversarial class |
| Dependent | Supported-claim false rejection | per method, overall and on paraphrases |
| Dependent | P95 verdict latency | per claim, per method |
| Controlled | Corpus | quality corpus (frozen, 120 triples) |
| Controlled | Claim set | one frozen labelled triple set shared by all cells |
| Controlled | Judge prompt | v1 (protocol-only, no answer context) |

### Deviation from protocol

> Amendment 5 (2026-09-02, before any judge run): the judge was switched from
> the local answer model (qwen3:4b via Ollama) to cloud models — Z.AI GLM-5.3
> for Cell B, DeepSeek V4 Flash 0731 via OpenRouter for Cell C. On a 32 GB M1 Pro,
> LlamaIndex's Ollama client sent `num_ctx=262144` (qwen3's model-info
> default), consuming 43 GB and producing zero verdicts in 10+ minutes. The
> judge-only substitution weakens the shared-blind-spot concern (the judge is
> now a different model family from the production answer generator). The
> lexical cell (Cell A) is unaffected. See protocol amendment 5 for full detail.

## Environment and corpus

| Item | Value |
| --- | --- |
| Python | 3.12 |
| Judge model (Cell B) | Z.AI GLM-5.3 via `ZAI_API_KEY` (cloud, OpenAI-compatible) |
| Cross model (Cell C) | DeepSeek V4 Flash 0731 via `OPENROUTER_API_KEY` (OpenRouter) |
| LLM library | `llama-index-llms-openai-like` 0.7.2 (`uv sync --extra openrouter`) |
| Hardware | MacBook Pro M1 Pro (32 GB), network access to cloud APIs |
| Corpus | 120 labelled (claim, evidence-text, label) triples; 60 unsupported (20 contradicted, 20 invented, 20 swapped), 60 supported (40 faithful, 20 paraphrase) |
| Ground truth | [`ground-truth.json`](./ground-truth.json) — frozen, audited |
| Key config | `ANSWER__TIMEOUT=600`, temperature 0, `is_chat_model=True` |

## Method / reproduction

```bash
# Cell A — lexical negative control (deterministic, no model)
PYTHONUNBUFFERED=1 uv run python -u experiments/20-citation-faithfulness-2026-09-02/run_eval.py \
  --methods lexical

# Cell B — primary judge gate (Z.AI GLM-5.3)
ZAI_API_KEY=... PYTHONUNBUFFERED=1 ANSWER__TIMEOUT=600 \
  uv run python -u experiments/20-citation-faithfulness-2026-09-02/run_eval.py \
  --methods judge-local --resume

# Cell C — cross-model diagnostic (DeepSeek V4 Flash 0731 via OpenRouter)
OPENROUTER_API_KEY=... PYTHONUNBUFFERED=1 ANSWER__TIMEOUT=600 \
  uv run python -u experiments/20-citation-faithfulness-2026-09-02/run_eval.py \
  --methods judge-cross --cross-model deepseek/deepseek-v4-flash-0731 --resume
```

## Results

### Main summary table

| Cell | Method | Model | Unsupported recall | False rejection | Accuracy | F1 | Unparseable | P50 latency | P95 latency |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| A | lexical (best constrained @0.7) | — | 0.617 | 0.017 | 0.800 | 0.755 | 0 | 0.01 ms | 0.02 ms |
| B | judge-local | GLM-5.3 | **1.000** | **0.000** | **1.000** | **1.000** | 0 | 2032 ms | 3328 ms |
| C | judge-cross | DeepSeek V4 Flash 0731 | 1.000 | 0.000 | 1.000 | 1.000 | 0 | 2132 ms | 9976 ms |

### Per-class recall (unsupported claims)

| Class | Lexical (Cell A) | Judge-local (Cell B) | Judge-cross (Cell C) |
| --- | ---: | ---: | ---: |
| contradicted | 0.0 | 1.0 | 1.0 |
| invented | 0.85 | 1.0 | 1.0 |
| swapped | 1.0 | 1.0 | 1.0 |

### Per-class false rejection (supported claims)

| Class | Lexical (Cell A) | Judge-local (Cell B) | Judge-cross (Cell C) |
| --- | ---: | ---: | ---: |
| faithful | 0.0 | 0.0 | 0.0 |
| paraphrase | 0.05 | 0.0 | 0.0 |

### Cross-model agreement

| Metric | Value |
| --- | --- |
| Shared parsed verdicts | 120 / 120 |
| Agreement rate | 1.000 |

### Lexical operating points (H2 reference)

| Operating point | Threshold | Unsupported recall | False rejection | Notes |
| --- | ---: | ---: | ---: | --- |
| Constrained (H2 reference) | 0.7 | 0.617 | 0.017 | Best threshold subject to false rejection ≤ 0.10 |
| Unconstrained | 0.9 | 0.967 | 0.233 | Best threshold without the false-rejection constraint |

The constrained lexical operating point (recall 0.617) is the H2 reference.
The judge gap is 1.0 − 0.617 = **0.383**, well above the 0.20 gate. The
unconstrained lexical best (recall 0.967 at 0.233 false rejection) shows that
lexical overlap can approach the judge's recall only by rejecting nearly a
quarter of supported claims — an unacceptable trade.

## Pass-gate evaluation

| Gate | Threshold | Cell B result | Pass? |
| --- | ---: | ---: | :---: |
| Unsupported recall | ≥ 0.80 | 1.000 | ✅ |
| Per-class recall: contradicted | ≥ 0.80 | 1.0 | ✅ |
| Per-class recall: invented | ≥ 0.80 | 1.0 | ✅ |
| Per-class recall: swapped | ≥ 0.80 | 1.0 | ✅ |
| Supported false rejection | ≤ 0.10 | 0.000 | ✅ |
| Paraphrase false rejection | ≤ 0.10 | 0.0 | ✅ |
| Lexical gap (H2) | ≥ 0.20 | 0.383 | ✅ |
| P95 latency (H3) | ≤ 5 s | 3.33 s | ✅ |
| Unparseable rate | report | 0.0% | ✅ |

**All gates pass.**

## Analysis

The judge achieves perfect accuracy on this corpus. Three factors explain this:

1. **Contradicted claims are lexically invisible but semantically obvious.**
   The lexical baseline scores 0.0 recall on contradicted claims (amendment 3
   made them explicitly exclusive with "instead of" contrast). The judge
   detects all 20 — semantic entailment checking is exactly what a lexical
   overlap score cannot do.

2. **The corpus is entity-disjoint per file.** Swapped evidence comes from a
   completely different document, so both lexical and semantic methods detect
   it easily (lexical 1.0, judge 1.0). The protocol's amendment 4 records
   this as a known limitation: if the swapped class used topically related
   evidence, the judge's advantage might shrink.

3. **Cloud reasoning models are strong at entailment.** GLM-5.3 and DeepSeek
   V4 Flash 0731 are both reasoning models with large context windows. The
   judge prompt is short (a few hundred tokens), so the task is well within
   their capacity. The zero unparseable rate confirms the JSON output format
   is reliable at temperature 0.

The P95 latency of 3.33 s for GLM-5.3 includes the full cloud round-trip plus
reasoning. DeepSeek V4 Flash 0731 is slower (P95 9.98 s) but Cell C is a
diagnostic cell, not latency-gated. The P50 for both judges is ~2 s, which is
acceptable for an optional verification stage.

The perfect cross-model agreement (120/120) between two different model
families (GLM and DeepSeek) rules out single-model self-agreement bias — the
verdicts are not an artefact of one model's quirks.

## Conclusion / Decision

### Decision

Per the protocol's interpretation rules: **all gates pass → propose the
verification-stage change** (optionally behind `ANSWER__VERIFY_CLAIMS=true`,
default decided in the OpenSpec change). Security F4 moves from open residual
to mitigated.

```text
Propose an OpenSpec change adding an optional claim-verification stage to the
answer pipeline, gated behind ANSWER__VERIFY_CLAIMS=true. The stage uses an
LLM judge to verify that cited evidence supports each claim before reporting
ok. Default on/off is decided in the change proposal.
```

### What should change

1. OpenSpec change proposing the verification stage (new status or `ok`
   gating), including prompt-injection resistance of the judge itself.
2. A pipeline-derived faithful claims validation set (amendment 1) before any
   deployment decision built on H1.
3. Security F4 status updated from open residual to mitigated.

### What should not change

- The referential-only `ok` guarantee stays as the fallback when verification
  is disabled.
- The production answer generator remains qwen3:4b (local) — the judge is a
  separate cloud call, not a replacement for the answer model.
- The lexical baseline is not promoted to a verification method — it is the
  negative control and stays documented as insufficient.

### Caveats

- The corpus is entity-disjoint per file; the swapped class has only one
  related-file pair. Perfect swapped detection may not generalise to
  topically related evidence (protocol amendment 4).
- The judge uses cloud APIs (Z.AI, OpenRouter) — the production answer
  pipeline is local-first. The verification stage would be an opt-in cloud
  dependency, which needs explicit user consent per the project's
  local-first policy (ADR-024).
- 120 triples is a small dataset. Perfect accuracy may indicate corpus
  saturation for the judge class, though the per-class breakdown (lexical
  0.0 on contradicted) shows the corpus is not trivially easy for all
  methods.

## Follow-ups

| Follow-up | Reason | Priority |
| --- | --- | --- |
| OpenSpec change for claim-verification stage | All gates pass; protocol escalation rule fires | high |
| Pipeline-derived faithful claims validation set | Amendment 1 requires this before deployment | high |
| Rebuild corpus with related-file swapped pairs | Amendment 4 known limitation; validates swapped class generalisation | medium |
| ADR recording the verification-stage decision | Permanent record once the OpenSpec change is confirmed | medium |

## Reproduction

```bash
uv sync --extra openrouter
export ZAI_API_KEY=...
export OPENROUTER_API_KEY=...

# All cells in one run (lexical is instant; judges take ~4 min each)
PYTHONUNBUFFERED=1 ANSWER__TIMEOUT=600 \
  uv run python -u experiments/20-citation-faithfulness-2026-09-02/run_eval.py \
  --methods lexical,judge-local,judge-cross \
  --cross-model deepseek/deepseek-v4-flash-0731 --resume
```

Raw output is stored at:

```text
experiments/20-citation-faithfulness-2026-09-02/output/eval_results.json
experiments/20-citation-faithfulness-2026-09-02/output/eval_results_checkpoint.json
experiments/20-citation-faithfulness-2026-09-02/output/run_eval.log
```

## Cleanup

No cleanup required. The `output/` directory contains only JSON results and
the log — no ChromaDB indexes or large artefacts. Keep `ground-truth.json`,
`eval_results.json`, and `results.md` per the protocol's artefact requirements.

## Artefacts

| File / directory | Description |
| --- | --- |
| `protocol.md` | Pre-run plan and pass criteria (5 amendments) |
| `results.md` | This report |
| `run_eval.py` | Evaluation runner (cloud judge, checkpoint/resume) |
| `ground-truth.json` | 120 frozen labelled triples |
| `output/eval_results.json` | Raw results (all 3 cells) |
| `output/eval_results_checkpoint.json` | Resumable checkpoint |
| `output/run_eval.log` | Full run log |
| `corpus/` | Local copy of the quality corpus |

## References

- [`protocol.md`](./protocol.md)
- `openspec/changes/add-grounded-answer-synthesis-3/security-review.md` — F4
- `openspec/changes/add-grounded-answer-synthesis-3/tasks.md` — task 7.2
- `docs/guides/mcp-tools.md` — status semantics (citations prove lineage)
