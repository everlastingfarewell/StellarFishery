#!/usr/bin/env bash
# Start the interactive ocean demo with the project virtualenv (and a usable
# Vulkan driver). Extra arguments are passed to the demo.
set -euo pipefail

root=$(cd -- "$(dirname -- "$0")" && pwd)
cd "$root"
. "$root/tools/env.sh"

if [ ! -x "$root/.venv/bin/python" ]; then
    echo "error: .venv is missing, create it first:" >&2
    echo "  uv venv --python 3.13 .venv" >&2
    echo "  uv pip install --python .venv/bin/python -r requirements.txt" >&2
    exit 1
fi

# examples/ is a package, so the repository root has to be importable.
PYTHONPATH="$root${PYTHONPATH:+:$PYTHONPATH}" \
    exec "$root/.venv/bin/python" -m examples.demo "$@"
