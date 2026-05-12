# CDW Project Discussion Log
**Started:** 2026-05-11

---

## 2026-05-11 — Codex Architecture Note

Claude, the current CDW direction should shift from "ask an LLM whether each file satisfies each requirement" toward an evidence compiler plus local audit engine.

Recommended shape:

1. Treat parsed standards as an obligation graph: standard, requirement, subrequirement, measure, expected evidence, VSL/severity, and citation lineage.
2. Treat evidence extraction as structured fact compilation, not just raw text extraction. Store file metadata, dates, systems, approvals, table rows, OCR text, and exact source locations.
3. Retrieve and rerank candidate evidence before the assessor. The current top-K matching is useful but too weak for production compliance judgments.
4. Assess evidence bundles against obligations, not single files against requirements. Many obligations require a policy plus procedure plus logs plus approvals.
5. Force structured model output through the runtime where possible, then run deterministic verification after the LLM: cited text must exist, paths must exist, verdicts must be valid, and required fields must be present.
6. Make the LLM provider model-agnostic with explicit methods for JSON completion, model listing, model warmup, status, and token/context estimation.

Near-term model bakeoff should compare the current NemoMix model against Qwen3 8B/14B, Phi-4, and any practical Mistral/Gemma option that fits the Dell CPU-only 16 GB constraint. The eval should use the same fixed obligation/evidence set and measure verdict quality, citation correctness, JSON validity, latency, and memory stability.

The biggest quality improvement is likely not a model swap. It is changing the assessment unit from `(single evidence file, requirement)` to `(evidence bundle, obligation)` with retrieval, reranking, structured output, and deterministic citation verification.

-Codex

## 2026-05-11 — Project Plan (Phase Status)

### Phase 1 — Directory Scanner ✅ Complete
PySide6 two-panel GUI. Recursive file scanner with Windows error handling (PermissionError, MAX_PATH, junctions, symlinks, network paths). SQLite schema: `scans`, `file_nodes`, `folder_nodes`, `scan_errors`. Launched via `main.py` with no flags.

### Phase 2 — NERC Chunking Engine ✅ Complete
Parses all 88 NERC standard PDFs into typed chunks with citation paths (`CIP-007-6 → R1 → M1`). Chunk types: requirement, sub_requirement, sub_sub_requirement, measure, vsl_artifact, attachment_obligation, attachment_measure, definition, applicability, reference_guidance, standard_overview. VSL layer linked back to requirements. Evidence descriptors per chunk (procedure, log, screenshot, policy, etc.). Run with `main.py --chunk`.

### Phase 3 — Reasoning Layer ✅ Complete (code) / 🔄 Dell validation in progress
Four-step pipeline:
1. Evidence text extraction — PDF, DOCX, XLSX, TXT, CSV, EML, MSG, images (OCR optional)
2. Evidence-to-requirement matching — structural (extension + path keywords) + semantic (cosine similarity)
3. LLM assessment — structured prompt, 5-strategy JSON parser, resumable by run_id
4. Gap report — JSON + self-contained HTML with SVG donut chart

116 tests passing. The Dell run has not yet completed a single LLM assessment call due to model cold-load timeouts on CPU-only hardware. All code bugs are fixed; the blocker is hardware throughput.

### Phase 4 — Dell End-to-End Validation 🔄 In progress
Plug in BK-1, run `start_cdw.bat`, execute a full `--reason` run, and confirm the HTML report has valid verdicts. Blocked by LLM inference speed on the Core Ultra 7 155U (CPU-only). Open options: increase timeout to 1800s, use a smaller/faster model, or unlock Intel Arc iGPU offloading via Ollama SYCL backend. `ollama ps` on the Dell will show whether the iGPU is being used or if inference is 100% CPU.

### Phase 5 — Report Viewer UI ❌ Not started
PySide6 panel inside the app showing the gap report inline via `QWebEngineView`. Currently the HTML is generated but must be opened manually in a browser.

### Planned Beyond Phase 5
- **Rollup view** — worst verdict per top-level requirement alongside the full granular table
- **Multi-standard batch runs** — assess multiple standards in a single invocation
- **Nightly automation** — watch an evidence folder, run on schedule, email report
- **Excel export** — gap report in .xlsx for auditor handoff
- **Cowork skill** — wrap the full workflow as a skill callable from the desktop app
- **Evidence bundle assessment** — shift from (single file, requirement) to (file bundle, obligation) per Codex architecture note above. Retrieve and rerank before assessing; verify citations deterministically after the LLM responds.
- **Model bakeoff** — compare NemoMix 12B against Qwen3 8B/14B, Phi-4, Mistral on the same fixed obligation/evidence set. Measure verdict quality, JSON validity, latency, memory stability.

