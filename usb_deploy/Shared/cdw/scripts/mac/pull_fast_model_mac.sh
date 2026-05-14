#!/bin/bash
# =============================================================================
# pull_fast_model_mac.sh - Pull a smaller Ollama model into the USB model store.
#
# Run this on the Mac with BK-1 mounted. It keeps model downloads off the Dell:
#
#   /Volumes/BK-1/USB-Uncensored-LLM/Shared/cdw/scripts/mac/pull_fast_model_mac.sh [model]
#
# Default model: llama3.2:3b
# =============================================================================

set -euo pipefail

RED='\033[0;31m'; GREEN='\033[0;32m'; CYAN='\033[0;36m'; BOLD='\033[1m'; RESET='\033[0m'
info()    { echo -e "${CYAN}  -> $*${RESET}"; }
success() { echo -e "${GREEN}  OK: $*${RESET}"; }
error()   { echo -e "${RED}  ERROR: $*${RESET}"; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
USB_ROOT="$(cd "$SCRIPT_DIR/../../../.." && pwd)"
MODEL="${1:-llama3.2:3b}"
BASE="$USB_ROOT/Shared"
OLLAMA_DATA="$BASE/models/ollama_data"
OLLAMA_MAC="$BASE/bin/ollama-darwin"
OLLAMA_HOST_PORT="${OLLAMA_HOST_PORT:-11435}"
OLLAMA_HOST_URL="127.0.0.1:$OLLAMA_HOST_PORT"

echo -e "${BOLD}"
echo "============================================================"
echo "  CDW Mac-Side Fast Model Pull"
echo "  USB root   : $USB_ROOT"
echo "  Model      : $MODEL"
echo "  Store      : $OLLAMA_DATA"
echo -e "============================================================${RESET}"

if [[ ! -x "$OLLAMA_MAC" ]]; then
  error "ollama-darwin not found or not executable at:"
  error "$OLLAMA_MAC"
  error "Run bash usb_deploy/setup_usb.sh /Volumes/BK-1 first."
  exit 1
fi

mkdir -p "$OLLAMA_DATA"

stale_pid=$(lsof -ti tcp:"$OLLAMA_HOST_PORT" 2>/dev/null || true)
if [[ -n "$stale_pid" ]]; then
  info "Stopping existing process on port $OLLAMA_HOST_PORT (PID $stale_pid)..."
  kill "$stale_pid" 2>/dev/null || true
  sleep 2
fi

info "Starting temporary Ollama server on Mac with USB model store..."
OLLAMA_MODELS="$OLLAMA_DATA" \
OLLAMA_HOST="0.0.0.0:$OLLAMA_HOST_PORT" \
  "$OLLAMA_MAC" serve >/tmp/cdw_fast_model_ollama.log 2>&1 &
OLLAMA_PID=$!

cleanup() {
  kill "$OLLAMA_PID" 2>/dev/null || true
  wait "$OLLAMA_PID" 2>/dev/null || true
}
trap cleanup EXIT

sleep 5
if ! kill -0 "$OLLAMA_PID" 2>/dev/null; then
  error "Ollama server failed to start. Check /tmp/cdw_fast_model_ollama.log."
  exit 1
fi

info "Pulling $MODEL into USB model store..."
OLLAMA_MODELS="$OLLAMA_DATA" \
OLLAMA_HOST="$OLLAMA_HOST_URL" \
  "$OLLAMA_MAC" pull "$MODEL"

success "Model pull complete."
info "Registered models in USB store:"
OLLAMA_MODELS="$OLLAMA_DATA" \
OLLAMA_HOST="$OLLAMA_HOST_URL" \
  "$OLLAMA_MAC" list
