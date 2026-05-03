#!/bin/bash
# run_batch.sh - Run batch_generate.py as a background job that survives disconnection.
#
# Usage:
#   ./run_batch.sh <course_name>          # full run (resumes automatically)
#   ./run_batch.sh <course_name> --test   # test with 1 slide
#
# The job runs in the background via nohup. You can safely disconnect from SSH.
# Reconnect and run:  tail -f <log>   to check progress.

if [ -z "$1" ]; then
    echo "Usage: ./run_batch.sh <course_name> [--test]"
    echo "Example: ./run_batch.sh the_disengaged_kinesthetic"
    exit 1
fi

COURSE="$1"
MUSETALK_DIR="/home/gilrubin/MuseTalk"
LOG_DIR="$MUSETALK_DIR/logs"
mkdir -p "$LOG_DIR"

TIMESTAMP=$(date +%Y%m%d_%H%M%S)
LOG="$LOG_DIR/${COURSE}_${TIMESTAMP}.log"
PID_FILE="$LOG_DIR/${COURSE}.pid"

# Check if already running
if [ -f "$PID_FILE" ]; then
    OLD_PID=$(cat "$PID_FILE")
    if kill -0 "$OLD_PID" 2>/dev/null; then
        echo "Already running (PID $OLD_PID). To check progress:"
        echo "  tail -f $(ls -t $LOG_DIR/${COURSE}_*.log | head -1)"
        exit 1
    fi
fi

# Activate conda environment
source /home/gilrubin/miniconda/etc/profile.d/conda.sh
conda activate musetalk
export CUDA_HOME=$CONDA_PREFIX

echo "Starting batch for: $COURSE"
echo "Log: $LOG"

cd "$MUSETALK_DIR"
nohup python batch_generate.py "$@" >> "$LOG" 2>&1 &

PID=$!
echo $PID > "$PID_FILE"
echo "PID: $PID"
echo ""
echo "To follow progress:  tail -f $LOG"
echo "To check status:     kill -0 $PID && echo running || echo done"
