# Experiment 10.1 Results: DOC_SIMILARITY_THRESHOLD Calibration

**Recommendation:** Results inconclusive. Optimal threshold=0.90 but FP rates not yet rated or too high. Complete manual ratings and re-run summarise.

## Corpus and setup

- Documents: 68
- Embedding model: qwen3-embedding:0.6b
- Thresholds tested: [0.7, 0.75, 0.8, 0.85, 0.9]

## Per-threshold metrics

| Threshold | Nodes | Edges | Sim Edges | Clusters | Mean Size | Modularity | FP Rate |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 0.70 | 68 | 1330 | 39 | 2 | 34.0 | 0.2598 | N/A |
| 0.75 | 68 | 1314 | 23 | 2 | 34.0 | 0.2646 | N/A |
| 0.80 | 68 | 1301 | 10 | 2 | 34.0 | 0.2688 | N/A |
| 0.85 | 68 | 1297 | 6 | 2 | 34.0 | 0.2702 | N/A |
| 0.90 | 68 | 1291 | 0 | 2 | 34.0 | 0.2724 | N/A |

## Pass gates

- **Optimal threshold**: 0.9
- **Optimal modularity**: 0.27241
- **Optimal FP rate**: None
- **Default (0.85) modularity**: 0.270208
- **Default (0.85) FP rate**: None
- **Default within 10% of optimal**: True
