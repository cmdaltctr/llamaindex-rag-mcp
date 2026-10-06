#!/bin/zsh
# Stop the Experiment 37 OCR runs cleanly (both engines). Finished pages are
# kept; start_ocr.sh resumes from the next page.
EXP_DIR=${0:A:h}
if ! pgrep -f "$EXP_DIR/run_ocr.py" >/dev/null; then
  rm -f "$EXP_DIR"/output/run_ocr*.pid; echo "not running"; exit 0
fi
# caffeinate -> uv -> python: signal the python runners so they close their workers.
for pid in $(pgrep -f "$EXP_DIR/run_ocr.py"); do kill -TERM "$pid" 2>/dev/null; done
for i in {1..30}; do
  pgrep -f "$EXP_DIR/run_ocr.py" >/dev/null || break
  sleep 1
done
if pgrep -f "$EXP_DIR/run_ocr.py" >/dev/null; then
  echo "still running after 30 s; check with status_ocr.py"
else
  rm -f "$EXP_DIR"/output/run_ocr*.pid; echo "stopped"
fi
