#!/bin/bash
set -e
cd -- "$(dirname -- "$0")"
if [ ! -x translation/.venv/bin/python ]; then
  echo 'Run bash setup.command with native Python 3.11 first.'
  exit 1
fi
translation/.venv/bin/python scripts/doctor.py
exec translation/.venv/bin/python app/floating_asr.py