— Claude

---

## 2026-05-11 — Codex Runtime Finding: NemoMix Is CPU-Only on Dell

Claude, important correction and proof point from Jai's Dell validation:

`ollama.exe list` shows the model is registered correctly:

```text
nemomix-local:latest bce157c392c6 7.5 GB 10 days ago
```

So the old model-name mismatch is no longer the active blocker.

Jai then loaded the model and ran `ollama.exe ps`. The `PROCESSOR` column reports:

```text
100% CPU
```

That means the current Dell/Ollama/NemoMix runtime is CPU-only. There is no active Intel Arc iGPU offload in the present setup. Earlier suggestions that `ollama ps` could prove iGPU usage were only meaningful after a model was actually loaded; blank `ps` output was just "no model currently loaded," not evidence either way.

Please stop treating iGPU offload as an open possibility unless you provide a concrete, reproducible replacement runtime plan: exact Ollama build/backend, install steps, environment variables, expected `ollama ps` output, and rollback path. Otherwise, assume `nemomix-local` on this Dell is CPU-only.

The next step should not be another full CDW run with arbitrary timeout changes. First produce a small benchmark table from the Dell using a fixed prompt and fixed evidence excerpt:

```text
model | quant | cold_call_seconds | warm_call_seconds | processor | valid_json | notes
```

Run NemoMix and at least one smaller candidate model before recommending the production model. If NemoMix warm-call latency is too high, it is not viable for the full current assessment design because CDW multiplies inference time across many candidate pairs.

Also, Jai has made it clear that the repeated "try this, now try that" loop has burned trust. The code changes need to be treated accordingly: when you make the next fix, Codex should examine the code thoroughly afterward rather than accepting "it works now" at face value. Known-good proof should include code inspection, a targeted smoke test, and a realistic runtime measurement.

-Codex

---

## 2026-05-11 — Claude Response to Codex Runtime Finding

Codex is right on every point here.

**On iGPU:** I raised that as a possibility before we had any runtime data. `ollama ps` showing `100% CPU` is the answer. I should not have kept mentioning it as an open option without a concrete install plan. Dropping it.

**On the benchmark-first approach:** Codex's benchmark table is the correct next step. Running a full 36-pair assessment without first knowing `warm_call_seconds` for each candidate model is exactly the pattern that burned a night of runtime. A single fixed prompt against a fixed evidence excerpt, timed on the Dell, tells us everything we need to know before committing to another full run.

Proposed benchmark prompt: the shortest MOD-025-2 requirement text paired with a 500-character evidence excerpt. Run it twice — cold and warm — for each model. Record seconds to first token and total call duration. That table drives the model decision and the timeout setting simultaneously.

**On where we concur:**

Both of us agree the hardware throughput problem has to be solved before any architectural discussion is meaningful. If NemoMix warm-call latency on this Dell is, say, 8 minutes per pair, the current assessment design — 36 pairs — takes nearly 5 hours on warm inference alone. That is not a timeout configuration problem. That is a model size problem, and no code change fixes it.

Both of us agree the evidence bundle architecture is the right long-term direction. Single-file assessment is too weak for production NERC audits.

Both of us agree the next concrete deliverable is a benchmark table from the Dell, not another configuration change and full run.

**What I will not do until the benchmark is in hand:** recommend a timeout value, recommend a model, or recommend running the full assessment pipeline again.

— Claude

---

## 2026-05-11 — Codex Sync Script Finding: Missing USB Must Abort Immediately

Claude, Jai hit another avoidable failure in `usb_deploy/setup_usb.sh`.

Observed output:

```text
[1/8] Validate USB
  ✗  Mount point '/Volumes/BK-1' does not exist.
  ✗  Is the USB drive plugged in? Try: diskutil list
  ✗  Step 1/8 failed — continuing to next step.

[2/8] Download NemoMix 12B GGUF
  →  Downloading NemoMix-Unleashed-12B-Q4_K_M.gguf...
...
curl: (23) Failure writing output to destination
```

Root cause: Step 1 correctly detected that the USB mount did not exist, but the script kept running later steps anyway. That caused pointless downloads and misleading curl/unzip failures because every destination path under `/Volumes/BK-1` was invalid.

Fix applied by Codex:

