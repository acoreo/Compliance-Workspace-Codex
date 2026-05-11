#!/bin/bash
# =============================================================================
# setup_usb.sh — CDW (Compliance Discovery Workspace) USB staging script
#
# Usage:
#   bash setup_usb.sh [/Volumes/DRIVE_NAME]
#
# Defaults to /Volumes/BK-1 if no argument is given.
#
# Re-run safe: every step checks if its work is already done and skips it.
# =============================================================================

set -euo pipefail

# ─── Colour helpers ──────────────────────────────────────────────────────────
RED='\033[0;31m'; YELLOW='\033[1;33m'; GREEN='\033[0;32m'
CYAN='\033[0;36m'; BOLD='\033[1m'; RESET='\033[0m'

info()    { echo -e "${CYAN}  →  $*${RESET}"; }
success() { echo -e "${GREEN}  ✓  $*${RESET}"; }
warn()    { echo -e "${YELLOW}  ⚠  $*${RESET}"; }
error()   { echo -e "${RED}  ✗  $*${RESET}"; }
header()  { echo -e "\n${BOLD}$*${RESET}"; }

# ─── Paths ───────────────────────────────────────────────────────────────────
USB="${1:-/Volumes/BK-1}"
BASE="$USB/USB-Uncensored-LLM/Shared"
MODELS_DIR="$BASE/models"
BIN_DIR="$BASE/bin"
CDW_DIR="$BASE/cdw"
OLLAMA_DATA="$MODELS_DIR/ollama_data"
GGUF_FILE="$MODELS_DIR/NemoMix-Unleashed-12B-Q4_K_M.gguf"
MODELFILE="$MODELS_DIR/Modelfile-nemomix-local"
OLLAMA_MAC="$BIN_DIR/ollama-darwin"
OLLAMA_WIN="$BIN_DIR/ollama.exe"
PYTHON_DIR="$CDW_DIR/python"
WHEELS_DIR="$CDW_DIR/wheels"
REQ_FILE="$HOME/Projects/Compliance-Workspace/usb_deploy/Shared/cdw/requirements/cdw.txt"
SRC_DIR="$HOME/Projects/Compliance-Workspace"
SCRIPTS_WIN="$CDW_DIR/scripts/windows"

OLLAMA_PORT=11435
MIN_FREE_GB=25
GGUF_MIN_MB=7000
WHEEL_MIN_COUNT=50

# ─── Step result tracking ─────────────────────────────────────────────────────
# Parallel arrays instead of `declare -A` so this works on macOS bash 3.2.
STEP_KEYS=()
STEP_VALUES=()

# Find index of a key in STEP_KEYS; prints index or -1 if not found.
_step_index() {
  local needle="$1" i
  for i in "${!STEP_KEYS[@]}"; do
    if [[ "${STEP_KEYS[$i]}" == "$needle" ]]; then
      echo "$i"
      return 0
    fi
  done
  echo "-1"
  return 1
}

step_status_set() {
  local key="$1" value="$2" idx
  idx=$(_step_index "$key")
  if [[ "$idx" == "-1" ]]; then
    STEP_KEYS+=("$key")
    STEP_VALUES+=("$value")
  else
    STEP_VALUES[$idx]="$value"
  fi
}

step_status_get() {
  local key="$1" default="${2-}" idx
  idx=$(_step_index "$key")
  if [[ "$idx" == "-1" ]]; then
    echo "$default"
  else
    echo "${STEP_VALUES[$idx]}"
  fi
}

# ─── Step runner helper ───────────────────────────────────────────────────────
# Usage: run_step <key> <label> <function>
run_step() {
  local key="$1" label="$2" fn="$3" current
  header "[$key] $label"
  if $fn; then
    current=$(step_status_get "$key")
    # Preserve SKIPPED if the step marked itself; otherwise mark DONE.
    # (Status is pre-initialised to PENDING in main, so we can't rely on
    # ${current:-DONE} — PENDING is non-empty and would persist.)
    if [[ "$current" != "SKIPPED" ]]; then
      step_status_set "$key" "DONE"
    fi
  else
    step_status_set "$key" "FAILED"
    error "Step $key failed."
  fi
}

