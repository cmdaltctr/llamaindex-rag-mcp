# Experiment 25 debug pause

Date: 2026-09-10

## Status

Experiment 25 rebuild authorisation is partially implemented. The builder cannot create a vector store.

The guarded test command produced 19 passed and 2 failed tests in 18.62 seconds. The failures are `test_main_recounts_and_ingests_one_unchanged_private_snapshot` and `test_main_refuses_reused_force_and_competing_destination`.

Both fail in `LanceVectorStore.write_nodes` during first-table creation. The exception is an `AssertionError` without a message.

## Root cause

`BudgetStopEmbedder` in `estimate_gate.py` is a plain wrapper. LlamaIndex requires a `BaseEmbedding` instance when it resolves an embedding model.

A raw installed `OpenAILikeEmbedding` control succeeds. The wrapper fails. The guarded fake, network block and test environment did not cause this failure.

## Proposed next step

Make `BudgetStopEmbedder` an experiment-only `BaseEmbedding` subclass. Preserve its guarded batching and request-count accounting. Implement required abstract methods and private attributes. Do not apply this change without approval.

## Evidence limits

Guard prefix: `env -i PATH="$PATH" HOME="$HOME" HF_HOME="$HOME/.cache/huggingface" HF_HUB_OFFLINE=1 PYTHONPATH="/var/folders/r1/7zdb3kt10bn4b6ggpgzf__380000gn/T/opencode/exp25-estimator-pytest-guard" PYTHON_DOTENV_DISABLED=1`.

Command: `uv run --no-sync pytest tests/test_exp25_estimate_requests.py tests/test_exp25_rebuild_repair.py tests/test_exp25_build_authorisation.py tests/test_exp25_request_accounting.py -q`.

No paid requests occurred. The parent did not inspect credentials. An earlier test-agent command omitted the process-wide guard and could read `.env` through config imports. That run is not isolated verification. Subsequent commands used the guard described above. The estimator and its independent preparation test now avoid ambient config resolution.

No full-corpus estimator or historical experiment was rerun. The expanded estimator matrix needs a fresh guarded run after future changes.

## Preserved state and remaining work

All 21 inventoried historical plan/raw hashes still match. The protected routing source, routing test and preserved patch hashes also match. HEAD and the remote-tracking feature ref remain `afe151e93dd9b79e18618811dc15e35c6a96b16d`. Repair changes remain uncommitted.

Experiment 25's historical PASS and tokenizer promotion stand. The operator explicitly said: "Do not rerun Experiment 25." Future rebuild tooling remains unfinished. Recovered count fragments remain unpriced and their code identities predate these edits; they cannot approve spending.

Experiments 26/27 await fresh verification of recovered repairs. Experiment 28's identity/privacy changes have not started. Personal-document selection and routing decisions remain pending.

On resumption, fix the wrapper, then run the complete scoped Experiment 25 matrix. Finish the entry-point documentation and TDR follow-up. Trim the 506-line gate and 515-line estimator test below the 500-line ceiling. The separate partial estimator remains preserved; deletion needs approval. No `a-review` or `a-security` agent ran. Final local checks, refactoring and the complete post-change scan remain outstanding.
