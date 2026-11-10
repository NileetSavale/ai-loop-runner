#!/bin/bash
# Copy the results back from the VM, then delete the VM and its disk, so nothing keeps billing. Run on the Mac, from
# backend/.
#
#     PROJECT=my-project bash benchmarks/cloud/gcp_down.sh
set -euo pipefail

: "${PROJECT:?Set PROJECT to your Google Cloud project id}"
ZONE=${ZONE:-us-central1-a}
NAME=${NAME:-swe-runner}
COPY=$(mktemp -d)

# Back into benchmarks/results, so the Mac's spending cap counts what the VM spent. Files the Mac has stay as they are.
gcloud compute scp --project "$PROJECT" --zone "$ZONE" --recurse \
  "$NAME":~/loop_runner/backend/benchmarks/results "$NAME":/data/swe/labels.jsonl "$COPY"/
cp -n "$COPY"/results/*.json benchmarks/results/
cp "$COPY"/labels.jsonl "benchmarks/results/labels-cloud-$(date +%Y%m%d).jsonl"
echo "Results copied to benchmarks/results."
read -r -p "Delete $NAME and its disk? This can't be undone. [y/N] " answer
[ "$answer" = y ] && gcloud compute instances delete "$NAME" --project "$PROJECT" --zone "$ZONE" --delete-disks all
