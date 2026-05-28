#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."
source .venv/bin/activate
python -m compileall app run.py launcher.py
python -m pip check
pyinstaller WaterLevelMonitorStudio.spec --noconfirm
