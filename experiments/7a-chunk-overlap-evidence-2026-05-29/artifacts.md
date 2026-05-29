# External artifacts

Heavy/generated artifacts for this experiment are stored in GitHub Releases,
not Git.

## Release

- Tag: `experiment-artifacts-2026-05-29`
- Release: <https://github.com/cmdaltctr/llamaindex-rag-mcp/releases/tag/experiment-artifacts-2026-05-29>
- Asset: `experiment-7a-chunk-overlap-evidence-2026-05-29-artifacts.zip`
- URL: <https://github.com/cmdaltctr/llamaindex-rag-mcp/releases/download/experiment-artifacts-2026-05-29/experiment-7a-chunk-overlap-evidence-2026-05-29-artifacts.zip>
- SHA256: `2309dc58ccc0b6ef9bd77d73e94281a6eaa3af0ee84bb2eb92e701496551fa0c`

## Contents

- `experiments/7a-chunk-overlap-evidence-2026-05-29/corpus/`
- `experiments/7a-chunk-overlap-evidence-2026-05-29/ground-truth.json`
- `experiments/7a-chunk-overlap-evidence-2026-05-29/eval_results.json`

## Regeneration

```bash
cd experiments/7a-chunk-overlap-evidence-2026-05-29
uv run python prepare_dataset.py
uv run python ingest_overlap.py --overlaps 32
uv run python ingest_overlap.py --overlaps 64
uv run python ingest_overlap.py --overlaps 100
uv run python ingest_overlap.py --overlaps 128
uv run python run_eval.py --overlaps 32,64,100,128 --top-ks 5,10,20 --rerank both
```

## Notes

ChromaDB directories are reproducible generated artifacts and are intentionally
excluded from Git. The release asset stores raw corpus/evaluation data needed to
audit the summarized results.