mark_skipped() { step_status_set "$1" "SKIPPED"; }

abort_summary() {
  local msg="$1"
  echo ""
  error "$msg"
  echo -e "${RED}${BOLD}Aborting USB staging before any download or sync steps.${RESET}"
  echo "Fix the issue above and re-run:"
  echo "  bash usb_deploy/setup_usb.sh /Volumes/BK-1"
  echo ""
}

# =============================================================================
# [1/8] Validate USB
# =============================================================================
step_validate_usb() {
  # Check mount point exists
  if [[ ! -d "$USB" ]]; then
    error "Mount point '$USB' does not exist."
    error "Is the USB drive plugged in? Try: diskutil list"
    return 1
  fi

  # Check writable
  if ! touch "$USB/.cdw_write_test" 2>/dev/null; then
    error "'$USB' is not writable. Check disk permissions."
    return 1
  fi
  rm -f "$USB/.cdw_write_test"
  success "USB mount point '$USB' is writable."

  # Free space check (macOS df outputs 512-byte blocks)
  local free_gb
  free_gb=$(df -g "$USB" 2>/dev/null | awk 'NR==2 {print $4}')
  if [[ -n "$free_gb" ]]; then
    info "USB free space: ${free_gb} GB"
    if (( free_gb < MIN_FREE_GB )); then
      warn "Only ${free_gb} GB free — recommended minimum is ${MIN_FREE_GB} GB."
      warn "The GGUF model alone is ~8 GB. Proceeding anyway."
    fi
  else
    warn "Could not determine free space."
  fi

  # Create base directory tree
  info "Creating base directories..."
  mkdir -p "$MODELS_DIR" "$BIN_DIR" "$CDW_DIR/requirements" "$WHEELS_DIR" \
           "$CDW_DIR/projects/cdw" "$SCRIPTS_WIN"
  success "Directory structure ready."
}

# =============================================================================
# [2/8] Download NemoMix 12B GGUF
# =============================================================================
step_download_gguf() {
  local url="https://huggingface.co/bartowski/NemoMix-Unleashed-12B-GGUF/resolve/main/NemoMix-Unleashed-12B-Q4_K_M.gguf"

  # Skip if file already exists and is large enough
  if [[ -f "$GGUF_FILE" ]]; then
    local size_mb
    size_mb=$(du -m "$GGUF_FILE" 2>/dev/null | cut -f1)
    if (( size_mb >= GGUF_MIN_MB )); then
      success "GGUF already exists (${size_mb} MB ≥ ${GGUF_MIN_MB} MB). Skipping."
      mark_skipped "2/8"
      return 0
    else
      warn "GGUF found but only ${size_mb} MB — resuming download."
    fi
  fi

  info "Downloading NemoMix-Unleashed-12B-Q4_K_M.gguf..."
  info "This is ~8 GB and may take a while depending on your connection."
  if curl -L -C - --progress-bar -o "$GGUF_FILE" "$url"; then
    local final_mb
    final_mb=$(du -m "$GGUF_FILE" 2>/dev/null | cut -f1)
    success "GGUF downloaded (${final_mb} MB)."
  else
    error "curl failed downloading GGUF."
    return 1
  fi
}

# =============================================================================
# [3/8] Download Ollama binaries
# =============================================================================
step_download_ollama() {
  local mac_url="https://github.com/ollama/ollama/releases/latest/download/ollama-darwin"
  local win_url="https://github.com/ollama/ollama/releases/latest/download/ollama-windows-amd64.zip"
  local win_zip="/tmp/ollama-windows-amd64.zip"
  local any_failed=0

  # --- macOS binary ---
  if [[ -f "$OLLAMA_MAC" ]]; then
    success "ollama-darwin already exists. Skipping."
  else
    info "Downloading ollama-darwin..."
    if curl -L --progress-bar -o "$OLLAMA_MAC" "$mac_url"; then
      chmod +x "$OLLAMA_MAC"
      success "ollama-darwin downloaded and marked executable."
    else
      error "Failed to download ollama-darwin."
      any_failed=1
    fi
  fi

  # --- Windows binary ---
  if [[ -f "$OLLAMA_WIN" ]]; then
    success "ollama.exe already exists. Skipping."
  else
    info "Downloading ollama-windows-amd64.zip..."
    if curl -L --progress-bar -o "$win_zip" "$win_url"; then
      info "Extracting ollama.exe..."
      if unzip -j -o "$win_zip" "ollama.exe" -d "$BIN_DIR"; then
        success "ollama.exe extracted."
      else
        error "Failed to extract ollama.exe from zip."
        any_failed=1
      fi
      rm -f "$win_zip"
    else
      error "Failed to download ollama Windows zip."
      any_failed=1
    fi
  fi

  return $any_failed
}

