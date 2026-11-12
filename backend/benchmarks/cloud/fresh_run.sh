#!/bin/bash
# Runs on the VM: setups on many bugs, a batch at a time, since the disk can't hold every bug's image at once.
# Each batch: build its images with SWE-bench's gold run (which also checks the official fix natively), run each
# stage on them, then remove the images. Every stage runs while the images exist, so each image is built once.
#
#     bash benchmarks/cloud/fresh_run.sh BUGS_FILE BATCH_SIZE -- <stage 1 swe_run options> [-- <stage 2 options> ...]
#
# Stage options are swe_run's, without --instances. A stage starting with `--only FILE` runs only on the batch's bugs
# that are listed in FILE. BUGS_FILE and FILE have one instance id per line. Results go to benchmarks/results/ as
# one file per batch and stage; a stage whose log already has a "Saved to" line is skipped, and so is a build whose
# log has SWE-bench's "Report written to" line, so the script can be restarted after a stop. BUILD_JOBS sets how many images build at once (default 6: each build is mostly one core
# setting up its environment).
set -uo pipefail
BUGS=${1:?bugs file}; SIZE=${2:?batch size}; shift 2; [ "${1:-}" = "--" ] && shift
SWE=/data/swe
LOGS=${LOGS:-~/fresh_logs}; mkdir -p "$LOGS"
cd ~/loop_runner/backend
mapfile -t IDS < <(grep -v '^\s*$' "$BUGS")

# Split the remaining arguments into stages at each "--", joined by a separator that can't appear in an option
STAGES=(); stage=""
for arg in "$@"; do
  if [ "$arg" = "--" ]; then STAGES+=("$stage"); stage=""; else stage+="$arg"$'\x1f'; fi
done
STAGES+=("$stage")

for ((start = 0; start < ${#IDS[@]}; start += SIZE)); do
  batch=("${IDS[@]:start:SIZE}"); n=$((start / SIZE))
  pending=0
  for k in "${!STAGES[@]}"; do grep -q '^Saved to ' "$LOGS/batch-$n-s$k.log" 2>/dev/null || pending=1; done
  if [ $pending = 0 ]; then echo "batch $n done already"; continue; fi
  if grep -q '^Report written to ' "$LOGS/build-$n.log" 2>/dev/null; then echo "batch $n: images built already"
  else echo "batch $n: ${#batch[@]} bugs, building images $(date)"
  (cd $SWE && DOCKER_DEFAULT_PLATFORM=linux/amd64 venv/bin/swebench eval verified --gold \
     $(printf -- '-i %s ' "${batch[@]}") --run-id "fresh-gold-$n" --task-repo ./swe-bench-tasks -j "${BUILD_JOBS:-6}" \
     > "$LOGS/build-$n.log" 2>&1); fi
  stopped=0
  for k in "${!STAGES[@]}"; do
    log="$LOGS/batch-$n-s$k.log"
    if grep -q '^Saved to ' "$log" 2>/dev/null; then continue; fi
    IFS=$'\x1f' read -r -a opts <<< "${STAGES[$k]}"
    bugs=("${batch[@]}")
    if [ "${opts[0]:-}" = "--only" ]; then
      mapfile -t bugs < <(printf '%s\n' "${batch[@]}" | grep -Fxf "${opts[1]}"); opts=("${opts[@]:2}")
      if [ ${#bugs[@]} = 0 ]; then echo "Saved to (no bugs in this batch)" > "$log"; continue; fi
    fi
    echo "batch $n stage $k: ${#bugs[@]} bugs, running $(date)"
    SWEBENCH_DIR=$SWE .venv/bin/python -m benchmarks.swe_run --yes --instances "$(IFS=,; echo "${bugs[*]}")" \
      "${opts[@]}" > "$log" 2>&1
    grep -E '^Saved to |^Stopping' "$log"
    if grep -q '^Stopping' "$log"; then echo "batch $n stage $k hit its spending cap"; stopped=1; fi
  done
  docker rmi -f $(printf 'swebench/sweb.eval.x86_64.%s:latest ' $(printf '%s\n' "${batch[@]}" | sed 's/__/_1776_/' | tr A-Z a-z)) \
    > /dev/null 2>&1
  docker image prune -f > /dev/null 2>&1; docker builder prune -af > /dev/null 2>&1
  if [ $stopped = 1 ]; then echo "stopping after batch $n"; exit 1; fi
done
echo "all batches done $(date)"
