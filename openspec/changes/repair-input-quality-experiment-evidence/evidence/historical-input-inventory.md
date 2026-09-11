# Historical experiment input inventory

## Summary

This inventory fixes the starting identities of the plans and saved JSON results
for experiments 25 to 28. It does not change the plans, indexes, raw results,
or their historical conclusions.

## Discussion

Later repair output must not overwrite a file listed below. A later report or
recomputation must use a dated recovery destination and identify its source
hashes. The preserved indexes remain read-only evidence. A new experiment 25
build, if later approved, needs a separate operator-approved destination.

## SHA-256 inventory

| Experiment | File | SHA-256 |
| --- | --- | --- |
| 25 | `plan.json` | `f035fd7c55288a1e68ec5d7db2ea91afe29df811e4661e92b5a8b5028149b028` |
| 25 | `output/build_done.json` | `719b743c29e6dde8db5f18224fb6ea89b3d9f11a22577824e71a140335fc3047` |
| 25 | `output/cells/model_token_markdown.json` | `34cdc7b306a73620390614cfe78814b288b4083d52f911620e19eb49d86cc1fc` |
| 25 | `output/eval_results.summary.json` | `18c79ba718b120969cc796aeb9bbaa396eb834824367d5f93363ec4c1c039211` |
| 25 | `output/token_accounting_baseline.json` | `d4e1f92a4e696339f92fbddc3a20daf06174932273aaa22694510cfe50faa1d8` |
| 25 | `output/token_accounting_candidate.json` | `98765d4bf047eb132933e59d4ee3c381581a4f6f34697fcb354925371613753a` |
| 25 | `output/verify_accounting_baseline.json` | `9e1d459a8375aaf3865c13d8c8bd1bb516a463a721f8c52cbe6e17d6cdcee97f` |
| 25 | `output/verify_accounting_candidate.json` | `91ed32d52c68bf9eec0ae22d702bf4cd8c8200f4589c140fc2389f527e68e19e` |
| 26 | `plan.json` | `5721d3a609c73d4fb3663a8880861c63c1449c55fb70116eca3b75b2729b4f21` |
| 26 | `output/cells/candidate_instruction.json` | `4b7cfa680e7fdadfda8531688eb5190c47af8894d4d04e6d4d2086eaeae68b02` |
| 26 | `output/cells/raw_none.json` | `3188af9299eb4a8ece8fcde4adc548a388beb34e09586454bb04345bbc8d90ee` |
| 26 | `output/eval_results.summary.json` | `a1434178143c55d864156d845abce5dc7270c10cd141a88ed2d6fbf959c54496` |
| 26 | `output/runtime_manifest.json` | `061415e07dc15c6a7134718e9fbdd0d55158a2c9d2fd9efb3bd43f8cea772a3a` |
| 27 | `plan.json` | `8f5f70b0ae0b16f79b2880e228a55edadb8fa30602d1fc98cc94ee1c76dcc012` |
| 27 | `output/cells/chunking_only_raw.json` | `f9b837ae7099f10037cdc57b723829fca4f2233e055fa0b1142b592c7c4f1d78` |
| 27 | `output/cells/combined_candidate.json` | `2abaa1635117f817615ccabb4f3589ee745d26f646a169af9b54a4f95eee02cf` |
| 27 | `output/eval_results.summary.json` | `2dd99413c8c6c683e8382000e70d08e47b71247d5fe08bf85174bab92ba07088` |
| 27 | `output/runtime_manifest.json` | `64f62c484fd2f17fa72495b719c0e9b537529d159cd0dddb82200df6cc20e164` |
| 28 | `plan.json` | `656629f9c21635abc540bca44e96e22e1a3cbdca2f2b3b7d4e803ad401201c43` |
| 28 | `output/classifications.json` | `b616feec44d9faca29d6aef4536f5c4bf9338cd3198a53ec1eac29fc4fc34b39` |
| 28 | `output/eval_results.summary.json` | `559ffcbe85488185699e98ee96ce2cd1669d213e2e5b07acd4b096e04932ad7c` |

## Preserved indexes

- Experiment 25 baseline: `~/Development/DATA/omrg/experiments/exp22-lancedb`.
- Experiment 25 candidate and experiment 27 read-only index:
  `~/Development/DATA/omrg/experiments/exp25-lancedb`, collection
  `exp25_model_token`.
- Experiment 26 read-only index:
  `~/Development/DATA/omrg/experiments/exp22-lancedb`.
- Experiment 28 has no vector index. Its historical public output is the
  listed `output/classifications.json` file.

## Destination rule

No new file may replace an inventoried file. Each later repair output will use
a distinct dated recovery destination, cite this inventory, and preserve the
historical source hash. No new output destination has been created yet.
