#!/bin/bash
# Runs on the VM (gcp_up.sh copies it over): Docker, SWE-bench in /data/swe, and the backend from a git bundle.
#
#     bash vm_setup.sh ~/loop_runner.bundle
#
# Mirrors the Mac's setup (install-swe.sh on the SSD), with SWE-bench at /data/swe instead of the SSD, so runs need
# SWEBENCH_DIR=/data/swe. The images are native here: no emulation.
set -euo pipefail
BUNDLE=${1:?Pass the git bundle}

sudo apt-get update -q
sudo apt-get install -yq docker.io git curl
sudo usermod -aG docker "$USER"
curl -LsSf https://astral.sh/uv/install.sh | sh
export PATH="$HOME/.local/bin:$PATH"

sudo mkdir -p /data/swe && sudo chown "$USER" /data/swe
cd /data/swe
uv venv --python 3.12 venv
git clone https://github.com/SWE-bench/SWE-bench.git src
git clone --depth 1 https://github.com/SWE-bench/swe-bench-tasks.git swe-bench-tasks
uv pip install --python venv/bin/python -e src

git clone "$BUNDLE" ~/loop_runner
cd ~/loop_runner/backend
mkdir -p benchmarks/results
uv venv --python 3.13 .venv
uv pip install --python .venv/bin/python -r requirements.txt pytest pytest-asyncio
.venv/bin/python -m pytest tests -q -x

echo "Set up. Log out and back in once, so this user can run docker without sudo."
