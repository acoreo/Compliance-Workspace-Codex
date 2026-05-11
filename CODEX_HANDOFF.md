# CDW — Codex Handoff Document

**Project:** Compliance Discovery Workspace (CDW)  
**Purpose:** NERC CIP compliance gap analysis — fully air-gapped, CPU-only, no admin rights required  
**Target Hardware:** Dell Latitude, Intel Core Ultra 7 155U, 16GB RAM, Windows 11, no GPU  
**USB Drive:** BK-1 (116GB, mounts as `D:\` on Dell)  
**Author/Owner:** Jai (acoreo@gmail.com)  
**Repo:** https://github.com/acoreo/Compliance-Workspace  

---

## What This System Does

CDW automates NERC CIP compliance gap analysis. A compliance officer points it at a folder of evidence documents (PDFs, Word docs, emails, spreadsheets) and selects a NERC standard. The system:

1. **Scans** the evidence directory and catalogs all files
2. **Chunks** the 88 NERC standard PDFs into requirement/sub-requirement/measure/attachment chunks with citation paths like `CIP-007-6 -> R1 -> M1`
3. **Matches** each evidence file to the requirements it most likely satisfies (structural + semantic scoring)
4. **Assesses** each (evidence file, requirement) pair using a local LLM that acts as a NERC auditor
5. **Reports** verdicts — satisfied / partial / gap / not_applicable — in a self-contained HTML report with SVG donut chart

Everything runs locally. No internet. No cloud APIs. No admin rights needed after the USB is set up.

---

## Architecture

### Stack
- **Python 3.12** embeddable (no install, runs from USB)
- **SQLite** — single `workspace.db` for all state
- **Ollama** — local LLM server, OpenAI-compatible REST API
- **NemoMix-Unleashed-12B-Q4_K_M** — ~7GB GGUF model, CPU-only inference (~30–60s per assessment call)
- **PySide6** — GUI (Phase 1 scanner UI; Phase 5 report viewer not yet built)
- **pdfminer.six** — PDF text extraction
- **sentence-transformers** (optional) — semantic matching

### Repository Layout
```
Compliance-Workspace/
├── compliance_workspace/       ← main Python package
│   ├── main.py                 ← CLI entry point (--chunk, --reason flags)
│   ├── config/
│   │   └── cdw_config.toml     ← LLM backend config
│   ├── data/
│   │   └── workspace.db        ← SQLite DB (created at runtime)
│   ├── NERC-DOCS/              ← 88 NERC standard PDFs (gitignored)
│   ├── mapper/
│   │   ├── db/schema.py        ← Phase 1 schema (scans, file_nodes)
│   │   ├── chunker/            ← Phase 2 NERC parser + chunker
│   │   ├── index/              ← Phase 2 chunk storage
│   │   └── reasoning/          ← Phase 3 pipeline
│   │       ├── schema.py       ← Phase 3 DB tables
│   │       ├── extractor.py    ← text extraction from evidence files
│   │       ├── matcher.py      ← evidence→requirement matching
│   │       ├── assessor.py     ← LLM assessment per (chunk, file) pair
│   │       ├── llm.py          ← Ollama HTTP backend
│   │       ├── reporter.py     ← JSON + HTML gap report generation
│   │       └── runner.py       ← Phase 3 orchestrator
│   └── tests/                  ← 110 passing tests
├── usb_deploy/
│   ├── setup_usb.sh            ← Mac → BK-1 sync script (runs test_pipeline.sh first)
│   ├── test_pipeline.sh        ← presync validation (chunk → evidence → mock LLM)
│   ├── USB_MANIFEST.md         ← expected USB file tree
│   └── Shared/
│       └── cdw/
│           ├── requirements/cdw.txt
│           └── scripts/windows/
│               ├── start_cdw.bat
│               └── install_offline.bat
└── .gitignore                  ← excludes PDFs, GGUF, wheels, DBs
```

### USB Layout on Dell (`D:\`)
```
D:\USB-Uncensored-LLM\Shared\
├── bin\
│   └── ollama.exe
├── models\
│   ├── NemoMix-Unleashed-12B-Q4_K_M.gguf
│   └── ollama_data\manifests\registry.ollama.ai\library\nemomix-local\latest
└── cdw\
    ├── python\python.exe       ← embeddable Python 3.12 (USE THIS, not system Python)
    ├── get-pip.py
    ├── requirements\cdw.txt
    ├── wheels\                 ← 81 offline .whl files
    ├── scripts\windows\
    │   ├── start_cdw.bat
    │   └── install_offline.bat
    └── projects\cdw\           ← CDW source (synced from Mac via setup_usb.sh)
        ├── compliance_workspace\
        │   └── main.py         ← entry point IS HERE, not in projects\cdw\
        └── config\
            └── cdw_config.toml
```

---

## Database Schema

### Phase 1 Tables
- `scans` — one row per evidence scan (scan_id, root_path, scope_key)
- `file_nodes` — one row per file discovered (linked to scan_id)
- `folder_nodes`, `scan_errors`

### Phase 2 Tables
- `chunks` — NERC requirement chunks (chunk_id, standard_id, chunk_type, official_citation_path, requirement_id, expected_evidence JSON, text)
- `chunk_relationships`, `vsl_artifacts`

**Critical:** The NERC chunker writes to a separate system scan with `scope_key = 'nerc_standards'`. Evidence files are in user scans with `scope_key = 'evidence'`. These must never be mixed.

### Phase 3 Tables
- `evidence_text` — extracted text per file_node_id
- `evidence_candidates` — top-K (chunk_id, file_node_id) pairs per assessment run, scoped to one scan_id
- `evidence_assessments` — LLM verdict per candidate pair (resumable: skips existing rows)
- `gap_reports` — final JSON + HTML report

---

## Phase 3 Pipeline — How It Should Work

### Run command (from Dell CDW project dir)
```bat
D:\USB-Uncensored-LLM\Shared\cdw\python\python.exe compliance_workspace\main.py --reason --scan-id 1 --standard MOD-025-2
```

### What happens step by step

**[1/4] Text extraction (`extractor.py`)**  
Reads every `file_node` for the given `scan_id` and extracts text (PDF via pdfminer, DOCX via python-docx, etc.). Results cached in `evidence_text`. Skips already-cached nodes.

**[2/4] Matching (`matcher.py`)**  
For each requirement chunk in the given standard, scores every evidence file:
- Structural score: file extension vs expected evidence descriptors + path keyword hits
- Semantic score: cosine similarity via sentence-transformers (skipped if not installed)
- Combined = 0.4×structural + 0.6×semantic (or just structural if no embedder)

Top-K candidates (default 5) per chunk written to `evidence_candidates`. **Scoped to scan_id** — only evidence from the specified scan is considered.

**[3/4] LLM Assessment (`assessor.py`)**  
For each candidate pair:
1. Builds a structured prompt: requirement text + measure text + evidence excerpt (capped at 1500 chars)
2. Calls Ollama via `llm.py` (OpenAI-compatible REST at `localhost:11434/v1/chat/completions`)
3. Parses response with 5-strategy fallback: direct JSON → markdown fenced → brace-balanced → keyword regex → parse_error
4. Writes result to `evidence_assessments`
5. Sleeps `inter_call_delay_seconds` between calls (default 3s, for memory pressure relief)

**Resumable:** already-assessed (run_id, chunk_id, file_node_id) pairs are skipped.  
**Backend failure:** if Ollama goes down mid-run, raises RuntimeError, prints `[FATAL]`, and aborts. Re-run with `--run-id <same_id>` to resume.

**[4/4] Report generation (`reporter.py`)**  
- Collects best assessment (highest confidence) per obligation chunk
- Chunk types assessed: `requirement`, `sub_requirement`, `sub_sub_requirement`, `measure`, `attachment_obligation`, `attachment_measure`
- Generates JSON report + self-contained HTML with SVG donut chart
- Saves to `gap_reports` table

---

## Config File

`compliance_workspace/config/cdw_config.toml`:
```toml
[llm]
backend = "ollama"
base_url = "http://localhost:11434/v1"
model = "nemomix-local"          ← MUST match Ollama registered name exactly
timeout_seconds = 300
max_retries = 3
max_tokens = 1024
temperature = 0.1
inter_call_delay_seconds = 3
```

**The model name `nemomix-local` is how it was imported into Ollama's registry via the Modelfile.** Do not change it to the GGUF filename or the HuggingFace model name.

---

## What's Built (Status)

| Phase | Component | Status |
|-------|-----------|--------|
| 1 | Directory scanner + PySide6 GUI | ✅ Complete |
| 2 | NERC chunker (88 PDFs, 11 chunk types) | ✅ Complete |
| 3 | Evidence extraction | ✅ Complete |
| 3 | Evidence→requirement matcher | ✅ Complete |
| 3 | LLM assessor + parser | ✅ Complete |
| 3 | Gap report (JSON + HTML) | ✅ Complete |
| 3 | Pre-sync pipeline validation | ✅ Complete |
| 4 | Dell end-to-end validation | 🔄 In progress |
| 5 | Report viewer in PySide6 GUI | ❌ Not started |

**Tests:** 110 passing (unit + integration, covering all Phase 3 components)

---

## What's Next

### Immediate (Dell validation — in progress)
- Fix model name in config on USB (`nemomix-unleashed-12b` → `nemomix-local`) — source working tree is updated, needs commit/sync to Dell
- Run `--reason` with correct model name and confirm it produces a valid HTML gap report
- Verify the HTML report is meaningful — correct verdicts, no corrupted rows

### Short-term
- **Rollup view in reporter:** currently reports all sub-requirements individually (200+ rows for MOD-025-2). Compliance officers expect a rolled-up view: worst verdict per top-level requirement. Add a `summary_by_requirement` section to the JSON report and a collapsible section in the HTML.
- **Phase 5 — Report UI:** PySide6 panel inside the app showing the gap report inline (QWebEngineView). Currently the HTML is generated but has to be opened in a browser manually.

### Longer-term
- Scheduling / automation (run nightly against a watched evidence folder)
- Multi-standard batch runs
- Export to Excel for auditor review

---

## Recurring Issues — Why Things Keep Breaking

This section exists because the same classes of problem have recurred multiple times.

### 1. Config values not validated against runtime state (fixed)
**What happened:** `cdw_config.toml` had `model = "nemomix-unleashed-12b"` but Ollama registered the model as `nemomix-local`. The LLM layer made no attempt to verify the model name against Ollama's `/api/tags` endpoint before assessment runs. 36 candidate pairs were generated before the first LLM call revealed the mismatch.

**Fixed:** `assert_healthy()` in `llm.py` now calls `GET /api/tags`, parses the registered model list, and raises a clear RuntimeError with the full available model list and a pointer to `cdw_config.toml` if the configured model name is missing. A `list_models()` method was added for this purpose. If `/api/tags` returns an empty list (old Ollama), the model check is skipped rather than false-alarming. 6 tests cover all branches in `test_llm.py`.

### 2. Path assumptions not validated (fixed)
**What happened:** Instructions said to run `python main.py` from `projects\cdw\` but `main.py` is actually at `projects\cdw\compliance_workspace\main.py`. The correct invocation is never validated by the launch scripts.

**Fixed:** `start_cdw.bat` now has an explicit preflight check — it verifies `compliance_workspace\main.py` exists before proceeding and fails with an actionable message if it doesn't. The Ollama start command uses `cmd /C "set OLLAMA_MODELS=... && ollama serve"` so the env var is explicit rather than inherited (which breaks when launched from Windows Explorer).

### 3. Wrong Python used on Dell (fixed)
**What happened:** The Dell has system Python 3.14 at `C:\Users\jfrancis\AppData\...`. When running from CMD without the full USB Python path, Windows resolves `python` to the system Python which has none of the CDW dependencies installed.

**Fixed:** `start_cdw.bat` uses `%~d0` to detect the drive letter at runtime and always invokes the full path `%USB%\Shared\cdw\python\python.exe`. It also checks that `python.exe` exists at that path before attempting any install or launch. `run_cdw.bat` and `verify_env.bat` had the wrong path (`Shared\python\` missing `cdw\`) — both fixed.

### 4. URL double-path bug (fixed)
`llm.py` appended `/v1/chat/completions` to a base URL that already ended in `/v1`, producing `http://localhost:11434/v1/v1/chat/completions` → 404 on every call. Fixed by normalizing the URL in `llm.py` before appending the path.

### 5. Evidence scan contamination (fixed)
`matcher.py` queried all `evidence_text` rows regardless of `scan_id`. A file from scan 1 could appear as a candidate in an assessment for scan 2's run. Fixed by adding `WHERE fn.scan_id = ?` to the evidence query.

### 6. Reporter silently dropping sub-requirements (fixed)
`reporter.py` only queried `chunk_type = 'requirement'`. All sub-requirements, measures, and attachment chunks were assessed but never included in the gap report. Fixed by expanding to all 6 obligation chunk types.

### 7. LLM parser only tried direct JSON parse (fixed)
NemoMix frequently wraps JSON in markdown code fences or produces plain-text verdicts. A single `json.loads()` attempt produced `parse_error` verdicts on most calls. Fixed with 5-strategy fallback parser.

### 8. Backend errors stored as gap data (fixed)
When Ollama went down mid-run, the `except RuntimeError` in `assessor.py` caught the error and stored it as a `parse_error` row. The resumability logic then skipped that pair permanently. Fixed by letting RuntimeError propagate so the run aborts cleanly and can be resumed.

### 10. --run-id flag documented but not wired up in main.py (fixed)
`main.py` argparse had no `--run-id` argument. The CODEX_HANDOFF.md and runner.py both documented resuming failed runs with `--run-id <uuid>`, but passing the flag would have caused argparse to error. Even if it hadn't, `run_phase3()` was called without `run_id=` so a new UUID was always generated, re-doing all matching.

**Fixed:** `--run-id` added to argparse in `main.py` and wired through to `run_phase3(run_id=args.run_id)`.

### 11. .gitignore created after first commit (fixed — now in memory)
The repo was initialized without a `.gitignore`. `git add` staged the 4GB GGUF model, 88 NERC PDFs, and 78 wheel files. 66 failed `git gc` attempts left 52GB of `tmp_pack_*` files. The repo required nuking `.git` and reinitializing. The `.gitignore` must be the first file committed on any project with large binaries.

---

## Running the System

### On the Dell (correct invocation)
```bat
:: Start Ollama (separate window)
D:\USB-Uncensored-LLM\Shared\bin\ollama.exe serve

:: From the CDW project directory
cd D:\USB-Uncensored-LLM\Shared\cdw\projects\cdw

:: Run chunking (one-time, processes all 88 NERC standards)
D:\USB-Uncensored-LLM\Shared\cdw\python\python.exe compliance_workspace\main.py --chunk

:: Run gap analysis
D:\USB-Uncensored-LLM\Shared\cdw\python\python.exe compliance_workspace\main.py --reason --scan-id 1 --standard MOD-025-2

:: Resume a failed run (same run_id)
D:\USB-Uncensored-LLM\Shared\cdw\python\python.exe compliance_workspace\main.py --reason --scan-id 1 --standard MOD-025-2 --run-id <uuid>
```

### Clearing stale assessment data
```bat
D:\USB-Uncensored-LLM\Shared\cdw\python\python.exe -c "import sqlite3; c=sqlite3.connect('compliance_workspace\\data\\workspace.db'); [c.execute(f'DELETE FROM {t}') for t in ['evidence_assessments','evidence_candidates','gap_reports']]; c.commit(); print('Done')"
```

### Syncing updated code to USB (from Mac)
```bash
cd /Users/jai/Projects/Compliance-Workspace
bash usb_deploy/setup_usb.sh   # runs pipeline validation first, then syncs
```
