#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUTPUT_DIR="$ROOT_DIR/outputs"
CONFIG_PATH="$ROOT_DIR/config.demo.yaml"

mkdir -p "$OUTPUT_DIR"

python3 "$ROOT_DIR/build_tv_channel_sheet.py" "$CONFIG_PATH"

if [ -f "$OUTPUT_DIR/demo_tv_channels.pdf" ]; then
  echo "Demo PDF created at $OUTPUT_DIR/demo_tv_channels.pdf"
else
  echo "Expected demo PDF not found in $OUTPUT_DIR" >&2
  exit 1
fi
