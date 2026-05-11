#!/usr/bin/env bash
# verify_cache.sh — Check what's in the wheel cache

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
USB_ROOT="$(cd "$SCRIPT_DIR/../../../.." && pwd)"
WHEELS_DIR="$USB_ROOT/Shared/cdw/wheels"

echo "=== Wheel Cache Contents ==="
echo "Location: $WHEELS_DIR"
echo ""

if [ ! -d "$WHEELS_DIR" ] || [ -z "$(ls -A "$WHEELS_DIR" 2>/dev/null)" ]; then
  echo "Cache is empty. Run sync_wheels.sh first."
  exit 1
fi

ls -lh "$WHEELS_DIR" | tail -n +2
echo ""
echo "Total: $(ls "$WHEELS_DIR" | wc -l | tr -d ' ') files"