# =============================================================================
# [4/8] Import NemoMix into Ollama model registry on USB
# =============================================================================
step_import_ollama_model() {
  local manifest_dir="$OLLAMA_DATA/manifests/registry.ollama.ai/library/nemomix-local"

  if [[ -d "$manifest_dir" ]]; then
    success "Ollama manifest for nemomix-local already exists. Skipping import."
    mark_skipped "4/8"
    return 0
  fi

  if [[ ! -f "$OLLAMA_MAC" ]]; then
    error "ollama-darwin not found at '$OLLAMA_MAC' — cannot import model."
    return 1
  fi

  if [[ ! -f "$GGUF_FILE" ]]; then
    error "GGUF model not found at '$GGUF_FILE' — cannot import model."
    return 1
  fi

  # Write Modelfile (path is relative — we'll cd into MODELS_DIR before running)
  info "Writing Modelfile..."
  cat > "$MODELFILE" <<'MODELFILE_EOF'
FROM ./NemoMix-Unleashed-12B-Q4_K_M.gguf
PARAMETER temperature 0.7
SYSTEM You are a NERC CIP compliance expert assistant.
MODELFILE_EOF
  success "Modelfile written to $MODELFILE"

  # Kill any stale ollama on our port
  info "Checking for stale ollama processes on port $OLLAMA_PORT..."
  local stale_pid
  stale_pid=$(lsof -ti tcp:$OLLAMA_PORT 2>/dev/null || true)
  if [[ -n "$stale_pid" ]]; then
    warn "Killing existing process on port $OLLAMA_PORT (PID $stale_pid)..."
    kill -9 "$stale_pid" 2>/dev/null || true
    sleep 2
  fi

  # Start ollama server in background
  info "Starting ollama server on port $OLLAMA_PORT..."
  OLLAMA_MODELS="$OLLAMA_DATA" \
  OLLAMA_HOST="0.0.0.0:$OLLAMA_PORT" \
    "$OLLAMA_MAC" serve &>/tmp/ollama_serve.log &
  local OLLAMA_PID=$!
  info "Ollama server started (PID $OLLAMA_PID). Waiting 5 seconds..."
  sleep 5

  # Verify server is up
  if ! kill -0 "$OLLAMA_PID" 2>/dev/null; then
    error "Ollama server failed to start. Check /tmp/ollama_serve.log."
    return 1
  fi

  # Run ollama create from inside the models directory
  info "Importing nemomix-local into Ollama registry (this may take several minutes)..."
  local import_ok=0
  (
    cd "$MODELS_DIR"
    OLLAMA_HOST="127.0.0.1:$OLLAMA_PORT" \
    OLLAMA_MODELS="$OLLAMA_DATA" \
      "$OLLAMA_MAC" create nemomix-local -f "$MODELFILE"
  ) && import_ok=1

  # Always kill background ollama
  info "Stopping ollama server..."
  kill "$OLLAMA_PID" 2>/dev/null || true
  wait "$OLLAMA_PID" 2>/dev/null || true

  if (( import_ok == 1 )); then
    success "nemomix-local imported successfully."
  else
    error "ollama create failed. Check /tmp/ollama_serve.log."
    return 1
  fi
}