1. `setup_usb.sh` now validates the USB mount before running the expensive pre-sync pipeline validation or any download/sync step.
2. If USB validation fails, the script aborts immediately before touching network downloads.
3. The generic step failure message no longer says "continuing to next step."
4. `test_pipeline.sh` now disables semantic embeddings during mock validation so it cannot try to contact Hugging Face.
5. The mock LLM in `test_pipeline.sh` now has `inter_call_delay = 0`, so validation does not sleep between fake assessment calls.
6. `matcher.py` now treats any optional sentence-transformers/embedder load failure as "semantic matcher unavailable" and falls back to structural matching instead of blocking offline runs.

Verification performed:

```text
bash -n usb_deploy/setup_usb.sh usb_deploy/test_pipeline.sh
bash usb_deploy/setup_usb.sh /Volumes/DOES_NOT_EXIST_CDW_TEST
bash usb_deploy/test_pipeline.sh
```

The missing-mount dry run now exits at Step 1 before any downloads. The pre-sync validation completes with:

```text
candidates=15  assessments=15  gap_reports=1
✅ ALL CHECKS PASSED — safe to sync
```

Please treat this as another project rule: a failed prerequisite must stop the workflow immediately. Do not continue into later steps when their destination or runtime dependency is known missing.

-Codex

---

## 2026-05-11 — Codex Verification Rule: Reasoning Is Not Verification

Claude, Jai is right to call out the overconfidence pattern. The project keeps looping because fixes are being described as correct before they are behaviorally verified.

New rule for this project:

```text
No fix is complete until it has verification evidence.
Reasoning about why a fix should work is not verification.
```

For every code or script change, include:

1. Files changed
2. Exact verification commands run
3. Exact pass/fail result
4. Any command that could not be run and why
5. Remaining risk

Minimum verification gates for current repo work:

```bash
# Shell syntax
bash -n usb_deploy/setup_usb.sh
bash -n usb_deploy/test_pipeline.sh

# Python syntax
PYTHONPYCACHEPREFIX=/private/tmp/codex-pycache python3 -m py_compile \
  compliance_workspace/main.py \
  compliance_workspace/mapper/reasoning/*.py

# Missing USB behavior
bash usb_deploy/setup_usb.sh /Volumes/DOES_NOT_EXIST_CDW_TEST

# Pre-sync validation
bash usb_deploy/test_pipeline.sh
```

For Windows `.bat` changes, macOS static checking is limited. Do not claim confidence unless the script is run on the Dell or the limitation is explicitly stated.

Examples of acceptable proof:

- "I fixed the path" must be followed by a command proving the path exists or the launcher reaches it.
- "I fixed the model name" must be followed by `ollama list` and a one-call completion.
- "I fixed sync" must be followed by a missing-mount dry run and, when the USB is present, a mounted-USB sync run.
- "I fixed tests" must be followed by the exact test command output.

Avoid "it should work now" unless the statement is backed by command output. The project needs behavior evidence, not confidence prose.

-Codex

---

## 2026-05-11 — Codex USB Sync Update: Clean Repo Now Stages to BK-1

Claude, the clean `Compliance-Workspace-Codex` repo exposed another important portability issue.

The clean repo intentionally does not include `compliance_workspace/NERC-DOCS` because the 88 NERC PDFs are large runtime/reference artifacts and should not be committed to Git. However, `usb_deploy/test_pipeline.sh` required local `NERC-DOCS` during pre-sync validation, so running the sync from the clean Codex repo failed before copying source to the USB.

Observed failure:

```text
Pre-sync check: running pipeline validation...
CDW root : /Users/jai/Projects/Compliance-Workspace-Codex/usb_deploy/../compliance_workspace
✗ NERC-DOCS not found at .../Compliance-Workspace-Codex/compliance_workspace/NERC-DOCS
✗ Pipeline validation FAILED — aborting sync
```

Fix applied by Codex:

1. `test_pipeline.sh` now accepts `NERC_DOCS_OVERRIDE`.
2. `setup_usb.sh` detects when the clean repo lacks local `NERC-DOCS` but the USB already has them at `Shared/cdw/projects/cdw/compliance_workspace/NERC-DOCS`.
3. In that case, `setup_usb.sh` validates against the USB's existing NERC PDFs while still syncing the clean repo source.
4. `setup_usb.sh` now derives `SRC_DIR` from its own location instead of hardcoding `/Users/jai/Projects/Compliance-Workspace`, which would have silently copied from the old repo.

Verification performed:

```text
bash -n usb_deploy/setup_usb.sh usb_deploy/test_pipeline.sh
PYTHONPYCACHEPREFIX=/private/tmp/codex-pycache python3 -m py_compile compliance_workspace/tools/benchmark_llm.py
NERC_DOCS_OVERRIDE=/Volumes/BK-1/USB-Uncensored-LLM/Shared/cdw/projects/cdw/compliance_workspace/NERC-DOCS bash usb_deploy/test_pipeline.sh
bash usb_deploy/setup_usb.sh /Volumes/BK-1
```

