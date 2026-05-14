# CDW USB Contents Reference

Expected structure under `<USB drive>:\<layout-root>\Shared\`.

The default layout root created by `setup_usb.sh` is `USB-Uncensored-LLM`,
but the Windows scripts resolve paths relative to their own location, so the
drive letter can be `D:`, `E:`, `F:`, etc. and the layout root can be renamed
as long as the `Shared\cdw\scripts\windows\` structure is preserved.

---

## Directory Tree

```
<USB drive>:\
└── <layout-root>\
    └── Shared\
        ├── bin\
        │   ├── ollama.exe                          ← Ollama server (Windows)
        │   └── ollama-darwin                       ← Ollama server (Mac, for sync use)
        │
        ├── models\
        │   ├── NemoMix-Unleashed-12B-Q4_K_M.gguf  ← LLM model (~7 GB)
        │   └── ollama_data\                        ← Ollama model registry
        │       └── manifests\
        │           └── registry.ollama.ai\
        │               └── library\
        │                   └── nemomix-local\
        │                           └── latest      ← Model manifest (JSON)
        │
        └── cdw\
            ├── get-pip.py                          ← pip bootstrapper
            ├── requirements\
            │   └── cdw.txt                         ← Python dependency list
            │
            ├── python\                             ← Python 3.12 embeddable (Windows)
            │   ├── python.exe
            │   ├── python312.zip
            │   ├── python312._pth                  ← import site enabled
            │   └── ...
            │
            ├── wheels\                             ← Offline pip wheels (81 files)
            │   ├── pip-*.whl
            │   ├── setuptools-*.whl
            │   ├── wheel-*.whl
            │   ├── pdfminer.six-*.whl
            │   ├── pyside6-*.whl
            │   ├── numpy-*.whl
            │   ├── sentence_transformers-*.whl
            │   └── ...                             ← all win_amd64 / py312 wheels
            │
            ├── scripts\
            │   ├── windows\
            │   │   ├── start_cdw.bat               ← Main launcher (run this first)
            │   │   ├── start_ollama.bat            ← Starts Ollama with USB model store
            │   │   ├── install_offline.bat          ← Bootstraps pip + all deps
            │   │   ├── run_cdw.bat                 ← Runs CDW after install
            │   │   ├── benchmark_llm.bat           ← Runs the Ollama benchmark
            │   │   ├── benchmark_fast.bat          ← Benchmarks the smaller model lane
            │   │   ├── pull_fast_model.bat         ← Pulls llama3.2:3b into USB store
            │   │   └── verify_env.bat              ← Checks Python + deps are OK
            │   └── mac\
            │       ├── start_env.sh
            │       ├── sync_one.sh
            │       ├── sync_wheels.sh
            │       └── verify_cache.sh
            │
            └── projects\
                └── cdw\                            ← CDW source code
                    ├── main.py                     ← Entry point
                    ├── config\
                    │   └── cdw_config.toml         ← LLM backend config
                    ├── data\
                    │   └── workspace.db            ← SQLite database (created at runtime)
                    ├── NERC-DOCS\                  ← 88 NERC standard PDFs
                    │   ├── CIP-002-5.1a 1.pdf
                    │   ├── CIP-003-8.pdf
                    │   └── ...
                    ├── mapper\                     ← Core pipeline modules
                    │   ├── chunker\
                    │   ├── db\
                    │   ├── index\
                    │   ├── reasoning\
                    │   └── scanner\
                    └── tests\
```

---

## Key File Checks

| File | Min Size | Notes |
|------|----------|-------|
| `bin\ollama.exe` | ~60 MB | Windows Ollama server |
| `models\NemoMix-Unleashed-12B-Q4_K_M.gguf` | 7,000 MB | LLM — largest file on drive |
| `python\python.exe` | ~5 MB | Python 3.12 embeddable |
| `wheels\` | 81 files | All win_amd64 cp312 wheels |
| `projects\cdw\main.py` | — | CDW entry point |
| `projects\cdw\NERC-DOCS\` | 88 PDFs | NERC standard documents |
| `projects\cdw\config\cdw_config.toml` | — | Points to Ollama at localhost:11434 |

---

## First-Run Sequence on Dell

1. Plug in the USB drive and note its assigned drive letter.
2. Double-click `<USB drive>:\<layout-root>\Shared\cdw\scripts\windows\start_cdw.bat`
3. First run installs all deps (~2 min), then launches CDW
4. In a separate window: `<USB drive>:\<layout-root>\Shared\cdw\scripts\windows\start_ollama.bat`
5. Optional fast-model setup: `<USB drive>:\<layout-root>\Shared\cdw\scripts\windows\pull_fast_model.bat`
6. Fast-model benchmark: `<USB drive>:\<layout-root>\Shared\cdw\scripts\windows\benchmark_fast.bat`
7. Run assessment: `python main.py --reason --scan-id 1 --standard MOD-025-2`