# =============================================================================
# [5/8] Download Python 3.12 embeddable for Windows
# =============================================================================
step_download_python() {
  local url="https://www.python.org/ftp/python/3.12.9/python-3.12.9-embed-amd64.zip"
  local zip_path="/tmp/python-3.12.9-embed-amd64.zip"
  local pth_file="$PYTHON_DIR/python312._pth"

  if [[ -f "$PYTHON_DIR/python.exe" ]]; then
    success "python.exe already exists. Skipping."
    mark_skipped "5/8"
    return 0
  fi

  info "Downloading Python 3.12.9 embeddable package..."
  if ! curl -L --progress-bar -o "$zip_path" "$url"; then
    error "Failed to download Python embeddable zip."
    return 1
  fi

  info "Extracting to $PYTHON_DIR ..."
  mkdir -p "$PYTHON_DIR"
  if ! unzip -o "$zip_path" -d "$PYTHON_DIR"; then
    error "Failed to extract Python zip."
    rm -f "$zip_path"
    return 1
  fi

  # Enable site-packages by uncommenting 'import site' in python312._pth
  if [[ -f "$pth_file" ]]; then
    info "Enabling site-packages in python312._pth..."
    sed -i '' 's/#import site/import site/' "$pth_file"
    success "python312._pth patched."
  else
    warn "python312._pth not found — skipping patch."
  fi

  rm -f "$zip_path"
  success "Python 3.12 embeddable installed."
}

# =============================================================================
# [6/8] Download get-pip.py
# =============================================================================
step_download_getpip() {
  local target="$CDW_DIR/get-pip.py"
  local url="https://bootstrap.pypa.io/get-pip.py"

  if [[ -f "$target" ]]; then
    success "get-pip.py already exists. Skipping."
    mark_skipped "6/8"
    return 0
  fi

  info "Downloading get-pip.py..."
  if curl -L --progress-bar -o "$target" "$url"; then
    success "get-pip.py downloaded."
  else
    error "Failed to download get-pip.py."
    return 1
  fi
}

