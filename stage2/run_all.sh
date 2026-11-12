#!/usr/bin/env bash
# Stage 2 preprocessing only. Does not train, rebuild Stage 1, or download rain.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
if [[ -x "$ROOT/.venv/bin/python" ]]; then
  PYTHON="$ROOT/.venv/bin/python"
else
  PYTHON="${PYTHON:-python3}"
fi
echo "repo root: $ROOT"
echo "python: $PYTHON"
"$PYTHON" stage2/aggregate_ward_terrain.py
"$PYTHON" stage2/clean_complaints.py
"$PYTHON" stage2/build_rain_features.py
"$PYTHON" stage2/build_ward_days.py
"$PYTHON" stage2/make_temporal_splits.py
echo "Stage 2 preprocessing finished. Models were not trained."
