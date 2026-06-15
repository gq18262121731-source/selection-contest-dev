#!/usr/bin/env bash
set -e

if [ -z "${CONDA_PREFIX:-}" ]; then
  echo "This project is configured to run inside the 'health' conda environment." >&2
  exit 1
fi

"$CONDA_PREFIX/python" -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
