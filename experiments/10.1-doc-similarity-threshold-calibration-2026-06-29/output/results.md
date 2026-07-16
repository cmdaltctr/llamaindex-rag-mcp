# Experiment 10.1 Results: DOC_SIMILARITY_THRESHOLD Calibration

**Recommendation:** Optimal modularity at 0.90 but FP rate too high (N/A (no edges) ≥ 20% or unrated). Current default (0.85) is acceptable with FP rate 0.0%. No change.

## Corpus and setup

- Documents: 80
- Embedding model: qwen3-embedding:0.6b
- Thresholds tested: [0.7, 0.75, 0.8, 0.85, 0.9]

## Per-threshold metrics

| Threshold | Nodes | Edges | Sim Edges | Clusters | Mean Size | Modularity | FP Rate |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 0.70 | 80 | 1968 | 47 | 2 | 40.0 | 0.1875 | 20.0% |
| 0.75 | 80 | 1945 | 24 | 2 | 40.0 | 0.1908 | 10.0% |
| 0.80 | 80 | 1932 | 11 | 2 | 40.0 | 0.1928 | 10.0% |
| 0.85 | 80 | 1926 | 5 | 2 | 40.0 | 0.1939 | 0.0% |
| 0.90 | 80 | 1921 | 0 | 2 | 40.0 | 0.1947 | N/A |

## Pass gates

- **Optimal threshold**: 0.9
- **Optimal modularity**: 0.194735
- **Optimal FP rate**: None
- **Default (0.85) modularity**: 0.193854
- **Default (0.85) FP rate**: 0.0
- **Default within 10% of optimal**: True
