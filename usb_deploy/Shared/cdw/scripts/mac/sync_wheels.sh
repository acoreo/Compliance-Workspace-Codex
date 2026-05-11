#!/usr/bin/env bash
# sync_wheels.sh — Run on Mac to populate the wheel cache for Windows offline install
# Usage: ./sync_wheels.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
USB_ROOT="$(cd "$SCRIPT_DIR/../../../.." && pwd)"
WHEELS_DIR="$USB_ROOT/Shared/cdw/wheels"
REQS="$USB_ROOT/Shared/cdw/requirements/cdw.txt"

echo "=== CDW Wheel Sync ==="
echo "Target: $WHEELS_DIR"
echo "Platform: win_amd64 / Python 3.12 / cp312"
echo ""

mkdir -p "$WHEELS_DIR"

python3 -m pip download \
  --platform win_amd64 \
  --python-version 3.12 \
  --abi cp312 \
  --only-binary=:all: \
  --dest "$WHEELS_DIR" \
  -r "$REQS"

echo ""
echo "Done. $(ls "$WHEELS_DIR" | wc -l | tr -d ' ') wheels cached."
