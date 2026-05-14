# Claude Operating Contract for CDW

This project has already lost time to overconfident claims, partial reads, and
manual troubleshooting loops. Your job is to break that pattern.

## Project Intent

CDW is a portable local/offline NERC CIP compliance workstation.

- Mac: download, staging, packaging, and Git work.
- BK-1 USB: transfer package and shared runtime/log artifact location.
- Dell: local/offline execution target.
- `C:\CDW`: Dell-local working runtime.
- `D:\USB-Uncensored-LLM`: expected BK-1 path on the Dell.
- `Shared\cdw\run_logs`: canonical USB log output path.

The local LLM is not the compliance authority. Deterministic evidence extraction,
matching, validation, and logged artifacts are the authority. The LLM may help
draft explanations, summarize evidence, and propose gap language only when its
outputs are constrained and verified.

## Required Behavior

Do not say "it should work" when you can run or inspect something.

Before giving advice:

1. Read current project state.
2. Check whether the newest information is at the top, bottom, or duplicated.
3. Identify what changed since your last understanding.
4. Verify claims with commands, logs, or file inspection.
5. Give Jai the next concrete instruction.

When Jai reports a failure:

1. Treat the report as evidence, not user error.
2. Restate the exact failing command/output.
3. Identify the most likely code/script cause.
4. Make the smallest useful fix.
5. Add a check that would have caught the failure earlier.
6. Commit/push when working in the Codex repo.
7. Update `05112026-discussion.md`.

When you touch Windows batch scripts:

- Avoid mixing PowerShell commands with CMD caret escapes.
- If a generated `.bat` is needed, reason about both layers:
  - generator syntax in `sync_to_dell.bat`
  - generated syntax in `C:\CDW\*.bat`
- Run or update the static launcher gate in `usb_deploy/test_pipeline.sh`.
- Confirm relevant markers with `rg`.

When you touch USB/Dell workflow:

- Prefer Mac-side downloads.
- Keep Dell network activity unnecessary to the task at hand out of the plan.
- Do not ask Jai to paste long output if the script can write a log.
- Write logs to `Shared\cdw\run_logs`.
- Use append logs for history and `latest_*.log` for quick review.

## Proof of Reading

If Jai asks whether you read a file, prove it. Do not answer with a generic
recap. Separate:

1. What you originally believed or built.
2. What the file proves actually happened.
3. What you learned from the mismatch.
4. What you will change because of it.

Important: `05112026-discussion.md` may contain duplicated sections and may not
be chronological from top to bottom. Search headings and inspect both ends of the
file before deciding what is current.

## Current Known State

As of the latest Codex validation:

- BK-1 logging works.
- `Shared\cdw\run_logs` exists after Dell runs.
- `run_all_local_tests.bat` completed successfully.
- `benchmark_raw.jsonl` exists.
- `behavior_probe_raw.jsonl` exists.
- `llama3.2:3b` is usable as the current fast local structured-output model.
- Dell runtime remains CPU-only.
- NemoMix works but is too slow for practical Dell CPU use.
- All-tests benchmark result, with model already loaded:
  - first token: `0.6s`
  - total: `45.9s`
  - processor: `100% CPU`
  - valid JSON: `True`
  - verdict: `satisfied`
- Standalone local benchmark result:
  - first token: `104.0s`
  - total: `147.0s`
  - processor: `100% CPU`
  - valid JSON: `True`
  - verdict: `satisfied`
- Windows launcher syntax gate was added:
  - commit `988e0f9 Add Windows launcher syntax gate`

## How to Be Useful Here

Be proactive inside the available workspace. If a change is clearly needed, make
it. If a command can answer the question, run it. If a script can remove manual
copy/paste from Jai's workflow, write the script. If a bug happens, add a guard
so it is harder to repeat.

End every working response with the next exact instruction for Jai.
