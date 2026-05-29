# External artifacts

Heavy/generated artifacts for this experiment are stored in GitHub Releases,
not Git.

## Release

- Tag: `experiment-artifacts-2026-05-29`
- Release: <https://github.com/cmdaltctr/llamaindex-rag-mcp/releases/tag/experiment-artifacts-2026-05-29>
- Asset: `experiment-8a-query-embedding-cache-fullsize-2026-05-29-artifacts.zip`
- URL: <https://github.com/cmdaltctr/llamaindex-rag-mcp/releases/download/experiment-artifacts-2026-05-29/experiment-8a-query-embedding-cache-fullsize-2026-05-29-artifacts.zip>
- SHA256: `e5f164b74ad9fd8e6aefb128379b4fef508eb504155dbfbb3fa30a7a627c77ce`

## Contents

- `experiments/8a-query-embedding-cache-fullsize-2026-05-29/corpus/`
- `experiments/8a-query-embedding-cache-fullsize-2026-05-29/eval_results.json`

## Regeneration

```bash
cd experiments/8a-query-embedding-cache-fullsize-2026-05-29
uv run python run_eval.py --corpus ./corpus --regenerate-traces
```

## Notes

The local corpus contains binary PDFs and copied README fixtures, so it is kept
outside Git. The release asset stores raw corpus/evaluation data needed to audit
