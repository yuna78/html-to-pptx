#!/usr/bin/env bash
# Create the Python virtualenv html-to-pptx runs in. Idempotent: re-running is cheap.
# 创建 html-to-pptx 所用的 Python 虚拟环境。幂等，可重复运行。
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="$DIR/.venv"
PY="${PYTHON:-python3}"

if ! command -v "$PY" >/dev/null 2>&1; then
  echo "[setup] Python 3.11+ not found. Install it first (macOS: brew install python)." >&2
  exit 1
fi

if [ ! -x "$VENV/bin/python" ]; then
  echo "[setup] creating venv: $VENV"
  "$PY" -m venv "$VENV"
fi

if "$VENV/bin/python" -c "import pptx, bs4" >/dev/null 2>&1; then
  echo "[setup] dependencies already present, skipping install."
else
  echo "[setup] installing dependencies (python-pptx, beautifulsoup4)…"
  "$VENV/bin/pip" install --quiet --upgrade pip
  "$VENV/bin/pip" install --quiet -r "$DIR/requirements.txt"
fi

echo "[setup] environment check:"
"$VENV/bin/python" "$DIR/convert.py" --doctor
