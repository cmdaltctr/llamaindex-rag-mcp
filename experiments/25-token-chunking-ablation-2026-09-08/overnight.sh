#!/bin/bash
# Experiment 25 overnight pipeline (task 5.2 candidate build).
#
# 1. Baseline token accounting (local, free, ~45 min)
# 2. Candidate token accounting (local, free, ~45 min)
# 3. Candidate index build (~8 h, OpenRouter; build_index.py refuses to
#    start if the frozen 1.15x cost gate is breached by steps 1-2)
#
# Everything is checkpointed: accounting rewrites atomically, the build
# skips completed files on re-run. Log: output/overnight.log

set -euo pipefail
cd "$(dirname "$0")/../.."

uv run --no-sync python experiments/25-token-chunking-ablation-2026-09-08/token_accounting.py --mode baseline
uv run --no-sync python experiments/25-token-chunking-ablation-2026-09-08/token_accounting.py --mode candidate
uv run --no-sync python experiments/25-token-chunking-ablation-2026-09-08/build_index.py
echo "[overnight] all stages complete"
