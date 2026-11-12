#!/usr/bin/env bash
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
"$PYTHON" stage1/build_flood_points.py
"$PYTHON" stage1/build_wards.py
"$PYTHON" stage1/label_nodes.py
"$PYTHON" stage1/sanity_check.py
"$PYTHON" stage1/add_drain_features.py
"$PYTHON" stage1/export_for_colab.py
echo "Stage 1 data prep finished."