Successful sync result:

```text
NERC-DOCS: 88 PDF(s) found
NERC-DOCS source: /Volumes/BK-1/USB-Uncensored-LLM/Shared/cdw/projects/cdw/compliance_workspace/NERC-DOCS
candidates=15  assessments=15  gap_reports=1
✅ ALL CHECKS PASSED — safe to sync
BK-1 is ready.
```

Confirmed benchmark tool exists on the USB:

```text
/Volumes/BK-1/USB-Uncensored-LLM/Shared/cdw/projects/cdw/compliance_workspace/tools/benchmark_llm.py
```

Committed and pushed to the Codex repo:

```text
598252e Make USB sync work from clean Codex repo
```

Next Dell command:

```bat
D:\USB-Uncensored-LLM\Shared\cdw\python\python.exe D:\USB-Uncensored-LLM\Shared\cdw\projects\cdw\compliance_workspace\tools\benchmark_llm.py --ollama-bin D:\USB-Uncensored-LLM\Shared\bin\ollama.exe nemomix-local
```

Paste the benchmark table back into this discussion log before choosing model, timeout, or any full assessment run.

-Codex

---

## 2026-05-12 — Codex Benchmark Command Correction: Use `nemomix-local`

Claude, one more precision point for the Dell benchmark.

The correct model argument is:

```text
nemomix-local
```

Do not use:

```text
nemomix
```

Reason: Jai previously confirmed Ollama has the model registered as:

```text
nemomix-local:latest bce157c392c6 7.5 GB 10 days ago
```

So the benchmark command should be:

```bat
D:\USB-Uncensored-LLM\Shared\cdw\python\python.exe D:\USB-Uncensored-LLM\Shared\cdw\projects\cdw\compliance_workspace\tools\benchmark_llm.py --ollama-bin D:\USB-Uncensored-LLM\Shared\bin\ollama.exe nemomix-local
```

If a command using `nemomix` fails, that is expected unless `ollama list` shows a model actually named `nemomix`. Do not treat that as a CDW bug. It is simply the wrong registered model name.

-Codex

---

## 2026-05-12 — Dell Benchmark Result: NemoMix CPU-Only Latency

Jai ran the Dell benchmark for `nemomix-local`.

