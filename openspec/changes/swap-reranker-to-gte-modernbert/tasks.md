## 1. Pre-flight: ONNX export verification (AIE-20 subtask 1)

- [ ] 1.1 Confirm `onnx/model_quantized.onnx` loads via `onnxruntime.InferenceSession` (official pre-exported ONNX variant, 151MB int8)
- [ ] 1.2 Verify ONNX model loads with `AutoTokenizer.from_pretrained("Alibaba-NLP/gte-reranker-modernbert-base")`
- [ ] 1.3 Run a smoke test: score 5 query-document pairs and verify sigmoid-normalised outputs are in (0, 1)
- [ ] 1.4 Measure cold-start download time and memory footprint on consumer hardware (macOS ARM)

## 2. Experiment: A/B comparison (AIE-20 subtask 2 & 3)

- [ ] 2.1 Create experiment directory `experiments/N-gte-reranker-swap-YYYY-MM-DD/` with protocol.md
- [ ] 2.2 Build FreshStack LangChain index (reuse from Exp 9a/10b if available)
- [ ] 2.3 Run A/B cells: (a) MiniLM reranker, (b) gte-reranker, (c) rerank-off baseline
- [ ] 2.4 Evaluate on FreshStack LangChain + Qasper query sets
- [ ] 2.5 Compare Coverage@20, Hit@1, MRR@10 across all three cells
- [ ] 2.6 Verify gte-reranker beats rerank-off baseline (must beat 0.738 Coverage@20 hybrid)
- [ ] 2.7 Measure and compare latency (ms per query) for all three cells
- [ ] 2.8 Record raw logit distributions for MiniLM vs gte-reranker to assess threshold scaling

## 3. Threshold recalibration (if needed)

- [ ] 3.1 Compare logit standard deviations between MiniLM and gte-reranker (from experiment data)
- [ ] 3.2 If logit distributions differ by >2× in std dev, run threshold calibration experiment (following Exp 1 protocol)
- [ ] 3.3 Update `_effective_threshold()` in `retrieval.py` if recalibration is needed
- [ ] 3.4 Document recalibration results in experiment `results.md`

## 4. Code changes

- [x] 4.1 Update `RERANK_MODEL` default in `src/rag_mcp/reranker.py` to `Alibaba-NLP/gte-reranker-modernbert-base`
- [x] 4.2 Update `_select_onnx_variant()` to be model-aware — prefer `onnx/model_quantized.onnx` (int8, 151MB) for ModernBERT models; preserve existing MiniLM `qint8_arm64` path for the old model
- [x] 4.3 Update tokenizer `max_length` from 256 to 2048 in the `rerank()` method
- [x] 4.4 Update module docstring in `reranker.py` to reference new model
- [x] 4.5 Update `.env.example` with new `RERANK_MODEL` default

## 5. Tests

- [x] 5.1 Update `tests/unit/test_reranker.py` (or equivalent) to use new model ID in mocked tests
- [x] 5.2 Update ONNX variant selection test for ModernBERT path
- [x] 5.3 Update docstring assertion test for new model name
- [x] 5.4 Add test verifying `max_length=2048` is passed to tokenizer
- [x] 5.5 Run `uv run pytest -m "not slow" -v` and verify all pass
- [x] 5.6 Run `uv run pytest --cov=rag_mcp` and verify coverage thresholds met

## 6. Documentation

- [x] 6.1 Update `docs/guides/reranker.md` (or architecture.md reranker section) with new model details
- [x] 6.2 Update `docs/guides/configuration.md` reranker env var table with new default
- [x] 6.3 Write ADR for the model swap decision and threshold recalibration results
- [x] 6.4 Update `docs/adr/ADR_README.md` index with new ADR
- [x] 6.5 Update `README.md` if reranker model is mentioned

## 7. NiftyPM sync

- [ ] 7.1 Update AIE-20 subtasks as completed in NiftyPM
- [ ] 7.2 Mark AIE-20 task as completed in NiftyPM
- [ ] 7.3 Update `niftypm/llamaindex-rag-mcp.json` with completion status
