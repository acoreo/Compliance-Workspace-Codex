#!/usr/bin/env bash
# start_env.sh — Start a Mac dev shell with the CDW project on PYTHONPATH

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
USB_ROOT="$(cd "$SCRIPT_DIR/../../../.." && pwd)"
CDW_SRC="$USB_ROOT/Shared/cdw/projects/cdw"

export PYTHONPATH="$CDW_SRC:${PYTHONPATH:-}"

echo "CDW dev shell — PYTHONPATH set to $CDW_SRC"
echo "Run: python main.py"
echo ""

exec bash
