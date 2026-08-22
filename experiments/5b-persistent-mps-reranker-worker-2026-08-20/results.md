# Experiment 5b results — persistent MPS reranker worker

**Protocol version:** 1.1 (v1.0 budget-filter amendment, 2026-08-22)
**Campaign date:** 2026-08-22 (second campaign; see invalidation record below)
**Overall verdict:** **FAIL — promotion rejected; ONNX CPU remains the production default**

## 1. Host and runtime identity

| Item | Value |
| --- | --- |
| Host | Apple Silicon, `arm64` |
| macOS | 26.5.1 |
| Python | 3.12.10 |
| Torch | 2.13.0 |
| sentence_transformers | 5.7.0 |
| transformers | 5.15.0 |
| Repo HEAD | `a04e8ee70a6db46911bdffeeb61a2ac95222e9aa` |
| Lock hash | `3a225230a6ebe0f7513a4b4191b6158e1435135158a22ee4a63844cec4c5f77d` |
| Plan SHA-256 | `94290eccc1ee29ed0ec1813509649ac013887ee1c0c38f2ac64faf4f57a752b9` |
| Workload SHA-256 | `bb412ddcd1e3c855a6bd78e06e61ff6a5bf72592a1566602c3b769524d06e1dc` (Experiment 5 workload, reused unmodified) |
| Longevity schedule SHA-256 | `5463c0a9991a9348a3e1ca9a3dca9a4db9f9419067a3f5a0bf83f0c1eb9978e7` (v1.1) |
| Model | `cross-encoder/ms-marco-MiniLM-L-6-v2` @ `233902d25c440f23af6f7d6e94d2946bac0bee0a` |
| Model file digests | config `380e02c9…`, safetensors `821d1aa6…`, tokenizer `d241a60d…`, tokenizer_config `a5c2e5a7…`, vocab `07eced37…`, special_tokens_map `3c3507f3…` — all matched protocol section 7 in every handshake |
| MPS | built and available; W2/W3 effective device `mps:0`; W4/W5 `cpu`; W1 `CPUExecutionProvider` first; `PYTORCH_ENABLE_MPS_FALLBACK=0` in every route |

## 2. Validity evidence

All three blocks ran on AC power with nominal thermal state (`pmset -g therm`:
no thermal/performance warning recorded at any block boundary). Operator
declaration recorded verbatim per block: "No foreground interference during
the measured campaign". Memory pressure ranged 61.1–80.3 % across block
boundaries (recorded per block in `output/campaign_context.jsonl`). The
parent process never imported `torch`, `transformers` or
`sentence_transformers` (`parent_torch_free: true`, module list empty).
`HF_HUB_OFFLINE=1` throughout; every handshake resolved the local snapshot
only.

## 3. Campaign shape

Three counterbalanced blocks over W1–W5 (block orders W5,W3,W2,W4,W1 /
W2,W4,W1,W5,W3 / W1,W5,W3,W2,W4). Every W3 and W4 lifetime served 1,000
measured primary-workload requests plus the 204-request heterogeneous
longevity schedule (v1.1). W1, W2 and W5 each served 1,000 measured
requests per block. 15/15 units completed; checkpoint complete; correctness
projection generated twice, byte-identical.

## 4. Latency results (parent-observed, ms)

| Cell | Median | P95 | n |
| --- | ---: | ---: | ---: |
| W1 `onnx_cpu_in_process` | 66.47 | 144.17 | 3,000 |
| W2 `torch_mps_fresh` | 44.13 | 87.00 | 3,000 |
| W3 `torch_mps_persistent` | 46.15 | 128.20 | 3,000 |
| W4 `torch_cpu_persistent` | 62.83 | 127.80 | 3,000 |
| W5 `torch_cpu_fresh` | 62.60 | 131.16 | 3,000 |

## 5. Gate verdicts

