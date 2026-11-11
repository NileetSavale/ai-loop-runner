#!/bin/bash
# Runs on the VM: setups on many bugs, a batch at a time, since the disk can't hold every bug's image at once.
# Each batch: build its images with SWE-bench's gold run (which also checks the official fix natively), run the
# setups, then remove the images.
#
#     bash benchmarks/cloud/fresh_run.sh BUGS_FILE BATCH_SIZE -- <swe_run options without --instances>
#
# BUGS_FILE has one instance id per line. Results go to benchmarks/results/ as one file per batch; a batch that
# already has a "Saved to" line in its log is skipped, so the script can be restarted after a stop.
set -uo pipefail
BUGS=${1:?bugs file}; SIZE=${2:?batch size}; shift 2; [ "${1:-}" = "--" ] && shift
SWE=/data/swe
LOGS=~/fresh_logs; mkdir -p "$LOGS"
cd ~/loop_runner/backend
mapfile -t IDS < <(grep -v '^\s*$' "$BUGS")

for ((start = 0; start < ${#IDS[@]}; start += SIZE)); do
  batch=("${IDS[@]:start:SIZE}"); n=$((start / SIZE))
  log="$LOGS/batch-$n.log"
  if grep -q '^Saved to ' "$log" 2>/dev/null; then echo "batch $n done already"; continue; fi
  echo "batch $n: ${#batch[@]} bugs, building images $(date)"
  (cd $SWE && DOCKER_DEFAULT_PLATFORM=linux/amd64 venv/bin/swebench eval verified --gold \
     $(printf -- '-i %s ' "${batch[@]}") --run-id "fresh-gold-$n" --task-repo ./swe-bench-tasks -j 4 \
     > "$LOGS/build-$n.log" 2>&1)
  echo "batch $n: running $(date)"
  SWEBENCH_DIR=$SWE .venv/bin/python -m benchmarks.swe_run --yes --instances "$(IFS=,; echo "${batch[*]}")" "$@" \
    > "$log" 2>&1
  grep -E '^Saved to |^Stopping' "$log"
  docker rmi -f $(printf 'swebench/sweb.eval.x86_64.%s:latest ' $(printf '%s\n' "${batch[@]}" | sed 's/__/_1776_/' | tr A-Z a-z)) \
    > /dev/null 2>&1
  docker image prune -f > /dev/null 2>&1; docker builder prune -af > /dev/null 2>&1
  if grep -q '^Stopping' "$log"; then echo "batch $n hit the spending cap; stopping"; exit 1; fi
done
echo "all batches done $(date)"