# =============================================================================
# [7/8] Download Windows pip wheels
# =============================================================================
step_download_wheels() {
  # Count existing wheels
  local existing
  existing=$(find "$WHEELS_DIR" -name "*.whl" 2>/dev/null | wc -l | tr -d ' ')

  # Also verify the bootstrapper packages (pip, setuptools, wheel) are present
  local has_pip has_setuptools has_wheel
  has_pip=$(find "$WHEELS_DIR" -name "pip-*.whl" 2>/dev/null | wc -l | tr -d ' ')
  has_setuptools=$(find "$WHEELS_DIR" -name "setuptools-*.whl" 2>/dev/null | wc -l | tr -d ' ')
  has_wheel=$(find "$WHEELS_DIR" -name "wheel-*.whl" 2>/dev/null | wc -l | tr -d ' ')

  if (( existing >= WHEEL_MIN_COUNT )) \
      && (( has_pip > 0 )) \
      && (( has_setuptools > 0 )) \
      && (( has_wheel > 0 )); then
    success "$existing .whl files already in wheels dir (≥ $WHEEL_MIN_COUNT) and pip/setuptools/wheel present. Skipping."
    mark_skipped "7/8"
    return 0
  fi

  if [[ ! -f "$REQ_FILE" ]]; then
    error "Requirements file not found: $REQ_FILE"
    return 1
  fi

  if ! command -v python3 &>/dev/null; then
    error "python3 not found on this Mac — cannot download wheels."
    return 1
  fi

  info "Downloading Windows wheels for requirements in $REQ_FILE ..."
  info "Platform: win_amd64 / Python 3.12"
  if python3 -m pip download \
      -r "$REQ_FILE" \
      --platform win_amd64 \
      --python-version 312 \
      --only-binary=:all: \
      -d "$WHEELS_DIR"; then
    local count
    count=$(find "$WHEELS_DIR" -name "*.whl" | wc -l | tr -d ' ')
    success "Downloaded $count CDW requirement wheel files."
  else
    error "pip download failed for CDW requirements."
    return 1
  fi

  # ── Bootstrappers + ALL Windows-conditional extras (single call) ─────────────
  # Why one call without --platform/--python-version:
  #   pip download -r requirements.txt --platform win_amd64 silently skips any
  #   package whose marker is sys_platform == "win32" because we're on macOS.
  #   By downloading them explicitly here (no platform filter), pip resolves the
  #   correct pure-Python (py3-none-any) wheels that install fine on Windows.
  #
  # Packages covered:
  #   pip / setuptools / wheel  — must be in the cache for get-pip.py bootstrap
  #   tzdata                    — pandas Windows conditional dep
  #   colorama                  — loguru / click / tqdm Windows conditional dep
  #   win32-setctime            — loguru Windows conditional dep
  #   pyreadline3               — readline substitute for Windows
  #   windows-curses            — curses for Windows (has a PyPI wheel)
  #
  # NOTE: win-unicode-console has NO wheel on PyPI — handled by stub below.
  info "Downloading bootstrappers + Windows-only conditional extras ..."
  info "  (pip, setuptools, wheel, tzdata, colorama, win32-setctime, pyreadline3, windows-curses)"
  if python3 -m pip download \
      pip setuptools wheel \
      tzdata colorama "win32-setctime" pyreadline3 windows-curses \
      --only-binary=:all: \
      -d "$WHEELS_DIR"; then
    local subtotal
    subtotal=$(find "$WHEELS_DIR" -name "*.whl" | wc -l | tr -d ' ')
    success "Bootstrappers + extras downloaded. Running total: $subtotal wheel files."
  else
    warn "Some extras had download errors — see output above."
    warn "(win_unicode_console failures are expected; stub wheel is created next.)"
  fi

  # ── win-unicode-console stub wheel ──────────────────────────────────────────
  # This package has no wheel on PyPI.  Python 3.12+ includes native Unicode
  # console support, so a no-op stub satisfies any import without side effects.
  info "Creating win_unicode_console stub wheel (no PyPI wheel exists)..."
  python3 - <<PYSTUB
import zipfile, hashlib, base64, os

wheels_dir = "$WHEELS_DIR"
wheel_path = os.path.join(wheels_dir, "win_unicode_console-0.5-py3-none-any.whl")

if os.path.exists(wheel_path):
    print("  stub already present — skipping.")
else:
    pkg_dir   = "win_unicode_console"
    dist_info = "win_unicode_console-0.5.dist-info"

    init_content = (
        b"# win-unicode-console stub\n"
        b"# Python 3.12+ has native unicode console support; this is a safe no-op.\n"
        b"def enable(*args, **kwargs): pass\n"
        b"def disable(*args, **kwargs): pass\n"
    )
    metadata_content = (
        b"Metadata-Version: 2.1\n"
        b"Name: win-unicode-console\n"
        b"Version: 0.5\n"
        b"Summary: Stub (Python 3.12+ has built-in Unicode console support).\n"
        b"License: MIT\n"
    )
    wheel_info = (
        b"Wheel-Version: 1.0\n"
        b"Generator: stub\n"
        b"Root-Is-Purelib: true\n"
        b"Tag: py3-none-any\n"
    )

    def sha256_record(data):
        digest = hashlib.sha256(data).digest()
        return "sha256=" + base64.urlsafe_b64encode(digest).decode().rstrip("=")

    files = {
        f"{pkg_dir}/__init__.py": init_content,
        f"{dist_info}/METADATA":  metadata_content,
        f"{dist_info}/WHEEL":     wheel_info,
    }

    record_lines = [
        f"{path},{sha256_record(content)},{len(content)}"
        for path, content in files.items()
    ]
    record_lines.append(f"{dist_info}/RECORD,,")
    record_content = "\n".join(record_lines).encode()

    with zipfile.ZipFile(wheel_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for path, content in files.items():
            zf.writestr(path, content)
        zf.writestr(f"{dist_info}/RECORD", record_content)

    print(f"  Created: {wheel_path}")
PYSTUB

  local total_final
  total_final=$(find "$WHEELS_DIR" -name "*.whl" | wc -l | tr -d ' ')
  success "Wheel cache complete — $total_final total .whl files."
}

# =============================================================================
# [8/8] Copy CDW source and launch scripts
# =============================================================================
step_copy_cdw() {
  local any_failed=0

  # Copy CDW source files (rsync skips unchanged files automatically)
  info "Syncing CDW source to USB..."
  if rsync -a \
      --exclude='__pycache__' \
      --exclude='*.pyc' \
      --exclude='.git' \
      --exclude='data/' \
      "$SRC_DIR/." \
      "$CDW_DIR/projects/cdw/"; then
    success "CDW source synced."
  else
    error "rsync failed for CDW source."
    any_failed=1
  fi

  # Copy requirements file
  info "Copying requirements file..."
  if cp "$REQ_FILE" "$CDW_DIR/requirements/cdw.txt"; then
    success "requirements/cdw.txt copied."
  else
    error "Failed to copy requirements file."
    any_failed=1
  fi

  # ── Windows batch scripts ────────────────────────────────────────────────────
  mkdir -p "$SCRIPTS_WIN"

  # install_offline.bat — always generated inline so the flags are guaranteed
  # correct regardless of what the source copy says.
  # Key: --prefer-binary (not --only-binary=:all:) so pip can fall back to
  # building from sdist for any package that lacks a pre-built wheel.
  info "Writing install_offline.bat (--prefer-binary)..."
  cat > "$SCRIPTS_WIN/install_offline.bat" <<'BAT_EOF'
@echo off
setlocal EnableDelayedExpansion

:: ─── CDW Offline Installer ───────────────────────────────────────────────────
:: Bootstraps pip from the local wheel cache, then installs all CDW requirements
:: with no internet access required.
::
:: Layout expected on the USB drive:
::   USB-Uncensored-LLM\Shared\cdw\
::     python\          — Python 3.12 embeddable
::     wheels\          — pre-downloaded .whl files
::     requirements\    — cdw.txt
::     get-pip.py
::     scripts\windows\ — this script lives here

set "SCRIPT_DIR=%~dp0"
set "CDW_DIR=%SCRIPT_DIR%..\..\\"
set "PYTHON=%CDW_DIR%python\python.exe"
set "WHEELS=%CDW_DIR%wheels"
set "REQ=%CDW_DIR%requirements\cdw.txt"
set "GET_PIP=%CDW_DIR%get-pip.py"

echo.
echo ============================================================
echo   CDW Offline Installer
echo ============================================================
echo.

:: Verify Python exists
if not exist "%PYTHON%" (
    echo ERROR: python.exe not found at %PYTHON%
    echo        Ensure the full USB-Uncensored-LLM\Shared folder was copied.
    pause
    exit /b 1
)

:: [1/2] Bootstrap pip from wheel cache (get-pip.py uses --find-links offline)
echo [1/2] Bootstrapping pip from offline wheel cache...
"%PYTHON%" "%GET_PIP%" --no-index --find-links="%WHEELS%"
if errorlevel 1 (
    echo ERROR: pip bootstrap failed. Verify pip-*.whl exists in %WHEELS%
    pause
    exit /b 1
)

:: [2/2] Install CDW requirements
echo.
echo [2/2] Installing CDW requirements from offline wheel cache...
"%PYTHON%" -m pip install ^
    -r "%REQ%" ^
    --no-index ^
    --find-links="%WHEELS%" ^
    --prefer-binary ^
    --no-warn-script-location
if errorlevel 1 (
    echo ERROR: pip install failed.
    echo        Check that all required .whl files are present in %WHEELS%
    pause
    exit /b 1
)

echo.
echo ============================================================
echo   Installation complete!  Run start_cdw.bat to launch CDW.
echo ============================================================
echo.
endlocal
BAT_EOF
  if [[ $? -eq 0 ]]; then
    success "install_offline.bat written (uses --prefer-binary)."
  else
    error "Failed to write install_offline.bat."
    any_failed=1
  fi

  # start_cdw.bat — copy from source if present, otherwise warn and skip
  local bat_src="$SRC_DIR/usb_deploy/Shared/cdw/scripts/windows"
  if [[ -f "$bat_src/start_cdw.bat" ]]; then
    info "Copying start_cdw.bat..."
    cp "$bat_src/start_cdw.bat" "$SCRIPTS_WIN/start_cdw.bat" \
      && success "Copied start_cdw.bat." \
      || { error "Failed to copy start_cdw.bat."; any_failed=1; }
  else
    warn "start_cdw.bat not found in $bat_src — skipping."
  fi

  return $any_failed
}

# =============================================================================
# Main
# =============================================================================
main() {
  echo -e "${BOLD}"
  echo "============================================================"
  echo "  CDW USB Staging Script"
  echo "  Target: $USB"
  echo "  Date:   $(date)"
  echo "============================================================${RESET}"

  # Initialise all statuses as PENDING so we can detect uncompleted steps
  for k in "1/8" "2/8" "3/8" "4/8" "5/8" "6/8" "7/8" "8/8"; do
    step_status_set "$k" "PENDING"
  done

  # Validate USB first. This is a hard prerequisite: every later step writes
  # under $USB, and even the pre-sync validation can take real time. Fail fast
  # before doing any expensive local validation or network downloads.
  run_step "1/8" "Validate USB"                          step_validate_usb     || true
  if [[ "$(step_status_get "1/8")" != "DONE" ]]; then
    abort_summary "USB validation failed for target '$USB'."
    exit 1
  fi

  # ─── Pre-sync pipeline validation ─────────────────────────────────────────
  echo ""
  echo -e "${BOLD}Pre-sync check: running pipeline validation…${RESET}"
  SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  if bash "$SCRIPT_DIR/test_pipeline.sh"; then
    echo -e "${GREEN}  ✓ Pipeline validated — proceeding with sync${RESET}"
  else
    echo -e "${RED}  ✗ Pipeline validation FAILED — aborting sync${RESET}"
    echo "    Fix the errors above before re-running setup_usb.sh"
    exit 1
  fi

  # Run remaining steps — errors are caught inside run_step, script continues
  run_step "2/8" "Download NemoMix 12B GGUF"             step_download_gguf    || true
  run_step "3/8" "Download Ollama binaries"              step_download_ollama  || true
  run_step "4/8" "Import NemoMix into Ollama registry"   step_import_ollama_model || true
  run_step "5/8" "Download Python 3.12 embeddable"       step_download_python  || true
  run_step "6/8" "Download get-pip.py"                   step_download_getpip  || true
  run_step "7/8" "Download Windows pip wheels"           step_download_wheels  || true
  run_step "8/8" "Copy CDW source and launch scripts"    step_copy_cdw         || true

  # ─── Summary ────────────────────────────────────────────────────────────────
  echo -e "\n${BOLD}============================================================"
  echo "  SUMMARY"
  echo "============================================================${RESET}"

  local labels=(
    "1/8|Validate USB"
    "2/8|Download NemoMix GGUF"
    "3/8|Download Ollama binaries"
    "4/8|Import NemoMix → Ollama"
    "5/8|Download Python 3.12 embeddable"
    "6/8|Download get-pip.py"
    "7/8|Download Windows wheels"
    "8/8|Copy CDW source & scripts"
  )

  local all_ok=1
  for entry in "${labels[@]}"; do
    local key="${entry%%|*}"
    local label="${entry##*|}"
    local status
    status=$(step_status_get "$key" "PENDING")
    case "$status" in
      DONE)    echo -e "  ${GREEN}✓ DONE   ${RESET}  [$key] $label" ;;
      SKIPPED) echo -e "  ${CYAN}– SKIPPED${RESET}  [$key] $label" ;;
      FAILED)  echo -e "  ${RED}✗ FAILED ${RESET}  [$key] $label"; all_ok=0 ;;
      *)       echo -e "  ${YELLOW}? PENDING${RESET}  [$key] $label"; all_ok=0 ;;
    esac
  done

  echo ""
  if (( all_ok == 1 )); then
    echo -e "${GREEN}${BOLD}BK-1 is ready.${RESET}"
  else
    echo -e "${YELLOW}${BOLD}BK-1 staging completed with warnings/failures — see above.${RESET}"
  fi
  echo -e "${BOLD}On the Dell: navigate to USB-Uncensored-LLM\\Shared\\cdw\\scripts\\windows\\ and run start_cdw.bat${RESET}"
  echo ""
}

# ─── Entry point ─────────────────────────────────────────────────────────────
# Wrap main so that set -e inside a step function won't kill the whole script
# before we can record the failure. Each step function returns 0/1 explicitly.
set +e
main "$@"
