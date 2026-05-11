# BK-1 USB Contents Reference

Expected structure under `D:\USB-Uncensored-LLM\Shared\`

---

## Directory Tree

```
D:\
└── USB-Uncensored-LLM\
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
            │   │   ├── install_offline.bat          ← Bootstraps pip + all deps
            │   │   ├── run_cdw.bat                 ← Runs CDW after install
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

1. Plug in BK-1 (mounts as `D:\`)
2. Double-click `D:\USB-Uncensored-LLM\Shared\cdw\scripts\windows\start_cdw.bat`
3. First run installs all deps (~2 min), then launches CDW
4. In a separate window: `D:\USB-Uncensored-LLM\Shared\bin\ollama.exe serve`
5. Run assessment: `python main.py --reason --scan-id 1 --standard MOD-025-2`
