#!/bin/bash
# run_all.sh - Run multiple courses sequentially in one background job.
# Usage: ./run_all.sh

MUSETALK_DIR="/home/gilrubin/MuseTalk"
LOG_DIR="$MUSETALK_DIR/logs"
mkdir -p "$LOG_DIR"

TIMESTAMP=$(date +%Y%m%d_%H%M%S)
LOG="$LOG_DIR/all_courses_${TIMESTAMP}.log"
PID_FILE="$LOG_DIR/all_courses.pid"

# Check if already running
if [ -f "$PID_FILE" ]; then
    OLD_PID=$(cat "$PID_FILE")
    if kill -0 "$OLD_PID" 2>/dev/null; then
        echo "Already running (PID $OLD_PID). To check progress:"
        echo "  tail -f $(ls -t $LOG_DIR/all_courses_*.log | head -1)"
        exit 1
    fi
fi

# Activate conda environment
source /home/gilrubin/miniconda/etc/profile.d/conda.sh
conda activate musetalk
export CUDA_HOME=$CONDA_PREFIX

echo "Starting all courses sequentially"
echo "Log: $LOG"
echo ""

cd "$MUSETALK_DIR"

nohup bash -c "
source /home/gilrubin/miniconda/etc/profile.d/conda.sh
conda activate musetalk
export CUDA_HOME=\$CONDA_PREFIX
cd $MUSETALK_DIR

echo '=== [1/2] Starting: the_disengaged_kinesthetic ==='
python batch_generate.py the_disengaged_kinesthetic
echo '=== [1/2] Done: the_disengaged_kinesthetic ==='

echo '=== [2/2] Starting: the_autonomous_architect ==='
python batch_generate.py the_autonomous_architect
echo '=== [2/2] Done: the_autonomous_architect ==='

echo '=== All courses complete ==='
" >> "$LOG" 2>&1 &

PID=$!
echo $PID > "$PID_FILE"
echo "PID: $PID"
echo ""
echo "To follow progress:  tail -f $LOG"
echo "To check status:     kill -0 $PID && echo running || echo done"
