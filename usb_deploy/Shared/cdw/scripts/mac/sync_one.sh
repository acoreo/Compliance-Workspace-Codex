#!/usr/bin/env bash
# sync_one.sh — Add one package to the wheel cache
# Usage: ./sync_one.sh "package>=version"

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
USB_ROOT="$(cd "$SCRIPT_DIR/../../../.." && pwd)"
WHEELS_DIR="$USB_ROOT/Shared/cdw/wheels"

if [ -z "${1:-}" ]; then
  echo "Usage: $0 \"package>=version\""
  exit 1
fi

mkdir -p "$WHEELS_DIR"

pip download \
  --platform win_amd64 \
  --python-version 3.12 \
  --abi cp312 \
  --only-binary=:all: \
  --dest "$WHEELS_DIR" \
  "$1"

echo "Done."
