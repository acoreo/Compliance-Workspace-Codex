# CDW Issues Log — What Kept Breaking and Why

**Project:** Compliance Discovery Workspace (CDW)  
**Hardware:** Dell Latitude, Intel Core Ultra 7 155U, 16 GB RAM, CPU-only, Windows 11  
**USB:** BK-1 (`D:\USB-Uncensored-LLM\Shared\`)  
**Author:** Claude / Jai

---

## Issue 1 — Wrong Config File Edited (Repeated)

**File:** `config/cdw_config.toml` (repo root) vs `compliance_workspace/config/cdw_config.toml` (inside package)

**What happened:** There are two config files. `main.py` loads the one at:
```python
_PROJECT_ROOT / "config" / "cdw_config.toml"
# resolves to: compliance_workspace/config/cdw_config.toml
```
Every time a config fix was made in this session, it was applied to `config/cdw_config.toml` at the repo root — a file that nothing actually reads. The correct file inside `compliance_workspace/config/` still had the old wrong values.

**How many times:** At least twice — model name fix, timeout fix.

**Correct file to edit:**
```
compliance_workspace/config/cdw_config.toml
```

**Correct values (current):**
```toml
[llm]
backend = "ollama"
base_url = "http://localhost:11434/v1"
model = "nemomix-local"
timeout_seconds = 300
max_retries = 3
max_tokens = 1024
temperature = 0.1
inter_call_delay_seconds = 3

[llm.fallback]
model = "qwen2.5:9b"
```

---

## Issue 2 — Model Name Mismatch

**File:** `compliance_workspace/config/cdw_config.toml`

**What happened:** Config had `model = "nemomix-unleashed-12b"` (the HuggingFace/GGUF filename). Ollama registered the model as `nemomix-local` when imported via Modelfile. These are different things — Ollama ignores the GGUF filename and uses whatever name was passed to `ollama create <name>`.

**Symptom:** 36 candidates generated, first LLM call returned HTTP 404:
```
{"error":{"message":"model 'nemomix-unleashed-12b' not found"}}
```

**Why it wasn't caught:** The pre-sync validation (`test_pipeline.sh`) uses a `MockLLM` and never calls Ollama. All 110 tests use mocks. No test validates the model name against a live Ollama instance.

**Fix applied:** `assert_healthy()` in `llm.py` now calls `GET /api/tags`, checks the configured model name against the Ollama registry, and raises a clear error before any candidates are assessed.

**Dell workaround (applied manually):**
```bat
powershell -Command "(Get-Content 'D:\USB-Uncensored-LLM\Shared\cdw\projects\cdw\compliance_workspace\config\cdw_config.toml') -replace 'nemomix-unleashed-12b', 'nemomix-local' | Set-Content 'D:\USB-Uncensored-LLM\Shared\cdw\projects\cdw\compliance_workspace\config\cdw_config.toml'"
```

---

## Issue 3 — LLM Timeout on First Inference (Model Cold Load)

**File:** `compliance_workspace/mapper/reasoning/llm.py`

**What happened:** Ollama loads the 7 GB model into RAM on the *first inference call*, not at startup. On a CPU-only 16 GB machine, loading can exceed the original 120-second timeout. The run failed after 2 attempts × 120s = 4 minutes.

**Symptom:**
```
[FATAL] LLM backend error: Ollama unreachable after 2 attempt(s)
[http://localhost:11434/v1/chat/completions]: timed out
```

**Fix:** Increased `timeout_seconds` from 120 to 300 in `compliance_workspace/config/cdw_config.toml`. Pre-warming is still a required operator step before a long assessment run; it is documented here but not yet automated in `start_cdw.bat` or `main.py`.

**Pre-warm command:**
```bat
curl -s -X POST http://127.0.0.1:11434/v1/chat/completions -H "Content-Type: application/json" -d "{\"model\":\"nemomix-local\",\"messages\":[{\"role\":\"user\",\"content\":\"hello\"}],\"max_tokens\":5}"
```

---

## Issue 4 — Wrong Python Invoked on Dell

**File:** `usb_deploy/Shared/cdw/scripts/windows/run_cdw.bat`, `verify_env.bat`

**What happened:** The Dell has system Python 3.14 installed at `C:\Users\jfrancis\AppData\...`. Running `python` without the full path resolves to system Python, which has none of the CDW dependencies. All three bat scripts (`run_cdw.bat`, `verify_env.bat`) had the wrong path — missing the `cdw\` segment:

```bat
# Wrong:
set "PYTHON=%USB%\Shared\python\python.exe"

# Correct:
set "PYTHON=%USB%\Shared\cdw\python\python.exe"
```

**Fix:** All bat scripts updated to use full path via `%~d0` drive detection:
```bat
set "USB=%~d0\USB-Uncensored-LLM"
set "PYTHON=%USB%\Shared\cdw\python\python.exe"
```

---

## Issue 5 — Wrong main.py Path

**File:** `usb_deploy/Shared/cdw/scripts/windows/run_cdw.bat`

**What happened:** `run_cdw.bat` called `python main.py` from `projects\cdw\`. But `main.py` is at `projects\cdw\compliance_workspace\main.py`, not at the project root.

**Symptom:**
```
python: can't open file 'main.py': [Errno 2] No such file or directory
```

**Fix:**
```bat
"%PYTHON%" "%CDW_SRC%\compliance_workspace\main.py" %*
```

---

## Issue 6 — --run-id Flag Not Wired Into main.py

**File:** `compliance_workspace/main.py`

**What happened:** The `--run-id` argument was documented in `CODEX_HANDOFF.md` and passed to `run_phase3()` in concept, but was never added to `argparse`. Passing `--run-id` would have caused argparse to error. Even if it hadn't, `run_phase3()` was not receiving it — every run generated a new UUID, making resume impossible.

**Fix:**
```python
parser.add_argument(
    "--run-id",
    type=str,
    default=None,
    metavar="UUID",
    help="Resume a previous --reason run using its run_id."
)
...
report_id = run_phase3(
    conn,
    scan_id=args.scan_id,
    standard_id=args.standard,
    run_id=args.run_id or None,   # ← wired here
    backend=backend,
    verbose=True,
)
```

---

## Issue 7 — OLLAMA_MODELS Not Reliably Forwarded to Ollama Process

**File:** `usb_deploy/Shared/cdw/scripts/windows/start_cdw.bat`

**What happened:** Original `start_cdw.bat` used:
```bat
start "" "%OLLAMA%" serve
```
Windows `start` inherits env vars from the parent CMD process, so this works when launched from CMD. But when double-clicked from Windows Explorer, the process tree is different and `OLLAMA_MODELS` may not reach Ollama — causing it to look for models in the default location rather than the USB.

**Fix:** Explicit env forwarding in the new process:
```bat
start "Ollama - CDW" cmd /C "set OLLAMA_MODELS=%OLLAMA_MODELS% && set OLLAMA_HOST=%OLLAMA_HOST% && "%OLLAMA%" serve"
```

---

## Issue 8 — Backend Errors Stored as Permanent parse_error Rows

**File:** `compliance_workspace/mapper/reasoning/assessor.py`

**What happened:** When Ollama went down mid-run, the original code caught `RuntimeError` and stored it as a `parse_error` row in `evidence_assessments`. The resumability logic then skipped that row permanently on every subsequent run — the pair was marked "done" even though it was never actually assessed.

**Original code:**
```python
try:
    raw_response = backend.complete(_SYSTEM_PROMPT, user_prompt)
except RuntimeError as exc:
    raw_response = f"ERROR: {exc}"   # ← became permanent garbage row
```

**Fix:** Let `RuntimeError` propagate. Runner catches it, prints `[FATAL]`, re-raises so the run aborts cleanly and can be resumed.

---

## Issue 9 — URL Double-Path Bug

**File:** `compliance_workspace/mapper/reasoning/llm.py`

**What happened:** `base_url = "http://localhost:11434/v1"` in config. Code appended `/v1/chat/completions` unconditionally, producing:
```
http://localhost:11434/v1/v1/chat/completions  → 404
```

**Fix:** Normalize before appending:
```python
base = self.base_url.rstrip("/")
if base.endswith("/v1"):
    url = f"{base}/chat/completions"
else:
    url = f"{base}/v1/chat/completions"
```

---

## Issue 10 — Evidence Scan Contamination

**File:** `compliance_workspace/mapper/reasoning/matcher.py`

**What happened:** `compute_candidates()` queried all `evidence_text` rows regardless of `scan_id`. Evidence from scan 1 appeared as candidates in assessments for scan 2, producing cross-contaminated results.

**Fix:** Added `WHERE fn.scan_id = ?` to scope the evidence query to the specified scan.

---

## Issue 11 — Reporter Dropped Sub-Requirements

**File:** `compliance_workspace/mapper/reasoning/reporter.py`

**What happened:** `reporter.py` only queried `chunk_type = 'requirement'`. All sub-requirements, measures, and attachment chunks were assessed but silently excluded from the gap report. A 200+ row standard like MOD-025-2 showed only a handful of top-level rows.

**Fix:** Expanded to all 6 obligation chunk types:
```python
chunk_types = (
    'requirement', 'sub_requirement', 'sub_sub_requirement',
    'measure', 'attachment_obligation', 'attachment_measure'
)
```

---

## Issue 12 — LLM Parser Only Tried Direct JSON

**File:** `compliance_workspace/mapper/reasoning/assessor.py`

**What happened:** NemoMix frequently wraps JSON in markdown fences or gives plain-text verdicts. A single `json.loads()` attempt produced `parse_error` on most calls.

**Fix:** 5-strategy fallback parser:
1. Direct `json.loads()`
2. Extract from markdown code fence (` ```json ... ``` `)
3. Brace-balanced extraction
4. Keyword regex (`verdict:`, `rationale:`)
5. `parse_error` (last resort)

---

## Issue 13 — 52 GB Git Bloat

**Root cause:** No `.gitignore` existed when the repo was first initialized. Running `git add` staged the 4 GB GGUF model, 88 NERC PDFs, and 78 wheel files as unreachable blobs. 66 failed `git gc` attempts left 66 `tmp_pack_*` files totaling 52 GB.

**What we had to do:** Nuke `.git`, `git init` fresh, commit with proper `.gitignore` first.

**Rule encoded in memory:** `.gitignore` must be the very first file committed on any repo that will ever touch large binaries.

---

## Issue 14 — STD_ID Lost Between Heredoc Steps on macOS

**File:** `usb_deploy/test_pipeline.sh`

**What happened:** `set -u` (unset variable causes exit) combined with bash heredoc subshell boundaries on macOS bash 3.2 caused `STD_ID` to appear unbound in step 3 even though it was set in step 1. The script exited silently mid-run, but the parent `setup_usb.sh` missed the failure and synced anyway.

**Fixes applied:**
- Removed `-u` from `set -euo pipefail` with an explanatory comment
- Persisted `STD_ID` to a temp file after step 1
- Re-read from file at start of step 3 with an explicit guard that aborts if empty

---

## Issue 15 — /tmp Full Blocked Bash Heredocs on Mac

**File:** `usb_deploy/test_pipeline.sh`

**What happened:** macOS `/tmp` was full. Bash writes heredoc temp files to `$TMPDIR` (defaults to `/tmp`). The pre-sync test script failed immediately:
```
test_pipeline.sh: cannot create temp file for here document:
No space left on device
```

**Fix:** Set `TMPDIR` to a project-local directory:
```bash
PIPE_TMP="$CDW_ROOT/data/.pipe_tmp"
mkdir -p "$PIPE_TMP"
export TMPDIR="$PIPE_TMP"
```

---

## Summary Table

| # | Issue | File(s) | Status |
|---|-------|---------|--------|
| 1 | Wrong config file edited | `config/cdw_config.toml` vs `compliance_workspace/config/cdw_config.toml` | Fixed |
| 2 | Model name mismatch (nemomix-unleashed-12b vs nemomix-local) | `compliance_workspace/config/cdw_config.toml`, `llm.py` | Fixed |
| 3 | LLM timeout on cold model load | `compliance_workspace/config/cdw_config.toml` | Fixed |
| 4 | Wrong Python path in bat scripts | `run_cdw.bat`, `verify_env.bat` | Fixed |
| 5 | Wrong main.py path in bat scripts | `run_cdw.bat` | Fixed |
| 6 | --run-id not in argparse | `main.py` | Fixed |
| 7 | OLLAMA_MODELS not forwarded to Ollama | `start_cdw.bat` | Fixed |
| 8 | Backend errors stored as permanent parse_error rows | `assessor.py` | Fixed |
| 9 | URL double-path (/v1/v1/chat/completions) | `llm.py` | Fixed |
| 10 | Evidence scan contamination (scan_id not scoped) | `matcher.py` | Fixed |
| 11 | Reporter dropped sub-requirements | `reporter.py` | Fixed |
| 12 | LLM parser tried only direct JSON | `assessor.py` | Fixed |
| 13 | 52 GB git bloat from missing .gitignore | `.gitignore` | Fixed |
| 14 | STD_ID lost between heredoc steps on macOS | `test_pipeline.sh` | Fixed |
| 15 | /tmp full blocked bash heredocs | `test_pipeline.sh` | Fixed |

---

## What Still Needs Watching

- **Model cold load on Dell:** First inference after Ollama starts loads 7 GB into RAM. Always pre-warm before starting an assessment run. Close other apps if memory is tight. This is not currently automated.
- **Git lock files in VM:** The Cowork VM can't delete git lock files left by crashed git processes. Commits must be done from the Mac (Codex handles this).
- **Two config files:** `config/cdw_config.toml` (root) is NOT used. `compliance_workspace/config/cdw_config.toml` IS used. Always edit the latter.
- **USB sync propagates all fixes:** After Codex pushes, re-run `bash /Users/jai/Projects/Compliance-Workspace/usb_deploy/setup_usb.sh /Volumes/BK-1` to push all source fixes to the Dell.