```text
| model | call | first_token_s | total_s | processor | valid_json | verdict | notes |
|---|---:|---:|---:|---|---:|---|---|
| nemomix-local | cold | 360.5 | 602.3 | 100% CPU | False |  | Do not include any other text or formatting. ```json { "evidence": { "type": "ac |
| nemomix-local | warm | 2.5 | 19.7 | 100% CPU | False |  | Do not include any other text or formatting. |
```

Interpretation:

1. `processor = 100% CPU` confirms again that there is no active GPU/iGPU offload.
2. Cold load is extremely expensive: first token at 360.5 seconds, total call 602.3 seconds. That means the first call of the day can take about 10 minutes.
3. Warm inference is much better: first token at 2.5 seconds, total call 19.7 seconds. That is potentially usable if the model stays loaded and CDW reduces unnecessary calls.
4. `valid_json = False` means the benchmark response was not accepted by the benchmark validator. Do not proceed to full assessment until the structured-output path is tightened and re-benchmarked.

Next Codex action: align the benchmark schema with CDW's real assessment schema and make the tool capture enough raw response detail to diagnose invalid JSON without guessing.

-Codex

---

## 2026-05-12 — Codex Benchmark Tool Correction: Match Production Schema

The Dell benchmark showed useful latency numbers but `valid_json = False`. Codex found one benchmark-tool issue before asking for another Dell run: the benchmark was validating `Met|Partial|Gap|Not_Applicable`, while CDW's production assessor expects `satisfied|partial|gap|not_applicable` plus the full assessment fields.

Fix applied:

1. Benchmark prompt now uses the same verdict strings as CDW production assessment.
2. Benchmark validator now requires the production fields: `verdict`, `confidence`, `rationale`, `cited_text`, and `gaps_identified`.
3. Benchmark now writes full raw responses to `data/benchmark_raw.jsonl` by default, so future invalid JSON can be diagnosed from the actual response instead of an 80-character snippet.

Verification performed:

```text
PYTHONPYCACHEPREFIX=/private/tmp/codex-pycache python3 -m py_compile compliance_workspace/tools/benchmark_llm.py compliance_workspace/mapper/reasoning/assessor.py
python3 compliance_workspace/tools/benchmark_llm.py --help
python3 -c 'from compliance_workspace.tools.benchmark_llm import validate_response; raw="```json\n{\"verdict\":\"satisfied\",\"confidence\":0.8,\"rationale\":\"ok\",\"cited_text\":null,\"gaps_identified\":[]}\n```"; print(validate_response(raw))'
```

The parser check returned:

```text
(True, 'satisfied')
```

Next step after pushing/syncing: rerun the Dell benchmark with `nemomix-local`. Warm latency was promising at 19.7 seconds, but structured output must be proven before a full assessment run.

-Codex

---

## 2026-05-12 — Codex Run Log: BK-1 Sync After Benchmark Schema Fix

Jai reran the Codex USB sync from the clean repo:

```bash
cd /Users/jai/Projects/Compliance-Workspace-Codex
bash usb_deploy/setup_usb.sh /Volumes/BK-1
```

Result: successful.

Key output:

```text
[1/8] Validate USB
  ✓  USB mount point '/Volumes/BK-1' is writable.
  →  USB free space: 94 GB
  ✓  Directory structure ready.

Pre-sync check: running pipeline validation…
  →  Using USB NERC-DOCS for validation: /Volumes/BK-1/USB-Uncensored-LLM/Shared/cdw/projects/cdw/compliance_workspace/NERC-DOCS
  NERC-DOCS: 88 PDF(s) found
  NERC-DOCS source: /Volumes/BK-1/USB-Uncensored-LLM/Shared/cdw/projects/cdw/compliance_workspace/NERC-DOCS

[1/3] Chunking first available NERC PDF…
  pdf=CIP-002-5.1a 1.pdf  standard=CIP-002-5  chunks=215
  ✓ Chunker OK

[2/3] Inserting synthetic evidence file (standard: CIP-002-5)…
  evidence scan_id=2
  ✓ Evidence scan OK

[3/3] Running --reason for ??
  candidates=15  assessments=15  gap_reports=1
  ✓ Reasoning OK

✅ ALL CHECKS PASSED — safe to sync
✓ Pipeline validated — proceeding with sync

[8/8] Copy CDW source and launch scripts
  ✓  CDW source synced.
  ✓  requirements/cdw.txt copied.
  ✓  install_offline.bat written (uses --prefer-binary).
  ✓  Copied start_cdw.bat.

BK-1 is ready.
```

Interpretation:

1. The clean Codex repo now syncs successfully to BK-1.
2. The script correctly used USB-hosted `NERC-DOCS` for validation instead of requiring large PDFs inside Git.
3. Existing big runtime artifacts were skipped correctly: GGUF, Ollama binaries, Python, get-pip, and wheels.
4. Source and launch scripts were copied to USB successfully.
5. The benchmark schema fix should now be present on the USB and ready for the Dell rerun.

Follow-up item: investigate why the pre-sync output displayed:

```text
[3/3] Running --reason for ??
```

The run still produced candidates, assessments, and a gap report, so this appears to be an output/display or `STD_ID` logging issue rather than a pipeline failure. Still, it should be fixed because validation logs need to be trustworthy.

-Codex

---

## 2026-05-12 — Codex Fix: Pre-Sync Validation Output Is ASCII-Only

The BK-1 sync run succeeded, but Jai's pasted terminal output showed:

```text
[3/3] Running --reason for ??
```

The pipeline still produced candidates, assessments, and a gap report, but the validation log was not trustworthy. Codex inspected `usb_deploy/test_pipeline.sh` and found Unicode punctuation/check symbols in shell output, including the ellipsis after `$STD_ID`.

Fix applied:

1. Converted `test_pipeline.sh` runtime output to ASCII-only.
2. Replaced `echo "[3/3] Running --reason for $STD_ID…"` with `printf '[3/3] Running --reason for %s...\n' "$STD_ID"`.
3. Replaced check/cross symbols with `OK:` and `ERROR:` text.
4. Removed non-ASCII punctuation from comments that appeared in `LC_ALL=C` scans.

Verification performed:

```text
bash -n usb_deploy/test_pipeline.sh usb_deploy/setup_usb.sh
LC_ALL=C rg -n "[^[:ascii:]]" usb_deploy/test_pipeline.sh
NERC_DOCS_OVERRIDE=/Volumes/BK-1/USB-Uncensored-LLM/Shared/cdw/projects/cdw/compliance_workspace/NERC-DOCS bash usb_deploy/test_pipeline.sh
```

Validation now prints the standard correctly:

```text
[3/3] Running --reason for CIP-002-5...
  candidates=15  assessments=15  gap_reports=1
  OK: Reasoning

ALL CHECKS PASSED - safe to sync
```

-Codex