| Gate | Verdict | Key numbers |
| --- | --- | --- |
| G1a | **PASS** | W3 vs W2: ranking equality 3,000/3,000; max score delta 0.0 |
| G1b | **PASS** | W3 vs W4: ranking equality 3,000/3,000; max score delta 4.02e-07 |
| G1c | **PASS** | 0 route/rerank-truth violations across all cells (warm-up included) |
| G2 | **PASS** | W3/W4 median ratio 0.713 ≤ 0.8 (per-block 0.713 / 0.988 / 0.649) |
| G3 | **PASS** | W3/W1 median ratio 0.728 ≤ 0.8 (per-block 0.728 / 0.783 / 0.656) |
| G4 | **FAIL** | Median N* 156 > 150; block UBs 233 / ∞ / 233; block 2 N* = 798 |
| G5 | **PASS** | Every W3 lifetime inside ceilings (worst: worker plateau 631 MiB ≤ 750; tree plateau 853 ≤ 1,250; tree peak 1,464 ≤ 1,500) |
| G6 | **PASS** | Every lifetime and pooled upper bound ≤ 3.5 MiB per 1,000 requests < 20 (seeded block bootstrap) |
| G7 | **PASS** | All 12 probes pass; no late response admitted; deadline 5.0 s honoured |
| G8 | **PASS** | Zero workers/descendants after bounded TERM/KILL across shutdown/EOF/idle/parent-death probes |
| G9 | **FAIL** | "preflight not green" — harness flag-clobber defect, see section 8 |
| **Overall** | **FAIL** | Any FAIL gate rejects promotion |

## 6. Break-even analysis (G4)

Cumulative persistent cost per W3 lifetime (startup + model load + untimed
warm-up): 5.39 s / 7.45 s / 6.30 s (blocks 1–3).

| Block | N* (first sustained crossover) | One-sided 95 % UB |
| --- | ---: | ---: |
| 1 | 156 | 233 |
| 2 | 798 | ∞ (resamples exceed the 1,000-request horizon) |
| 3 | 135 | 233 |

Median N* = 156; the pooled upper bound is infinite because block-2
resampling never reliably crosses within the registered horizon. The gate
requires the one-sided 95 % upper bound ≤ 150 requests: **failed** on both
median and bound. Block 2's W3 lifetime was atypically slow against its
paired W4 (per-block G2 ratio 0.988), pushing that lifetime's crossover to
request 798.

### Secondary estimands (longevity schedule, W3 vs W4, n = 36 per stratum)

| Stratum (cand × tok) | W3 median ms | W4 median ms | W3/W4 | W3 ms per 1k candidate-tokens |
| ---: | ---: | ---: | ---: | ---: |
| 10×32 | 34.0 | 48.4 | 0.70 | 106.33 |
| 10×128 | 75.7 | 187.0 | 0.40 | 59.15 |
| 10×256 | 64.1 | 178.7 | 0.36 | 25.05 |
| 10×512 | 67.8 | 183.5 | 0.37 | 13.25 |
| 25×32 | 67.2 | 106.0 | 0.63 | 83.97 |
| 25×128 | 152.3 | 450.4 | 0.34 | 47.60 |
| 25×256 | 148.9 | 443.5 | 0.34 | 23.26 |
| 25×512 | 155.9 | 442.4 | 0.35 | 12.18 |
| 50×32 | 109.4 | 206.6 | 0.53 | 68.38 |
| 50×128 | 297.6 | 887.2 | 0.34 | 46.50 |
| 50×256 | 293.7 | 864.7 | 0.34 | 22.94 |
| 50×512 | 304.9 | 853.9 | 0.36 | 11.91 |
| 100×32 | 206.1 | 416.6 | 0.49 | 64.41 |
| 100×128 | 566.0 | 1,705.0 | 0.33 | 44.22 |
| 100×256 | 594.9 | 1,696.1 | 0.35 | 23.24 |
| 200×32 | 364.5 | 800.5 | 0.46 | 56.95 |
| 200×128 | 1,100.0 | 3,319.6 | 0.33 | 42.97 |

The MPS device advantage grows with per-candidate text volume (0.33–0.37
ratios for token length ≥ 128) and shrinks for the 32-token strata
(0.46–0.70), where fixed IPC overhead dominates. Normalised
candidate-token work falls with volume: the worker amortises per-request
costs over larger batches.

## 7. Memory results

### Absolute (W3 lifetimes)

| Lifetime | Worker plateau RSS | Tree plateau RSS | Tree peak RSS | MPS current alloc | MPS driver alloc |
| --- | ---: | ---: | ---: | ---: | ---: |
| block 1 | 336.5 MiB | 443.6 MiB | 1,057.1 MiB | 86.7 MiB (flat) | 1,074.9 MiB (flat) |
| block 2 | 166.2 MiB | 207.3 MiB | 615.0 MiB | 86.7 MiB (flat) | 1,074.9 MiB (flat) |
| block 3 | 631.1 MiB | 852.7 MiB | 1,464.5 MiB | 86.7 MiB (flat) | 1,074.9 MiB (flat) |

