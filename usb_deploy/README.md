# CDW USB Portable Layer

This is the Compliance Discovery Workspace (CDW) merge layer for the
techjarves/USB-Uncensored-LLM portable USB structure. It slots into the
`Shared/cdw/` subdirectory of that USB layout, alongside the techjarves
Python embeddable, Ollama binaries, and GGUF models.

CDW is a fully air-gapped compliance gap-analysis tool that runs on a
Windows work laptop with no internet access. It uses Ollama (bundled by
techjarves) as its local LLM backend over the OpenAI-compatible API at
`http://localhost:11434/v1`.

## Target USB Layout

```
USB_ROOT/
├── Windows/                 ← techjarves
├── Mac/                     ← techjarves
├── Linux/                   ← techjarves
├── Shared/
│   ├── bin/                 ← techjarves: Ollama binaries
│   ├── models/              ← techjarves: GGUF model files
│   ├── python/              ← techjarves: Python 3.12 embeddable
│   ├── chat_data/           ← techjarves: chat UI
│   └── cdw/                 ← THIS LAYER
│       ├── wheels/          ← offline wheel cache (built on Mac)
│       ├── projects/cdw/    ← CDW source code
│       ├── requirements/    ← cdw.txt + cdw-dev.txt
│       └── scripts/
│           ├── windows/     ← daily-use launchers + offline installer
│           └── mac/         ← wheel-cache build helpers
```

## Prerequisites

The techjarves/USB-Uncensored-LLM portable layout must be installed
on the USB drive first. CDW relies on:

- `Shared/python/python.exe`         — Python 3.12 embeddable (Windows)
- `Shared/bin/ollama-windows.exe`    — Ollama server (Windows)
- `Shared/models/`                    — GGUF model files

## One-time Mac Setup (build the wheel cache)

The Mac is the only machine with internet access. Use it to populate the
offline wheel cache so the Windows laptop can install CDW dependencies
without network.

1. Install techjarves on the USB drive (run their `Mac/install.command`).

2. Download `get-pip.py` so Windows can bootstrap pip from the cache:

   ```sh
   curl -o usb_deploy/Shared/cdw/wheels/get-pip.py \
        https://bootstrap.pypa.io/get-pip.py
   ```

3. Sync all production wheels (targets `win_amd64` / cp312):

   ```sh
   bash usb_deploy/Shared/cdw/scripts/mac/sync_wheels.sh
   ```

4. (Optional) Verify the cache:

   ```sh
   bash usb_deploy/Shared/cdw/scripts/mac/verify_cache.sh
   ```

5. Copy the CDW source code into `Shared/cdw/projects/cdw/` (the project's
   `compliance_workspace/` directory contents go there).

6. Copy the entire `usb_deploy/Shared/cdw/` tree into the USB drive's
   `Shared/cdw/` directory.

To add a single new package to the cache later:

```sh
bash usb_deploy/Shared/cdw/scripts/mac/sync_one.sh "package>=1.2.3"
```

## One-time Windows Setup (offline install)

On the work laptop, with the USB plugged in:

```bat
Shared\cdw\scripts\windows\install_offline.bat
```

This script:

1. Edits `python312._pth` to enable `site-packages` in the embeddable.
2. Bootstraps pip from `wheels/get-pip.py` (no internet).
3. Installs everything in `requirements/cdw.txt` from the wheel cache.

To verify the install:

```bat
Shared\cdw\scripts\windows\verify_env.bat
```

## Daily Use (Windows)

```bat
Shared\cdw\scripts\windows\start_cdw.bat
```

This checks whether Ollama is already serving on `localhost:11434`,
launches it via `Shared/bin/ollama-windows.exe serve` if not, waits
for it to be ready, then runs `python main.py` from the CDW source
directory.

If Ollama is already running, use the lightweight launcher:

```bat
Shared\cdw\scripts\windows\run_cdw.bat
```

## Model Recommendation

CDW reasoning quality is dominated by the LLM. Recommended models:

- **Primary: NemoMix Unleashed 12B** — best reasoning quality for
  compliance/regulatory analysis (~10 GB RAM during inference).
- **Fallback: Qwen2.5 9B** — good balance, lower memory footprint,
  faster on lighter hardware.

Both ship as part of the techjarves model bundle in `Shared/models/`.

## How CDW Talks to Ollama

CDW uses the `openai` Python client pointed at Ollama's
OpenAI-compatible endpoint. The relevant configuration lives in the
project's `compliance_workspace/config/cdw_config.toml`:

```toml
[llm]
backend = "ollama"
base_url = "http://localhost:11434/v1"
model = "nemomix-unleashed-12b"
```

No internet is required at any point during CDW use — the LLM,
embedder (ONNX runtime), document parsers, and GUI all run locally
from the USB drive.

## CDW Commands (run from `Shared/cdw/projects/cdw/`)

```
python main.py                                              # Scanner GUI
python main.py --chunk                                      # Index documents
python main.py --reason --scan-id 1 --standard CIP-007-6    # Gap report
```
