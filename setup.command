#!/bin/bash
set -e
cd -- "$(dirname -- "$0")"
python=python3
if [ -x translation/.venv/bin/python ]; then
  python=translation/.venv/bin/python
fi
exec "$python" scripts/setup.py "$@"