W1 fallback-ready parent plateau: 215.2 MiB. The MPS allocator current
allocation was flat at 86.7 MiB in every sample of every lifetime (matches
Experiment 5's 86.7 MiB observation); the driver-allocated figure is a
system-wide wired-memory reading, constant at 1,074.9 MiB, and is recorded
as descriptive evidence only.

### Ratios to paired W1 parent state

| Lifetime | Worker/W1 | Tree/W1 |
| --- | ---: | ---: |
| block 1 | 1.56 | 2.06 |
| block 2 | 0.77 | 0.96 |
| block 3 | 2.93 | 3.96 |

Block 3 came within 36 MiB of the 1,500 MiB tree-peak ceiling — the opt-in
budget is real and nearly binding on a 16 GiB-class host under concurrent
system memory pressure (80 % at block-3 boundaries).

## 8. Invalid, interrupted and not-evaluable record

1. **Protocol v1.0 campaign (2026-08-22, first campaign) — invalidated.**
   Aborted at W3 block 1 longevity request 3 (`invalid_request`): the v1.0
   schedule contained 24 requests (strata 100×512, 200×256) that could never
   satisfy the section 11 token budget. Evidence preserved in
   `output_invalidated_protocol_v1.0_2026-08-22/`. Protocol amended to v1.1;
   schedule regenerated (204 requests, 17 strata).
2. **Protocol v1.1 campaign (2026-08-22, second campaign) — completed but
   memory-invalidated.** A harness race in `MemorySampler._loop` retired the
   sampler on its first context-less background tick (during untimed
   warm-up), silently voiding every memory sample. Latency/correctness
   evidence was complete, but G5/G6 had no data (`NOT_EVALUABLE`). Evidence
   preserved in `output_sampler_race_invalidated_2026-08-22/`. The race was
   fixed (context-less ticks are skipped, not fatal; regression test added)
   and the full campaign repeated per the protocol's repeat-the-lifetime
   rule. No statistic from the invalid campaign enters any aggregate here.
3. **G9 "preflight not green" (this campaign) — harness flag-clobber
   defect.** The measured run rewrote `preflight/_summary.json` without the
   dry-run's `probes_green`/`all_green` flags, so the summariser reported
   preflight not green. The underlying G9 requirements are individually
   green and evidenced: plan agreement green, frozen identities verified,
   all five routes green with correct devices, parent Torch-free, 12/12
   lifecycle probes passing before the first measured row
   (`output/lifecycle_probes.jsonl`), checkpoint 15/15 complete, raw rows
   contract-valid, correctness projection byte-identical across two runs.
   The verdict stands as FAIL per the no-relaxation rule; the defect is
   fixed for future campaigns (`merge_prior_preflight_green`, regression
   test added) and noted here rather than patched into the evidence.
4. No measured lifetime in this campaign was invalid: all 15 units
   completed with zero route/rerank violations and mains-power/thermal
   evidence at every block boundary.

## 9. ONNX/Torch divergence (descriptive only, excluded from G1)

W1 (ONNX int8) versus W3 (Torch fp32): ranking equality 0/3,000; maximum
absolute score delta 0.0508; sigmoid-normalised threshold decisions at 0.5:
0 flips in 3,000 pairs. Consistent with Experiment 5's finding — backend/
quantisation divergence, not an MPS defect, with no practical decision
impact at the production threshold.

## 10. Overall verdict and promotion decision

**FAIL.** G4 (cumulative break-even ≤ 150 requests at 95 % one-sided
confidence) failed genuinely: median N* = 156, upper bounds 233–∞. G9
failed on a bookkeeping defect whose substantive requirements were all met.
Per protocol section 19, any FAIL gate rejects promotion: **ONNX CPU
remains the production default; no production-worker OpenSpec/ADR is
recommended from this experiment.** Experiment 5's H3 verdict remains FAIL
and is untouched by this outcome.

Positive diagnostic findings retained for future reference: persistent MPS
preserves compatible Torch fp32 rankings exactly (G1), is ~29 % faster than
persistent CPU and ~27 % faster than the in-process ONNX baseline on
median parent-observed latency (G2/G3), fits the declared memory budget
with bounded growth (G5/G6), and the worker lifecycle is deadline-bounded
with zero orphans (G7/G8). The economics of amortising a ~5–7 s
startup/load/warm-up cost within 150 requests on this workload do not
close at 95 % confidence.
