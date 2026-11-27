#!/usr/bin/env bash
# Set up the Python virtual environment using uv (designed for nvidia/13.1.2-cudnn-devel-ubuntu24.04 or local macOS/Linux).
set -euo pipefail
cd "$(dirname "$0")"

if ! command -v uv >/dev/null 2>&1; then
  echo "ERROR: 'uv' is required but not found on PATH." >&2
  exit 1
fi

uv venv --clear .venv
# shellcheck disable=SC1091
source .venv/bin/activate
uv pip install -r requirements.txt


echo "Environment ready in .venv. Activate with: source .venv/bin/activate"
