# Continuation approval (2026-09-09)

The operator replied to the progress report and installation question:

> exp 25 - proceed
> exp 26 and 27 - ok proceed
> exp 28 - ok remember we need to solve the routing decision issue

This authorises the described offline tooling repairs and the requested
`uv sync --extra openrouter` installation. It supplies no paid-run budget,
selected PDF cohort or replacement routing policy. Those gates remain open.

After verifying the feature worktree and branch, the installation completed:

- `llama-index-embeddings-openai-like==0.3.1`
- `llama-index-llms-openai-like==0.7.2`

The command installed two declared optional packages. It did not execute an
experiment. Subsequent test commands use `uv run --no-sync` to preserve this
environment. No further dependency changes are authorised by this record.

Experiment 28 must resolve the routing question through explicit policy and
cohort decisions. Fixing checkpoint identity and error privacy does not itself
resolve that question. The existing mixed patch remains unapproved.
