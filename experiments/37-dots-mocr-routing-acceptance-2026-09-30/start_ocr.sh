#!/bin/zsh
# Start (or resume) the Experiment 37 OCR runs, detached from the terminal.
# Both engines run at the same time: dots-mocr on the GPU, paddleocr-vl on
# the CPU. Pass one engine name to start only that engine.
# It keeps running when you close the terminal or Claude Code.
# caffeinate stops idle sleep while it runs (plugged in is safest).
# After a shutdown or restart, run this script again: it resumes.
#   start_ocr.sh                      # both engines
#   start_ocr.sh dots-mocr            # one engine
#   start_ocr.sh --retry-failed       # both, retry pages that errored
set -eu
EXP_DIR=${0:A:h}
REPO=$(git -C "$EXP_DIR" rev-parse --show-toplevel)

if [[ "$(git -C "$REPO" branch --show-current)" != "feat/experiment-37-dots-mocr-acceptance" ]]; then
  echo "wrong branch in $REPO; stop" >&2; exit 1
fi

engines=()
extra=()
for arg in "$@"; do
  case "$arg" in
    dots-mocr|paddleocr-vl) engines+=("$arg") ;;
    *) extra+=("$arg") ;;
  esac
done
(( ${#engines} )) || engines=(dots-mocr paddleocr-vl)

export OCR_WORKERS_DIR=/Users/aizat/Development/PROJECTS/llamaindex-rag-mcp-feat-modular-ocr-workers-dots-mocr/ocr-workers
export OMRG_OCR_MODEL_CACHE=$HOME/Development/DATA/omrg/ocr-models
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 PYTHONUNBUFFERED=1
unset OCR_WORKER_COMMAND OCR_WORKER_ENV_DIR

mkdir -p "$EXP_DIR/output"
cd "$REPO"
for engine in $engines; do
  pidfile="$EXP_DIR/output/run_ocr_$engine.pid"
  log="$EXP_DIR/output/run_ocr_$engine.log"
  if [[ -f "$pidfile" ]] && kill -0 "$(cat "$pidfile")" 2>/dev/null; then
    echo "$engine: already running (pid $(cat "$pidfile"))"; continue
  fi
  echo "=== start $(date -u +%Y-%m-%dT%H:%M:%SZ)" >> "$log"
  nohup caffeinate -i uv run python -u "$EXP_DIR/run_ocr.py" --engine "$engine" --resume "${extra[@]}" >> "$log" 2>&1 &
  echo $! > "$pidfile"
  echo "$engine: started (pid $!), log $log"
done
echo "Status: uv run python $EXP_DIR/status_ocr.py"
