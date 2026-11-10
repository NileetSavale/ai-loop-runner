#!/bin/bash
# Create a Google Cloud VM for SWE-bench runs and set it up. Run on the Mac, from backend/, after `gcloud auth login`.
#
#     PROJECT=my-project bash benchmarks/cloud/gcp_up.sh
#
# Creates billable resources: the VM (n2-standard-8, about $0.40/hour while running) and its disk (600 GB, about
# $60/month even while the VM is stopped). benchmarks/cloud/gcp_down.sh deletes both. The free trial allows 8 running
# vCPUs; MACHINE=n2-standard-16 needs the billing account upgraded first.
#
# Only committed code (a git bundle of HEAD) and the saved results go over, never .env: copy the API key yourself
# afterwards, as printed at the end. Nothing is pushed anywhere.
set -euo pipefail

: "${PROJECT:?Set PROJECT to your Google Cloud project id}"
ZONE=${ZONE:-us-central1-a}
NAME=${NAME:-swe-runner}
MACHINE=${MACHINE:-n2-standard-8}
DISK_GB=${DISK_GB:-600}
HERE=$(cd "$(dirname "$0")" && pwd)
BACKEND=$(cd "$HERE/../.." && pwd)

if [ -n "$(git -C "$BACKEND" status --porcelain)" ]; then
  echo "Uncommitted changes in the repo; only committed code goes to the VM. Commit first." >&2
  exit 1
fi

gcloud config set project "$PROJECT"
gcloud services enable compute.googleapis.com
gcloud compute instances create "$NAME" --zone "$ZONE" --machine-type "$MACHINE" \
  --image-family ubuntu-2404-lts-amd64 --image-project ubuntu-os-cloud \
  --boot-disk-size "${DISK_GB}GB" --boot-disk-type pd-balanced

BUNDLE=$(mktemp -d)/loop_runner.bundle
git -C "$BACKEND" bundle create "$BUNDLE" HEAD
# A fresh VM takes a minute or so to accept SSH
for i in $(seq 1 20); do gcloud compute ssh "$NAME" --zone "$ZONE" --command true && break; sleep 15; done
gcloud compute scp --zone "$ZONE" "$BUNDLE" "$HERE/vm_setup.sh" "$NAME":~
gcloud compute ssh "$NAME" --zone "$ZONE" --command "bash ~/vm_setup.sh ~/loop_runner.bundle"
# Results aren't in git, but the overall spending cap is counted from them, so the VM must start with the Mac's
gcloud compute scp --zone "$ZONE" "$BACKEND"/benchmarks/results/*.json "$NAME":~/loop_runner/backend/benchmarks/results/

cat <<EOF

The VM is set up. Next, from backend/ on the Mac:
  1. Copy the API key (only you do this step):
       gcloud compute scp --zone $ZONE .env $NAME:~/loop_runner/backend/.env
  2. Build the images and label the bugs (no API cost; hours for all 500):
       gcloud compute ssh $NAME --zone $ZONE
       cd ~/loop_runner/backend && SWEBENCH_DIR=/data/swe .venv/bin/python -m benchmarks.swe_label --sample 10
  3. Delete everything when done:
       PROJECT=$PROJECT bash benchmarks/cloud/gcp_down.sh
EOF
